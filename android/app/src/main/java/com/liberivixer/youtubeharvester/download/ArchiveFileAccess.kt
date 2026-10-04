package com.liberivixer.youtubeharvester.download

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import androidx.core.content.FileProvider
import java.io.File
import java.io.FileNotFoundException

class ArchiveFileProvider : FileProvider()

fun archiveUriExists(context: Context, rawUri: String?): Boolean? {
    val uri = rawUri?.takeIf(String::isNotBlank)?.let(Uri::parse) ?: return false
    return when (uri.scheme?.lowercase()) {
        "file" -> uri.path?.let(::File)?.isFile == true
        "content" -> try {
            context.contentResolver.openAssetFileDescriptor(uri, "r")?.use { true } ?: false
        } catch (_: FileNotFoundException) {
            false
        } catch (_: IllegalArgumentException) {
            missingFromArchiveTree(context, uri)
        } catch (_: Exception) {
            // Access or provider failures do not prove that the file was deleted.
            null
        }
        else -> false
    }
}

private fun missingFromArchiveTree(context: Context, uri: Uri): Boolean? = runCatching {
    if (!DocumentsContract.isTreeUri(uri)) return@runCatching null
    val documentId = DocumentsContract.getDocumentId(uri)
    val children = DocumentsContract.buildChildDocumentsUriUsingTree(uri, DocumentsContract.getTreeDocumentId(uri))
    // The publisher places archive files directly in the selected tree. Android may
    // wrap a missing child's FileNotFoundException in IllegalArgumentException.
    context.contentResolver.query(children, arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID), null, null, null)?.use { cursor ->
        while (cursor.moveToNext()) {
            if (cursor.getString(0) == documentId) return@use null
        }
        false
    }
}.getOrNull()

fun shareableArchiveUri(context: Context, uri: Uri): Uri =
    if (uri.scheme.equals("file", ignoreCase = true)) {
        FileProvider.getUriForFile(context, "${context.packageName}.downloads", File(requireNotNull(uri.path)))
    } else uri
