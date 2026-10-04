package com.liberivixer.youtubeharvester.data.db

import com.liberivixer.youtubeharvester.model.ArchiveItem
import com.liberivixer.youtubeharvester.model.ChannelItem
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.DownloadStatus
import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.model.QueueItem
import com.liberivixer.youtubeharvester.model.SelectedAudioTrack
import org.junit.Assert.assertEquals
import org.junit.Test

class DatabaseMappersTest {
    @Test
    fun channelEntityRoundTripKeepsContentSelection() {
        val channel = ChannelItem(
            id = "handle:prohitech",
            url = "https://www.youtube.com/@PROHiTech",
            name = "PROHiTech",
            handle = "@PROHiTech",
            videosEnabled = true,
            shortsEnabled = false,
            streamsEnabled = true,
        )

        assertEquals(channel, channel.toEntity(sortOrder = 3).toModel())
    }

    @Test
    fun queueEntityRoundTripKeepsMetadata() {
        val item = QueueItem(
            id = "video-id",
            url = "https://rutube.ru/video/video-id/",
            title = "Название",
            channel = "Канал",
            source = MediaSource.Rutube,
            contentType = ContentType.Shorts,
            thumbnailUrl = "https://example.com/thumb.jpg",
            resolution = "1440p",
            selected = false,
            status = "Ожидает",
            audioTracks = listOf(SelectedAudioTrack("140", "audio", "en", "English")),
            subtitleSelections = listOf("manual:ru", "auto:en"),
        )

        assertEquals(item, item.toEntity(sortOrder = 4).toModel())
    }

    @Test
    fun archiveEntityRoundTripKeepsAudioAndSubtitles() {
        val item = ArchiveItem(
            id = "video-id",
            title = "Название",
            channel = "Канал",
            source = MediaSource.YouTube,
            type = ContentType.Video,
            resolution = "1080p",
            downloadedAt = "30 августа 2026, 12:00",
            downloadedAtEpochMs = 1_788_087_600_000,
            thumbnailUrl = "https://example.com/archive.jpg",
            fileUri = "content://media/external/video/media/42",
            audio = listOf("ru", "en"),
            subtitles = listOf("uk", "ja"),
        )

        assertEquals(item, item.toEntity(downloadedAtEpochMs = 1_788_087_600_000).toModel())
    }

    @Test
    fun downloadJobEntityKeepsQueueOriginAndResolution() {
        val item = QueueItem(
            id = "05h8f6kX6g8",
            url = "https://www.youtube.com/watch?v=05h8f6kX6g8",
            title = "Video title",
            channel = "Channel",
            source = MediaSource.YouTube,
            contentType = ContentType.Stream,
            originChannelId = "handle:channel",
            thumbnailUrl = "https://example.com/thumb.jpg",
            resolution = "720p",
        )

        val job = item.toDownloadJobEntity("job-1", fromQueue = true, now = 42L).toModel()

        assertEquals("job-1", job.jobId)
        assertEquals(DownloadStatus.QUEUED, job.status)
        assertEquals(DownloadStatus.QUEUED.name, job.message)
        assertEquals("720p", job.resolution)
        assertEquals(ContentType.Stream, job.contentType)
        assertEquals("handle:channel", job.originChannelId)
        assertEquals(true, job.fromQueue)
        assertEquals(42L, job.createdAtEpochMs)
    }
}
