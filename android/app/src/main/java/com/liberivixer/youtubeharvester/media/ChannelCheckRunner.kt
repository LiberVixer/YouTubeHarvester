package com.liberivixer.youtubeharvester.media

import android.content.Context
import com.liberivixer.youtubeharvester.data.AndroidAppRepository
import com.liberivixer.youtubeharvester.logging.AppLogLevel
import com.liberivixer.youtubeharvester.logging.AppLogStore
import com.liberivixer.youtubeharvester.model.AppSettings
import com.liberivixer.youtubeharvester.model.CHANNEL_STATUS_CHECKED
import com.liberivixer.youtubeharvester.model.CHANNEL_STATUS_FAILED
import com.liberivixer.youtubeharvester.model.ChannelItem
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.model.PaidContentStatus
import com.liberivixer.youtubeharvester.model.QueueItem
import com.liberivixer.youtubeharvester.model.SectionResult
import com.liberivixer.youtubeharvester.model.SectionStatus
import com.liberivixer.youtubeharvester.model.overviewContentTypes
import kotlinx.coroutines.delay
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class ChannelCheckProgress(
    val channelId: String?,
    val contentType: ContentType?,
    val completedChannels: Int,
    val totalChannels: Int,
    val queuedItems: Int,
    val errorMessage: String? = null,
    val sections: Map<ContentType, SectionResult> = emptyMap(),
    val errors: Int = 0,
    val channelInfo: ChannelItem? = null,
)

data class ChannelCheckSummary(
    val completedChannels: Int,
    val queuedItems: Int,
    val failedChannels: Int,
    val markedItems: Int = 0,
    val errors: Int = failedChannels,
)

internal interface ChannelScanEngine {
    suspend fun scanSection(channelUrl: String, contentType: ContentType, limit: Int): EngineResult<ChannelSectionScan>
    suspend fun checkPaidContent(channelUrl: String, sections: List<ContentType>): EngineResult<Boolean>
    fun cancel()
}

internal interface ChannelCheckStorage {
    suspend fun markDiscoveredItems(items: List<ChannelScanEntry>): Int
    suspend fun updateChannelScanResult(channel: ChannelItem, checkedAt: Long, status: String)
}

class ChannelCheckRunner internal constructor(
    private val scanner: ChannelScanEngine,
    private val repository: ChannelCheckStorage,
    private val logError: suspend (String) -> Unit,
) {
    constructor(context: Context, repository: AndroidAppRepository) : this(
        YtDlpChannelScanner(context.applicationContext),
        repository,
        AppLogStore(context.applicationContext).let { log ->
            { message ->
                log.append(AppLogLevel.ERROR, "Channel check", message)
                Unit
            }
        },
    )

    suspend fun run(
        channels: List<ChannelItem>,
        settings: AppSettings,
        checkPaidContent: Boolean,
        sectionResultDelayMs: Long = 0L,
        markOnly: Boolean = false,
        onDiscovered: suspend (List<QueueItem>) -> Int = { 0 },
        onProgress: (ChannelCheckProgress) -> Unit = {},
    ): ChannelCheckSummary = scanMutex.withLock {
        var queuedItems = 0
        var failedChannels = 0
        var markedItems = 0
        var errors = 0
        channels.forEachIndexed { index, originalChannel ->
            var updatedChannel = originalChannel
            var paidContentSeen = false
            var paidProbeCompleted = false
            var sectionFailed = false
            val toMark = mutableListOf<ChannelScanEntry>()
            val supportsPaidCheck = ChannelUrlParser.parse(originalChannel.url)?.source == MediaSource.YouTube
            val sections = overviewContentTypes.associateWith {
                SectionResult(status = if (it in enabledSections(originalChannel)) SectionStatus.WAITING else SectionStatus.DISABLED)
            }.toMutableMap()
            fun report(type: ContentType?, message: String? = null, completed: Int = index) = onProgress(
                ChannelCheckProgress(originalChannel.id, type, completed, channels.size, queuedItems,
                    message, sections.toMap(), errors, updatedChannel),
            )
            report(null)

            enabledSections(originalChannel).forEach { contentType ->
                sections[contentType] = SectionResult(status = SectionStatus.CHECKING)
                report(contentType)
                when (
                    val result = scanner.scanSection(
                        originalChannel.url,
                        contentType,
                        sectionLimit(contentType, settings),
                    )
                ) {
                    is EngineResult.Success -> {
                        val scan = result.value
                        paidContentSeen = paidContentSeen || scan.paidContentSeen
                        updatedChannel = updatedChannel.copy(
                            name = scan.channelName.ifBlank { updatedChannel.name },
                            handle = scan.channelHandle.takeIf { it.startsWith('@') } ?: updatedChannel.handle,
                            thumbnailUrl = scan.channelThumbnailUrl ?: updatedChannel.thumbnailUrl,
                        )
                        val discovered = scan.entries.filterNot { it.membersOnly }.map { entry ->
                            QueueItem(
                                id = entry.mediaId,
                                url = entry.url,
                                title = entry.title,
                                channel = entry.channel.ifBlank { updatedChannel.name },
                                source = entry.source,
                                contentType = entry.contentType,
                                originChannelId = originalChannel.id,
                                thumbnailUrl = entry.thumbnailUrl,
                                resolution = settings.maxResolution,
                            )
                        }
                        sections[contentType] = SectionResult(scan.entries.size, SectionStatus.CHECKED)
                        report(contentType)
                        if (markOnly) toMark += scan.entries else queuedItems += onDiscovered(discovered)
                        report(contentType)
                    }
                    is EngineResult.Failure -> {
                        sectionFailed = true
                        errors++
                        sections[contentType] = SectionResult(status = SectionStatus.FAILED)
                        logError(
                            "Section failed channel=${originalChannel.id.take(80)} section=${contentType.name}: ${result.message}",
                        )
                        report(contentType, result.message)
                    }
                }
                if (sectionResultDelayMs > 0) delay(sectionResultDelayMs)
            }

            if (!markOnly && checkPaidContent && supportsPaidCheck && !paidContentSeen) {
                report(null)
                when (val result = scanner.checkPaidContent(originalChannel.url, enabledSections(originalChannel))) {
                    is EngineResult.Success -> {
                        paidProbeCompleted = true
                        paidContentSeen = result.value
                    }
                    is EngineResult.Failure -> {
                        sectionFailed = true
                        errors++
                        logError(
                            "Paid-content probe failed channel=${originalChannel.id.take(80)}: ${result.message}",
                        )
                        report(null, result.message)
                    }
                }
            }

            val paidStatus = when {
                !supportsPaidCheck -> updatedChannel.paidContent
                paidContentSeen -> PaidContentStatus.MembersOnly
                markOnly || !checkPaidContent -> updatedChannel.paidContent
                paidProbeCompleted -> PaidContentStatus.FreeOnly
                else -> PaidContentStatus.Unknown
            }
            val status = if (sectionFailed) CHANNEL_STATUS_FAILED else CHANNEL_STATUS_CHECKED
            currentCoroutineContext().ensureActive()
            if (markOnly && !sectionFailed) markedItems += repository.markDiscoveredItems(toMark)
            if (sectionFailed) failedChannels += 1
            val checkedAt = System.currentTimeMillis()
            updatedChannel = updatedChannel.copy(
                paidContent = paidStatus,
                status = status,
                lastCheckedEpochMs = checkedAt,
            )
            repository.updateChannelScanResult(updatedChannel, checkedAt, status)
            onProgress(
                ChannelCheckProgress(null, null, index + 1, channels.size, queuedItems, sections = sections.toMap(), errors = errors),
            )
        }
        ChannelCheckSummary(channels.size, queuedItems, failedChannels, markedItems, errors)
    }

    fun cancel() = scanner.cancel()

    private fun enabledSections(channel: ChannelItem): List<ContentType> = buildList {
        if (channel.videosEnabled) add(ContentType.Video)
        if (channel.shortsEnabled) add(ContentType.Shorts)
        if (channel.streamsEnabled) add(ContentType.Stream)
    }.filter { it in ChannelUrlParser.parse(channel.url)?.sections.orEmpty() }

    private fun sectionLimit(contentType: ContentType, settings: AppSettings): Int = when (contentType) {
        ContentType.Video -> settings.videoLimit
        ContentType.Shorts -> settings.shortsLimit
        ContentType.Stream -> settings.streamsLimit
        ContentType.Queue -> 1
    }

    private companion object {
        val scanMutex = Mutex()
    }
}
