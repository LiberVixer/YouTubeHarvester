package com.liberivixer.youtubeharvester.model

import com.liberivixer.youtubeharvester.download.HarvestPhase
import org.junit.Assert.*
import org.junit.Test

class OverviewChannelTest {
    private val first = ChannelItem("first", "https://example.test/first", "First", "", "https://example.test/first.png")
    private val second = first.copy(id = "second", name = "Second", thumbnailUrl = "https://example.test/second.png")
    private val active = AppUiState(channels = listOf(first, second), isScanning = true,
        harvestPhase = HarvestPhase.CHANNELS, activeScanChannelId = first.id)

    @Test fun showsTheCurrentChannelFromStoredChannels() {
        assertEquals(first, active.overviewChannel())
    }

    @Test fun stoppedOrIdleAlwaysUsesPlaceholderEvenWithStaleScanData() {
        assertNull(active.copy(isScanning = false, scanChannel = first).overviewChannel())
    }

    @Test fun bothQueuePassesUsePlaceholder() {
        assertNull(active.copy(harvestPhase = HarvestPhase.QUEUE_BEFORE).overviewChannel())
        assertNull(active.copy(harvestPhase = HarvestPhase.QUEUE_AFTER).overviewChannel())
    }

    @Test fun freshMetadataOverridesCachedChannel() {
        val updated = first.copy(name = "Updated", thumbnailUrl = "https://example.test/fresh.png")
        assertEquals(updated, active.copy(scanChannel = updated).overviewChannel())
    }

    @Test fun switchingChannelNeverReusesPreviousChannelMetadata() {
        assertEquals(second, active.copy(activeScanChannelId = second.id, scanChannel = first).overviewChannel())
        assertNull(active.copy(activeScanChannelId = "missing", scanChannel = first).overviewChannel())
    }

    @Test fun completionAndSectionValidationAreHandled() {
        assertNull(active.copy(activeScanChannelId = null, scanChannel = first).overviewChannel())
        assertEquals(first, active.copy(harvestPhase = null).overviewChannel())
    }
}
