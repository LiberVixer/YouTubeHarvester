package com.liberivixer.youtubeharvester.model

import java.time.Instant
import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Test

class DailyDownloadsTest {
    private val now = Instant.parse("2026-09-07T12:00:00Z").toEpochMilli()
    private val zone = ZoneId.of("Europe/Moscow")
    private fun job(id: String, type: ContentType = ContentType.Video, time: Long = now, status: DownloadStatus = DownloadStatus.COMPLETED) = DownloadJob(
        id, id, "https://example.test/$id", id, "Channel", MediaSource.YouTube, type, null, null, "1080p", status,
        100, null, "", time, time, "content://video/$id", null, false, emptyList(), emptyList())
    private fun archive(id: String) = ArchiveItem(id, id, "Channel", MediaSource.YouTube, ContentType.Video, "1080p", "", now, fileUri = "content://video/$id")

    @Test fun countsCompletedDownloadsByTypeWithoutArchiveDuplicates() {
        val jobs = listOf(job("video"), job("short", ContentType.Shorts), job("live", ContentType.Stream), job("failed", status = DownloadStatus.FAILED))
        assertEquals(mapOf(ContentType.Video to 1, ContentType.Shorts to 1, ContentType.Stream to 1), dailyDownloads(jobs, listOf(archive("video")), now, zone))
    }

    @Test fun deletingArchiveOrDownloadingSameMediaAgainDoesNotLoseDailyCount() {
        assertEquals(2, dailyDownloads(listOf(job("first"), job("second").copy(mediaId = "first")), emptyList(), now, zone)[ContentType.Video])
    }

    @Test fun includesLegacyArchiveAndUsesLocalMidnight() {
        val beforeMidnight = Instant.parse("2026-09-06T20:59:59Z").toEpochMilli()
        val midnight = beforeMidnight + 1_000
        val tomorrow = Instant.parse("2026-09-07T21:00:00Z").toEpochMilli()
        assertEquals(2, dailyDownloads(listOf(job("old", time = beforeMidnight), job("today", time = midnight), job("future", time = tomorrow)), listOf(archive("legacy")), now, zone)[ContentType.Video])
    }
}
