package com.liberivixer.youtubeharvester

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.room.Room
import androidx.test.platform.app.InstrumentationRegistry
import com.liberivixer.youtubeharvester.data.*
import com.liberivixer.youtubeharvester.data.db.*
import com.liberivixer.youtubeharvester.model.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.Assume.assumeTrue
import org.json.JSONObject
import android.util.Base64
import android.content.pm.PackageManager
import java.security.MessageDigest
import java.io.File
import java.io.IOException
import java.util.UUID

class DataTransferTest {
    private val context: Context = InstrumentationRegistry.getInstrumentation().targetContext
    private val password get() = "QA-only-migration-passphrase".toCharArray()

    @Test fun crossIdentityTransferUsesDestinationKeystore() = runBlocking {
        val phase = InstrumentationRegistry.getArguments().getString("crossIdentityPhase")
        assumeTrue("Opt-in cross-UID fixture", phase in setOf("source", "target"))
        val file = File(requireNotNull(context.getExternalFilesDir(null)), "cross-identity-qa.json")
        Fixture(context, persistent = true).use { fixture ->
            if (phase == "source") {
                assertEquals("com.liberivixer.youtubeharvester.debug", context.packageName)
                populate(fixture)
                val sourceSecret = fixture.preferences.data.first()[stringPreferencesKey("telegram_bot_token")]!!
                assertTrue(sourceSecret.startsWith(SecretCipher.PREFIX))
                val encrypted = fixture.transfer.export(password)
                file.writeText(JSONObject().put("sourcePackage", context.packageName)
                    .put("sourceUid", context.applicationInfo.uid).put("sourceSecret", sourceSecret)
                    .put("transfer", Base64.encodeToString(encrypted, Base64.NO_WRAP)).toString())
                encrypted.fill(0)
                assertEquals(42, fixture.db.downloadJobDao().get("qa-paused-job")!!.progress)
                assertTrue(fixture.db.scheduleDao().getAll().single().enabled)
            } else {
                assertEquals("com.liberivixer.youtubeharvester.migrationqa", context.packageName)
                val flags = if (android.os.Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
                val info = context.packageManager.getPackageInfo(context.packageName, flags)
                @Suppress("DEPRECATION")
                val certificates = if (android.os.Build.VERSION.SDK_INT >= 28) info.signingInfo!!.apkContentsSigners else info.signatures!!
                assertEquals(1, certificates.size)
                val fingerprint = MessageDigest.getInstance("SHA-256").digest(certificates.single().toByteArray())
                    .joinToString("") { "%02x".format(it) }
                assertEquals("25bec4a973717a990f023b7dc07b2588629883c268d71ed820956c0f8bca23ca", fingerprint)
                val input = JSONObject(file.readText())
                assertEquals("com.liberivixer.youtubeharvester.debug", input.getString("sourcePackage"))
                assertNotEquals(input.getInt("sourceUid"), context.applicationInfo.uid)
                val backup = Base64.decode(input.getString("transfer"), Base64.NO_WRAP)
                try { fixture.transfer.import(backup, password) } finally { backup.fill(0) }
                val settings = fixture.settings.settings.first()
                assertEquals("QA-only-token:0123456789", settings.telegramBotToken)
                assertEquals("http://qa:QA-only-password@example.org:8080", settings.telegramProxyUrl)
                assertFalse(settings.telegramCredentialError)
                assertEquals(9, settings.videoLimit)
                assertNull(settings.downloadDirectoryUri)
                assertEquals(1, fixture.db.channelDao().count())
                assertEquals(4, fixture.db.queueDao().getAll().single().sortOrder)
                assertTrue(fixture.db.markedMediaDao().contains("YouTube", "aqz-KE-bpKQ"))
                assertNull(fixture.db.archiveDao().observeAll().first().single().fileUri)
                assertFalse(fixture.db.archiveDao().observeAll().first().single().fileExists)
                assertEquals(0, fixture.db.downloadJobDao().get("qa-paused-job")!!.progress)
                assertFalse(fixture.db.scheduleDao().getAll().single().enabled)
                assertNull(fixture.db.pendingTransferDao().get())
                val destinationSecret = fixture.preferences.data.first()[stringPreferencesKey("telegram_bot_token")]!!
                assertTrue(destinationSecret.startsWith(SecretCipher.PREFIX))
                assertEquals(settings.telegramBotToken, SecretCipher().decrypt(destinationSecret, "telegram_bot_token"))
                try {
                    SecretCipher().decrypt(input.getString("sourceSecret"), "telegram_bot_token")
                    fail("Source ciphertext must not decrypt with destination Keystore")
                } catch (_: java.security.GeneralSecurityException) { }
            }
        }
    }

    private class Fixture(val context: Context, private val persistent: Boolean = false) : AutoCloseable {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val file = File(context.cacheDir, "transfer-${UUID.randomUUID()}.preferences_pb")
        val preferences = PreferenceDataStoreFactory.create(scope = scope, produceFile = { file })
        val settings = SettingsDataStore(context, preferences)
        private val databaseName = "transfer-qa-${UUID.randomUUID()}.db"
        val db = if (persistent) Room.databaseBuilder(context, HarvesterDatabase::class.java, databaseName).build()
            else Room.inMemoryDatabaseBuilder(context, HarvesterDatabase::class.java).build()
        val transfer = DataTransferStore(context, db, settings)
        override fun close() {
            db.close(); scope.cancel(); file.delete()
            if (persistent) context.deleteDatabase(databaseName)
        }
    }

    private suspend fun populate(f: Fixture) {
        val now = System.currentTimeMillis()
        f.db.channelDao().insert(ChannelItem("handle:qa-channel", "https://www.youtube.com/@qa-channel", "QA channel", "@qa-channel",
            paidContent = PaidContentStatus.MembersOnly, lastCheckedEpochMs = now).toEntity(7))
        val item = QueueItem("jNQXAC9IVRw", "https://www.youtube.com/watch?v=jNQXAC9IVRw", "QA video", "QA channel", MediaSource.YouTube,
            selected = false, audioTracks = listOf(SelectedAudioTrack("140", "audio", "en", "QA audio")), subtitleSelections = listOf("en"))
        f.db.queueDao().upsert(item.toEntity(4))
        f.db.downloadJobDao().upsert(item.toDownloadJobEntity("qa-paused-job", false, now).copy(status = "PAUSED", progress = 42))
        f.db.archiveDao().upsert(ArchiveItem("dQw4w9WgXcQ", "QA archive", "QA author", MediaSource.YouTube, ContentType.Video,
            "480p", "QA date", now, fileExists = false, audio = listOf("English"), subtitles = listOf("en"), variantKey = "qa-variant")
            .toEntity(now, "content://media/external/video/media/123456789"))
        f.db.markedMediaDao().insert(MarkedMediaEntity("YouTube", "aqz-KE-bpKQ", now))
        f.db.scheduleDao().upsert(ScheduleItem("qa-schedule", 23, 47, true, createdAtEpochMs = now).toEntity())
        f.settings.save(AppSettings(maxResolution = "720p", videoLimit = 9, shortsLimit = 7, streamsLimit = 3,
            themeMode = AppThemeMode.Dark, watchClipboard = true, systemNotifications = false, logRetentionDays = 14,
            downloadDirectoryUri = "content://com.android.externalstorage.documents/tree/primary%3AQA",
            telegramEnabled = true, telegramBotToken = "QA-only-token:0123456789", telegramChannelId = "@qa-channel",
            telegramProxyUrl = "http://qa:QA-only-password@example.org:8080"), replaceSecrets = true)
    }

    @Test fun roundTripPreservesDataButRequiresExplicitResumeAndFolderGrant() = runBlocking {
        Fixture(context).use { source -> Fixture(context).use { target ->
            populate(source)
            val backup = source.transfer.export(password)
            target.transfer.import(backup, password)
            val channel = target.db.channelDao().observeAll().first().single()
            assertEquals(7, channel.sortOrder)
            assertEquals("MembersOnly", channel.paidContent)
            val queue = target.db.queueDao().getAll().single()
            assertFalse(queue.selected)
            assertEquals(4, queue.sortOrder)
            assertEquals("140", queue.toModel().audioTracks.single().formatId)
            assertEquals(listOf("en"), queue.toModel().subtitleSelections)
            assertTrue(target.db.markedMediaDao().contains("YouTube", "aqz-KE-bpKQ"))
            val archive = target.db.archiveDao().observeAll().first().single()
            assertEquals("qa-variant", archive.variantKey)
            assertNull(archive.fileUri)
            assertFalse(archive.fileExists)
            val job = target.db.downloadJobDao().get("qa-paused-job")!!
            assertEquals("PAUSED", job.status)
            assertEquals(0, job.progress)
            assertNull(job.fileUri)
            assertEquals(0, target.db.downloadJobDao().pendingCount())
            val schedule = target.db.scheduleDao().getAll().single()
            assertEquals(23, schedule.hour)
            assertEquals(47, schedule.minute)
            assertFalse(schedule.enabled)
            val settings = target.settings.settings.first()
            assertEquals("720p", settings.maxResolution)
            assertEquals(9, settings.videoLimit)
            assertEquals(14, settings.logRetentionDays)
            assertEquals("QA-only-token:0123456789", settings.telegramBotToken)
            assertEquals("http://qa:QA-only-password@example.org:8080", settings.telegramProxyUrl)
            assertTrue(settings.telegramEnabled)
            assertFalse(settings.telegramCredentialError)
            assertNull(settings.downloadDirectoryUri)
            assertNull(target.db.pendingTransferDao().get())
            try { target.transfer.import(backup, password); fail("Expected repeated import rejection") }
                catch (_: DataTransferNotEmptyException) { }
            assertEquals(1, target.db.queueDao().count())
            assertEquals(42, source.db.downloadJobDao().get("qa-paused-job")!!.progress)
            assertTrue(source.db.scheduleDao().getAll().single().enabled)
        } }
    }

    @Test fun unreadableArchiveAndCredentialsCannotProduceMisleadingCompleteExport() = runBlocking {
        Fixture(context).use { fixture ->
            populate(fixture)
            val archive = fixture.db.archiveDao().observeAll().first().single()
            fixture.db.archiveDao().upsert(archive.copy(fileExists = true, fileUri = null))
            try { fixture.transfer.export(password); fail("Expected unreadable archive rejection") }
                catch (_: DataTransferArchiveException) { }
            fixture.db.archiveDao().upsert(archive)
            fixture.preferences.edit {
                it[stringPreferencesKey("telegram_bot_token")] = "keystore:v1:QA-invalid-ciphertext"
            }
            assertTrue(fixture.settings.settings.first().telegramCredentialError)
            try { fixture.transfer.export(password); fail("Expected unreadable credential rejection") }
                catch (_: DataTransferCredentialsException) { }
            assertEquals(1, fixture.db.archiveDao().observeAll().first().size)
            assertEquals(1, fixture.db.queueDao().count())
        }
    }

    @Test fun wrongPasswordAndNonEmptyTargetNeverOverwriteExistingData() = runBlocking {
        Fixture(context).use { source -> Fixture(context).use { target ->
            populate(source)
            val backup = source.transfer.export(password)
            fails { target.transfer.import(backup, "incorrect-QA-passphrase".toCharArray()) }
            assertEquals(0, target.db.channelDao().count())
            assertNull(target.db.pendingTransferDao().get())
            target.db.markedMediaDao().insert(MarkedMediaEntity("YouTube", "preserve-existing", 123L))
            target.settings.save(AppSettings(videoLimit = 2))
            try { target.transfer.import(backup, password); fail("Expected nonempty rejection") }
                catch (_: DataTransferNotEmptyException) { }
            assertTrue(target.db.markedMediaDao().contains("YouTube", "preserve-existing"))
            assertEquals(0, target.db.queueDao().count())
            assertEquals(2, target.settings.settings.first().videoLimit)
            assertNull(target.db.pendingTransferDao().get())
            source.db.downloadJobDao().upsert(source.db.downloadJobDao().get("qa-paused-job")!!.copy(status = "DOWNLOADING"))
            try { source.transfer.export(password); fail("Expected busy rejection") }
                catch (_: DataTransferBusyException) { }
        } }
    }

    @Test fun failedDatabaseInsertRollsBackEveryTableAndJournal() = runBlocking {
        Fixture(context).use { source -> Fixture(context).use { target ->
            populate(source)
            val backup = source.transfer.export(password)
            target.db.openHelper.writableDatabase.execSQL("CREATE TRIGGER qa_reject_queue BEFORE INSERT ON queue_items BEGIN SELECT RAISE(ABORT, 'QA injected failure'); END")
            fails { target.transfer.import(backup, password) }
            assertEquals(0, target.db.channelDao().count())
            assertEquals(0, target.db.queueDao().count())
            assertNull(target.db.pendingTransferDao().get())
            assertEquals(5, target.settings.settings.first().videoLimit)
        } }
    }

    @Test fun interruptedSettingsCommitRecoversIdempotentlyFromEncryptedJournal() = runBlocking {
        Fixture(context).use { source -> Fixture(context).use { target ->
            populate(source)
            val backup = source.transfer.export(password)
            val failingPreferences = object : DataStore<Preferences> {
                override val data: Flow<Preferences> = target.preferences.data
                override suspend fun updateData(transform: suspend (t: Preferences) -> Preferences): Preferences {
                    throw IOException("QA injected storage failure")
                }
            }
            val failingTransfer = DataTransferStore(context, target.db, SettingsDataStore(context, failingPreferences))
            try { failingTransfer.import(backup, password); fail("Expected pending recovery") }
                catch (_: DataTransferPendingException) { }
            assertEquals(1, target.db.channelDao().count())
            val pending = target.db.pendingTransferDao().get()!!
            assertTrue(pending.encryptedSettings.startsWith(SecretCipher.PREFIX))
            assertFalse(pending.encryptedSettings.contains("QA-only-token"))
            target.transfer.finishPendingImport()
            target.transfer.finishPendingImport()
            assertNull(target.db.pendingTransferDao().get())
            assertEquals(1, target.db.queueDao().count())
            assertEquals(9, target.settings.settings.first().videoLimit)
            assertEquals("QA-only-token:0123456789", target.settings.settings.first().telegramBotToken)
        } }
    }

    private suspend fun fails(block: suspend () -> Unit) {
        try { block(); fail("Expected failure") } catch (_: Exception) { }
    }
}
