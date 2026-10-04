package com.liberivixer.youtubeharvester.download

internal enum class BootDownloadAction { NONE, START, PROMPT }

internal fun bootDownloadAction(sdk: Int, pendingCount: Int): BootDownloadAction = when {
    pendingCount <= 0 -> BootDownloadAction.NONE
    // Android 15 disallows dataSync foreground services started from BOOT_COMPLETED.
    sdk >= 35 -> BootDownloadAction.PROMPT
    else -> BootDownloadAction.START
}
