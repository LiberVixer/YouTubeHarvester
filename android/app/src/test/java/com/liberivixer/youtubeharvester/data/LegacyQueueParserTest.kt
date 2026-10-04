package com.liberivixer.youtubeharvester.data

import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.model.DownloadStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LegacyQueueParserTest {
    @Test
    fun migratesValidItemsAndSkipsUnknownSources() {
        val raw = """
            [
              {
                "id":"abc12345",
                "url":"https://www.youtube.com/watch?v=abc12345",
                "title":"Видео из старой очереди",
                "channel":"Канал",
                "source":"YouTube",
                "thumbnail_url":"https://example.com/thumb.jpg",
                "resolution":"720p",
                "selected":false,
                "status":"Ожидает"
              },
              {
                "id":"invalid",
                "url":"https://example.com/video",
                "source":"Unknown"
              }
            ]
        """.trimIndent()

        val queue = parseLegacyQueue(raw)

        assertEquals(1, queue.size)
        assertEquals(MediaSource.YouTube, queue.single().source)
        assertEquals("Видео из старой очереди", queue.single().title)
        assertEquals("https://example.com/thumb.jpg", queue.single().thumbnailUrl)
        assertEquals("720p", queue.single().resolution)
        assertEquals(false, queue.single().selected)
        assertEquals(DownloadStatus.QUEUED.name, queue.single().status)
    }

    @Test
    fun corruptedPayloadBecomesAnEmptyQueue() {
        assertTrue(parseLegacyQueue("not json").isEmpty())
        assertTrue(parseLegacyQueue(null).isEmpty())
    }

    @Test
    fun missingLegacyTextUsesNeutralFallbacks() {
        val queue = parseLegacyQueue(
            """[{"id":"old-id","url":"https://vk.com/video-1_2","source":"Vk"}]""",
        )

        assertEquals("Video old-id", queue.single().title)
        assertEquals("VK", queue.single().channel)
        assertEquals(DownloadStatus.QUEUED.name, queue.single().status)
    }
}
