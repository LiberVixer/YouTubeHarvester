package com.liberivixer.youtubeharvester.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "download_jobs",
    indices = [
        Index(value = ["status", "created_at_epoch_ms"]),
        Index(value = ["source", "media_id"]),
    ],
)
data class DownloadJobEntity(
    @PrimaryKey @ColumnInfo(name = "job_id") val jobId: String,
    val source: String,
    @ColumnInfo(name = "media_id") val mediaId: String,
    val url: String,
    val title: String,
    val channel: String,
    @ColumnInfo(name = "content_type", defaultValue = "'Video'") val contentType: String,
    @ColumnInfo(name = "origin_channel_id") val originChannelId: String?,
    @ColumnInfo(name = "thumbnail_url") val thumbnailUrl: String?,
    val resolution: String,
    val status: String,
    val progress: Int,
    @ColumnInfo(name = "eta_seconds") val etaSeconds: Long?,
    val message: String,
    @ColumnInfo(name = "created_at_epoch_ms") val createdAtEpochMs: Long,
    @ColumnInfo(name = "updated_at_epoch_ms") val updatedAtEpochMs: Long,
    @ColumnInfo(name = "file_uri") val fileUri: String?,
    @ColumnInfo(name = "error_message") val errorMessage: String?,
    @ColumnInfo(name = "from_queue") val fromQueue: Boolean,
    @ColumnInfo(name = "audio_json", defaultValue = "'[]'") val audioJson: String,
    @ColumnInfo(name = "subtitles_json", defaultValue = "'[]'") val subtitlesJson: String,
    @ColumnInfo(name = "retry_count", defaultValue = "0") val retryCount: Int = 0,
)
