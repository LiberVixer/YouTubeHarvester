package com.liberivixer.youtubeharvester.download

import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat

object DownloadServiceController {
    fun start(context: Context) {
        val intent = Intent(context, DownloadForegroundService::class.java).setAction(DownloadForegroundService.ACTION_RUN)
        ContextCompat.startForegroundService(context, intent)
    }

    fun cancel(context: Context, jobId: String) {
        val intent = Intent(context, DownloadForegroundService::class.java)
            .setAction(DownloadForegroundService.ACTION_CANCEL)
            .putExtra(DownloadForegroundService.EXTRA_JOB_ID, jobId)
        ContextCompat.startForegroundService(context, intent)
    }

    fun pause(context: Context, jobId: String) = command(context, jobId, DownloadForegroundService.ACTION_PAUSE)
    fun resume(context: Context, jobId: String) = command(context, jobId, DownloadForegroundService.ACTION_RESUME)

    private fun command(context: Context, jobId: String, action: String) {
        ContextCompat.startForegroundService(context, Intent(context, DownloadForegroundService::class.java)
            .setAction(action).putExtra(DownloadForegroundService.EXTRA_JOB_ID, jobId))
    }
}
