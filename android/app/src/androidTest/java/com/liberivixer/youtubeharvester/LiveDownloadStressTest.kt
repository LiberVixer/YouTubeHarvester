package com.liberivixer.youtubeharvester

import android.content.Context
import android.util.Log
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.work.Data
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.liberivixer.youtubeharvester.data.AndroidAppRepository
import com.liberivixer.youtubeharvester.data.db.HarvesterDatabase
import com.liberivixer.youtubeharvester.download.DownloadServiceController
import com.liberivixer.youtubeharvester.download.HarvestCoordinator
import com.liberivixer.youtubeharvester.download.HarvestSessionStore
import com.liberivixer.youtubeharvester.model.ChannelItem
import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.model.QueueItem
import com.liberivixer.youtubeharvester.model.ScheduleItem
import com.liberivixer.youtubeharvester.scheduler.ChannelCheckWorker
import com.liberivixer.youtubeharvester.scheduler.DailyCheckScheduler
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

class LiveDownloadStressTest {
    @get:Rule val activity = ActivityScenarioRule(MainActivity::class.java)
    private val context: Context = ApplicationProvider.getApplicationContext()
    private val repo = AndroidAppRepository(context)
    private val db = HarvesterDatabase.getInstance(context)
    private val jobs = mutableListOf<String>()
    private val evidence = File(context.getExternalFilesDir(null), "live-stress.txt")

    @Test fun optedInLiveScenarios() = runBlocking {
        val mode = InstrumentationRegistry.getArguments().getString("liveStress")
        assumeTrue("Live downloads require explicit liveStress opt-in", mode != null)
        assertEquals("com.liberivixer.youtubeharvester.debug", context.packageName)
        repo.initialize()
        assertEquals(0, db.downloadJobDao().pendingCount())
        assertTrue(db.queueDao().getAll().isEmpty())
        assertTrue(repo.channels.first().isEmpty())
        assertNull(HarvestSessionStore(context).current())
        evidence.writeText("mode=$mode\n")
        record("baseline")
        try {
            when (mode) {
                "cancel" -> cancellationCycles()
                "errors" -> sourceErrors()
                "queue" -> queuedBatch()
                "soak" -> repeat(5) { queuedBatch(); record("soak-batch=$it") }
                "catalog" -> largeQueue()
                "overlap" -> overlappingHarvest()
                "boot" -> prepareReboot()
                "resume" -> resumeAfterReboot()
                else -> error("Unknown liveStress mode")
            }
            record("finished")
        } finally {
            if (mode != "boot") {
                jobs.forEach { id ->
                    if (db.downloadJobDao().get(id)?.status !in listOf("COMPLETED", "CANCELLED")) {
                        DownloadServiceController.cancel(context, id)
                        await(id, setOf("COMPLETED", "CANCELLED"), 30)
                    }
                }
                assertEquals(0, db.downloadJobDao().pendingCount())
            }
        }
    }

    private fun item(id: String, resolution: String = "240p") = QueueItem(
        id, "https://www.youtube.com/watch?v=$id", "QA $id", "Live QA",
        MediaSource.YouTube, resolution = resolution)

    private suspend fun start(item: QueueItem, fromQueue: Boolean = false): String {
        val id = repo.enqueueDownload(item, fromQueue)
        jobs += id
        DownloadServiceController.start(context)
        return id
    }

    private suspend fun await(id: String, statuses: Set<String>, seconds: Int = 180): String {
        repeat(seconds * 4) {
            val job = db.downloadJobDao().get(id) ?: error("Missing job $id")
            if (job.status in statuses) {
                if (job.status == "FAILED") probeNetwork()
                if (job.status in setOf("COMPLETED", "CANCELLED")) {
                    until(10) { !staging(id).exists() }
                }
                record("job=$id status=${job.status} progress=${job.progress} retries=${job.retryCount} error=${job.errorMessage}")
                return job.status
            }
            if (job.status == "FAILED" && "CANCELLED" !in statuses) {
                probeNetwork()
                error("Unexpected source failure: ${job.errorMessage}")
            }
            delay(250)
        }
        error("Timeout job=$id state=${db.downloadJobDao().get(id)}")
    }

    private fun staging(id: String) = File(context.getExternalFilesDir(android.os.Environment.DIRECTORY_DOWNLOADS), "staging/$id")

    private suspend fun cancellationCycles() {
        repeat(5) { round ->
            val cancelled = start(item("SVJiCL3K0j4", "480p"))
            assertEquals("DOWNLOADING", await(cancelled, setOf("DOWNLOADING")))
            until(10) { staging(cancelled).walkTopDown().any { it.isFile && it.length() > 0 } }
            assertTrue(staging(cancelled).walkTopDown().any { it.isFile && it.length() > 0 })
            DownloadServiceController.cancel(context, cancelled)
            assertEquals("CANCELLED", await(cancelled, setOf("CANCELLED")))
            assertFalse("Cancelled staging retained", staging(cancelled).exists())
            val completed = start(item("jNQXAC9IVRw"))
            assertEquals("COMPLETED", await(completed, setOf("COMPLETED")))
            assertFalse(staging(completed).exists())
            assertEquals(1, db.archiveDao().observeAll().first().count {
                it.mediaId == "jNQXAC9IVRw" && it.resolution == "240p" && it.variantKey == "default" })
            record("cancel-round=$round")
        }
    }

    private suspend fun sourceErrors() {
        val count = db.downloadJobDao().observeAll().first().size
        for (url in listOf("", "not a URL", "https://example.com/video", "https://youtube.com/watch?v=bad")) {
            assertNull(repo.queueItemFromUrl(url, "240p"))
        }
        assertEquals(count, db.downloadJobDao().observeAll().first().size)
        for (media in listOf("aaaaaaaaaaa", "BaW_jenozKc")) {
            val failed = start(item(media))
            val status = await(failed, setOf("FAILED", "COMPLETED"))
            assertEquals("Expected unavailable QA source $media", "FAILED", status)
            assertNull(db.downloadJobDao().get(failed)!!.fileUri)
            assertFalse(db.archiveDao().containsMedia("YouTube", media))
            DownloadServiceController.cancel(context, failed)
            await(failed, setOf("CANCELLED"))
            val healthy = start(item("jNQXAC9IVRw"))
            assertEquals("COMPLETED", await(healthy, setOf("COMPLETED")))
        }
    }

    private suspend fun queuedBatch() {
        val media = listOf("SVJiCL3K0j4", "jNQXAC9IVRw", "dQw4w9WgXcQ", "aqz-KE-bpKQ", "YE7VzlLtp-4", "ScMzIvxBSi4")
        try {
            media.forEachIndexed { index, id -> repo.upsertQueueItem(item(id), index) }
            assertEquals(media.size, repo.enqueueSelectedDownloads())
            val batch = db.downloadJobDao().observeAll().first().filter { it.status == "QUEUED" && it.fromQueue }
            jobs += batch.map { it.jobId }
            assertEquals(media.size, batch.size)
            assertEquals(0, repo.enqueueSelectedDownloads())
            DownloadServiceController.start(context)
            for (job in batch) assertEquals("COMPLETED", await(job.jobId, setOf("COMPLETED"), 600))
            assertEquals(0, db.queueDao().count())
            batch.forEach { assertFalse(staging(it.jobId).exists()) }
        } finally {
            repo.removeQueueItems(media.map { item(it) })
        }
    }

    private suspend fun overlappingHarvest() {
        val channel = ChannelItem("live-qa-blender", "https://www.youtube.com/channel/UCSMOQeBJ2RAnuFungnQOxLg",
            "Blender QA", "@BlenderOfficial", shortsEnabled = false, streamsEnabled = false)
        val settings = repo.settings.first()
        val schedule = ScheduleItem("live-qa-overlap", 23, 59, true)
        val work = OneTimeWorkRequestBuilder<ChannelCheckWorker>()
            .setInputData(Data.Builder().putString(ChannelCheckWorker.KEY_SCHEDULE_ID, schedule.id).build()).build()
        try {
            repo.saveSettings(settings.copy(videoLimit = 1, maxResolution = "480p"))
            repo.insertChannel(channel)
            repo.upsertSchedule(schedule)
            val direct = start(item("SVJiCL3K0j4", "480p"))
            await(direct, setOf("DOWNLOADING"))
            assertTrue(HarvestCoordinator.start(context))
            assertFalse(HarvestCoordinator.start(context))
            WorkManager.getInstance(context).enqueue(work).result.get()
            until(60) { repo.getSchedule(schedule.id)?.lastRunEpochMs != null }
            assertNotNull(repo.getSchedule(schedule.id)!!.lastRunEpochMs)
            assertEquals("COMPLETED", await(direct, setOf("COMPLETED"), 600))
            until(150) { HarvestSessionStore(context).current() == null }
            assertNull(HarvestSessionStore(context).current())
            assertEquals(1, db.downloadJobDao().observeAll().first().count { it.jobId == direct })
            assertEquals(0, db.downloadJobDao().pendingCount())
        } finally {
            HarvestCoordinator.stop(context)
            WorkManager.getInstance(context).cancelWorkById(work.id).result.get()
            DailyCheckScheduler.cancel(context, schedule.id)
            repo.deleteSchedule(schedule.id)
            repo.deleteChannel(channel.id)
            repo.saveSettings(settings)
        }
    }

    private suspend fun prepareReboot() {
        val paused = start(item("SVJiCL3K0j4", "480p"))
        await(paused, setOf("DOWNLOADING"))
        until(10) { staging(paused).walkTopDown().any { it.isFile && it.length() > 0 } }
        DownloadServiceController.pause(context, paused)
        assertEquals("PAUSED", await(paused, setOf("PAUSED")))
        val pending = listOf(item("dQw4w9WgXcQ"), item("jNQXAC9IVRw"))
            .map { repo.enqueueDownload(it, false).also(jobs::add) }
        record("BOOT_READY paused=$paused pending=${pending.joinToString()}")
        // Leave these durable jobs for the host-side reboot check, without an Activity launch.
    }

    private suspend fun resumeAfterReboot() {
        val id = requireNotNull(InstrumentationRegistry.getArguments().getString("resumeJob"))
        val job = requireNotNull(db.downloadJobDao().get(id))
        assertEquals("SVJiCL3K0j4", job.mediaId)
        assertEquals("PAUSED", job.status)
        jobs += id
        DownloadServiceController.resume(context, id)
        assertEquals("COMPLETED", await(id, setOf("COMPLETED"), 600))
    }

    private suspend fun largeQueue() {
        val items = (0 until 500).map { index ->
            item("qa%09d".format(java.util.Locale.US, index)).copy(
                title = "QA large queue $index with a long title for wrapping and scrolling",
                selected = false)
        }
        try {
            items.forEachIndexed { index, value -> repo.upsertQueueItem(value, index) }
            assertEquals(500, db.queueDao().count())
            assertEquals(0, repo.enqueueSelectedDownloads())
            assertTrue(repo.moveQueueItem(MediaSource.YouTube, items.first().id, 1))
            assertEquals(items[1].id, db.queueDao().getAll().first().mediaId)
            record("LARGE_QUEUE_READY")
            delay(60000)
        } finally { repo.removeQueueItems(items) }
        assertEquals(0, db.queueDao().count())
    }

    private fun probeNetwork() {
        for (url in listOf("https://www.youtube.com/generate_204", "https://www.youtube.com/watch?v=jNQXAC9IVRw")) {
            val result = runCatching {
                val connection = URL(url).openConnection() as HttpURLConnection
                try {
                    connection.connectTimeout = 10000
                    connection.readTimeout = 10000
                    connection.responseCode
                } finally { connection.disconnect() }
            }
            record("source-connectivity $url $result")
        }
    }

    private suspend fun until(seconds: Int, predicate: suspend () -> Boolean) {
        repeat(seconds * 4) {
            if (predicate()) return
            delay(250)
        }
        error("Condition did not become true within $seconds seconds")
    }

    private fun record(message: String) {
        val memory = android.os.Debug.MemoryInfo()
        android.os.Debug.getMemoryInfo(memory)
        val root = File(context.getExternalFilesDir(android.os.Environment.DIRECTORY_DOWNLOADS), "staging")
        val files = root.walkTopDown().filter { it.isFile }.toList()
        val line = "$message pssKb=${memory.totalPss} javaKb=${Runtime.getRuntime().totalMemory() / 1024} stagingFiles=${files.size} stagingBytes=${files.sumOf { it.length() }}"
        evidence.appendText("$line\n")
        Log.i("LiveStress", line)
    }
}
