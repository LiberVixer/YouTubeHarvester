package com.liberivixer.youtubeharvester.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ArchiveDao {
    @Query("SELECT * FROM archive_items ORDER BY downloaded_at_epoch_ms DESC, source ASC, media_id ASC, resolution ASC")
    fun observeAll(): Flow<List<ArchiveEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: ArchiveEntity)

    @Query("SELECT * FROM archive_items WHERE source = :source AND media_id = :mediaId AND resolution = :resolution AND variant_key = :variantKey LIMIT 1")
    suspend fun get(source: String, mediaId: String, resolution: String, variantKey: String): ArchiveEntity?

    @Query("SELECT EXISTS(SELECT 1 FROM archive_items WHERE source = :source AND media_id = :mediaId LIMIT 1)")
    suspend fun containsMedia(source: String, mediaId: String): Boolean

    @Query("UPDATE archive_items SET file_exists = :fileExists WHERE source = :source AND media_id = :mediaId AND resolution = :resolution AND variant_key = :variantKey")
    suspend fun setFileExists(source: String, mediaId: String, resolution: String, variantKey: String, fileExists: Boolean)

    @Query("DELETE FROM archive_items WHERE source = :source AND media_id = :mediaId AND resolution = :resolution AND variant_key = :variantKey")
    suspend fun delete(source: String, mediaId: String, resolution: String, variantKey: String)
}
