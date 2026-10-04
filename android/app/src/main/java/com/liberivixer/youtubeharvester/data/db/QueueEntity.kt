package com.liberivixer.youtubeharvester.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index

@Entity(
    tableName = "queue_items",
    primaryKeys = ["source", "media_id"],
    indices = [Index(value = ["sort_order"])],
)
data class QueueEntity(
    val source: String,
    @ColumnInfo(name = "media_id") val mediaId: String,
    val url: String,
    val title: String,
    val channel: String,
    @ColumnInfo(name = "content_type", defaultValue = "'Video'") val contentType: String,
    @ColumnInfo(name = "origin_channel_id") val originChannelId: String?,
    @ColumnInfo(name = "thumbnail_url") val thumbnailUrl: String?,
    val resolution: String,
    val selected: Boolean,
    val status: String,
    @ColumnInfo(name = "audio_json", defaultValue = "'[]'") val audioJson: String,
    @ColumnInfo(name = "subtitles_json", defaultValue = "'[]'") val subtitlesJson: String,
    @ColumnInfo(name = "sort_order") val sortOrder: Int,
)
