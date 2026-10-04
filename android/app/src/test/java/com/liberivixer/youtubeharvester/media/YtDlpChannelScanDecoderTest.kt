package com.liberivixer.youtubeharvester.media

import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.MediaSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class YtDlpChannelScanDecoderTest {
    @Test(expected = IncompleteChannelListException::class)
    fun rejectsPartialListAfterFailedPage() {
        YtDlpChannelScanDecoder.decodeResponse(
            """{"entries":[{"id":"59212d9fdaf8dd15df9e1eb74edc9093"}]}""",
            "ERROR: Unable to download JSON metadata: SSL timeout on page 3", 1,
            ContentType.Video, MediaSource.Rutube, collection = true,
        )
    }

    @Test(expected = IncompleteChannelListException::class)
    fun rejectsErrorEvenIfExtractorReportsSuccess() {
        YtDlpChannelScanDecoder.decodeResponse("""{"entries":[]}""", "ERROR: Page not available", 0,
            ContentType.Video, MediaSource.Rutube, collection = true)
    }

    @Test(expected = IncompleteChannelListException::class)
    fun missingListIsNotAnEmptyChannel() {
        YtDlpChannelScanDecoder.decode("""{"title":"Titans"}""", ContentType.Video, MediaSource.Rutube, true)
    }

    @Test
    fun emptyListAndWarningsAreAllowedButRutubeHasNoYoutubePaidStatus() {
        val scan = YtDlpChannelScanDecoder.decodeResponse("""{"entries":[]}""",
            "WARNING: members-only", 0, ContentType.Video, MediaSource.Rutube, false)
        assertTrue(scan.entries.isEmpty())
        assertTrue(scan.available)
        assertFalse(scan.paidContentSeen)
    }

    @Test
    fun nullMetadataFallsBackToRealUploader() {
        val scan = YtDlpChannelScanDecoder.decode(
            """{"channel":null,"title":"23704195","entries":[{"id":"59212d9fdaf8dd15df9e1eb74edc9093","uploader":"RUTUBE"}]}""",
            ContentType.Video, MediaSource.Rutube,
        )
        assertEquals("RUTUBE", scan.channelName)
    }

    @Test
    fun rutubeEntriesKeepTheirSourceAndNeverBecomeYoutubeLinks() {
        val id = "59212d9fdaf8dd15df9e1eb74edc9093"
        val result = YtDlpChannelScanDecoder.decode(
            """{"title":"Titans","entries":[{"id":"$id","uploader":"TNT","title":"Final"},{"id":"dQw4w9WgXcQ"}]}""",
            ContentType.Video, MediaSource.Rutube, collection = true,
        )
        assertEquals("Titans", result.channelName)
        assertEquals(1, result.entries.size)
        assertEquals("https://rutube.ru/video/$id/", result.entries.single().url)
        assertEquals(MediaSource.Rutube, result.entries.single().source)
        assertFalse(result.paidContentSeen)
    }

    @Test
    fun rutubeChannelUsesUploaderNameAndDoesNotDetectYoutubeMembers() {
        val result = YtDlpChannelScanDecoder.decode(
            """{"entries":[{"id":"59212d9fdaf8dd15df9e1eb74edc9093","uploader":"RUTUBE","title":"members-only"}]}""",
            ContentType.Shorts, MediaSource.Rutube,
        )
        assertEquals("RUTUBE", result.channelName)
        assertFalse(result.entries.single().membersOnly)
        assertFalse(result.paidContentSeen)
    }

    @Test
    fun decodesFlatPlaylistMetadataAndEntries() {
        val result = YtDlpChannelScanDecoder.decode(
            """
            {
              "channel": "PRO Hi-Tech",
              "channel_id": "UC1234567890",
              "channel_thumbnail": "https://example.com/avatar.jpg",
              "entries": [
                {"id":"dQw4w9WgXcQ","title":"First","thumbnails":[{"url":"small"},{"url":"large"}]},
                {"id":"05h8f6kX6g8","title":"Second","channel":"Resolved channel"},
                {"id":"invalid id","title":"Ignored"},
                {"id":"dQw4w9WgXcQ","title":"Duplicate"}
              ]
            }
            """.trimIndent(),
            ContentType.Shorts,
        )

        assertEquals("PRO Hi-Tech", result.channelName)
        assertEquals("UC1234567890", result.channelHandle)
        assertEquals("https://example.com/avatar.jpg", result.channelThumbnailUrl)
        assertEquals(2, result.entries.size)
        assertEquals(ContentType.Shorts, result.entries.first().contentType)
        assertEquals("large", result.entries.first().thumbnailUrl)
        assertEquals("Resolved channel", result.entries.last().channel)
        assertFalse(result.paidContentSeen)
    }

    @Test
    fun detectsMembersOnlyAvailabilityInFlatEntries() {
        val result = YtDlpChannelScanDecoder.decode(
            """{"entries":[{"id":"dQw4w9WgXcQ","title":"Members","availability":"subscriber_only"}]}""",
            ContentType.Video,
        )

        assertTrue(result.paidContentSeen)
        assertTrue(result.entries.single().membersOnly)
        assertTrue(hasPaidContentMarker("Join this channel to access members-only content"))
    }
}
