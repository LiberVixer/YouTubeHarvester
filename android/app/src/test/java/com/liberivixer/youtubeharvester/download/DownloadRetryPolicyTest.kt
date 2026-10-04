package com.liberivixer.youtubeharvester.download

import com.liberivixer.youtubeharvester.model.DownloadStatus
import org.junit.Assert.*
import org.junit.Test

class DownloadRetryPolicyTest {
    @Test fun transientNetworkErrorsAreRecognized() {
        listOf("[Errno 104] Connection reset by peer", "Errno104", "Temporary failure in name resolution",
            "Network is unreachable", "Read timed out", "IncompleteRead(1024 bytes read)").forEach {
            assertTrue(it, DownloadRetryPolicy.isNetworkError(it))
        }
    }

    @Test fun permanentFailuresDoNotTriggerNetworkRetries() {
        listOf("Join this channel for members-only content", "HTTP Error 403", "Video unavailable",
            "No space left on device", "Permission denied",
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
            "[SSL: WRONG_VERSION_NUMBER] wrong version number").forEach {
            assertFalse(it, DownloadRetryPolicy.isNetworkError(it))
        }
        listOf(
            "ERROR: [vk] This video has been deleted and is no longer available.",
            "Unable to download video JSON: HTTP Error 404: Not Found",
            "Unable to download video JSON: HTTP Error 403: Forbidden",
            "Video unavailable",
        ).forEach { assertTrue(it, DownloadRetryPolicy.isUnavailableMediaError(it)) }
        listOf("No space left on device", "Connection reset by peer", "Private video").forEach {
            assertFalse(it, DownloadRetryPolicy.isUnavailableMediaError(it))
        }
    }

    @Test fun interruptedTlsDownloadTriggersNetworkRetry() {
        listOf(
            "ERROR: [download] Got error: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1010). Giving up after 1 retries",
            "[SSL: UNEXPECTED_EOF_WHILE_READING]",
            "EOF occurred in violation of protocol (_ssl.c:1010)",
        ).forEach { assertTrue(it, DownloadRetryPolicy.isNetworkError(it)) }
    }

    @Test fun storageExhaustionErrorsAreRecognized() {
        listOf(
            "ERROR: unable to write data: [Errno 28] No space left on device",
            "open failed: ENOSPC (No space left on device)",
            "Disk full",
            "Insufficient storage available",
            "Not enough space to complete the operation",
            "Disk quota exceeded",
        ).forEach { assertTrue(it, DownloadRetryPolicy.isStorageFullError(it)) }
        listOf("Permission denied", "Connection reset by peer", "Video unavailable").forEach {
            assertFalse(it, DownloadRetryPolicy.isStorageFullError(it))
        }
    }

    @Test fun postprocessingDisablesPauseDespiteStaleProgress() {
        val processing = DownloadRetryPolicy.phaseForLine(DownloadStatus.DOWNLOADING, "[Merger] Merging formats")
        assertEquals(DownloadStatus.PROCESSING, processing)
        assertFalse(processing.canPause)
        assertEquals(processing, DownloadRetryPolicy.phaseForLine(processing, "Deleting original file"))
        assertEquals(processing, DownloadRetryPolicy.phaseForLine(DownloadStatus.DOWNLOADING, "YTH_POSTPROCESS"))
        assertEquals(processing, DownloadRetryPolicy.phaseForLine(DownloadStatus.DOWNLOADING, "[HarvestTracks] Verifying and mapping selected tracks"))
    }

    @Test fun nextAudioStreamEnablesPauseAgain() {
        assertEquals(DownloadStatus.DOWNLOADING,
            DownloadRetryPolicy.phaseForLine(DownloadStatus.PROCESSING, "[download] Destination: audio.m4a"))
    }

    @Test fun resumableJobsKeepTheirFilesWithoutBeingActive() {
        for (status in listOf(DownloadStatus.PAUSED, DownloadStatus.FAILED)) {
            assertTrue(status.isResumable)
            assertTrue(status.retainsFiles)
            assertFalse(status.isActive)
        }
        assertFalse(DownloadStatus.CANCELLED.retainsFiles)
        assertFalse(DownloadStatus.COMPLETED.retainsFiles)
        assertFalse(DownloadStatus.PUBLISHING.canPause)
        assertTrue(DownloadStatus.WAITING_NETWORK.isActive)
    }
}
