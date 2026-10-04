package com.liberivixer.youtubeharvester.media

import android.content.Context
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.MediaSource
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runInterruptible
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class ChannelScanEntry(
    val mediaId: String,
    val url: String,
    val title: String,
    val channel: String,
    val thumbnailUrl: String?,
    val contentType: ContentType,
    val membersOnly: Boolean,
    val source: MediaSource = MediaSource.YouTube,
)

data class ChannelSectionScan(
    val contentType: ContentType,
    val channelName: String,
    val channelHandle: String,
    val channelThumbnailUrl: String?,
    val entries: List<ChannelScanEntry>,
    val available: Boolean,
    val paidContentSeen: Boolean,
)

class YtDlpChannelScanner(private val context: Context) : ChannelScanEngine {
    @Volatile private var activeProcessId: String? = null

    override suspend fun scanSection(channelUrl: String, contentType: ContentType, limit: Int): EngineResult<ChannelSectionScan> {
        val parsed = ChannelUrlParser.parse(channelUrl)
            ?: return EngineResult.Failure("Invalid channel URL")
        if (contentType !in parsed.sections) return EngineResult.Failure("Unsupported channel section")
        val processId = "channel-scan-${UUID.randomUUID()}"
        activeProcessId = processId
        return try {
            val response = runInterruptible(Dispatchers.IO) {
                AndroidYtDlpRuntime.ensure(context, requireFfmpeg = false)
                val request = YoutubeDLRequest(parsed.sectionUrl(contentType))
                    .addOption("--flat-playlist")
                    .addOption("--playlist-items", parsed.recentItems(limit))
                    .addOption("--no-lazy-playlist")
                    .addOption("--dump-single-json")
                    .addOption("--skip-download")
                    .addOption("--abort-on-error")
                    .addOption("--socket-timeout", 15)
                    .addOption("--extractor-retries", 2)
                    .addOption("--no-warnings")
                YoutubeDL.execute(request, processId)
            }
            EngineResult.Success(YtDlpChannelScanDecoder.decodeResponse(
                response.out, response.err, response.exitCode, contentType, parsed.source, parsed.collection,
            ))
        } catch (error: CancellationException) {
            runCatching { YoutubeDL.destroyProcessById(processId) }
            throw error
        } catch (error: Exception) {
            val message = error.message.orEmpty().replace(Regex("\\s+"), " ").trim()
            if (parsed.source == MediaSource.YouTube && error !is IncompleteChannelListException &&
                MISSING_SECTION_MARKERS.any { message.contains(it, ignoreCase = true) }) {
                EngineResult.Success(
                    ChannelSectionScan(contentType, "", "", null, emptyList(), available = false, paidContentSeen = false),
                )
            } else {
                EngineResult.Failure(message.takeIf(String::isNotBlank)?.take(260) ?: "yt-dlp channel scan failed", retryable = true)
            }
        } finally {
            if (activeProcessId == processId) activeProcessId = null
        }
    }

    override fun cancel() {
        activeProcessId?.let { processId -> runCatching { YoutubeDL.destroyProcessById(processId) } }
    }

    override suspend fun checkPaidContent(channelUrl: String, sections: List<ContentType>): EngineResult<Boolean> {
        if (ChannelUrlParser.parse(channelUrl)?.source != MediaSource.YouTube) {
            return EngineResult.Failure("Paid-content checks are only available for YouTube")
        }
        var completedProbe = false
        var lastError = ""
        for (contentType in sections) {
            val processId = "paid-scan-${UUID.randomUUID()}"
            activeProcessId = processId
            try {
                val response = runInterruptible(Dispatchers.IO) {
                    AndroidYtDlpRuntime.ensure(context, requireFfmpeg = false)
                    val request = YoutubeDLRequest("${channelUrl.trimEnd('/')}/${sectionName(contentType)}")
                        .addOption("--playlist-end", PAID_SCAN_LIMIT)
                        .addOption("--skip-download")
                        .addOption("--simulate")
                        .addOption("--no-warnings")
                        .addOption("--print", "%(id)s %(availability)s")
                        .addOption("--socket-timeout", 15)
                        .addOption("--extractor-retries", 2)
                    YoutubeDL.execute(request, processId)
                }
                completedProbe = completedProbe || response.exitCode == 0
                if (hasPaidContentMarker(response.out) || hasPaidContentMarker(response.err)) {
                    return EngineResult.Success(true)
                }
            } catch (error: CancellationException) {
                runCatching { YoutubeDL.destroyProcessById(processId) }
                throw error
            } catch (error: Exception) {
                val message = error.message.orEmpty().replace(Regex("\\s+"), " ").trim()
                if (hasPaidContentMarker(message)) return EngineResult.Success(true)
                if (MISSING_SECTION_MARKERS.none { message.contains(it, ignoreCase = true) }) lastError = message
            } finally {
                if (activeProcessId == processId) activeProcessId = null
            }
        }
        return if (completedProbe) {
            EngineResult.Success(false)
        } else {
            EngineResult.Failure(lastError.takeIf(String::isNotBlank) ?: "Paid-content check failed", retryable = true)
        }
    }

    private fun sectionName(contentType: ContentType): String = when (contentType) {
        ContentType.Video -> "videos"
        ContentType.Shorts -> "shorts"
        ContentType.Stream -> "streams"
        ContentType.Queue -> error("Queue is not a channel section")
    }

    private companion object {
        const val PAID_SCAN_LIMIT = 5
        val MISSING_SECTION_MARKERS = listOf(
            "does not have a videos tab",
            "does not have a shorts tab",
            "does not have a streams tab",
            "does not have a live tab",
            "this channel has no videos",
        )
    }
}

internal object YtDlpChannelScanDecoder {
    private val youtubeId = Regex("^[A-Za-z0-9_-]{11}$")
    private val rutubeId = Regex("^[a-z0-9]{32}$")

    fun decodeResponse(
        payload: String,
        stderr: String,
        exitCode: Int,
        contentType: ContentType,
        source: MediaSource,
        collection: Boolean,
    ): ChannelSectionScan {
        if (exitCode != 0 || stderr.lineSequence().any { it.trimStart().startsWith("ERROR:", ignoreCase = true) }) {
            throw IncompleteChannelListException(stderr.ifBlank { "Incomplete channel list" })
        }
        val decoded = decode(payload, contentType, source, collection)
        return decoded.copy(paidContentSeen = decoded.paidContentSeen ||
            (source == MediaSource.YouTube && hasPaidContentMarker(stderr)))
    }

    fun decode(payload: String, contentType: ContentType, source: MediaSource = MediaSource.YouTube, collection: Boolean = false): ChannelSectionScan {
        val data = JSONObject(payload.trim())
        val firstEntry = data.optJSONArray("entries")?.optJSONObject(0)
        val channelName = if (collection) firstNonBlank(data, "title") else
            firstNonBlank(data, "channel", "uploader", "playlist_uploader").ifBlank {
                firstEntry?.let { firstNonBlank(it, "channel", "uploader") }.orEmpty()
            }.ifBlank { firstNonBlank(data, "title") }
        val channelHandle = firstNonBlank(data, "uploader_id", "channel_id")
        val channelThumbnail = firstNonBlank(data, "channel_thumbnail", "uploader_avatar").ifBlank {
            bestThumbnail(data.optJSONArray("thumbnails"))
        }.ifBlank { null }
        val entries = mutableListOf<ChannelScanEntry>()
        val rawEntries = data.optJSONArray("entries") ?: throw IncompleteChannelListException("Missing channel entries")
        repeat(rawEntries.length()) { index ->
            val entry = rawEntries.optJSONObject(index) ?: return@repeat
            val mediaId = entry.optString("id").trim()
            if (!(if (source == MediaSource.Rutube) rutubeId else youtubeId).matches(mediaId)) return@repeat
            val entryChannel = firstNonBlank(entry, "channel", "uploader").ifBlank { channelName }
            entries += ChannelScanEntry(
                mediaId = mediaId,
                url = if (source == MediaSource.Rutube) "https://rutube.ru/video/$mediaId/" else "https://www.youtube.com/watch?v=$mediaId",
                title = firstNonBlank(entry, "title").ifBlank { "${source.label} $mediaId" },
                channel = entryChannel,
                thumbnailUrl = bestThumbnail(entry.optJSONArray("thumbnails")).ifBlank {
                    firstNonBlank(entry, "thumbnail")
                }.ifBlank { null },
                contentType = contentType,
                membersOnly = source == MediaSource.YouTube && containsPaidMarker(entry),
                source = source,
            )
        }
        return ChannelSectionScan(
            contentType = contentType,
            channelName = channelName,
            channelHandle = channelHandle,
            channelThumbnailUrl = channelThumbnail,
            entries = entries.distinctBy { it.mediaId },
            available = true,
            paidContentSeen = source == MediaSource.YouTube && containsPaidMarker(data),
        )
    }

    private fun containsPaidMarker(data: JSONObject): Boolean {
        val text = data.toString().lowercase()
        return hasPaidContentMarker(text)
    }

    private fun firstNonBlank(data: JSONObject, vararg keys: String): String = keys.firstNotNullOfOrNull { key ->
        data.optString(key).trim().takeIf { !data.isNull(key) && it.isNotBlank() }
    }.orEmpty()

    private fun bestThumbnail(thumbnails: JSONArray?): String {
        if (thumbnails == null) return ""
        for (index in thumbnails.length() - 1 downTo 0) {
            val url = thumbnails.optJSONObject(index)?.let { firstNonBlank(it, "url") }.orEmpty()
            if (url.isNotBlank()) return url
        }
        return ""
    }
}

internal class IncompleteChannelListException(message: String) : IllegalStateException(message)

internal fun hasPaidContentMarker(text: String): Boolean {
    val normalized = text.lowercase()
    return listOf("subscriber_only", "members-only", "members_only", "join this channel").any(normalized::contains)
}
