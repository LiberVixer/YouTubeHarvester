package com.liberivixer.youtubeharvester.ui.screens

import android.os.Build
import android.text.format.Formatter
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.liberivixer.youtubeharvester.BuildConfig
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.model.AppUiState
import java.text.DateFormat
import java.util.Date

@Composable
fun DiagnosticsDialog(
    state: AppUiState,
    onDismiss: () -> Unit,
    onRefresh: () -> Unit,
    onShare: (String) -> Unit,
) {
    val report = diagnosticsReport(state)
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.diagnostics_report)) },
        text = {
            Column {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        if (state.isDiagnosticsLoading) {
                            stringResource(R.string.diagnostics_checking)
                        } else {
                            state.diagnosticsError.orEmpty()
                        },
                        modifier = Modifier.weight(1f),
                        color = if (state.diagnosticsError != null) {
                            MaterialTheme.colorScheme.error
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                        fontSize = 13.sp,
                    )
                    if (state.isDiagnosticsLoading) {
                        CircularProgressIndicator(modifier = Modifier.size(24.dp), strokeWidth = 2.dp)
                    } else {
                        IconButton(onClick = onRefresh) {
                            Icon(Icons.Default.Refresh, contentDescription = stringResource(R.string.refresh))
                        }
                    }
                }
                Spacer(Modifier.size(8.dp))
                Surface(
                    modifier = Modifier.fillMaxWidth().heightIn(min = 260.dp, max = 480.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = MaterialTheme.shapes.small,
                ) {
                    SelectionContainer {
                        Text(
                            report,
                            modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(12.dp),
                            fontFamily = FontFamily.Monospace,
                            fontSize = 12.sp,
                            lineHeight = 17.sp,
                        )
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onShare(report) },
                enabled = !state.isDiagnosticsLoading && !state.isLogLoading,
            ) {
                Icon(Icons.Default.Share, contentDescription = null)
                Spacer(Modifier.size(5.dp))
                Text(stringResource(R.string.share))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.close)) }
        },
    )
}

@Composable
private fun diagnosticsReport(state: AppUiState): String {
    val context = LocalContext.current
    val appVersion = stringResource(R.string.app_version)
    val androidVersion = stringResource(R.string.android_version)
    val device = stringResource(R.string.device)
    val supportedAbis = stringResource(R.string.supported_abis)
    val downloadDestination = stringResource(R.string.download_destination)
    val schedules = stringResource(R.string.schedules_count)
    val channels = stringResource(R.string.channels)
    val queue = stringResource(R.string.queue_short)
    val archive = stringResource(R.string.archive)
    val checkedAt = stringResource(R.string.diagnostics_checked_at)
    val runtime = stringResource(R.string.runtime_initialization)
    val network = stringResource(R.string.network_status)
    val validated = stringResource(R.string.connection_validated)
    val unvalidated = stringResource(R.string.connection_unvalidated)
    val unavailable = stringResource(R.string.diagnostic_unavailable)
    val notifications = stringResource(R.string.notifications_permission)
    val folderAccess = stringResource(R.string.download_folder_access)
    val freeStorage = stringResource(R.string.free_storage)
    val battery = stringResource(R.string.battery_optimization)
    val optimized = stringResource(R.string.battery_optimized)
    val unrestricted = stringResource(R.string.battery_unrestricted)
    val ok = "OK"
    val attention = stringResource(R.string.diagnostic_attention)
    val snapshot = state.diagnostics
    return buildString {
        appendLine("YouTube Harvester")
        appendLine("$appVersion: ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
        appendLine("$androidVersion: ${Build.VERSION.RELEASE} / API ${Build.VERSION.SDK_INT}")
        appendLine("$device: ${Build.MANUFACTURER} ${Build.MODEL}")
        appendLine("$supportedAbis: ${Build.SUPPORTED_ABIS.joinToString()}")
        appendLine("$downloadDestination: ${state.settings.downloadDirectory}")
        appendLine("$channels: ${state.channels.size}")
        appendLine("$queue: ${state.queue.size}")
        appendLine("$archive: ${state.archive.size}")
        appendLine("$schedules: ${state.schedule.count { it.enabled }} / ${state.schedule.size}")
        appendLine()
        if (snapshot == null) {
            append(stringResource(R.string.diagnostics_not_run))
            return@buildString
        }
        appendLine("$checkedAt: ${DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.MEDIUM).format(Date(snapshot.checkedAtEpochMs))}")
        appendLine("$runtime: ${if (snapshot.runtimeReady) ok else attention}")
        snapshot.runtimeError?.let { appendLine("  $it") }
        appendLine("yt-dlp: ${snapshot.ytDlpVersion ?: unavailable}")
        appendLine("FFmpeg / ffprobe: ${if (snapshot.ffmpegBundled && snapshot.runtimeReady) ok else attention}")
        appendLine("QuickJS: ${if (snapshot.quickJsBundled) ok else attention}")
        appendLine(
            "$network: ${when {
                snapshot.networkValidated -> validated
                snapshot.networkConnected -> unvalidated
                else -> unavailable
            }}",
        )
        appendLine("$notifications: ${if (snapshot.notificationsAllowed) ok else attention}")
        appendLine("$folderAccess: ${if (snapshot.downloadDestinationAccessible) ok else attention}")
        appendLine("$freeStorage: ${snapshot.availableStorageBytes?.let { Formatter.formatFileSize(context, it) } ?: unavailable}")
        append("$battery: ${if (snapshot.batteryOptimizationExempt) unrestricted else optimized}")
    }
}
