package com.liberivixer.youtubeharvester.download

import android.content.Context
import com.liberivixer.youtubeharvester.data.AndroidAppRepository
import com.liberivixer.youtubeharvester.media.ChannelCheckProgress
import com.liberivixer.youtubeharvester.media.ChannelCheckRunner
import com.liberivixer.youtubeharvester.media.ChannelCheckSummary
import com.liberivixer.youtubeharvester.model.AppSettings
import com.liberivixer.youtubeharvester.model.ChannelItem
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.DownloadStatus
import com.liberivixer.youtubeharvester.model.QueueItem
import com.liberivixer.youtubeharvester.model.CheckReport
import com.liberivixer.youtubeharvester.model.CheckOutcome
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

enum class HarvestPhase { QUEUE_BEFORE, CHANNELS, QUEUE_AFTER }

data class HarvestProgress(
    val phase: HarvestPhase,
    val channel: ChannelCheckProgress? = null,
    val downloaded: Map<ContentType, Int> = emptyMap(),
    val errors: Int = 0,
)

data class HarvestSummary(val channels: ChannelCheckSummary, val downloaded: Map<ContentType, Int>, val errors: Int)

internal interface HarvestDownloads {
    suspend fun queue(): List<QueueItem>
    suspend fun enqueue(item: QueueItem, fromQueue: Boolean): String?
    suspend fun await(jobId: String): DownloadStatus
    suspend fun cancel(jobId: String)
}

class HarvestCycleRunner internal constructor(
    private val downloads: HarvestDownloads,
    private val saveReport: suspend (CheckReport) -> Unit = {},
    private val scan: suspend (List<ChannelItem>, AppSettings, suspend (List<QueueItem>) -> Int, (ChannelCheckProgress) -> Unit) -> ChannelCheckSummary,
) {
    constructor(context: Context, repository: AndroidAppRepository, sessionId: String? = null) : this(
        object : HarvestDownloads {
            override suspend fun queue() = repository.quickQueueSnapshot()
            override suspend fun enqueue(item: QueueItem, fromQueue: Boolean): String? {
                val durableId = sessionId?.let { java.util.UUID.nameUUIDFromBytes("$it:${item.source.name}:${item.id}".toByteArray()).toString() }
                val id = if (fromQueue) repository.enqueueDownload(item, true, durableId) else repository.enqueueChannelDownload(item, durableId)
                if (id != null) DownloadServiceController.start(context)
                return id
            }
            override suspend fun await(jobId: String): DownloadStatus {
                // A pause holds the cycle at this video until the user resumes or cancels it.
                return repository.downloadJobs.first { jobs ->
                    jobs.none { it.jobId == jobId && (it.status.isActive || it.status == DownloadStatus.PAUSED) }
                }.firstOrNull { it.jobId == jobId }?.status ?: DownloadStatus.CANCELLED
            }
            override suspend fun cancel(jobId: String) {
                if (repository.downloadJob(jobId)?.status?.retainsFiles == true) DownloadServiceController.cancel(context, jobId)
            }
        },
        repository::saveCheckReport,
        { channels, settings, discovered, progress ->
            ChannelCheckRunner(context, repository).run(channels, settings, checkPaidContent = false,
                sectionResultDelayMs = 1_000, onDiscovered = discovered, onProgress = progress)
        },
    )

    suspend fun run(
        channels: List<ChannelItem>, settings: AppSettings,
        checkpoint: HarvestCheckpoint = HarvestCheckpoint(),
        saveCheckpoint: suspend (HarvestCheckpoint) -> Unit = {},
        cancelOnInterruption: Boolean = true,
        onProgress: (HarvestProgress) -> Unit = {},
    ): HarvestSummary = cycleMutex.withLock {
        val attempted = checkpoint.attempted.toMutableSet()
        val counts = checkpoint.downloaded.toMutableMap()
        var errors = checkpoint.downloadErrors
        var phase = checkpoint.phase
        var checked = checkpoint.completedChannels
        var scanErrors = checkpoint.scanErrors
        var sections = checkpoint.sections
        var channelProgress: ChannelCheckProgress? = null
        var pending = checkpoint.pending
        fun report() = onProgress(HarvestProgress(phase, channelProgress, counts.toMap(), errors + scanErrors))
        suspend fun persist() = saveCheckpoint(HarvestCheckpoint(phase, checked, scanErrors, errors,
            counts.toMap(), attempted.toSet(), pending, sections))
        suspend fun finish(outcome: CheckOutcome) {
            saveReport(CheckReport(System.currentTimeMillis(), outcome, checked, channels.size,
                errors + scanErrors, counts.values.sum(), sections, attempted.size + if (pending == null) 0 else 1))
        }

        suspend fun finishPending() {
            val item = pending ?: return
            val result = downloads.await(item.jobId)
            if (result == DownloadStatus.COMPLETED) counts[item.type] = (counts[item.type] ?: 0) + 1
            if (result == DownloadStatus.FAILED) errors++
            attempted.add(item.key)
            pending = null
            persist()
            report()
        }

        suspend fun download(item: QueueItem, fromQueue: Boolean): Boolean {
            currentCoroutineContext().ensureActive()
            val key = "${item.source.name}:${item.id}"
            if (key in attempted) return false
            withContext(NonCancellable) {
                downloads.enqueue(item, fromQueue)?.also {
                    pending = PendingHarvestDownload(key, it, item.contentType)
                    persist()
                }
            } ?: return false
            currentCoroutineContext().ensureActive()
            finishPending()
            return true
        }

        suspend fun drainQueue() {
            // Re-read after each batch to include links added while the pass is running.
            while (true) {
                val pending = downloads.queue().filter { "${it.source.name}:${it.id}" !in attempted }
                if (pending.isEmpty()) return
                for (item in pending) download(item, true)
            }
        }

        try {
            report()
            finishPending()
            if (phase == HarvestPhase.QUEUE_BEFORE) {
                drainQueue()
                phase = HarvestPhase.CHANNELS
                persist()
            }
            suspend fun scanBatch(batch: List<ChannelItem>) {
                val base = checked
                val summary = scan(batch, settings, { items ->
                    var handled = 0
                    for (item in items) if (download(item, false)) handled++
                    handled
                }, {
                    channelProgress = it.copy(completedChannels = base + it.completedChannels, totalChannels = channels.size)
                    sections = it.sections
                    report()
                })
                checked += summary.completedChannels
                scanErrors += summary.errors
                persist()
            }
            if (phase == HarvestPhase.CHANNELS) {
                report()
                // Commit a cursor after each channel; stable job IDs cover interrupted publications.
                if (channels.isEmpty()) scanBatch(emptyList())
                else for (channel in channels.drop(checked)) scanBatch(listOf(channel))
                phase = HarvestPhase.QUEUE_AFTER
                persist()
            }
            channelProgress = null
            report()
            drainQueue()
            finish(CheckOutcome.COMPLETED)
            HarvestSummary(ChannelCheckSummary(checked, attempted.size, 0, errors = scanErrors), counts.toMap(), errors + scanErrors)
        } catch (error: CancellationException) {
            if (cancelOnInterruption) withContext(NonCancellable) {
                try { pending?.let { downloads.cancel(it.jobId) } }
                finally { finish(CheckOutcome.STOPPED) }
            }
            throw error
        } catch (error: Exception) {
            errors++
            if (cancelOnInterruption) finish(CheckOutcome.FAILED)
            throw error
        }
    }

    companion object { private val cycleMutex = Mutex() }
}
