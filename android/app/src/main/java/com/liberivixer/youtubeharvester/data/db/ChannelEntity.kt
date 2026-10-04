package com.liberivixer.youtubeharvester.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "channels",
    indices = [Index(value = ["sort_order"])],
)
data class ChannelEntity(
    @PrimaryKey val id: String,
    val url: String,
    val name: String,
    val handle: String,
    @ColumnInfo(name = "thumbnail_url") val thumbnailUrl: String?,
    @ColumnInfo(name = "videos_enabled") val videosEnabled: Boolean,
    @ColumnInfo(name = "shorts_enabled") val shortsEnabled: Boolean,
    @ColumnInfo(name = "streams_enabled") val streamsEnabled: Boolean,
    @ColumnInfo(name = "paid_content") val paidContent: String,
    val status: String,
    @ColumnInfo(name = "last_checked_epoch_ms") val lastCheckedEpochMs: Long?,
    @ColumnInfo(name = "sort_order") val sortOrder: Int,
)
