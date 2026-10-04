package com.liberivixer.youtubeharvester.media

import com.liberivixer.youtubeharvester.model.MediaSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MediaUrlParserTest {
    @Test fun acceptsMixedCaseSchemeAndPreservesVideoId() {
        listOf("https://", "HTTPS://", "HtTpS://", "HTTP://", "").forEach { scheme ->
            assertEquals("dQw4w9WgXcQ", MediaUrlParser.parse("${scheme}youtu.be/dQw4w9WgXcQ")?.mediaId)
        }
        assertEquals("dQw4w9WgXcQ", MediaUrlParser.extract("Watch HTTPS://youtu.be/dQw4w9WgXcQ")?.mediaId)
        assertEquals("8fd4a5d2-ABCD", MediaUrlParser.parse("HTTPS://rutube.ru/video/8fd4a5d2-ABCD/")?.mediaId)
    }

    @Test fun schemeFixDoesNotWeakenUrlRestrictions() {
        listOf("HTTPS://youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
            "file:///youtu.be/dQw4w9WgXcQ", "ftp://youtu.be/dQw4w9WgXcQ",
            "HTTPS://user@youtu.be/dQw4w9WgXcQ", "HTTPS://youtu.be:443/dQw4w9WgXcQ",
            "https://youtu.be@evil.example/dQw4w9WgXcQ").forEach { assertNull(it, MediaUrlParser.parse(it)) }
    }

    @Test
    fun parsesSupportedServices() {
        assertEquals(MediaSource.YouTube, MediaUrlParser.parse("https://youtu.be/dQw4w9WgXcQ")?.source)
        assertEquals(MediaSource.YouTube, MediaUrlParser.parse("youtube.com/shorts/dQw4w9WgXcQ")?.source)
        assertEquals(MediaSource.Vk, MediaUrlParser.parse("https://vk.com/video-12345_67890")?.source)
        assertEquals(MediaSource.Vk, MediaUrlParser.parse("https://vk.ru/clip-12345_67890")?.source)
        assertEquals(MediaSource.Rutube, MediaUrlParser.parse("https://rutube.ru/video/8fd4a5d2-1234/")?.source)
        assertEquals(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            MediaUrlParser.parse("https://youtu.be/dQw4w9WgXcQ?t=42")?.normalizedUrl,
        )
        assertEquals(
            "https://vk.com/video-12345_67890",
            MediaUrlParser.parse("https://vkvideo.ru/video-12345_67890?from=search")?.normalizedUrl,
        )
        assertEquals(
            "https://vk.com/video-12345_67890",
            MediaUrlParser.parse("https://vk.com/video?oid=-12345&id=67890")?.normalizedUrl,
        )
        assertEquals(
            "https://rutube.ru/play/embed/8fd4a5d2-1234/",
            MediaUrlParser.parse("https://rutube.ru/play/embed/8fd4a5d2-1234/")?.normalizedUrl,
        )
        assertEquals(
            "https://rutube.ru/live/video/private/8fd4a5d2-1234/?p=secret",
            MediaUrlParser.parse("https://rutube.ru/live/video/private/8fd4a5d2-1234/?p=secret")?.normalizedUrl,
        )
    }

    @Test
    fun rejectsUnknownAndIncompleteUrls() {
        assertNull(MediaUrlParser.parse("https://example.com/watch?v=dQw4w9WgXcQ"))
        assertNull(MediaUrlParser.parse("https://youtube.com/watch?v=x"))
        assertNull(MediaUrlParser.parse("https://youtube.com/watch?v=too-short"))
        assertNull(MediaUrlParser.parse("just some text"))
        assertNull(MediaUrlParser.parse("https://fake-youtube.com/watch?v=dQw4w9WgXcQ"))
        assertNull(MediaUrlParser.parse("https://notvk.com/video-12345_67890"))
        assertNull(MediaUrlParser.parse("https://fakerutube.ru/video/8fd4a5d2-1234/"))
        assertNull(MediaUrlParser.parse("https://user@rutube.ru/video/8fd4a5d2-1234/"))
        assertNull(MediaUrlParser.parse("https://rutube.ru:444/video/8fd4a5d2-1234/"))
    }

    @Test
    fun extractsSupportedLinkFromSharedText() {
        assertEquals(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            MediaUrlParser.extract("Watch this: https://youtu.be/dQw4w9WgXcQ?t=42.")?.normalizedUrl,
        )
        assertEquals(
            MediaSource.Vk,
            MediaUrlParser.extract("Видео дня\nhttps://vk.com/video-12345_67890)")?.source,
        )
        assertEquals(
            MediaSource.Rutube,
            MediaUrlParser.extract("https://example.com/x and https://rutube.ru/video/8fd4a5d2-1234/")?.source,
        )
        assertNull(MediaUrlParser.extract("Text without a supported media link https://example.com/video"))
    }
}
