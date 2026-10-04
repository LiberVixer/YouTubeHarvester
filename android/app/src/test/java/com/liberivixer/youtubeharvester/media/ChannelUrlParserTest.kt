package com.liberivixer.youtubeharvester.media

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.MediaSource

class ChannelUrlParserTest {
    @Test fun acceptsMixedCaseSchemesWithoutChangingPath() {
        listOf("https://", "HTTPS://", "HtTpS://", "HTTP://", "").forEach { scheme ->
            assertEquals("https://www.youtube.com/@PROHiTech",
                ChannelUrlParser.parse("${scheme}youtube.com/@PROHiTech")?.normalizedUrl)
        }
        assertEquals("rutube:channel:123", ChannelUrlParser.parse("HTTPS://rutube.ru/channel/123")?.id)
        listOf("file:///youtube.com/@PROHiTech", "HTTPS://user@youtube.com/@PROHiTech",
            "HTTPS://youtube.com:443/@PROHiTech", "HTTPS://youtube.com.evil.test/@PROHiTech")
            .forEach { assertNull(it, ChannelUrlParser.parse(it)) }
    }

    @Test
    fun rutubeChannelsAndShowsHaveSeparateIdentitiesAndSections() {
        val channel = requireNotNull(ChannelUrlParser.parse("http://www.rutube.ru/channel/0405933/shorts/?utm_source=test"))
        val show = requireNotNull(ChannelUrlParser.parse("https://rutube.ru/metainfo/tv/405933/"))
        assertEquals("rutube:channel:405933", channel.id)
        assertEquals("rutube:show:405933", show.id)
        assertEquals(MediaSource.Rutube, channel.source)
        assertEquals(listOf(ContentType.Video, ContentType.Shorts), channel.sections)
        assertEquals(listOf(ContentType.Video), show.sections)
        assertEquals("https://rutube.ru/channel/405933/shorts", channel.sectionUrl(ContentType.Shorts))
        assertEquals("https://rutube.ru/metainfo/tv/405933", show.sectionUrl(ContentType.Video))
        assertEquals("-1:-5:-1", show.recentItems(5))
        assertEquals("1-5", channel.recentItems(5))
        assertEquals("rutube:slug:rutube", ChannelUrlParser.parse("rutube.ru/u/rutube/videos/")?.id)
    }

    @Test
    fun rejectsUnsafeAndUnsupportedRutubeUrls() {
        listOf(
            "https://rutube.ru.evil.test/channel/1", "https://rutube.ru@evil.test/channel/1",
            "https://user:pass@rutube.ru/channel/1", "https://rutube.ru:8443/channel/1",
            "https://rutube.ru/metainfo/tv/1/videos", "https://rutube.ru/metainfo/tv/1/../2",
            "https://rutube.ru/channel/1/streams", "https://rutube.ru/channel/a", "https://rutube.ru/plst/1",
            "https://rutube.ru/channel/1%2Fvideos", "https://rutube.ru/video/59212d9fdaf8dd15df9e1eb74edc9093/",
        ).forEach { assertNull(it, ChannelUrlParser.parse(it)) }
    }

    @Test
    fun parsesModernHandleLinksAndBareHandles() {
        val link = ChannelUrlParser.parse("https://youtube.com/@PROHiTech/videos")
        assertEquals("handle:prohitech", link?.id)

        val parsed = ChannelUrlParser.parse("youtube.com/@PROHiTech")
        assertEquals("handle:prohitech", parsed?.id)
        assertEquals("https://www.youtube.com/@PROHiTech", parsed?.normalizedUrl)
        assertEquals("@PROHiTech", parsed?.handle)

        assertEquals("handle:prohitech", ChannelUrlParser.parse("@PROHiTech")?.id)
    }

    @Test
    fun parsesCanonicalAndLegacyChannelLinks() {
        val channel = ChannelUrlParser.parse("https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw")
        assertEquals("channel:uc_x5xg1ov2p6uzz5fsm9ttw", channel?.id)
        assertEquals("https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw", channel?.normalizedUrl)
        assertEquals("user:google", ChannelUrlParser.parse("youtube.com/user/Google")?.id)
        assertEquals("c:android", ChannelUrlParser.parse("https://youtube.com/c/Android")?.id)
    }

    @Test
    fun rejectsVideosPlaylistsUnknownDomainsAndIncompletePaths() {
        assertNull(ChannelUrlParser.parse("https://youtube.com/watch?v=dQw4w9WgXcQ"))
        assertNull(ChannelUrlParser.parse("https://youtube.com/shorts/dQw4w9WgXcQ"))
        assertNull(ChannelUrlParser.parse("https://youtube.com/playlist?list=PL123"))
        assertNull(ChannelUrlParser.parse("https://example.com/@PROHiTech"))
        assertNull(ChannelUrlParser.parse("https://fake-youtube.com/@PROHiTech"))
        assertNull(ChannelUrlParser.parse("https://youtube.com/channel/not-a-channel-id"))
        assertNull(ChannelUrlParser.parse("not a URL"))
    }
}
