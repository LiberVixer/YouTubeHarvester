package com.liberivixer.youtubeharvester.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index

@Entity(
    tableName = "archive_items",
    primaryKeys = ["source", "media_id", "resolution", "variant_key"],
    indices = [Index(value = ["downloaded_at_epoch_ms"])],
)
data class ArchiveEntity(
    val source: String,
    @ColumnInfo(name = "media_id") val mediaId: String,
    val title: String,
    val channel: String,
    @ColumnInfo(name = "thumbnail_url") val thumbnailUrl: String?,
    @ColumnInfo(name = "content_type") val contentType: String,
    val resolution: String,
    @ColumnInfo(name = "variant_key", defaultValue = "'default'") val variantKey: String,
    @ColumnInfo(name = "downloaded_at") val downloadedAt: String,
    @ColumnInfo(name = "downloaded_at_epoch_ms") val downloadedAtEpochMs: Long,
    @ColumnInfo(name = "file_exists") val fileExists: Boolean,
    @ColumnInfo(name = "file_uri") val fileUri: String?,
    @ColumnInfo(name = "audio_json") val audioJson: String,
    @ColumnInfo(name = "subtitles_json") val subtitlesJson: String,
)
