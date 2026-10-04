package com.liberivixer.youtubeharvester.download

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.data.db.HarvesterDatabase
import com.liberivixer.youtubeharvester.model.DownloadStatus
import com.liberivixer.youtubeharvester.ui.LocaleController

class DownloadTimeoutWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result {
        val id = inputData.getString("job") ?: return Result.failure()
        val db = HarvesterDatabase.getInstance(applicationContext)
        val dao = db.downloadJobDao()
        val job = dao.get(id) ?: return Result.success()
        // A later attempt or a committed archive record must never be rolled back.
        val message = LocaleController.wrap(applicationContext).getString(R.string.service_error_android_timeout)
        if (runAttemptCount == 0) {
            if (dao.markTimedOut(id, inputData.getLong("timeout", 0), message, System.currentTimeMillis()) == 0) return Result.success()
        } else if (job.status != DownloadStatus.FAILED.name) return Result.success()
        db.queueDao().updateFromJob(job, DownloadStatus.FAILED.name)
        return try {
            job.fileUri?.let {
                DownloadOutputPublisher(applicationContext).deletePublished(it)
                dao.recordPublication(id, null)
            }
            // Keep staging data so the visible failed job can be resumed by the user.
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }

    companion object {
        fun enqueue(context: Context, jobId: String) {
            val work = OneTimeWorkRequestBuilder<DownloadTimeoutWorker>()
                .setInputData(workDataOf("job" to jobId, "timeout" to System.currentTimeMillis()))
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork("download-timeout-$jobId", ExistingWorkPolicy.KEEP, work)
        }
    }
}
