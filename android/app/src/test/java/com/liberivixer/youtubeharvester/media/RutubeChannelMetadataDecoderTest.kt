package com.liberivixer.youtubeharvester.media

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RutubeChannelMetadataDecoderTest {
    private val show = requireNotNull(ChannelUrlParser.parse("https://rutube.ru/metainfo/tv/405933"))

    @Test
    fun aliasResolvesToSameIdAsNumericChannel() {
        val alias = requireNotNull(ChannelUrlParser.parse("https://rutube.ru/u/rutube"))
        val canonical = RutubeChannelMetadataDecoder.canonical(alias, JSONObject("""{"id":"23704195"}"""))
        assertEquals(ChannelUrlParser.parse("https://rutube.ru/channel/23704195"), canonical)
    }

    @Test
    fun showKeepsItsPosterAndNameNotTheUploadersAvatar() {
        val playlist = JSONObject("""{"id":"405933","title":"Titans","entries":[{"uploader":"TNT"}]}""")
        val artwork = JSONObject("""{"id":405933,"name":"Titans","picture":"https://pic.rtbcdn.ru/show.jpg"}""")
        val resolved = RutubeChannelMetadataDecoder.decode(show, playlist, artwork)
        assertEquals("Titans", resolved.title)
        assertEquals("https://pic.rtbcdn.ru/show.jpg", resolved.thumbnailUrl)
        assertEquals(show, resolved.channel)
        assertEquals("Titans", RutubeChannelMetadataDecoder.decode(show, playlist, null).title)
    }

    @Test
    fun badArtworkDoesNotReplaceValidTitle() {
        val playlist = JSONObject("""{"title":"Titans"}""")
        for (url in listOf("https://pic.rtbcdn.ru.evil.test/a", "http://pic.rtbcdn.ru/a", "file:///tmp/a", "https://u:p@pic.rtbcdn.ru/a")) {
            val artwork = JSONObject().put("id", 405933).put("picture", url)
            assertNull(RutubeChannelMetadataDecoder.decode(show, playlist, artwork).thumbnailUrl)
        }
        assertNull(RutubeChannelMetadataDecoder.decode(show, playlist, JSONObject("""{"id":1,"picture":"https://pic.rtbcdn.ru/wrong"}""")).thumbnailUrl)
    }

    @Test
    fun nullArtworkNameDoesNotErasePlaylistTitle() {
        val resolved = RutubeChannelMetadataDecoder.decode(show,
            JSONObject("""{"title":"Titans"}"""), JSONObject("""{"id":405933,"name":null,"picture":null}"""))
        assertEquals("Titans", resolved.title)
        assertNull(resolved.thumbnailUrl)
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsDifferentShowIdentity() {
        RutubeChannelMetadataDecoder.canonical(show, JSONObject("""{"id":"1"}"""))
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsDifferentNumericChannelIdentity() {
        val channel = requireNotNull(ChannelUrlParser.parse("https://rutube.ru/channel/23704195"))
        RutubeChannelMetadataDecoder.canonical(channel, JSONObject("""{"id":"1"}"""))
    }
}
