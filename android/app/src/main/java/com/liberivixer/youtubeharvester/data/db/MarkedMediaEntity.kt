package com.liberivixer.youtubeharvester.data.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Entity(tableName = "marked_media", primaryKeys = ["source", "media_id"])
data class MarkedMediaEntity(
    val source: String,
    @ColumnInfo(name = "media_id") val mediaId: String,
    @ColumnInfo(name = "marked_at_epoch_ms") val markedAtEpochMs: Long,
)

@Dao
interface MarkedMediaDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(item: MarkedMediaEntity): Long

    @Query("SELECT EXISTS(SELECT 1 FROM marked_media WHERE source = :source AND media_id = :mediaId)")
    suspend fun contains(source: String, mediaId: String): Boolean
}
