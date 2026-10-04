package com.liberivixer.youtubeharvester.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.model.DownloadJob
import com.liberivixer.youtubeharvester.model.DownloadStatus

@Composable
fun DownloadJobControls(job: DownloadJob, onPause: (String) -> Unit, onResume: (String) -> Unit, onCancel: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        if (job.status.canPause || job.status.isResumable) {
            val retry = job.status == DownloadStatus.FAILED
            val resume = job.status.isResumable
            OutlinedButton(onClick = { if (resume) onResume(job.jobId) else onPause(job.jobId) }) {
                Icon(if (retry) Icons.Default.Refresh else if (resume) Icons.Default.PlayArrow else Icons.Default.Pause, null)
                Spacer(Modifier.size(6.dp))
                Text(stringResource(if (retry) R.string.download_retry else if (resume) R.string.download_resume else R.string.download_pause))
            }
        }
        OutlinedButton(onClick = { onCancel(job.jobId) }) {
            Icon(Icons.Default.Close, null)
            Spacer(Modifier.size(6.dp))
            Text(stringResource(R.string.cancel))
        }
    }
}
