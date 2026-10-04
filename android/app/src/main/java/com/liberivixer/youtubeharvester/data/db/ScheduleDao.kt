package com.liberivixer.youtubeharvester.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ScheduleDao {
    @Query("SELECT * FROM check_schedules ORDER BY hour ASC, minute ASC, created_at_epoch_ms ASC")
    fun observeAll(): Flow<List<ScheduleEntity>>

    @Query("SELECT * FROM check_schedules ORDER BY hour ASC, minute ASC, created_at_epoch_ms ASC")
    suspend fun getAll(): List<ScheduleEntity>

    @Query("SELECT * FROM check_schedules WHERE id = :id LIMIT 1")
    suspend fun get(id: String): ScheduleEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: ScheduleEntity)

    @Query("UPDATE check_schedules SET enabled = :enabled WHERE id = :id")
    suspend fun setEnabled(id: String, enabled: Boolean)

    @Query("UPDATE check_schedules SET last_run_epoch_ms = :lastRunEpochMs WHERE id = :id")
    suspend fun markRun(id: String, lastRunEpochMs: Long)

    @Query("DELETE FROM check_schedules WHERE id = :id")
    suspend fun delete(id: String)
}
