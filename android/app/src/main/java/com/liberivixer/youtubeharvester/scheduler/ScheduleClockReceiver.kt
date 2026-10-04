package com.liberivixer.youtubeharvester.scheduler

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.liberivixer.youtubeharvester.data.AndroidAppRepository
import com.liberivixer.youtubeharvester.logging.AppLogLevel
import com.liberivixer.youtubeharvester.logging.AppLogStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class ScheduleClockReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action !in setOf(Intent.ACTION_TIME_CHANGED, Intent.ACTION_TIMEZONE_CHANGED)) return
        val result = goAsync()
        val app = context.applicationContext
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Only dispatch timers are replaced; the shared active harvest is untouched.
                AndroidAppRepository(app).getSchedules().forEach { DailyCheckScheduler.replace(app, it) }
            } catch (error: Exception) {
                AppLogStore(app).append(AppLogLevel.ERROR, "Schedule", "Clock reschedule failed: ${error.javaClass.simpleName}")
            } finally { result.finish() }
        }
    }
}
