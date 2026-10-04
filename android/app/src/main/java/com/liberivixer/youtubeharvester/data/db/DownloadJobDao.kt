package com.liberivixer.youtubeharvester.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import kotlinx.coroutines.flow.Flow

@Dao
interface DownloadJobDao {
    @Query("SELECT * FROM download_jobs ORDER BY created_at_epoch_ms DESC")
    fun observeAll(): Flow<List<DownloadJobEntity>>

    @Query("SELECT * FROM download_jobs WHERE job_id = :jobId")
    suspend fun get(jobId: String): DownloadJobEntity?

    @Query("SELECT * FROM download_jobs WHERE status = 'QUEUED' ORDER BY CASE WHEN from_queue = 0 AND origin_channel_id IS NULL THEN 0 ELSE 1 END, created_at_epoch_ms ASC LIMIT 1")
    suspend fun nextQueued(): DownloadJobEntity?

    @Query("UPDATE download_jobs SET status = 'INITIALIZING', updated_at_epoch_ms = :now WHERE job_id = :jobId AND status = 'QUEUED'")
    suspend fun claim(jobId: String, now: Long): Int

    @Query("UPDATE download_jobs SET status = 'CANCELLED', message = 'CANCELLED', updated_at_epoch_ms = :now WHERE job_id = :jobId AND status IN ('QUEUED', 'PAUSED', 'FAILED')")
    suspend fun cancelQueued(jobId: String, now: Long): Int

    @Query("UPDATE download_jobs SET status = 'FAILED', message = 'FAILED', error_message = :message, updated_at_epoch_ms = :now WHERE job_id = :jobId AND updated_at_epoch_ms <= :cutoff AND status IN ('INITIALIZING', 'DOWNLOADING', 'PROCESSING', 'WAITING_NETWORK', 'PUBLISHING')")
    suspend fun markTimedOut(jobId: String, cutoff: Long, message: String, now: Long): Int

    @Transaction
    suspend fun claimNext(now: Long): DownloadJobEntity? {
        val job = nextQueued() ?: return null
        return if (claim(job.jobId, now) == 1) job else null
    }

    @Query("UPDATE download_jobs SET file_uri = :uri WHERE job_id = :jobId")
    suspend fun recordPublication(jobId: String, uri: String?)

    @Query("SELECT * FROM download_jobs WHERE file_uri IS NOT NULL AND status != 'COMPLETED'")
    suspend fun unfinishedPublications(): List<DownloadJobEntity>

    @Query("SELECT COUNT(*) FROM download_jobs WHERE status IN ('QUEUED', 'INITIALIZING', 'DOWNLOADING', 'PROCESSING', 'WAITING_NETWORK', 'PUBLISHING')")
    suspend fun pendingCount(): Int

    @Query("DELETE FROM download_jobs WHERE status IN ('COMPLETED', 'FAILED', 'CANCELLED') AND (status = 'COMPLETED' OR file_uri IS NULL) AND updated_at_epoch_ms < :cutoffEpochMs")
    suspend fun deleteTerminalBefore(cutoffEpochMs: Long)

    @Query("SELECT job_id FROM download_jobs WHERE source = :source AND media_id = :mediaId AND resolution = :resolution AND audio_json = :audioJson AND subtitles_json = :subtitlesJson AND status IN ('QUEUED', 'INITIALIZING', 'DOWNLOADING', 'PROCESSING', 'WAITING_NETWORK', 'PUBLISHING', 'PAUSED', 'FAILED') ORDER BY CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END, created_at_epoch_ms DESC LIMIT 1")
    suspend fun findActiveJobId(
        source: String,
        mediaId: String,
        resolution: String,
        audioJson: String,
        subtitlesJson: String,
    ): String?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: DownloadJobEntity)

    @Query("UPDATE download_jobs SET status = 'QUEUED', eta_seconds = NULL, message = 'QUEUED', updated_at_epoch_ms = :updatedAt WHERE status IN ('INITIALIZING', 'DOWNLOADING', 'PROCESSING', 'WAITING_NETWORK', 'PUBLISHING')")
    suspend fun resetInterrupted(updatedAt: Long)

    @Query("UPDATE download_jobs SET status = 'QUEUED', eta_seconds = NULL, message = 'QUEUED', error_message = NULL, retry_count = 0, updated_at_epoch_ms = :now WHERE job_id = :jobId AND status IN ('PAUSED', 'FAILED') AND file_uri IS NULL")
    suspend fun resume(jobId: String, now: Long): Int

    @Query("UPDATE download_jobs SET status = 'PAUSED', eta_seconds = NULL, message = 'PAUSED', updated_at_epoch_ms = :now WHERE job_id = :jobId AND status IN ('QUEUED', 'INITIALIZING', 'DOWNLOADING', 'WAITING_NETWORK')")
    suspend fun pause(jobId: String, now: Long): Int

    @Query("UPDATE download_jobs SET status = 'PAUSED', message = 'PAUSED', updated_at_epoch_ms = :now WHERE job_id = :jobId AND status = 'QUEUED'")
    suspend fun pauseQueued(jobId: String, now: Long): Int

    @Query("UPDATE download_jobs SET retry_count = retry_count + 1, status = 'WAITING_NETWORK', eta_seconds = NULL, message = 'WAITING_NETWORK', updated_at_epoch_ms = :now WHERE job_id = :jobId AND retry_count < :limit AND status IN ('INITIALIZING', 'DOWNLOADING', 'WAITING_NETWORK')")
    suspend fun scheduleRetry(jobId: String, limit: Int, now: Long): Int

    @Query("UPDATE download_jobs SET status = :status, progress = :progress, eta_seconds = :etaSeconds, message = :message, updated_at_epoch_ms = :updatedAt WHERE job_id = :jobId")
    suspend fun updateProgress(
        jobId: String,
        status: String,
        progress: Int,
        etaSeconds: Long?,
        message: String,
        updatedAt: Long,
    )

    @Query("UPDATE download_jobs SET subtitles_json = :subtitlesJson, message = :message, updated_at_epoch_ms = :updatedAt WHERE job_id = :jobId")
    suspend fun updateSubtitleSelections(jobId: String, subtitlesJson: String, message: String, updatedAt: Long)

    @Query("UPDATE download_jobs SET status = 'COMPLETED', progress = 100, eta_seconds = NULL, message = :message, file_uri = :fileUri, error_message = NULL, updated_at_epoch_ms = :updatedAt WHERE job_id = :jobId")
    suspend fun markCompleted(jobId: String, fileUri: String, message: String, updatedAt: Long)

    @Query("UPDATE download_jobs SET status = 'FAILED', eta_seconds = NULL, message = :message, error_message = :errorMessage, updated_at_epoch_ms = :updatedAt WHERE job_id = :jobId")
    suspend fun markFailed(jobId: String, message: String, errorMessage: String, updatedAt: Long)

    @Query("UPDATE download_jobs SET status = 'CANCELLED', eta_seconds = NULL, message = :message, error_message = NULL, updated_at_epoch_ms = :updatedAt WHERE job_id = :jobId")
    suspend fun markCancelled(jobId: String, message: String, updatedAt: Long)
}
