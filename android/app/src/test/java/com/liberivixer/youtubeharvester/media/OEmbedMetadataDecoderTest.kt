package com.liberivixer.youtubeharvester.media

import com.liberivixer.youtubeharvester.model.MediaSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class OEmbedMetadataDecoderTest {
    @Test
    fun decodesMetadataWithoutLosingUnicode() {
        val url = ParsedMediaUrl(
            normalizedUrl = "https://rutube.ru/video/abc123/",
            source = MediaSource.Rutube,
            mediaId = "abc123",
        )

        val preview = OEmbedMetadataDecoder.decode(
            """{"title":"Проверка видео","author_name":"Тестовый канал","thumbnail_url":"https://example.com/thumb.jpg"}""",
            url,
        )

        assertEquals("Проверка видео", preview.title)
        assertEquals("Тестовый канал", preview.channel)
        assertEquals("https://example.com/thumb.jpg", preview.thumbnailUrl)
        assertEquals(MediaSource.Rutube, preview.source)
    }

    @Test
    fun acceptsMissingOptionalThumbnailAndAuthor() {
        val url = ParsedMediaUrl(
            normalizedUrl = "https://www.youtube.com/watch?v=abc12345",
            source = MediaSource.YouTube,
            mediaId = "abc12345",
        )

        val preview = OEmbedMetadataDecoder.decode("""{"title":"A video"}""", url)

        assertEquals("YouTube", preview.channel)
        assertNull(preview.thumbnailUrl)
    }

    @Test
    fun treatsJsonNullAsMissingOptionalMetadata() {
        val url = ParsedMediaUrl(
            normalizedUrl = "https://www.youtube.com/watch?v=abc12345",
            source = MediaSource.YouTube,
            mediaId = "abc12345",
        )

        val preview = OEmbedMetadataDecoder.decode(
            """{"title":"A video","author_name":null,"thumbnail_url":null}""",
            url,
        )

        assertEquals(MediaSource.YouTube.label, preview.channel)
        assertNull(preview.thumbnailUrl)
    }
}
