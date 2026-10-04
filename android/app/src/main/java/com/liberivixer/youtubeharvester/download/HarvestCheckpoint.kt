package com.liberivixer.youtubeharvester.download

import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.SectionResult

data class PendingHarvestDownload(val key: String, val jobId: String, val type: ContentType)

data class HarvestCheckpoint(
    val phase: HarvestPhase = HarvestPhase.QUEUE_BEFORE,
    val completedChannels: Int = 0,
    val scanErrors: Int = 0,
    val downloadErrors: Int = 0,
    val downloaded: Map<ContentType, Int> = emptyMap(),
    val attempted: Set<String> = emptySet(),
    val pending: PendingHarvestDownload? = null,
    val sections: Map<ContentType, SectionResult> = emptyMap(),
)
