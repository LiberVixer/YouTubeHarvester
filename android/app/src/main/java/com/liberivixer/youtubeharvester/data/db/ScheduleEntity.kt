package com.liberivixer.youtubeharvester.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "check_schedules",
    indices = [Index(value = ["hour", "minute"])],
)
data class ScheduleEntity(
    @PrimaryKey val id: String,
    val hour: Int,
    val minute: Int,
    val enabled: Boolean,
    @ColumnInfo(name = "last_run_epoch_ms") val lastRunEpochMs: Long?,
    @ColumnInfo(name = "created_at_epoch_ms") val createdAtEpochMs: Long,
)
