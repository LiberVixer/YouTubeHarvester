package com.liberivixer.youtubeharvester.data

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.OpenableColumns
import androidx.room.withTransaction
import com.liberivixer.youtubeharvester.data.db.HarvesterDatabase
import com.liberivixer.youtubeharvester.download.archiveUriExists
import com.liberivixer.youtubeharvester.model.AppSettings
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

internal class ArchiveTransferFiles(private val context: Context) {
    suspend fun capture(row: JSONObject): JSONObject? {
        if (row.isNull("file_uri")) return null
        val uri = Uri.parse(row.getString("file_uri"))
        return try {
            val name = when (uri.scheme) {
                "file" -> File(requireNotNull(uri.path)).name
                "content" -> context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
                    if (it.moveToFirst()) it.getString(0) else null
                }
                else -> null
            } ?: return null
            if (!validTransferFileName(name)) return null
            val coroutine = currentCoroutineContext()
            val identity = when (uri.scheme) {
                "file" -> File(requireNotNull(uri.path)).inputStream().use { transferFileIdentity(it, coroutine::ensureActive) }
                "content" -> context.contentResolver.openInputStream(uri)?.use { transferFileIdentity(it, coroutine::ensureActive) }
                else -> null
            } ?: return null
            JSONObject().apply {
                listOf("source", "media_id", "resolution", "variant_key").forEach { put(it, row.get(it)) }
                put("file_name", name); put("file_size", identity.size); put("sha256", identity.sha256)
            }
        } catch (cancelled: CancellationException) { throw cancelled
        } catch (_: Exception) { null }
    }

    suspend fun relink(database: HarvesterDatabase, settings: AppSettings) = withContext(Dispatchers.IO) {
        val hints = database.archiveRelinkDao().getAll()
        if (hints.isEmpty()) return@withContext
        val candidates = candidates(settings).groupBy { it.name }
        val coroutine = currentCoroutineContext()
        for (hint in hints) {
            coroutine.ensureActive()
            val existing = database.archiveDao().get(hint.source, hint.mediaId, hint.resolution, hint.variantKey)
                ?: continue
            if (existing.fileExists && archiveUriExists(context, existing.fileUri) == true) continue
            val matches = mutableListOf<Candidate>()
            for (candidate in candidates[hint.fileName].orEmpty().filter { it.size == null || it.size == hint.fileSize }) {
                try {
                    val identity = context.contentResolver.openInputStream(candidate.uri)?.use {
                        transferFileIdentity(it, coroutine::ensureActive)
                    } ?: continue
                    if (identity == TransferFileIdentity(hint.fileSize, hint.sha256)) matches.add(candidate)
                } catch (cancelled: CancellationException) { throw cancelled
                } catch (_: Exception) { }
            }
            val match = matches.singleOrNull() ?: continue
            database.withTransaction {
                // Do not resurrect or overwrite a record edited while the file was being hashed.
                if (database.archiveDao().get(hint.source, hint.mediaId, hint.resolution, hint.variantKey) == existing) {
                    database.archiveDao().upsert(existing.copy(fileUri = match.uri.toString(), fileExists = true))
                }
            }
        }
    }

    private data class Candidate(val name: String, val uri: Uri, val size: Long?)

    private fun candidates(settings: AppSettings): List<Candidate> {
        val tree = settings.downloadDirectoryUri?.let(Uri::parse)
        if (tree != null) {
            if (context.contentResolver.persistedUriPermissions.none { it.uri == tree && it.isReadPermission }) return emptyList()
            val id = DocumentsContract.getTreeDocumentId(tree)
            val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, id)
            val projection = arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME, DocumentsContract.Document.COLUMN_SIZE,
                DocumentsContract.Document.COLUMN_MIME_TYPE)
            return context.contentResolver.query(children, projection, null, null, null)?.use { cursor ->
                buildList {
                    while (cursor.moveToNext()) {
                        if (cursor.getString(3) == DocumentsContract.Document.MIME_TYPE_DIR) continue
                        add(Candidate(cursor.getString(1), DocumentsContract.buildDocumentUriUsingTree(tree, cursor.getString(0)),
                            if (cursor.isNull(2)) null else cursor.getLong(2)))
                    }
                }
            }.orEmpty()
        }
        if (android.os.Build.VERSION.SDK_INT >= 29) return emptyList()
        val directory = File(settings.downloadDirectory).canonicalFile
        if (!directory.path.startsWith("/storage/")) return emptyList()
        return directory.listFiles().orEmpty().filter { it.isFile && it.canonicalFile.parentFile == directory }
            .map { Candidate(it.name, Uri.fromFile(it), it.length()) }
    }
}
