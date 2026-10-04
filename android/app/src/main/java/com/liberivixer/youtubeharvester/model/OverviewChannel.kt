package com.liberivixer.youtubeharvester.model

import com.liberivixer.youtubeharvester.download.HarvestPhase

fun AppUiState.overviewChannel(): ChannelItem? {
    if (!isScanning || harvestPhase == HarvestPhase.QUEUE_BEFORE || harvestPhase == HarvestPhase.QUEUE_AFTER) return null
    val id = activeScanChannelId ?: return null
    return scanChannel?.takeIf { it.id == id } ?: channels.firstOrNull { it.id == id }
}
