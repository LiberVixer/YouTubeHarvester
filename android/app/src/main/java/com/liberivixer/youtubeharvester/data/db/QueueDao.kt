package com.liberivixer.youtubeharvester.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface QueueDao {
    @Query("SELECT * FROM queue_items ORDER BY sort_order ASC")
    fun observeAll(): Flow<List<QueueEntity>>

    @Query("SELECT * FROM queue_items ORDER BY sort_order ASC")
    suspend fun getAll(): List<QueueEntity>

    @Query("SELECT COUNT(*) FROM queue_items")
    suspend fun count(): Int

    @Query("SELECT * FROM queue_items WHERE selected = 1 ORDER BY sort_order ASC")
    suspend fun getSelected(): List<QueueEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: QueueEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(items: List<QueueEntity>)

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertIfMissing(item: QueueEntity): Long

    @Query("UPDATE queue_items SET selected = :selected WHERE source = :source AND media_id = :mediaId")
    suspend fun setSelected(source: String, mediaId: String, selected: Boolean)

    @Query("UPDATE queue_items SET status = :status WHERE source = :source AND media_id = :mediaId")
    suspend fun setStatus(source: String, mediaId: String, status: String)

    suspend fun updateFromJob(job: DownloadJobEntity, status: String) {
        if (job.fromQueue) setStatus(job.source, job.mediaId, status)
    }

    @Query("DELETE FROM queue_items WHERE source = :source AND media_id = :mediaId")
    suspend fun delete(source: String, mediaId: String)

    @Query("DELETE FROM queue_items WHERE source = :source AND media_id = :mediaId AND origin_channel_id IS NOT NULL")
    suspend fun deleteDiscovered(source: String, mediaId: String)

}
