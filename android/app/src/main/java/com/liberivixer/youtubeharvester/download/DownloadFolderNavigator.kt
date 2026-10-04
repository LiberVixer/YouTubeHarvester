package com.liberivixer.youtubeharvester.download

import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.DocumentsContract
import android.provider.MediaStore
import java.io.File
import androidx.core.net.toUri

enum class FolderOpenResult { DIRECT, FALLBACK, FAILED }

object DownloadFolderNavigator {
    fun directoryUri(context: Context, tree: String?, file: String?): Uri? = runCatching {
        val source = file?.toUri()
        when {
            source != null && DocumentsContract.isTreeUri(source) ->
                DocumentsContract.buildDocumentUriUsingTree(source, DocumentsContract.getTreeDocumentId(source))
            source?.scheme == "file" -> externalDirectory(File(requireNotNull(source.path)).parentFile!!.path.removePrefix("/storage/emulated/0/"))
            source?.authority == "media" && Build.VERSION.SDK_INT >= 29 -> {
                context.contentResolver.query(source, arrayOf(MediaStore.MediaColumns.RELATIVE_PATH), null, null, null)?.use {
                    if (it.moveToFirst()) externalDirectory(it.getString(0)) else null
                }
            }
            source != null -> null
            !tree.isNullOrBlank() -> tree.toUri().let {
                DocumentsContract.buildDocumentUriUsingTree(it, DocumentsContract.getTreeDocumentId(it))
            }
            else -> externalDirectory("Download/YTH")
        }
    }.getOrNull()

    private fun externalDirectory(path: String): Uri = DocumentsContract.buildDocumentUri(
        "com.android.externalstorage.documents", "primary:${path.trim('/')}",
    )

    fun open(context: Context, directory: Uri?): FolderOpenResult {
        if (directory != null) {
            val view = Intent(Intent.ACTION_VIEW).setDataAndType(directory, DocumentsContract.Document.MIME_TYPE_DIR)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
            if (runCatching { context.startActivity(view) }.isSuccess) return FolderOpenResult.DIRECT
            val browse = Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*")
                .addCategory(Intent.CATEGORY_OPENABLE)
                .putExtra(DocumentsContract.EXTRA_INITIAL_URI, directory)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            if (runCatching { context.startActivity(browse) }.isSuccess) return FolderOpenResult.FALLBACK
        }
        return if (runCatching {
            context.startActivity(Intent(DownloadManager.ACTION_VIEW_DOWNLOADS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }.isSuccess) FolderOpenResult.FALLBACK else FolderOpenResult.FAILED
    }
}
