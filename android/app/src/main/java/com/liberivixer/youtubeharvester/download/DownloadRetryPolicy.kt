package com.liberivixer.youtubeharvester.download

import com.liberivixer.youtubeharvester.model.DownloadStatus

internal object DownloadRetryPolicy {
    const val MAX_RETRIES = 3
    const val NETWORK_WAIT_SECONDS = 60

    fun phaseForLine(previous: DownloadStatus, line: String): DownloadStatus = when {
        line.startsWith("YTH_POSTPROCESS") || listOf("[HarvestTracks]", "[Merger]", "[Metadata]", "[EmbedSubtitle", "[Fixup", "[VideoConvertor]", "[VideoRemuxer]").any(line::startsWith) -> DownloadStatus.PROCESSING
        line.startsWith("[download]") -> DownloadStatus.DOWNLOADING
        else -> previous
    }

    fun isNetworkError(message: String): Boolean {
        val lower = message.lowercase()
        return listOf(
            "connection reset", "errno 104", "errno104", "connection aborted",
            "network is unreachable", "network unreachable", "no route to host",
            "temporary failure in name resolution", "unable to resolve host",
            "name or service not known", "timed out", "timeout", "remote end closed",
            "connection refused", "incomplete read", "incompleteread",
            "unexpected_eof_while_reading", "eof occurred in violation of protocol",
        ).any(lower::contains)
    }

    fun isUnavailableMediaError(message: String): Boolean {
        val lower = message.lowercase()
        return listOf(
            "video unavailable", "no longer available", "has been deleted",
            "http error 403", "http error 404",
        ).any(lower::contains)
    }

    fun isStorageFullError(message: String): Boolean {
        val lower = message.lowercase()
        return listOf(
            "no space left on device", "errno 28", "errno28", "enospc",
            "disk full", "storage is full", "storage full",
            "insufficient storage", "insufficient space", "not enough space",
            "disk quota exceeded",
        ).any(lower::contains)
    }
}
