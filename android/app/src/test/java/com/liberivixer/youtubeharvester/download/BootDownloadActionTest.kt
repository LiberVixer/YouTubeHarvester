package com.liberivixer.youtubeharvester.download

import org.junit.Assert.assertEquals
import org.junit.Test

class BootDownloadActionTest {
    @Test fun emptyQueueNeverStartsOrNotifies() {
        for (sdk in listOf(26, 31, 34, 35, 37)) {
            assertEquals(BootDownloadAction.NONE, bootDownloadAction(sdk, 0))
        }
    }

    @Test fun olderAndroidCanResumePendingDownloads() {
        for (sdk in listOf(26, 28, 31, 34)) {
            assertEquals(BootDownloadAction.START, bootDownloadAction(sdk, 1))
        }
    }

    @Test fun android15AndLaterRequireUserInteraction() {
        for (sdk in listOf(35, 36, 37)) {
            assertEquals(BootDownloadAction.PROMPT, bootDownloadAction(sdk, 2))
        }
    }
}
