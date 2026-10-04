package com.liberivixer.youtubeharvester.model

enum class ChannelFilter {
    All, Enabled, Disabled, NotChecked, Failed, MembersOnly, FreeOnly, UnknownPaid;

    fun matches(channel: ChannelItem): Boolean = when (this) {
        All -> true
        Enabled -> channel.videosEnabled || channel.shortsEnabled || channel.streamsEnabled
        Disabled -> !channel.videosEnabled && !channel.shortsEnabled && !channel.streamsEnabled
        NotChecked -> channel.status == CHANNEL_STATUS_NOT_CHECKED
        Failed -> channel.status == CHANNEL_STATUS_FAILED
        MembersOnly -> channel.paidContent == PaidContentStatus.MembersOnly
        FreeOnly -> channel.paidContent == PaidContentStatus.FreeOnly
        UnknownPaid -> channel.paidContent == PaidContentStatus.Unknown
    }
}

fun filterChannels(channels: List<ChannelItem>, query: String, filter: ChannelFilter): List<ChannelItem> {
    val search = query.trim()
    return channels.filter { channel ->
        filter.matches(channel) && listOf(channel.name, channel.handle, channel.url).any {
            it.contains(search, ignoreCase = true)
        }
    }
}
