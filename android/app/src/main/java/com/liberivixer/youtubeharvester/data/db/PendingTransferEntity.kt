package com.liberivixer.youtubeharvester.data.db

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query

@Entity(tableName = "pending_transfer")
data class PendingTransferEntity(
    @PrimaryKey val id: Int = 1,
    val encryptedSettings: String,
)

@Dao
interface PendingTransferDao {
    @Query("SELECT * FROM pending_transfer WHERE id = 1")
    suspend fun get(): PendingTransferEntity?

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(item: PendingTransferEntity)

    @Query("DELETE FROM pending_transfer WHERE id = 1")
    suspend fun clear()
}
