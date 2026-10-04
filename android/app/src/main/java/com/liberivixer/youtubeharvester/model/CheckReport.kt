package com.liberivixer.youtubeharvester.model

enum class SectionStatus { WAITING, CHECKING, CHECKED, DISABLED, FAILED }

data class SectionResult(val count: Int = 0, val status: SectionStatus = SectionStatus.WAITING)

enum class CheckOutcome { COMPLETED, STOPPED, FAILED }

data class CheckReport(
    val finishedAt: Long,
    val outcome: CheckOutcome,
    val checkedChannels: Int,
    val totalChannels: Int,
    val errors: Int,
    val downloaded: Int,
    val sections: Map<ContentType, SectionResult> = emptyMap(),
    val attempted: Int = 0,
)

val overviewContentTypes = listOf(ContentType.Video, ContentType.Shorts, ContentType.Stream)
