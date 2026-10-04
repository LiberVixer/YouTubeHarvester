package com.liberivixer.youtubeharvester.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.liberivixer.youtubeharvester.model.DownloadStatus
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.storedDownloadStatus
import com.liberivixer.youtubeharvester.model.stringResource

@Composable
fun downloadStatusLabel(status: DownloadStatus): String = stringResource(status.stringResource())

@Composable
fun queueStatusLabel(storedStatus: String): String {
    val status = storedDownloadStatus(storedStatus)
    return status?.let { downloadStatusLabel(it) } ?: storedStatus
}

@Composable
fun contentTypeLabel(contentType: ContentType): String = stringResource(
    when (contentType) {
        ContentType.Video -> com.liberivixer.youtubeharvester.R.string.video
        ContentType.Shorts -> com.liberivixer.youtubeharvester.R.string.shorts
        ContentType.Stream -> com.liberivixer.youtubeharvester.R.string.streams
        ContentType.Queue -> com.liberivixer.youtubeharvester.R.string.queue_short
    },
)
