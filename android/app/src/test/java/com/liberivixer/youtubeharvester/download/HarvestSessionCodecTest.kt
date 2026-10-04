package com.liberivixer.youtubeharvester.download

import com.liberivixer.youtubeharvester.model.*
import org.junit.Assert.*
import org.junit.Test

class HarvestSessionCodecTest {
    @Test fun preservesCursorPendingJobAndChannelOptionsWithoutCredentials() {
        val session = HarvestSession("session", listOf(ChannelItem("a", "https://example.test", "A", "@a",
            videosEnabled = false, paidContent = PaidContentStatus.MembersOnly)),
            AppSettings(videoLimit = 9, telegramBotToken = "secret"),
            HarvestCheckpoint(HarvestPhase.CHANNELS, 1, 2, 3, mapOf(ContentType.Shorts to 4), setOf("YouTube:old"),
                PendingHarvestDownload("YouTube:new", "job", ContentType.Video),
                mapOf(ContentType.Video to SectionResult(5, SectionStatus.CHECKED))), true)
        val raw = HarvestSessionCodec.encode(session)
        assertFalse(raw.contains("secret"))
        val restored = HarvestSessionCodec.decode(raw)
        assertEquals(session.channels, restored.channels)
        assertEquals(session.checkpoint, restored.checkpoint)
        assertEquals(9, restored.settings.videoLimit)
        assertTrue(restored.stopRequested)
    }
}
