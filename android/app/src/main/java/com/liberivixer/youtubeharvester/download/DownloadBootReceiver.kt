package com.liberivixer.youtubeharvester.download

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.data.db.HarvesterDatabase
import com.liberivixer.youtubeharvester.logging.AppLogLevel
import com.liberivixer.youtubeharvester.logging.AppLogStore
import com.liberivixer.youtubeharvester.ui.LocaleController
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class DownloadBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != Intent.ACTION_BOOT_COMPLETED) return
        val pending = goAsync()
        val app = context.applicationContext
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val count = HarvesterDatabase.getInstance(app).downloadJobDao().pendingCount()
                when (bootDownloadAction(Build.VERSION.SDK_INT, count)) {
                    BootDownloadAction.NONE -> Unit
                    BootDownloadAction.START -> {
                        try {
                            DownloadServiceController.start(app)
                            AppLogStore(app).append(AppLogLevel.INFO, "Download", "Boot recovery started pending=$count")
                        } catch (error: Exception) {
                            AppLogStore(app).append(AppLogLevel.ERROR, "Download", "Boot start denied: ${error.javaClass.simpleName}")
                            DownloadBootNotification.show(app)
                        }
                    }
                    BootDownloadAction.PROMPT -> DownloadBootNotification.show(app)
                }
            } catch (error: Exception) {
                AppLogStore(app).append(AppLogLevel.ERROR, "Download", "Boot recovery failed: ${error.javaClass.simpleName}")
            } finally {
                pending.finish()
            }
        }
    }
}

internal object DownloadBootNotification {
    private const val ID = 25002
    private const val CHANNEL = "download_recovery"

    fun show(context: Context) {
        val localized = LocaleController.wrap(context)
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL,
            localized.getString(R.string.service_download_channel_name), NotificationManager.IMPORTANCE_DEFAULT))
        val intent = Intent(context, DownloadForegroundService::class.java)
            .setAction(DownloadForegroundService.ACTION_RUN)
        val resume = PendingIntent.getForegroundService(context, ID, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_download)
            .setContentTitle(localized.getString(R.string.download_recovery_title))
            .setContentText(localized.getString(R.string.download_recovery_text))
            .setContentIntent(resume)
            .addAction(R.drawable.ic_stat_download, localized.getString(R.string.download_resume), resume)
            .setAutoCancel(true)
            .build()
        manager.notify(ID, notification)
    }

    fun clear(context: Context) {
        context.getSystemService(NotificationManager::class.java).cancel(ID)
    }
}
