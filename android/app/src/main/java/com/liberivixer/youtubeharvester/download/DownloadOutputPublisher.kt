package com.liberivixer.youtubeharvester.download

import android.Manifest
import android.content.ContentValues
import android.content.Context
import android.content.pm.PackageManager
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.DocumentsContract
import android.provider.MediaStore
import android.webkit.MimeTypeMap
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import androidx.annotation.RequiresApi
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.ui.LocaleController
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.io.OutputStream
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

class DownloadOutputPublisher(private val context: Context) {
    suspend fun publish(
        source: File,
        destinationTreeUri: String? = null,
        fileName: String = source.name,
        onCreated: suspend (String) -> Unit = {},
        checkCancelled: () -> Unit = {},
    ): String {
        require(fileName.isNotBlank() && File(fileName).name == fileName && fileName !in setOf(".", "..")) {
            "Invalid published file name"
        }
        return if (!destinationTreeUri.isNullOrBlank()) {
            publishWithDocumentTree(source, destinationTreeUri, fileName, onCreated, checkCancelled)
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            publishWithMediaStore(source, fileName, onCreated, checkCancelled)
        } else {
            publishLegacy(source, fileName, onCreated, checkCancelled)
        }
    }

    fun deletePublished(rawUri: String) {
        val uri = rawUri.toUri()
        when (uri.scheme?.lowercase()) {
            "content" -> {
                if (DocumentsContract.isDocumentUri(context, uri)) {
                    try {
                        val exists = context.contentResolver.query(uri, arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID), null, null, null)
                            ?.use { it.moveToFirst() } == true
                        if (exists) check(DocumentsContract.deleteDocument(context.contentResolver, uri)) { "Could not remove published document" }
                    } catch (error: Exception) {
                        // Some providers throw when querying a document already removed by cancellation.
                        if (archiveUriExists(context, rawUri) != false) throw error
                    }
                } else context.contentResolver.delete(uri, null, null)
            }
            "file" -> uri.path?.let(::File)?.let { check(!it.exists() || it.delete()) { "Could not remove published file" } }
        }
    }

    private suspend fun publishWithDocumentTree(source: File, destinationTreeUri: String, displayName: String, onCreated: suspend (String) -> Unit, checkCancelled: () -> Unit): String {
        val treeUri = runCatching { destinationTreeUri.toUri() }.getOrNull()
            ?.takeIf { it.scheme == "content" }
            ?: error(text(R.string.publisher_invalid_tree_uri))
        val hasWriteAccess = context.contentResolver.persistedUriPermissions.any { permission ->
            permission.uri == treeUri && permission.isWritePermission
        }
        check(hasWriteAccess) { text(R.string.publisher_permission_revoked) }

        val resolver = context.contentResolver
        val directoryDocumentId = runCatching { DocumentsContract.getTreeDocumentId(treeUri) }
            .getOrElse { error(text(R.string.publisher_directory_unavailable)) }
        val directoryUri = DocumentsContract.buildDocumentUriUsingTree(treeUri, directoryDocumentId)
        val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, directoryDocumentId)
        val fileName = uniqueDocumentName(displayName, documentNames(childrenUri))
        val documentUri = DocumentsContract.createDocument(resolver, directoryUri, source.mimeType(), fileName)
            ?: error(text(R.string.publisher_create_file_error))
        try {
            onCreated(documentUri.toString())
            resolver.openOutputStream(documentUri, "w")?.buffered()?.use { output ->
                source.inputStream().buffered().use { input -> copyCancellable(input, output, checkCancelled) }
            } ?: error(text(R.string.publisher_open_file_error))
            return documentUri.toString()
        } catch (error: Exception) {
            runCatching { DocumentsContract.deleteDocument(resolver, documentUri) }
            throw error
        }
    }

    private fun documentNames(childrenUri: Uri): Set<String> {
        val projection = arrayOf(DocumentsContract.Document.COLUMN_DISPLAY_NAME)
        return context.contentResolver.query(childrenUri, projection, null, null, null)?.use { cursor ->
            val nameColumn = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DISPLAY_NAME)
            buildSet {
                while (cursor.moveToNext()) {
                    cursor.getString(nameColumn)?.takeIf(String::isNotBlank)?.let(::add)
                }
            }
        }.orEmpty()
    }

    @RequiresApi(Build.VERSION_CODES.Q)
    private suspend fun publishWithMediaStore(source: File, fileName: String, onCreated: suspend (String) -> Unit, checkCancelled: () -> Unit): String {
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
            put(MediaStore.MediaColumns.MIME_TYPE, source.mimeType())
            put(MediaStore.MediaColumns.RELATIVE_PATH, "${Environment.DIRECTORY_DOWNLOADS}/YTH")
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val resolver = context.contentResolver
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: error(text(R.string.publisher_create_default_error))
        try {
            onCreated(uri.toString())
            resolver.openOutputStream(uri, "w")?.use { output ->
                source.inputStream().buffered().use { input -> copyCancellable(input, output, checkCancelled) }
            } ?: error(text(R.string.publisher_open_file_error))
            resolver.update(
                uri,
                ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) },
                null,
                null,
            )
            return uri.toString()
        } catch (error: Exception) {
            runCatching { resolver.delete(uri, null, null) }.exceptionOrNull()?.let(error::addSuppressed)
            throw error
        }
    }

    @Suppress("DEPRECATION")
    private suspend fun publishLegacy(source: File, fileName: String, onCreated: suspend (String) -> Unit, checkCancelled: () -> Unit): String {
        check(
            ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_EXTERNAL_STORAGE) ==
                PackageManager.PERMISSION_GRANTED,
        ) { text(R.string.publisher_storage_permission) }
        val directory = File(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
            "YTH",
        )
        check(directory.exists() || directory.mkdirs()) { text(R.string.publisher_create_default_directory_error) }
        val destination = uniqueDestination(directory, fileName)
        onCreated(destination.toURI().toString())
        source.inputStream().buffered().use { input ->
            FileOutputStream(destination).buffered().use { output -> copyCancellable(input, output, checkCancelled) }
        }
        MediaScannerConnection.scanFile(context, arrayOf(destination.absolutePath), arrayOf(source.mimeType()), null)
        return destination.toURI().toString()
    }

    private fun uniqueDestination(directory: File, fileName: String): File {
        val initial = File(directory, fileName)
        if (!initial.exists()) return initial
        val extension = initial.extension.takeIf { it.isNotBlank() }?.let { ".$it" }.orEmpty()
        val base = initial.name.removeSuffix(extension)
        var number = 2
        while (true) {
            val candidate = File(directory, "$base ($number)$extension")
            if (!candidate.exists()) return candidate
            number += 1
        }
    }

    private fun File.mimeType(): String =
        MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension.lowercase()) ?: "application/octet-stream"

    private fun text(resourceId: Int): String = LocaleController.wrap(context).getString(resourceId)
}

internal suspend fun copyCancellable(input: InputStream, output: OutputStream, checkCancelled: () -> Unit) {
    val buffer = ByteArray(64 * 1024)
    while (true) {
        currentCoroutineContext().ensureActive()
        checkCancelled()
        val count = input.read(buffer)
        if (count < 0) return
        output.write(buffer, 0, count)
    }
}
