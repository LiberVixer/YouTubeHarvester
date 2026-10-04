package com.liberivixer.youtubeharvester.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ChannelDao {
    @Query("SELECT * FROM channels ORDER BY sort_order ASC, name COLLATE NOCASE ASC")
    fun observeAll(): Flow<List<ChannelEntity>>

    @Query("SELECT COUNT(*) FROM channels")
    suspend fun count(): Int

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(channel: ChannelEntity): Long

    @Query(
        """
        UPDATE channels SET
            videos_enabled = :videosEnabled,
            shorts_enabled = :shortsEnabled,
            streams_enabled = :streamsEnabled
        WHERE id = :id
        """,
    )
    suspend fun updateContentSelection(
        id: String,
        videosEnabled: Boolean,
        shortsEnabled: Boolean,
        streamsEnabled: Boolean,
    )

    @Query(
        """
        UPDATE channels SET
            name = :name,
            handle = :handle,
            thumbnail_url = :thumbnailUrl,
            paid_content = CASE WHEN paid_content = 'MembersOnly' THEN paid_content ELSE :paidContent END,
            status = :status,
            last_checked_epoch_ms = :lastCheckedEpochMs
        WHERE id = :id
        """,
    )
    suspend fun updateScanResult(
        id: String,
        name: String,
        handle: String,
        thumbnailUrl: String?,
        paidContent: String,
        status: String,
        lastCheckedEpochMs: Long,
    )

    @Query("UPDATE channels SET paid_content = :paidContent WHERE id = :id")
    suspend fun updatePaidContent(id: String, paidContent: String)

    @Query("DELETE FROM channels WHERE id = :id")
    suspend fun delete(id: String)
}
