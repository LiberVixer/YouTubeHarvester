package com.liberivixer.youtubeharvester

import android.content.Context
import android.os.Build
import android.provider.MediaStore
import android.provider.DocumentsContract
import androidx.core.net.toUri
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.liberivixer.youtubeharvester.data.SecretCipher
import com.liberivixer.youtubeharvester.data.AndroidAppRepository
import com.liberivixer.youtubeharvester.data.db.HarvesterDatabase
import com.liberivixer.youtubeharvester.data.db.toDownloadJobEntity
import com.liberivixer.youtubeharvester.data.db.toEntity
import com.liberivixer.youtubeharvester.download.DownloadOutputPublisher
import com.liberivixer.youtubeharvester.download.DownloadFolderNavigator
import com.liberivixer.youtubeharvester.download.archiveUriExists
import com.liberivixer.youtubeharvester.media.AndroidYtDlpRuntime
import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.model.QueueItem
import com.yausername.youtubedl_android.YoutubeDL
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.first
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class AndroidIntegrationTest {
    private val context: Context = ApplicationProvider.getApplicationContext()

    @Test fun harvestCheckpointAndStopSurviveStoreRecreation() = runBlocking {
        val store = com.liberivixer.youtubeharvester.download.HarvestSessionStore(context)
        assumeTrue(store.current() == null)
        val session = com.liberivixer.youtubeharvester.download.HarvestSession(channels = emptyList(),
            settings = com.liberivixer.youtubeharvester.model.AppSettings())
        try {
            assertTrue(store.begin(session))
            assertFalse(store.begin(session.copy(id = "duplicate")))
            store.stop()
            val checkpoint = com.liberivixer.youtubeharvester.download.HarvestCheckpoint(
                phase = com.liberivixer.youtubeharvester.download.HarvestPhase.QUEUE_AFTER,
                pending = com.liberivixer.youtubeharvester.download.PendingHarvestDownload("YouTube:test", "job", com.liberivixer.youtubeharvester.model.ContentType.Video))
            store.checkpoint(session.id, checkpoint)
            val restored = com.liberivixer.youtubeharvester.download.HarvestSessionStore(context).current()!!
            assertTrue(restored.stopRequested)
            assertEquals(checkpoint, restored.checkpoint)
            store.clear("not-the-owner")
            assertNotNull(store.current())
        } finally { store.clear(session.id) }
    }

    @Test fun recoveredHarvestReusesItsTerminalJob() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, HarvesterDatabase::class.java).build()
        try {
            val repo = AndroidAppRepository(context, db)
            val item = QueueItem("durable", "https://example.test/durable", "Durable", "Channel", MediaSource.YouTube)
            val job = repo.enqueueDownload(item, false, "stable-job")
            db.downloadJobDao().markCompleted(job, "content://test/output", "COMPLETED", 10)
            assertEquals(job, repo.enqueueDownload(item, false, "stable-job"))
            assertEquals(job, repo.enqueueChannelDownload(item, "stable-job"))
            assertEquals("COMPLETED", db.downloadJobDao().get(job)!!.status)
        } finally { db.close() }
    }

    @Test fun bootRecoveryDoesNotRestartPausedOrTerminalJobs() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, HarvesterDatabase::class.java).build()
        try {
            val repo = AndroidAppRepository(context, db)
            val statuses = listOf("QUEUED", "INITIALIZING", "DOWNLOADING", "PROCESSING",
                "WAITING_NETWORK", "PUBLISHING", "PAUSED", "FAILED", "CANCELLED", "COMPLETED")
            for ((index, status) in statuses.withIndex()) {
                val item = QueueItem("boot-$index", "https://example.test/boot-$index", "Boot", "QA", MediaSource.YouTube)
                val id = repo.enqueueDownload(item, false)
                db.downloadJobDao().updateProgress(id, status, 0, null, status, index.toLong())
            }
            assertEquals(6, db.downloadJobDao().pendingCount())
            db.downloadJobDao().resetInterrupted(100)
            assertEquals(6, db.downloadJobDao().pendingCount())
            assertEquals(6, db.downloadJobDao().observeAll().first().count { it.status == "QUEUED" })
            assertEquals(1, db.downloadJobDao().observeAll().first().count { it.status == "PAUSED" })
        } finally { db.close() }
    }

    @Test fun positivePaidStatusSurvivesAnOlderScanSnapshot() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, HarvesterDatabase::class.java).build()
        try {
            val channel = com.liberivixer.youtubeharvester.model.ChannelItem("audit", "https://youtube.com/@audit", "Audit", "@audit")
            db.channelDao().insert(channel.toEntity(0))
            db.channelDao().updatePaidContent(channel.id, "MembersOnly")
            db.channelDao().updateScanResult(channel.id, channel.name, channel.handle, null, "Unknown", "checked", 1)
            assertEquals("MembersOnly", db.channelDao().observeAll().first().single().paidContent)
        } finally { db.close() }
    }

    @Test fun legacyDownloadsAreSharedThroughRestrictedContentProvider() {
        if (Build.VERSION.SDK_INT > 28) return
        androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().uiAutomation
            .grantRuntimePermission(context.packageName, android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
        @Suppress("DEPRECATION")
        val directory = File(android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOWNLOADS), "YTH")
        directory.mkdirs()
        val file = File.createTempFile("yth-access-", ".txt", directory)
        try {
            file.writeText("test")
            val uri = com.liberivixer.youtubeharvester.download.shareableArchiveUri(context, file.toURI().toString().toUri())
            assertEquals("content", uri.scheme)
            assertEquals("test", context.contentResolver.openInputStream(uri)!!.bufferedReader().use { it.readText() })
        } finally { file.delete() }
    }

    @Test fun lastCheckReportSurvivesStoreRecreationAndSettingsSave() = runBlocking {
        val testFile = File(context.cacheDir, "report-test-${java.util.UUID.randomUUID()}.preferences_pb")
        val testScope = kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.SupervisorJob() + kotlinx.coroutines.Dispatchers.IO)
        val preferences = androidx.datastore.preferences.core.PreferenceDataStoreFactory.create(
            scope = testScope, produceFile = { testFile })
        try {
            val store = com.liberivixer.youtubeharvester.data.SettingsDataStore(context, preferences)
            val settings = store.settings.first()
            val report = com.liberivixer.youtubeharvester.model.CheckReport(1_234L,
                com.liberivixer.youtubeharvester.model.CheckOutcome.STOPPED, 2, 5, 3, 4,
                com.liberivixer.youtubeharvester.model.overviewContentTypes.associateWith {
                    com.liberivixer.youtubeharvester.model.SectionResult(7, com.liberivixer.youtubeharvester.model.SectionStatus.CHECKED)
                }, 6)
            store.saveCheckReport(report)
            store.save(settings)
            val restored = com.liberivixer.youtubeharvester.data.SettingsDataStore(context, preferences)
            assertEquals(report, restored.lastCheck.first())
            assertEquals(settings, restored.settings.first())
        } finally {
            testScope.coroutineContext[kotlinx.coroutines.Job]!!.cancelAndJoin()
            testFile.delete()
        }
    }

    @Test fun channelDiscoveriesStayOutsideQuickQueueAndLegacyEntriesArePreserved() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, HarvesterDatabase::class.java).build()
        try {
            val repo = AndroidAppRepository(context, db)
            val quick = QueueItem("quick-id", "https://example.test/quick", "Quick", "Channel", MediaSource.YouTube)
            val legacy = quick.copy(id = "legacy-id", originChannelId = "channel")
            db.queueDao().upsert(quick.toEntity(0))
            db.queueDao().upsert(legacy.toEntity(1))
            repo.migrateDiscoveredQueue()
            repo.migrateDiscoveredQueue()
            assertEquals(listOf("quick-id"), repo.quickQueueSnapshot().map { it.id })
            val saved = db.downloadJobDao().findActiveJobId("YouTube", "legacy-id", legacy.resolution, "[]", "[]")!!
            assertEquals("PAUSED", db.downloadJobDao().get(saved)!!.status)
            assertFalse(db.downloadJobDao().get(saved)!!.fromQueue)
            val discovered = quick.copy(id = "channel-video", originChannelId = "channel")
            val jobId = repo.enqueueChannelDownload(discovered)!!
            assertFalse(db.downloadJobDao().get(jobId)!!.fromQueue)
            assertEquals(1, db.queueDao().count())
            assertNull(repo.enqueueChannelDownload(quick.copy(originChannelId = "channel")))
            assertNull(repo.enqueueChannelDownload(legacy))
        } finally { db.close() }
    }

    @Test fun directQuickDownloadHasPriorityWithoutReplacingRunningJobs() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, HarvesterDatabase::class.java).build()
        try {
            val item = QueueItem("priority", "https://example.test/video", "Test", "Channel", MediaSource.YouTube)
            val dao = db.downloadJobDao()
            dao.upsert(item.copy(originChannelId = "channel").toDownloadJobEntity("channel-job", false, 1))
            dao.upsert(item.toDownloadJobEntity("quick-job", false, 2))
            assertEquals("quick-job", dao.claimNext(3)!!.jobId)
            assertEquals("INITIALIZING", dao.get("quick-job")!!.status)
            assertEquals("QUEUED", dao.get("channel-job")!!.status)
        } finally { db.close() }
    }

    @Test fun onlyOneConcurrentConsumerCanClaimAJob() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, HarvesterDatabase::class.java).build()
        try {
            val item = QueueItem("test-id", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "Test", "Channel", MediaSource.YouTube)
            val job = item.toDownloadJobEntity("test-job", false, 1)
            db.downloadJobDao().upsert(job)
            db.queueDao().upsert(item.toEntity(0))
            db.queueDao().updateFromJob(job, "PUBLISHING")
            assertEquals("QUEUED", db.queueDao().getAll().single().status)
            db.queueDao().updateFromJob(job.copy(fromQueue = true), "DOWNLOADING")
            assertEquals("DOWNLOADING", db.queueDao().getAll().single().status)
            val claims = coroutineScope { (1..8).map { async { db.downloadJobDao().claimNext(2) } }.awaitAll() }
            assertEquals(1, claims.count { it != null })
            assertEquals(0, db.downloadJobDao().cancelQueued("test-job", 3))
            assertEquals(0, db.downloadJobDao().markTimedOut("test-job", 1, "expired", 4))
            assertEquals("INITIALIZING", db.downloadJobDao().get("test-job")!!.status)
            db.downloadJobDao().recordPublication("test-job", "content://test/output")
            assertEquals(1, db.downloadJobDao().unfinishedPublications().size)
            db.downloadJobDao().markFailed("test-job", "FAILED", "failure", 2)
            db.downloadJobDao().deleteTerminalBefore(100)
            assertNotNull(db.downloadJobDao().get("test-job"))
            db.downloadJobDao().markCompleted("test-job", "content://test/output", "COMPLETED", 3)
            assertTrue(db.downloadJobDao().unfinishedPublications().isEmpty())
        } finally { db.close() }
    }

    @Test fun keystoreEncryptsAndAuthenticatesEachField() {
        val cipher = SecretCipher()
        val encrypted = cipher.encrypt("test-secret", "token")
        assertFalse(encrypted.contains("test-secret"))
        assertNotEquals(encrypted, cipher.encrypt("test-secret", "token"))
        assertEquals("test-secret", SecretCipher().decrypt(encrypted, "token"))
        assertTrue(runCatching { cipher.decrypt(encrypted, "proxy") }.isFailure)
    }

    @Test fun pauseResumeAndNetworkRetryAreDurableAndConditional() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, HarvesterDatabase::class.java).build()
        try {
            val item = QueueItem("resume-id", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "Test", "Channel", MediaSource.YouTube)
            val dao = db.downloadJobDao()
            dao.upsert(item.toDownloadJobEntity("resume-job", true, 1))
            assertEquals(1, dao.pauseQueued("resume-job", 2))
            assertNull(dao.claimNext(3))
            dao.resetInterrupted(4)
            assertEquals("PAUSED", dao.get("resume-job")!!.status)
            assertEquals(1, dao.resume("resume-job", 5))
            assertNotNull(dao.claimNext(6))
            assertEquals(0, dao.pauseQueued("resume-job", 7))
            dao.updateProgress("resume-job", "DOWNLOADING", 42, null, "", 8)
            repeat(3) { assertEquals(1, dao.scheduleRetry("resume-job", 3, 9L + it)) }
            assertEquals(0, dao.scheduleRetry("resume-job", 3, 12))
            dao.resetInterrupted(13)
            assertEquals(3, dao.get("resume-job")!!.retryCount)
            assertEquals(42, dao.get("resume-job")!!.progress)
            dao.markFailed("resume-job", "FAILED", "Network", 14)
            dao.recordPublication("resume-job", "content://test/unfinished")
            assertEquals(0, dao.resume("resume-job", 15))
            dao.recordPublication("resume-job", null)
            assertEquals(1, dao.resume("resume-job", 16))
            assertEquals(0, dao.get("resume-job")!!.retryCount)
            assertEquals(42, dao.get("resume-job")!!.progress)
            dao.updateProgress("resume-job", "PROCESSING", 99, null, "", 17)
            assertEquals(0, dao.pause("resume-job", 18))
            dao.markCompleted("resume-job", "content://test/done", "COMPLETED", 19)
            assertEquals(0, dao.resume("resume-job", 20))
        } finally { db.close() }
    }

    @Test fun mediaStorePublicationRecordsUriBeforeWritingAndClearsPending() = runBlocking {
        assumeTrue(Build.VERSION.SDK_INT >= 29)
        val file = File.createTempFile("yth-test", ".mp4", context.cacheDir)
        val bytes = ByteArray(100_000) { 7 }
        file.writeBytes(bytes)
        var journal: String? = null
        val publisher = DownloadOutputPublisher(context)
        try {
            val fileName = "${file.nameWithoutExtension} [240p].mp4"
            val uri = publisher.publish(file, fileName = fileName, onCreated = { journal = it })
            assertEquals(uri, journal)
            val directory = DownloadFolderNavigator.directoryUri(context, null, uri)
            assertEquals("primary:Download/YTH", DocumentsContract.getDocumentId(directory!!))
            context.contentResolver.openInputStream(uri.toUri())!!.use { assertArrayEquals(bytes, it.readBytes()) }
            context.contentResolver.query(uri.toUri(), arrayOf(MediaStore.MediaColumns.IS_PENDING, MediaStore.MediaColumns.DISPLAY_NAME), null, null, null)!!.use {
                assertTrue(it.moveToFirst())
                assertEquals(0, it.getInt(0))
                assertEquals(fileName, it.getString(1))
            }
            assertTrue(file.isFile)
        } finally { journal?.let(publisher::deletePublished); file.delete() }
    }

    @Test fun archiveAvailabilityDetectsDeletedMediaStoreFile(): Unit = runBlocking {
        assumeTrue(Build.VERSION.SDK_INT >= 29)
        val file = File.createTempFile("yth-availability", ".mp4", context.cacheDir).apply { writeText("test") }
        val publisher = DownloadOutputPublisher(context)
        var uri: String? = null
        try {
            uri = publisher.publish(file)
            assertEquals(true, archiveUriExists(context, uri))
            assertEquals(1, context.contentResolver.delete(uri.toUri(), null, null))
            assertEquals(false, archiveUriExists(context, uri))
        } finally { uri?.let(publisher::deletePublished); file.delete() }
    }

    @Test fun archiveAvailabilityHandlesLegacyFilesAndEmptyUris() {
        val file = File.createTempFile("yth-availability", ".mp4", context.cacheDir)
        try {
            val uri = android.net.Uri.fromFile(file).toString()
            assertEquals(true, archiveUriExists(context, uri))
            assertTrue(file.delete())
            assertEquals(false, archiveUriExists(context, uri))
            assertEquals(false, archiveUriExists(context, null))
            assertEquals(false, archiveUriExists(context, " "))
        } finally { file.delete() }
    }

    @Test fun publicationRejectsPathsAsDisplayNames(): Unit = runBlocking {
        val file = File.createTempFile("yth-test", ".mp4", context.cacheDir).apply { writeText("test") }
        try {
            for (name in listOf("../outside.mp4", "/tmp/outside.mp4", "nested/file.mp4", ".", "..", "")) {
                val result = runCatching { DownloadOutputPublisher(context).publish(file, fileName = name) }
                assertTrue(result.exceptionOrNull() is IllegalArgumentException)
            }
        } finally { file.delete() }
    }

    @Test fun rejectedJournalRollsBackMediaStoreRow(): Unit = runBlocking {
        assumeTrue(Build.VERSION.SDK_INT >= 29)
        val file = File.createTempFile("yth-test", ".mp4", context.cacheDir).apply { writeText("test") }
        var uri: String? = null
        try {
            assertTrue(runCatching { DownloadOutputPublisher(context).publish(file, onCreated = {
                uri = it
                error("Simulated database failure")
            }) }.isFailure)
            context.contentResolver.query(uri!!.toUri(), arrayOf(MediaStore.MediaColumns._ID), null, null, null)?.use {
                assertFalse(it.moveToFirst())
            }
        } finally { file.delete() }
    }

    @Test fun archiveFolderUsesOriginalTreeInsteadOfCurrentSettings() {
        val current = "content://com.android.externalstorage.documents/tree/primary%3ADownload%2FNew"
        val archived = "content://com.android.externalstorage.documents/tree/primary%3AMovies%2FOld/document/primary%3AMovies%2FOld%2Fvideo.mp4"
        val directory = DownloadFolderNavigator.directoryUri(context, current, archived)
        assertEquals("primary:Movies/Old", DocumentsContract.getDocumentId(directory!!))
        val selected = DownloadFolderNavigator.directoryUri(context, current, null)
        assertEquals("primary:Download/New", DocumentsContract.getDocumentId(selected!!))
    }

    @Test fun bundledRuntimeInitializesWithoutNetwork() {
        AndroidYtDlpRuntime.ensure(context, requireFfmpeg = true)
        val version = YoutubeDL.execute(com.yausername.youtubedl_android.YoutubeDLRequest(listOf("--version"))).out.trim()
        assertEquals(BuildConfig.YTDLP_VERSION, version)
        listOf("libffmpeg.so", "libffprobe.so", "libqjs.so").forEach {
            assertTrue(it, File(context.applicationInfo.nativeLibraryDir, it).exists())
        }
        for (name in listOf("ffmpeg", "ffprobe")) {
            val output = File.createTempFile("yth-native-", ".txt", context.cacheDir)
            val builder = ProcessBuilder(File(context.applicationInfo.nativeLibraryDir, "lib$name.so").absolutePath, "-version")
                .redirectErrorStream(true).redirectOutput(output)
            val runtime = File(context.noBackupFilesDir, "youtubedl-android/packages")
            builder.environment()["LD_LIBRARY_PATH"] = listOf(
                File(runtime, "ffmpeg/usr/lib").absolutePath,
                File(runtime, "python/usr/lib").absolutePath,
                context.applicationInfo.nativeLibraryDir).joinToString(":")
            val process = builder.start()
            try {
                assertTrue(process.waitFor(30, java.util.concurrent.TimeUnit.SECONDS))
                assertEquals(output.readText(), 0, process.exitValue())
                assertTrue(output.readText().contains("$name version"))
            } finally { process.destroyForcibly(); output.delete() }
        }
    }
}
