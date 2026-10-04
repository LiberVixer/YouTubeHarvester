package com.liberivixer.youtubeharvester.model

import java.time.Instant
import java.time.ZoneId

fun dailyDownloads(jobs: List<DownloadJob>, archive: List<ArchiveItem>, now: Long, zone: ZoneId): Map<ContentType, Int> {
    val date = Instant.ofEpochMilli(now).atZone(zone).toLocalDate()
    val start = date.atStartOfDay(zone).toInstant().toEpochMilli()
    val end = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
    val completed = jobs.filter { it.status == DownloadStatus.COMPLETED && it.updatedAtEpochMs in start until end }
    val files = completed.mapNotNull { it.fileUri }.toSet()
    // Legacy archive entries can predate durable jobs. Do not count the same publication twice.
    val legacy = archive.filter { it.downloadedAtEpochMs in start until end && it.fileUri !in files }
    return (completed.map { it.contentType } + legacy.map { it.type }).groupingBy { it }.eachCount()
}
