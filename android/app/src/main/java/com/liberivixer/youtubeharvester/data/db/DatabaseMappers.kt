package com.liberivixer.youtubeharvester.data.db

import com.liberivixer.youtubeharvester.model.ArchiveItem
import com.liberivixer.youtubeharvester.model.ChannelItem
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.DownloadJob
import com.liberivixer.youtubeharvester.model.DownloadStatus
import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.model.QueueItem
import com.liberivixer.youtubeharvester.model.ScheduleItem
import com.liberivixer.youtubeharvester.model.SelectedAudioTrack
import org.json.JSONObject
import org.json.JSONArray

fun QueueEntity.toModel() = QueueItem(
    id = mediaId,
    url = url,
    title = title,
    channel = channel,
    source = enumValueOrDefault(source, MediaSource.YouTube),
    contentType = enumValueOrDefault(contentType, ContentType.Video),
    originChannelId = originChannelId,
    thumbnailUrl = thumbnailUrl,
    resolution = resolution,
    selected = selected,
    status = status,
    audioTracks = audioJson.toAudioTracks(),
    subtitleSelections = subtitlesJson.toStringList(),
)

fun ChannelEntity.toModel() = ChannelItem(
    id = id,
    url = url,
    name = name,
    handle = handle,
    thumbnailUrl = thumbnailUrl,
    videosEnabled = videosEnabled,
    shortsEnabled = shortsEnabled,
    streamsEnabled = streamsEnabled,
    paidContent = enumValueOrDefault(paidContent, com.liberivixer.youtubeharvester.model.PaidContentStatus.Unknown),
    status = status,
    lastCheckedEpochMs = lastCheckedEpochMs,
)

fun ChannelItem.toEntity(sortOrder: Int) = ChannelEntity(
    id = id,
    url = url,
    name = name,
    handle = handle,
    thumbnailUrl = thumbnailUrl,
    videosEnabled = videosEnabled,
    shortsEnabled = shortsEnabled,
    streamsEnabled = streamsEnabled,
    paidContent = paidContent.name,
    status = status,
    lastCheckedEpochMs = lastCheckedEpochMs,
    sortOrder = sortOrder,
)

fun ScheduleEntity.toModel() = ScheduleItem(
    id = id,
    hour = hour,
    minute = minute,
    enabled = enabled,
    lastRunEpochMs = lastRunEpochMs,
    createdAtEpochMs = createdAtEpochMs,
)

fun ScheduleItem.toEntity() = ScheduleEntity(
    id = id,
    hour = hour,
    minute = minute,
    enabled = enabled,
    lastRunEpochMs = lastRunEpochMs,
    createdAtEpochMs = createdAtEpochMs,
)

fun QueueItem.toEntity(sortOrder: Int) = QueueEntity(
    source = source.name,
    mediaId = id,
    url = url,
    title = title,
    channel = channel,
    contentType = contentType.name,
    originChannelId = originChannelId,
    thumbnailUrl = thumbnailUrl,
    resolution = resolution,
    selected = selected,
    status = status,
    audioJson = audioTracks.toAudioJson(),
    subtitlesJson = subtitleSelections.toJson(),
    sortOrder = sortOrder,
)

fun DownloadJobEntity.toModel() = DownloadJob(
    jobId = jobId,
    mediaId = mediaId,
    url = url,
    title = title,
    channel = channel,
    source = enumValueOrDefault(source, MediaSource.YouTube),
    contentType = enumValueOrDefault(contentType, ContentType.Video),
    originChannelId = originChannelId,
    thumbnailUrl = thumbnailUrl,
    resolution = resolution,
    status = enumValueOrDefault(status, DownloadStatus.FAILED),
    progress = progress,
    etaSeconds = etaSeconds,
    message = message,
    createdAtEpochMs = createdAtEpochMs,
    updatedAtEpochMs = updatedAtEpochMs,
    fileUri = fileUri,
    errorMessage = errorMessage,
    fromQueue = fromQueue,
    audioTracks = audioJson.toAudioTracks(),
    subtitleSelections = subtitlesJson.toStringList(),
)

fun QueueItem.toDownloadJobEntity(jobId: String, fromQueue: Boolean, now: Long) = DownloadJobEntity(
    jobId = jobId,
    source = source.name,
    mediaId = id,
    url = url,
    title = title,
    channel = channel,
    contentType = contentType.name,
    originChannelId = originChannelId,
    thumbnailUrl = thumbnailUrl,
    resolution = resolution,
    status = DownloadStatus.QUEUED.name,
    progress = 0,
    etaSeconds = null,
    message = DownloadStatus.QUEUED.name,
    createdAtEpochMs = now,
    updatedAtEpochMs = now,
    fileUri = null,
    errorMessage = null,
    fromQueue = fromQueue,
    audioJson = audioTracks.toAudioJson(),
    subtitlesJson = subtitleSelections.toJson(),
)

fun ArchiveEntity.toModel() = ArchiveItem(
    id = mediaId,
    title = title,
    channel = channel,
    thumbnailUrl = thumbnailUrl,
    source = enumValueOrDefault(source, MediaSource.YouTube),
    type = enumValueOrDefault(contentType, ContentType.Video),
    resolution = resolution,
    downloadedAt = downloadedAt,
    downloadedAtEpochMs = downloadedAtEpochMs,
    fileExists = fileExists,
    fileUri = fileUri,
    audio = audioJson.toStringList(),
    subtitles = subtitlesJson.toStringList(),
    variantKey = variantKey,
)

fun ArchiveItem.toEntity(downloadedAtEpochMs: Long, fileUri: String? = null) = ArchiveEntity(
    source = source.name,
    mediaId = id,
    title = title,
    channel = channel,
    thumbnailUrl = thumbnailUrl,
    contentType = type.name,
    resolution = resolution,
    variantKey = variantKey,
    downloadedAt = downloadedAt,
    downloadedAtEpochMs = downloadedAtEpochMs,
    fileExists = fileExists,
    fileUri = fileUri ?: this.fileUri,
    audioJson = audio.toJson(),
    subtitlesJson = subtitles.toJson(),
)

private fun List<String>.toJson(): String = JSONArray().also { array ->
    forEach(array::put)
}.toString()

private fun List<SelectedAudioTrack>.toAudioJson(): String = JSONArray().also { array ->
    forEach { track ->
        array.put(
            JSONObject()
                .put("format_id", track.formatId)
                .put("format_kind", track.formatKind)
                .put("language", track.language)
                .put("name", track.name),
        )
    }
}.toString()

private fun String.toAudioTracks(): List<SelectedAudioTrack> = runCatching {
    val array = JSONArray(this)
    buildList {
        repeat(array.length()) { index ->
            val item = array.optJSONObject(index) ?: return@repeat
            val formatId = item.optString("format_id").trim()
            if (formatId.isBlank()) return@repeat
            add(
                SelectedAudioTrack(
                    formatId = formatId,
                    formatKind = item.optString("format_kind", "audio"),
                    language = item.optString("language", "und"),
                    name = item.optString("name"),
                ),
            )
        }
    }
}.getOrDefault(emptyList())

private fun String.toStringList(): List<String> = runCatching {
    val array = JSONArray(this)
    List(array.length()) { index -> array.getString(index) }
}.getOrDefault(emptyList())

private inline fun <reified T : Enum<T>> enumValueOrDefault(value: String, fallback: T): T =
    enumValues<T>().firstOrNull { it.name == value } ?: fallback
