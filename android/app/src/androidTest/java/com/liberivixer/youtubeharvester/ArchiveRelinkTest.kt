package com.liberivixer.youtubeharvester

import android.content.Context
import android.provider.DocumentsContract
import androidx.core.net.toUri
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.room.Room
import androidx.test.platform.app.InstrumentationRegistry
import com.liberivixer.youtubeharvester.data.*
import com.liberivixer.youtubeharvester.data.db.*
import com.liberivixer.youtubeharvester.model.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import org.junit.Assert.*
import org.junit.Assume.assumeNotNull
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.File
import java.util.UUID

class ArchiveRelinkTest {
    @Test fun encryptedTransferRelinksOnlyDigestMatchingFileInSelectedSafTree() = runBlocking {
        val rawTree = InstrumentationRegistry.getArguments().getString("copySafQaTree")
        assumeNotNull(rawTree)
        val tree = requireNotNull(rawTree).toUri()
        require(tree.authority == "com.android.externalstorage.documents")
        require(DocumentsContract.getTreeDocumentId(tree).matches(Regex("primary:Download/YTH-SAF-QA-[0-9]+")))
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val resolver = context.contentResolver
        require(resolver.persistedUriPermissions.any { it.uri == tree && it.isReadPermission && it.isWritePermission })
        val directory = DocumentsContract.buildDocumentUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree))
        val name = "transfer-QA-${UUID.randomUUID()}.mp4"
        val document = requireNotNull(DocumentsContract.createDocument(resolver, directory, "video/mp4", name))
        val bytes = ByteArray(8192) { (it % 251).toByte() }
        val password = "QA-only-SAF-transfer-passphrase".toCharArray()
        val source = Room.inMemoryDatabaseBuilder(context, HarvesterDatabase::class.java).build()
        val target = Room.inMemoryDatabaseBuilder(context, HarvesterDatabase::class.java).build()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val sourceFile = File(context.cacheDir, "transfer-source-${UUID.randomUUID()}.preferences_pb")
        val targetFile = File(context.cacheDir, "transfer-target-${UUID.randomUUID()}.preferences_pb")
        val sourceSettings = SettingsDataStore(context, PreferenceDataStoreFactory.create(scope = scope, produceFile = { sourceFile }))
        val targetSettings = SettingsDataStore(context, PreferenceDataStoreFactory.create(scope = scope, produceFile = { targetFile }))
        try {
            resolver.openOutputStream(document, "wt")!!.use { it.write(bytes) }
            val archive = ArchiveItem("jNQXAC9IVRw", "QA archive", "QA channel", MediaSource.YouTube, ContentType.Video,
                "480p", "QA date", variantKey = "qa-saf")
            source.archiveDao().upsert(archive.toEntity(System.currentTimeMillis(), document.toString()))
            val backup = DataTransferStore(context, source, sourceSettings).export(password)
            DataTransferStore(context, target, targetSettings).import(backup, password)
            val hint = target.archiveRelinkDao().getAll().single()
            assertEquals(name, hint.fileName)
            assertEquals(transferFileIdentity(ByteArrayInputStream(bytes)).sha256, hint.sha256)
            assertNull(target.archiveDao().observeAll().first().single().fileUri)
            val files = ArchiveTransferFiles(context)
            val settings = targetSettings.settings.first().copy(downloadDirectoryUri = tree.toString())
            val altered = bytes.copyOf().also { it[0] = (it[0].toInt() xor 1).toByte() }
            resolver.openOutputStream(document, "wt")!!.use { it.write(altered) }
            files.relink(target, settings)
            assertNull(target.archiveDao().observeAll().first().single().fileUri)
            resolver.openOutputStream(document, "wt")!!.use { it.write(bytes) }
            files.relink(target, settings)
            files.relink(target, settings)
            val recovered = target.archiveDao().observeAll().first().single()
            assertTrue(recovered.fileExists)
            assertEquals(document.toString(), recovered.fileUri)
            resolver.openInputStream(recovered.fileUri!!.toUri())!!.use { assertArrayEquals(bytes, it.readBytes()) }
            assertEquals(1, target.archiveDao().observeAll().first().size)
        } finally {
            password.fill('\u0000')
            source.close(); target.close(); scope.cancel()
            sourceFile.delete(); targetFile.delete()
            DocumentsContract.deleteDocument(resolver, document)
        }
    }
}
