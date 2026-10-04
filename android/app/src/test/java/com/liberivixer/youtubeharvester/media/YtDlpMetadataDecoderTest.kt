package com.liberivixer.youtubeharvester.media

import com.liberivixer.youtubeharvester.model.MediaOptionSection
import com.liberivixer.youtubeharvester.model.MediaSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Test

class YtDlpMetadataDecoderTest {
    private val parsedUrl = ParsedMediaUrl(
        source = MediaSource.YouTube,
        mediaId = "video-id",
        normalizedUrl = "https://www.youtube.com/watch?v=video-id",
    )

    @Test
    fun prioritizesOriginalPreferredAndManualTracks() {
        val options = YtDlpMetadataDecoder.decode(PAYLOAD, parsedUrl)

        assertEquals("Real title", options.preview.title)
        assertEquals(listOf("en", "ru", "ja", "de"), options.audioTracks.map { it.language })
        assertEquals("140", options.audioTracks.first().formatId)
        assertFalse(options.audioTracks.any { it.formatId == "140-drc" })
        assertEquals(MediaOptionSection.ORIGINAL, options.audioTracks[0].section)
        assertEquals(MediaOptionSection.PREFERRED, options.audioTracks[2].section)
        assertEquals(
            listOf("manual:ru", "manual:en", "auto:ja", "auto:de"),
            options.subtitleTracks.map { it.selection },
        )
    }

    @Test
    fun resolvesCombinedAudioForSelectedResolution() {
        val options = YtDlpMetadataDecoder.decode(PAYLOAD, parsedUrl)
        val combined = options.audioTracks.first { it.formatKind == "combined" }

        val selected720 = YtDlpMetadataDecoder.resolveAudioTrack(combined, "720p")
        val selectedBest = YtDlpMetadataDecoder.resolveAudioTrack(combined, "Лучшее")

        assertNotNull(selected720)
        assertEquals("18", selected720?.formatId)
        assertEquals("137-ja", selectedBest?.formatId)
    }

    @Test
    fun nullTrackMetadataDoesNotBecomeLiteralTextOrInvalidFormats() {
        val options = YtDlpMetadataDecoder.decode(
            """{"formats":[
                {"format_id":"140","vcodec":"none","acodec":"aac","language":null,"format_note":null,"audio_track":{"display_name":null,"name":null}},
                {"format_id":null,"vcodec":"none","acodec":"aac"},
                {"format_id":"bad","vcodec":"none","acodec":null},
                {"format_id":"18","vcodec":"avc1","acodec":"aac","language":null}
            ],"subtitles":{"en":[{"name":null}]}}""",
            parsedUrl,
        )
        assertEquals(1, options.audioTracks.size)
        assertEquals("140", options.audioTracks.single().formatId)
        assertEquals("und", options.audioTracks.single().language)
        assertEquals("", options.audioTracks.single().name)
        assertEquals("", options.subtitleTracks.single().name)
    }

    @Test
    fun nullMetadataUsesStableFallbacks() {
        val options = YtDlpMetadataDecoder.decode(
            """{"id":null,"title":null,"channel":null,"uploader":null,"thumbnail":null,"webpage_url":null}""",
            parsedUrl,
            fallbackTitle = "Fallback title",
        )

        assertEquals(parsedUrl.mediaId, options.preview.mediaId)
        assertEquals(parsedUrl.normalizedUrl, options.preview.normalizedUrl)
        assertEquals("Fallback title", options.preview.title)
        assertEquals(MediaSource.YouTube.label, options.preview.channel)
        assertEquals(null, options.preview.thumbnailUrl)
    }

    private companion object {
        val PAYLOAD = """
            {
              "id": "video-id",
              "title": "Real title",
              "channel": "Real channel",
              "thumbnail": "https://example.com/thumb.jpg",
              "formats": [
                {"format_id":"140-drc","vcodec":"none","acodec":"mp4a","language":"en","ext":"m4a","abr":130,"asr":48000,"format_note":"original, DRC","audio_track":{"display_name":"English"}},
                {"format_id":"140","vcodec":"none","acodec":"mp4a","language":"en","ext":"m4a","abr":128,"asr":48000,"format_note":"original","language_preference":1,"audio_track":{"display_name":"English"}},
                {"format_id":"249","vcodec":"none","acodec":"opus","language":"ru","ext":"webm","abr":80,"asr":48000,"format_note":"Russian","audio_track":{"display_name":"Русский"}},
                {"format_id":"250","vcodec":"none","acodec":"opus","language":"de","ext":"webm","abr":90,"asr":48000,"format_note":"German","audio_track":{"display_name":"Deutsch"}},
                {"format_id":"18","vcodec":"avc1","acodec":"mp4a","language":"ja","ext":"mp4","height":360,"tbr":500,"format_note":"default","audio_track":{"display_name":"日本語"}},
                {"format_id":"137-ja","vcodec":"avc1","acodec":"mp4a","language":"ja","ext":"mp4","height":1080,"tbr":2500,"format_note":"default","audio_track":{"display_name":"日本語"}}
              ],
              "subtitles": {
                "en": [{"name":"English"}],
                "ru": [{"name":"Русский"}]
              },
              "automatic_captions": {
                "ja": [{"name":"日本語"}],
                "de": [{"name":"Deutsch"}],
                "live_chat": [{"name":"Chat"}]
              }
            }
        """.trimIndent()
    }
}
