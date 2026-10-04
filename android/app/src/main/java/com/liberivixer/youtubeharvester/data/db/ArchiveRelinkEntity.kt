package com.liberivixer.youtubeharvester.data.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Entity(tableName = "archive_relinks", primaryKeys = ["source", "media_id", "resolution", "variant_key"])
data class ArchiveRelinkEntity(
    val source: String,
    @ColumnInfo(name = "media_id") val mediaId: String,
    val resolution: String,
    @ColumnInfo(name = "variant_key") val variantKey: String,
    @ColumnInfo(name = "file_name") val fileName: String,
    @ColumnInfo(name = "file_size") val fileSize: Long,
    val sha256: String,
)

@Dao
interface ArchiveRelinkDao {
    @Query("SELECT * FROM archive_relinks")
    suspend fun getAll(): List<ArchiveRelinkEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: ArchiveRelinkEntity)

    @Query("DELETE FROM archive_relinks WHERE source = :source AND media_id = :mediaId AND resolution = :resolution AND variant_key = :variantKey")
    suspend fun delete(source: String, mediaId: String, resolution: String, variantKey: String)
}
