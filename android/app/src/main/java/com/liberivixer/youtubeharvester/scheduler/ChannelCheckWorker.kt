package com.liberivixer.youtubeharvester.scheduler

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.liberivixer.youtubeharvester.data.AndroidAppRepository
import com.liberivixer.youtubeharvester.download.HarvestCoordinator
import com.liberivixer.youtubeharvester.logging.AppLogLevel
import com.liberivixer.youtubeharvester.logging.AppLogStore
import kotlinx.coroutines.CancellationException

class ChannelCheckWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result {
        val id = inputData.getString(KEY_SCHEDULE_ID) ?: return Result.failure()
        val repository = AndroidAppRepository(applicationContext)
        val schedule = repository.getSchedule(id) ?: return Result.success()
        if (!schedule.enabled) return Result.success()
        return try {
            val started = HarvestCoordinator.start(applicationContext)
            AppLogStore(applicationContext).append(AppLogLevel.INFO, "Scheduled check",
                if (started) "Cycle dispatched" else "An existing cycle is already active")
            repository.markScheduleRun(id, System.currentTimeMillis())
            repository.getSchedule(id)?.takeIf { it.enabled }?.let { DailyCheckScheduler.appendNext(applicationContext, it) }
            Result.success()
        } catch (error: CancellationException) { throw error
        } catch (_: Exception) { Result.retry() }
    }

    companion object { const val KEY_SCHEDULE_ID = "schedule_id" }
}
