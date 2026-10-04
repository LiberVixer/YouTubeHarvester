package com.liberivixer.youtubeharvester.model

import org.junit.Assert.assertEquals
import org.junit.Test

class ChannelFilterTest {
    private val base = ChannelItem("a", "https://www.youtube.com/@alpha", "Alpha", "@alpha")
    private val disabled = base.copy(id = "b", name = "Beta", videosEnabled = false, shortsEnabled = false, streamsEnabled = false)

    @Test
    fun `enabled and disabled filters are complementary`() {
        val shortsOnly = base.copy(id = "c", videosEnabled = false, streamsEnabled = false)
        val channels = listOf(base, disabled, shortsOnly)
        assertEquals(listOf(base, shortsOnly), filterChannels(channels, "", ChannelFilter.Enabled))
        assertEquals(listOf(disabled), filterChannels(channels, "", ChannelFilter.Disabled))
    }

    @Test
    fun `search trims input and combines with filter without reordering`() {
        assertEquals(listOf(disabled), filterChannels(listOf(base, disabled), " BETA ", ChannelFilter.Disabled))
        assertEquals(emptyList<ChannelItem>(), filterChannels(listOf(base, disabled), " BETA ", ChannelFilter.Enabled))
        assertEquals(listOf(base, disabled), filterChannels(listOf(base, disabled), " YOUTUBE.COM ", ChannelFilter.All))
    }

    @Test
    fun `failed and unchecked statuses remain separate`() {
        val failed = base.copy(id = "f", status = CHANNEL_STATUS_FAILED)
        val checked = base.copy(id = "c", status = CHANNEL_STATUS_CHECKED)
        val channels = listOf(base, failed, checked)
        assertEquals(listOf(failed), filterChannels(channels, "", ChannelFilter.Failed))
        assertEquals(listOf(base), filterChannels(channels, "", ChannelFilter.NotChecked))
    }

    @Test
    fun `paid filters never classify unknown status as free`() {
        val members = base.copy(id = "m", paidContent = PaidContentStatus.MembersOnly)
        val free = base.copy(id = "f", paidContent = PaidContentStatus.FreeOnly)
        val channels = listOf(base, members, free)
        assertEquals(listOf(base), filterChannels(channels, "", ChannelFilter.UnknownPaid))
        assertEquals(listOf(members), filterChannels(channels, "", ChannelFilter.MembersOnly))
        assertEquals(listOf(free), filterChannels(channels, "", ChannelFilter.FreeOnly))
    }
}
