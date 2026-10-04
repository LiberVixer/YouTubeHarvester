package com.liberivixer.youtubeharvester.scheduler

import android.content.Context
import androidx.work.Constraints
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.liberivixer.youtubeharvester.model.ScheduleItem
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime
import java.util.concurrent.TimeUnit

object DailyCheckScheduler {
    fun ensure(context: Context, item: ScheduleItem) {
        if (!item.enabled) {
            cancel(context, item.id)
            return
        }
        enqueue(context, item, ExistingWorkPolicy.KEEP)
    }

    fun replace(context: Context, item: ScheduleItem) {
        if (!item.enabled) {
            cancel(context, item.id)
            return
        }
        enqueue(context, item, ExistingWorkPolicy.REPLACE)
    }

    fun appendNext(context: Context, item: ScheduleItem) {
        if (item.enabled) enqueue(context, item, ExistingWorkPolicy.APPEND_OR_REPLACE)
    }

    fun cancel(context: Context, scheduleId: String) {
        WorkManager.getInstance(context.applicationContext).cancelUniqueWork(workName(scheduleId))
    }

    private fun enqueue(context: Context, item: ScheduleItem, policy: ExistingWorkPolicy) {
        val delay = nextRunDelayMillis(item.hour, item.minute)
        val request = OneTimeWorkRequestBuilder<ChannelCheckWorker>()
            .setInputData(Data.Builder().putString(ChannelCheckWorker.KEY_SCHEDULE_ID, item.id).build())
            .setInitialDelay(delay, TimeUnit.MILLISECONDS)
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build(),
            )
            .addTag(workName(item.id))
            .build()
        WorkManager.getInstance(context.applicationContext)
            .enqueueUniqueWork(workName(item.id), policy, request)
    }

    private fun workName(scheduleId: String) = "daily-channel-check-$scheduleId"
}

internal fun nextRunDelayMillis(
    hour: Int,
    minute: Int,
    nowEpochMs: Long = System.currentTimeMillis(),
    zoneId: ZoneId = ZoneId.systemDefault(),
): Long {
    val now = ZonedDateTime.ofInstant(Instant.ofEpochMilli(nowEpochMs), zoneId)
    var target = now.toLocalDate().atTime(hour, minute).atZone(zoneId)
    if (!target.isAfter(now)) {
        target = now.toLocalDate().plusDays(1).atTime(hour, minute).atZone(zoneId)
    }
    return Duration.between(now, target).toMillis().coerceAtLeast(1L)
}
