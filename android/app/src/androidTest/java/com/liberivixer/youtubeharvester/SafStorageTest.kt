package com.liberivixer.youtubeharvester

import android.content.Context
import android.content.Intent
import android.provider.DocumentsContract
import androidx.core.net.toUri
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.liberivixer.youtubeharvester.download.DownloadOutputPublisher
import com.liberivixer.youtubeharvester.download.archiveUriExists
import com.liberivixer.youtubeharvester.ui.LocaleController
import java.io.File
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.CancellationException
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SafStorageTest {
    @Test fun oldSafDocumentRemainsReadableAfterFolderSwitch() {
        val arguments = InstrumentationRegistry.getArguments()
        val oldTree = arguments.getString("retainedSafQaTree")?.toUri() ?: return
        val newTree = arguments.getString("copySafQaTree")?.toUri() ?: return
        val document = arguments.getString("retainedSafQaDocument")?.toUri() ?: return
        require(oldTree != newTree)
        for (tree in listOf(oldTree, newTree)) {
            require(tree.authority == "com.android.externalstorage.documents")
            require(DocumentsContract.getTreeDocumentId(tree).matches(Regex("primary:Download/YTH-SAF-QA-[0-9]+")))
        }
        require(document.authority == oldTree.authority)
        require(DocumentsContract.getDocumentId(document).startsWith(DocumentsContract.getTreeDocumentId(oldTree) + "/"))
        val context = ApplicationProvider.getApplicationContext<Context>()
        val resolver = context.contentResolver
        for (tree in listOf(oldTree, newTree)) {
            assertTrue(resolver.persistedUriPermissions.any {
                it.uri == tree && it.isReadPermission && it.isWritePermission
            })
        }
        assertEquals(true, archiveUriExists(context, document.toString()))
        resolver.openInputStream(document)!!.use { assertTrue(it.readBytes().size > 0) }
    }

    @Test fun cancellationDuringSafCopyDeletesPartialDocument(): Unit = runBlocking {
        val rawTree = InstrumentationRegistry.getArguments().getString("copySafQaTree")
            ?: return@runBlocking
        val tree = rawTree.toUri()
        require(tree.authority == "com.android.externalstorage.documents")
        require(DocumentsContract.getTreeDocumentId(tree).matches(Regex("primary:Download/YTH-SAF-QA-[0-9]+")))
        val context = ApplicationProvider.getApplicationContext<Context>()
        assertTrue(context.contentResolver.persistedUriPermissions.any {
            it.uri == tree && it.isReadPermission && it.isWritePermission
        })
        val source = File.createTempFile("yth-saf-cancel", ".mp4", context.cacheDir)
        val bytes = ByteArray(192 * 1024) { (it % 251).toByte() }
        source.writeBytes(bytes)
        val publisher = DownloadOutputPublisher(context)
        var partial: String? = null
        var completed: String? = null
        var checks = 0
        try {
            val error = runCatching {
                publisher.publish(source, rawTree, onCreated = { partial = it }, checkCancelled = {
                    checks += 1
                    if (checks == 2) {
                        val uri = requireNotNull(partial).toUri()
                        context.contentResolver.openInputStream(uri)!!.use {
                            assertArrayEquals(bytes.copyOfRange(0, 64 * 1024), it.readBytes())
                        }
                        throw CancellationException("QA cancellation after first block")
                    }
                })
            }.exceptionOrNull()
            assertTrue(error is CancellationException)
            assertEquals(2, checks)
            assertEquals(false, archiveUriExists(context, requireNotNull(partial)))
            publisher.deletePublished(requireNotNull(partial))
            publisher.deletePublished(requireNotNull(partial))
            assertArrayEquals(bytes, source.readBytes())
            completed = publisher.publish(source, rawTree)
            context.contentResolver.openInputStream(requireNotNull(completed).toUri())!!.use {
                assertArrayEquals(bytes, it.readBytes())
            }
        } finally {
            completed?.let(publisher::deletePublished)
            partial?.let(publisher::deletePublished)
            source.delete()
        }
    }

    // Opt-in device QA: leaves this isolated tree revoked for the UI recovery test.
    @Test fun publicationAndExplicitPermissionRevocation(): Unit = runBlocking {
        val rawTree = InstrumentationRegistry.getArguments().getString("revokeSafQaTree")
        if (rawTree == null) return@runBlocking
        val tree = requireNotNull(rawTree).toUri()
        require(tree.authority == "com.android.externalstorage.documents")
        require(DocumentsContract.getTreeDocumentId(tree).matches(Regex("primary:Download/YTH-SAF-QA-[0-9]+")))
        val context = ApplicationProvider.getApplicationContext<Context>()
        val resolver = context.contentResolver
        assertTrue(resolver.persistedUriPermissions.any { it.uri == tree && it.isReadPermission && it.isWritePermission })
        val file = File.createTempFile("yth-saf-fixture", ".mp4", context.cacheDir)
        val bytes = ByteArray(4096) { (it % 251).toByte() }
        file.writeBytes(bytes)
        val publisher = DownloadOutputPublisher(context)
        var published: String? = null
        try {
            val uri = publisher.publish(file, rawTree, onCreated = { published = it })
            assertEquals(uri, published)
            assertEquals(true, archiveUriExists(context, uri))
            resolver.openInputStream(uri.toUri())!!.use { assertArrayEquals(bytes, it.readBytes()) }
            publisher.deletePublished(uri)
            published = null
            val openError = runCatching { resolver.openAssetFileDescriptor(uri.toUri(), "r")?.close() }.exceptionOrNull()
            assertEquals("Deleted SAF URI: $openError", false, archiveUriExists(context, uri))
            resolver.releasePersistableUriPermission(tree,
                Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            assertFalse(resolver.persistedUriPermissions.any { it.uri == tree })
            assertNull(archiveUriExists(context, uri))
            val error = runCatching {
                publisher.publish(file, rawTree, onCreated = { fail("Must not create a document without permission") })
            }.exceptionOrNull()
            assertTrue(error is IllegalStateException)
            assertEquals(LocaleController.wrap(context).getString(R.string.publisher_permission_revoked), error?.message)
            assertArrayEquals(bytes, file.readBytes())
        } finally {
            published?.let(publisher::deletePublished)
            file.delete()
        }
    }
}
