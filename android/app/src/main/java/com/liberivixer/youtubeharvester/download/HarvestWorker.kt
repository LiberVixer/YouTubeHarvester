package com.liberivixer.youtubeharvester.download

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.*
import com.liberivixer.youtubeharvester.MainActivity
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.data.AndroidAppRepository
import com.liberivixer.youtubeharvester.logging.AppLogLevel
import com.liberivixer.youtubeharvester.logging.AppLogStore
import com.liberivixer.youtubeharvester.model.CheckOutcome
import com.liberivixer.youtubeharvester.model.CheckReport
import com.liberivixer.youtubeharvester.ui.LocaleController
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first

object HarvestCoordinator {
    private const val WORK = "harvest-cycle"
    private val liveProgress = MutableStateFlow<HarvestProgress?>(null)
    val progress = liveProgress.asStateFlow()
    internal fun report(progress: HarvestProgress?) { liveProgress.value = progress }

    suspend fun start(context: Context): Boolean {
        val repository = AndroidAppRepository(context)
        repository.initialize()
        val store = HarvestSessionStore(context)
        val session = HarvestSession(channels = repository.channels.first(), settings = repository.settings.first())
        if (!store.begin(session)) return false
        enqueue(context, ExistingWorkPolicy.APPEND_OR_REPLACE)
        return true
    }

    suspend fun ensure(context: Context) {
        if (HarvestSessionStore(context).current() != null) enqueue(context, ExistingWorkPolicy.KEEP)
    }

    suspend fun stop(context: Context) {
        HarvestSessionStore(context).stop()
        ensure(context)
    }

    private suspend fun enqueue(context: Context, policy: ExistingWorkPolicy) = withContext(Dispatchers.IO) {
        WorkManager.getInstance(context).enqueueUniqueWork(WORK, policy,
            OneTimeWorkRequestBuilder<HarvestWorker>().build()).result.get()
        Unit
    }
}

class HarvestWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result {
        val store = HarvestSessionStore(applicationContext)
        val session = try { store.current() ?: return Result.success() }
        catch (error: CancellationException) { throw error }
        catch (error: Exception) {
            AppLogStore(applicationContext).append(AppLogLevel.ERROR, "Harvest", "Session read failed: ${error.javaClass.simpleName}")
            return if (runAttemptCount < 3) Result.retry() else Result.failure()
        }
        val repository = AndroidAppRepository(applicationContext)
        var complete = false
        try {
            setForeground(getForegroundInfo())
            repository.initialize()
            if (repository.hasPendingDownloads()) DownloadServiceController.start(applicationContext)
            coroutineScope {
                val execution = async {
                    if (store.current()?.stopRequested == true) throw CancellationException("User stopped harvest")
                    HarvestCycleRunner(applicationContext, repository, session.id).run(
                        session.channels, session.settings, session.checkpoint,
                        saveCheckpoint = { store.checkpoint(session.id, it) }, cancelOnInterruption = false,
                        onProgress = HarvestCoordinator::report)
                }
                val stopWatcher = launch {
                    store.sessions.first { it?.id != session.id || it.stopRequested }
                    execution.cancel()
                }
                try { execution.await() } finally { stopWatcher.cancelAndJoin() }
            }
            complete = true
            return Result.success()
        } catch (error: CancellationException) {
            withContext(NonCancellable) {
                val current = store.current()
                if (current?.id == session.id && current.stopRequested) {
                    current.checkpoint.pending?.let { DownloadServiceController.cancel(applicationContext, it.jobId) }
                    saveInterruptedReport(repository, current, CheckOutcome.STOPPED)
                    complete = true
                }
            }
            if (complete) return Result.success()
            throw error
        } catch (error: Exception) {
            AppLogStore(applicationContext).append(AppLogLevel.ERROR, "Harvest", "Cycle interrupted: ${error.javaClass.simpleName}")
            if (runAttemptCount < 3) return Result.retry()
            store.current()?.takeIf { it.id == session.id }?.let { saveInterruptedReport(repository, it, CheckOutcome.FAILED) }
            complete = true
            return Result.failure()
        } finally {
            withContext(NonCancellable) { if (complete) store.clear(session.id) }
            HarvestCoordinator.report(null)
        }
    }

    private suspend fun saveInterruptedReport(repository: AndroidAppRepository, session: HarvestSession, outcome: CheckOutcome) {
        val c = session.checkpoint
        repository.saveCheckReport(CheckReport(System.currentTimeMillis(), outcome, c.completedChannels, session.channels.size,
            c.scanErrors + c.downloadErrors + if (outcome == CheckOutcome.FAILED) 1 else 0,
            c.downloaded.values.sum(), c.sections, c.attempted.size))
    }

    override suspend fun getForegroundInfo(): ForegroundInfo {
        val context = LocaleController.wrap(applicationContext)
        val channel = "harvest_cycles"
        applicationContext.getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(channel, context.getString(R.string.background_check_channel), NotificationManager.IMPORTANCE_LOW))
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        val notification = NotificationCompat.Builder(applicationContext, channel)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle(context.getString(R.string.background_check_title))
            .setContentText(context.getString(R.string.background_check_text))
            .setOngoing(true).setOnlyAlertOnce(true)
            .setContentIntent(PendingIntent.getActivity(applicationContext, 0, Intent(applicationContext, MainActivity::class.java), flags))
            .addAction(android.R.drawable.ic_media_pause, context.getString(R.string.stop_check),
                PendingIntent.getBroadcast(applicationContext, 0, Intent(applicationContext, HarvestStopReceiver::class.java), flags))
            .build()
        return ForegroundInfo(25001, notification, if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC else 0)
    }
}

class HarvestStopReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val result = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try { HarvestCoordinator.stop(context.applicationContext) }
            catch (error: Exception) {
                AppLogStore(context.applicationContext).append(AppLogLevel.ERROR, "Harvest", "Stop failed: ${error.javaClass.simpleName}")
            }
            finally { result.finish() }
        }
    }
}
