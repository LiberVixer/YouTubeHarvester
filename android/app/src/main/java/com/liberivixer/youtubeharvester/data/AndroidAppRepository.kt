package com.liberivixer.youtubeharvester.data

import android.content.Context
import androidx.core.content.edit
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.data.db.HarvesterDatabase
import com.liberivixer.youtubeharvester.data.db.toEntity
import com.liberivixer.youtubeharvester.data.db.toDownloadJobEntity
import com.liberivixer.youtubeharvester.data.db.toModel
import com.liberivixer.youtubeharvester.media.MediaUrlParser
import com.liberivixer.youtubeharvester.model.AppSettings
import com.liberivixer.youtubeharvester.model.ArchiveItem
import com.liberivixer.youtubeharvester.model.ChannelItem
import com.liberivixer.youtubeharvester.model.DownloadStatus
import com.liberivixer.youtubeharvester.model.MediaPreview
import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.model.QueueItem
import com.liberivixer.youtubeharvester.model.SelectedAudioTrack
import com.liberivixer.youtubeharvester.model.storedDownloadStatus
import com.liberivixer.youtubeharvester.model.ScheduleItem
import com.liberivixer.youtubeharvester.ui.LocaleController
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import org.json.JSONArray
import java.util.UUID
import androidx.room.withTransaction
import com.liberivixer.youtubeharvester.data.db.MarkedMediaEntity
import com.liberivixer.youtubeharvester.data.db.QueueEntity
import com.liberivixer.youtubeharvester.media.ChannelScanEntry
import com.liberivixer.youtubeharvester.media.ChannelCheckStorage

class AndroidAppRepository(
    context: Context,
    private val database: HarvesterDatabase = HarvesterDatabase.getInstance(context),
) : ChannelCheckStorage {
    private val appContext = context.applicationContext
    private val legacyPreferences = appContext.getSharedPreferences(LEGACY_PREFERENCES, Context.MODE_PRIVATE)
    private val settingsStore = SettingsDataStore(appContext)
    private val queueDao = database.queueDao()
    private val archiveDao = database.archiveDao()
    private val downloadJobDao = database.downloadJobDao()
    private val channelDao = database.channelDao()
    private val scheduleDao = database.scheduleDao()
    private val markedMediaDao = database.markedMediaDao()

    val settings: Flow<AppSettings> = settingsStore.settings
    val lastCheck = settingsStore.lastCheck
    suspend fun saveCheckReport(report: com.liberivixer.youtubeharvester.model.CheckReport) = settingsStore.saveCheckReport(report)
    val queue: Flow<List<QueueItem>> = queueDao.observeAll().map { entities -> entities.map { it.toModel() } }
    val archive: Flow<List<ArchiveItem>> = archiveDao.observeAll().map { entities -> entities.map { it.toModel() } }
    val downloadJobs = downloadJobDao.observeAll().map { entities -> entities.map { it.toModel() } }
    val channels: Flow<List<ChannelItem>> = channelDao.observeAll().map { entities -> entities.map { it.toModel() } }
    val schedules: Flow<List<ScheduleItem>> = scheduleDao.observeAll().map { entities -> entities.map { it.toModel() } }

    suspend fun initialize() {
        settingsStore.migrateLegacy(legacyPreferences)
        DataTransferStore(appContext, database, settingsStore).finishPendingImport()
        migrateLegacyQueue()
        migrateDiscoveredQueue()
        downloadJobDao.deleteTerminalBefore(System.currentTimeMillis() - TERMINAL_JOB_RETENTION_MS)
    }

    suspend fun saveSettings(settings: AppSettings, replaceSecrets: Boolean = false) = settingsStore.save(settings, replaceSecrets)

    suspend fun upsertQueueItem(item: QueueItem, sortOrder: Int) {
        queueDao.upsert(item.toEntity(sortOrder))
    }

    suspend fun setQueueSelected(source: MediaSource, mediaId: String, selected: Boolean) {
        queueDao.setSelected(source.name, mediaId, selected)
    }

    suspend fun removeQueueItems(items: List<QueueItem>) = database.withTransaction {
        items.forEach { queueDao.delete(it.source.name, it.id) }
    }

    suspend fun moveQueueItem(source: MediaSource, mediaId: String, offset: Int): Boolean = database.withTransaction {
        val items = reorderQueueEntities(queueDao.getAll(), source.name, mediaId, offset)
            ?: return@withTransaction false
        queueDao.upsertAll(items)
        true
    }

    suspend fun insertChannel(channel: ChannelItem): Boolean = database.withTransaction {
        channelDao.insert(channel.toEntity(channelDao.count())) != -1L
    }

    suspend fun deleteChannel(id: String) = channelDao.delete(id)

    suspend fun updateChannelContentSelection(channel: ChannelItem) {
        channelDao.updateContentSelection(
            channel.id,
            channel.videosEnabled,
            channel.shortsEnabled,
            channel.streamsEnabled,
        )
    }

    override suspend fun updateChannelScanResult(channel: ChannelItem, checkedAt: Long, status: String) {
        channelDao.updateScanResult(
            id = channel.id,
            name = channel.name,
            handle = channel.handle,
            thumbnailUrl = channel.thumbnailUrl,
            paidContent = channel.paidContent.name,
            status = status,
            lastCheckedEpochMs = checkedAt,
        )
    }

    suspend fun getSchedules(): List<ScheduleItem> = scheduleDao.getAll().map { it.toModel() }

    suspend fun getSchedule(id: String): ScheduleItem? = scheduleDao.get(id)?.toModel()

    suspend fun upsertSchedule(item: ScheduleItem) = scheduleDao.upsert(item.toEntity())

    suspend fun setScheduleEnabled(id: String, enabled: Boolean) = scheduleDao.setEnabled(id, enabled)

    suspend fun markScheduleRun(id: String, lastRunEpochMs: Long) = scheduleDao.markRun(id, lastRunEpochMs)

    suspend fun deleteSchedule(id: String) = scheduleDao.delete(id)

    override suspend fun markDiscoveredItems(items: List<ChannelScanEntry>): Int = database.withTransaction {
        check(downloadJobDao.pendingCount() == 0) { localizedText(R.string.channel_mark_stop_downloads) }
        var added = 0
        for (item in items.distinctBy { it.source to it.mediaId }) {
            if (markedMediaDao.insert(MarkedMediaEntity(item.source.name, item.mediaId, System.currentTimeMillis())) != -1L) added += 1
            queueDao.deleteDiscovered(item.source.name, item.mediaId)
        }
        added
    }

    internal suspend fun migrateDiscoveredQueue() = database.withTransaction {
        for (old in queueDao.getAll().filter { it.originChannelId != null }) {
            val job = old.toModel().toDownloadJobEntity(UUID.randomUUID().toString(), false, System.currentTimeMillis())
            if (!archiveDao.containsMedia(old.source, old.mediaId) &&
                downloadJobDao.findActiveJobId(old.source, old.mediaId, old.resolution, old.audioJson, old.subtitlesJson) == null) {
                downloadJobDao.upsert(job.copy(status = DownloadStatus.PAUSED.name, message = DownloadStatus.PAUSED.name))
            }
            queueDao.deleteDiscovered(old.source, old.mediaId)
        }
    }

    suspend fun quickQueueSnapshot(): List<QueueItem> = queueDao.getSelected()
        .filter { it.originChannelId == null }.map { it.toModel() }

    suspend fun enqueueChannelDownload(item: QueueItem, durableId: String? = null): String? = database.withTransaction {
        if (durableId != null && downloadJobDao.get(durableId) != null) return@withTransaction durableId
        if (archiveDao.containsMedia(item.source.name, item.id) || markedMediaDao.contains(item.source.name, item.id)) return@withTransaction null
        // A manually queued link retains its selected format and is handled in the queue pass.
        if (queueDao.getAll().any { it.source == item.source.name && it.mediaId == item.id }) return@withTransaction null
        val candidate = item.toDownloadJobEntity("candidate", false, 0)
        val id = downloadJobDao.findActiveJobId(item.source.name, item.id, item.resolution, candidate.audioJson, candidate.subtitlesJson)
        if (id != null && downloadJobDao.get(id)?.status == DownloadStatus.PAUSED.name) return@withTransaction null
        enqueueDownload(item, fromQueue = false, durableId = durableId)
    }

    suspend fun downloadJob(jobId: String) = downloadJobDao.get(jobId)?.toModel()

    suspend fun enqueueDownload(item: QueueItem, fromQueue: Boolean, durableId: String? = null): String = database.withTransaction {
        if (durableId != null && downloadJobDao.get(durableId) != null) return@withTransaction durableId
        val now = System.currentTimeMillis()
        val jobId = durableId ?: UUID.randomUUID().toString()
        val entity = item.toDownloadJobEntity(jobId, fromQueue, now)
        val existing = downloadJobDao.findActiveJobId(
            item.source.name,
            item.id,
            item.resolution,
            entity.audioJson,
            entity.subtitlesJson,
        )
        if (existing != null) {
            if (downloadJobDao.resume(existing, now) == 1) {
                downloadJobDao.get(existing)?.let { queueDao.updateFromJob(it, DownloadStatus.QUEUED.name) }
            }
            return@withTransaction existing
        }
        downloadJobDao.upsert(entity)
        if (fromQueue) queueDao.setStatus(item.source.name, item.id, DownloadStatus.QUEUED.name)
        jobId
    }

    suspend fun enqueueSelectedDownloads(): Int = database.withTransaction {
        var added = 0
        queueDao.getSelected().map { it.toModel() }.forEach { item ->
            val candidate = item.toDownloadJobEntity("candidate", fromQueue = true, now = 0L)
            val existing = downloadJobDao.findActiveJobId(
                item.source.name,
                item.id,
                item.resolution,
                candidate.audioJson,
                candidate.subtitlesJson,
            )
            if (existing == null || downloadJobDao.get(existing)?.toModel()?.status?.isResumable == true) {
                enqueueDownload(item, fromQueue = true)
                added += 1
            }
        }
        added
    }

    suspend fun hasPendingDownloads(): Boolean = downloadJobDao.pendingCount() > 0

    suspend fun canDeleteTemporaryFiles(jobId: String): Boolean = downloadJobDao.get(jobId)?.toModel()?.status?.retainsFiles != true

    suspend fun resumeDownload(jobId: String): Boolean = database.withTransaction {
        val job = downloadJobDao.get(jobId) ?: return@withTransaction false
        val existing = downloadJobDao.findActiveJobId(job.source, job.mediaId, job.resolution, job.audioJson, job.subtitlesJson)
        if (existing != null && existing != jobId) return@withTransaction false
        if (downloadJobDao.resume(jobId, System.currentTimeMillis()) != 1) return@withTransaction false
        queueDao.updateFromJob(job, DownloadStatus.QUEUED.name)
        true
    }

    suspend fun upsertArchiveItem(item: ArchiveItem, downloadedAtEpochMs: Long, fileUri: String? = null) {
        archiveDao.upsert(item.toEntity(downloadedAtEpochMs, fileUri))
    }

    suspend fun setArchiveFileExists(item: ArchiveItem, fileExists: Boolean) {
        archiveDao.setFileExists(item.source.name, item.id, item.resolution, item.variantKey, fileExists)
    }

    suspend fun relinkImportedArchive(settings: AppSettings) = ArchiveTransferFiles(appContext).relink(database, settings)

    suspend fun deleteArchiveItem(item: ArchiveItem) = database.withTransaction {
        archiveDao.delete(item.source.name, item.id, item.resolution, item.variantKey)
        database.archiveRelinkDao().delete(item.source.name, item.id, item.resolution, item.variantKey)
    }

    fun queueItemFromUrl(
        rawUrl: String,
        resolution: String,
        preview: MediaPreview? = null,
        audioTracks: List<SelectedAudioTrack> = emptyList(),
        subtitleSelections: List<String> = emptyList(),
    ): QueueItem? {
        val parsed = MediaUrlParser.parse(rawUrl) ?: return null
        val matchingPreview = preview?.takeIf {
            it.source == parsed.source && it.mediaId == parsed.mediaId
        }
        val fallbackTitle = when (parsed.source) {
            MediaSource.YouTube -> localizedText(R.string.fallback_video_title, "YouTube", parsed.mediaId)
            MediaSource.Vk -> localizedText(R.string.fallback_video_title, "VK", parsed.mediaId)
            MediaSource.Rutube -> localizedText(R.string.fallback_video_title, "Rutube", parsed.mediaId.take(12))
        }
        return QueueItem(
            id = parsed.mediaId,
            url = matchingPreview?.normalizedUrl ?: parsed.normalizedUrl,
            title = matchingPreview?.title ?: fallbackTitle,
            channel = matchingPreview?.channel ?: localizedText(R.string.metadata_pending),
            source = parsed.source,
            thumbnailUrl = matchingPreview?.thumbnailUrl,
            resolution = resolution,
            audioTracks = audioTracks,
            subtitleSelections = subtitleSelections,
        )
    }

    private suspend fun migrateLegacyQueue() {
        if (legacyPreferences.getBoolean(ROOM_QUEUE_MIGRATED, false)) return
        if (queueDao.count() == 0) {
            val legacyQueue = parseLegacyQueue(legacyPreferences.getString("queue_json", null))
            if (legacyQueue.isNotEmpty()) {
                queueDao.upsertAll(legacyQueue.mapIndexed { index, item -> item.toEntity(index) })
            }
        }
        legacyPreferences.edit(commit = true) { putBoolean(ROOM_QUEUE_MIGRATED, true) }
    }

    private fun localizedText(resourceId: Int, vararg arguments: Any): String =
        LocaleController.wrap(appContext).getString(resourceId, *arguments)

    private companion object {
        const val LEGACY_PREFERENCES = "yth_android"
        const val ROOM_QUEUE_MIGRATED = "room_queue_migrated"
        const val TERMINAL_JOB_RETENTION_MS = 30L * 24 * 60 * 60 * 1_000
    }
}

internal fun reorderQueueEntities(
    items: List<QueueEntity>,
    source: String,
    mediaId: String,
    offset: Int,
): List<QueueEntity>? {
    val reordered = items.toMutableList()
    val currentIndex = reordered.indexOfFirst { it.source == source && it.mediaId == mediaId }
    val targetIndex = currentIndex + offset
    if (currentIndex < 0 || targetIndex !in reordered.indices) return null
    reordered.add(targetIndex, reordered.removeAt(currentIndex))
    return reordered.mapIndexed { index, item -> item.copy(sortOrder = index) }
}

internal fun parseLegacyQueue(raw: String?): List<QueueItem> {
    if (raw.isNullOrBlank()) return emptyList()
    return runCatching {
        val items = JSONArray(raw)
        buildList {
            repeat(items.length()) { index ->
                val item = items.getJSONObject(index)
                val source = MediaSource.entries.firstOrNull { it.name == item.optString("source") }
                    ?: return@repeat
                val id = item.optString("id").trim()
                val url = item.optString("url").trim()
                if (id.isBlank() || url.isBlank()) return@repeat
                add(
                    QueueItem(
                        id = id,
                        url = url,
                        title = item.optString("title").trim().ifBlank { "Video $id" },
                        channel = item.optString("channel").trim().ifBlank { source.label },
                        source = source,
                        thumbnailUrl = item.optString("thumbnail_url").ifBlank { null },
                        resolution = item.optString("resolution", "1080p"),
                        selected = item.optBoolean("selected", true),
                        status = storedDownloadStatus(item.optString("status"))?.name ?: DownloadStatus.QUEUED.name,
                    ),
                )
            }
        }
    }.getOrDefault(emptyList())
}
