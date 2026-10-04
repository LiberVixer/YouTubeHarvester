package com.liberivixer.youtubeharvester.ui.screens

import android.text.format.DateUtils
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.CleaningServices
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.Button
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.liberivixer.youtubeharvester.AppViewModel
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.media.MediaUrlParser
import com.liberivixer.youtubeharvester.model.AppUiState
import com.liberivixer.youtubeharvester.quick.QuickDownloadIntegration
import com.liberivixer.youtubeharvester.ui.BorderedPanel
import com.liberivixer.youtubeharvester.ui.Divider
import com.liberivixer.youtubeharvester.ui.DownloadOptionsSheet
import com.liberivixer.youtubeharvester.ui.downloadStatusLabel
import com.liberivixer.youtubeharvester.ui.contentTypeLabel
import com.liberivixer.youtubeharvester.ui.RemoteThumbnail
import com.liberivixer.youtubeharvester.ui.ScreenTitle
import com.liberivixer.youtubeharvester.ui.theme.ErrorRed
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.CheckOutcome
import com.liberivixer.youtubeharvester.model.SectionStatus
import com.liberivixer.youtubeharvester.model.SectionResult
import com.liberivixer.youtubeharvester.model.dailyDownloads
import com.liberivixer.youtubeharvester.model.overviewChannel
import com.liberivixer.youtubeharvester.model.ChannelItem
import com.liberivixer.youtubeharvester.download.HarvestPhase
import java.time.Instant
import java.time.ZoneId
import kotlinx.coroutines.delay

@Composable
fun OverviewScreen(state: AppUiState, viewModel: AppViewModel) {
    val context = LocalContext.current
    val stackLinkActions = LocalDensity.current.fontScale > 1.3f
    var url by rememberSaveable { mutableStateOf("") }
    val invalidUrl = url.isNotBlank() && MediaUrlParser.parse(url) == null
    var showDownloadOptions by rememberSaveable { mutableStateOf(false) }
    val scrollState = rememberScrollState()
    val clipboardEmpty = stringResource(R.string.clipboard_empty)
    var nowEpochMs by rememberSaveable { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(DateUtils.MINUTE_IN_MILLIS)
            nowEpochMs = System.currentTimeMillis()
        }
    }
    LaunchedEffect(url) { viewModel.inspectUrl(url) }
    LaunchedEffect(state.quickDownloadRequestId, state.pendingQuickDownloadUrl) {
        val quickUrl = state.pendingQuickDownloadUrl ?: return@LaunchedEffect
        val requestId = state.quickDownloadRequestId
        url = quickUrl
        if (viewModel.prepareDownloadOptions(quickUrl)) showDownloadOptions = true
        viewModel.consumeQuickDownloadRequest(requestId)
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(bottom = 20.dp),
    ) {
        ScreenTitle(stringResource(R.string.overview))
        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                placeholder = { Text(stringResource(R.string.url_hint)) },
                singleLine = true,
                isError = invalidUrl,
                supportingText = if (invalidUrl) {
                    { Text(stringResource(R.string.invalid_media_link)) }
                } else null,
                modifier = Modifier.fillMaxWidth(),
            )
            FlowRow(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                OutlinedButton(
                    onClick = { if (viewModel.addToQueue(url)) url = "" },
                    enabled = !state.isPreviewLoading,
                    modifier = (if (stackLinkActions) Modifier.fillMaxWidth() else Modifier.weight(1f)).heightIn(min = 52.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 8.dp, vertical = 8.dp),
                ) {
                    Text(stringResource(R.string.add_to_queue), fontSize = 14.sp, maxLines = 2)
                }
                FilledTonalButton(
                    onClick = {
                        val text = QuickDownloadIntegration.clipboardText(context)
                        if (text == null) viewModel.reportStatus(clipboardEmpty)
                        else if (viewModel.downloadClipboardLink(text)) url = ""
                    },
                    enabled = state.settingsLoaded,
                    modifier = (if (stackLinkActions) Modifier.fillMaxWidth() else Modifier.weight(0.8f)).heightIn(min = 52.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 4.dp, vertical = 8.dp),
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.Bolt, contentDescription = null, modifier = Modifier.size(18.dp))
                        Text(stringResource(R.string.quick), fontSize = 12.sp, maxLines = 2,
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                    }
                }
                Button(
                    onClick = { if (viewModel.downloadQuickLink(url)) url = "" },
                    enabled = url.isNotBlank() && !state.isPreviewLoading,
                    modifier = (if (stackLinkActions) Modifier.fillMaxWidth() else Modifier.weight(1f)).heightIn(min = 52.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 8.dp, vertical = 8.dp),
                ) {
                    Text(stringResource(R.string.download), fontSize = 14.sp, maxLines = 2)
                }
            }
        }

        FlowRow(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 14.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            StatusChip("📺", stringResource(R.string.channels_count, state.channels.size))
            StatusChip("📥", stringResource(R.string.queue_count, state.queue.size))
            StatusChip("🗃", stringResource(R.string.archive_count, state.archive.size))
        }

        BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
            Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val channel = state.overviewChannel()
                    OverviewChannelAvatar(channel)
                    Spacer(Modifier.size(10.dp))
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(channel?.name?.takeIf(String::isNotBlank) ?: stringResource(R.string.app_name),
                            fontSize = 18.sp, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        Text(stringResource(when {
                            channel != null -> R.string.overview_checking_channel
                            state.harvestPhase == HarvestPhase.QUEUE_BEFORE -> R.string.harvest_queue_before
                            state.harvestPhase == HarvestPhase.QUEUE_AFTER -> R.string.harvest_queue_after
                            else -> R.string.waiting_for_download
                        }), fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Spacer(Modifier.size(10.dp))
                    IconButton(
                        onClick = viewModel::runChannelCheck,
                        enabled = state.settingsLoaded,
                        modifier = Modifier.size(64.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primary),
                    ) {
                        Icon(if (state.isScanning) Icons.Default.Stop else Icons.Default.Download,
                            contentDescription = stringResource(if (state.isScanning) R.string.stop_check else R.string.harvest_start),
                            modifier = Modifier.size(34.dp), tint = MaterialTheme.colorScheme.onPrimary)
                    }
                }
                FlowRow(Modifier.fillMaxWidth().padding(top = 4.dp),
                    horizontalArrangement = Arrangement.SpaceBetween, verticalArrangement = Arrangement.spacedBy(6.dp),
                    itemVerticalAlignment = Alignment.CenterVertically) {
                    val checked = if (state.isScanning) state.scannedChannels else state.lastCheck?.checkedChannels ?: 0
                    val total = if (state.isScanning) state.scanTotalChannels else state.lastCheck?.totalChannels ?: state.channels.size
                    Text("${stringResource(R.string.channel_check)}  $checked / $total",
                        modifier = Modifier.padding(end = 8.dp), fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                    val lastCheck = state.lastCheck?.finishedAt ?: 0L
                    StatusChip("⏱", if (lastCheck > 0) DateUtils.getRelativeTimeSpanString(
                        lastCheck.coerceAtMost(nowEpochMs), nowEpochMs, DateUtils.MINUTE_IN_MILLIS,
                        DateUtils.FORMAT_ABBREV_RELATIVE,
                    ).toString() else stringResource(R.string.never_run))
                }
                LinearProgressIndicator(
                    progress = {
                        val total = if (state.isScanning) state.scanTotalChannels else state.lastCheck?.totalChannels ?: 0
                        val checked = if (state.isScanning) state.scannedChannels else state.lastCheck?.checkedChannels ?: 0
                        if (total > 0) (checked.toFloat() / total).coerceIn(0f, 1f) else 0f
                    },
                    modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)),
                )
                Column(verticalArrangement = Arrangement.spacedBy(18.dp), modifier = Modifier.padding(vertical = 8.dp)) {
                    OverviewContentLine(state, ContentType.Video, "📺")
                    OverviewContentLine(state, ContentType.Shorts, "⚡")
                    OverviewContentLine(state, ContentType.Stream, "●")
                }
                Divider()
                OverviewCheckReport(state, nowEpochMs)
            }
        }

        Spacer(Modifier.height(12.dp))
        BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
            OverviewPreview(state, viewModel)
        }

        state.downloadJobs.filter { it.status.isResumable }.forEach { job ->
            Spacer(Modifier.height(10.dp))
            BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                Column(Modifier.padding(12.dp)) {
                    Text(job.title, fontWeight = FontWeight.SemiBold, maxLines = 3, overflow = TextOverflow.Ellipsis)
                    Text(downloadStatusLabel(job.status), color = MaterialTheme.colorScheme.onSurfaceVariant)
                    job.errorMessage?.let { Text(it, fontSize = 13.sp) }
                    com.liberivixer.youtubeharvester.ui.DownloadJobControls(job, viewModel::pauseDownload, viewModel::resumeDownload, viewModel::cancelDownload)
                }
            }
        }

        OutlinedButton(
            onClick = viewModel::cleanupTemporaryFiles,
            modifier = Modifier.fillMaxWidth().padding(16.dp).heightIn(min = 48.dp),
        ) {
            Icon(Icons.Default.CleaningServices, contentDescription = null, modifier = Modifier.size(22.dp))
            Spacer(Modifier.size(8.dp))
            Text(stringResource(R.string.clear_temporary_files), modifier = Modifier.weight(1f),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        }
    }

    if (showDownloadOptions) {
        DownloadOptionsSheet(
            state = state,
            defaultResolution = state.settings.maxResolution,
            onDismiss = {
                showDownloadOptions = false
                viewModel.clearDownloadOptions()
            },
            onDownload = { resolution, audio, subtitles ->
                if (viewModel.downloadWithOptions(url, resolution, audio, subtitles)) {
                    url = ""
                    showDownloadOptions = false
                }
            },
            onAddToQueue = { resolution, audio, subtitles ->
                if (viewModel.addToQueueWithOptions(url, resolution, audio, subtitles)) {
                    url = ""
                    showDownloadOptions = false
                }
            },
        )
    }
}

@Composable
private fun OverviewChannelAvatar(channel: ChannelItem?) {
    val placeholder = painterResource(R.drawable.overview_logo)
    Box(Modifier.size(56.dp), contentAlignment = Alignment.Center) {
        val url = channel?.thumbnailUrl?.takeIf(String::isNotBlank)
        // Recreate image state for each channel so a previous avatar never flashes during loading.
        androidx.compose.runtime.key(channel?.id, url) {
            var loaded by androidx.compose.runtime.remember { mutableStateOf(false) }
            if (!loaded) {
                Image(placeholder, contentDescription = null, contentScale = ContentScale.Fit,
                    modifier = Modifier.fillMaxSize().clip(RoundedCornerShape(6.dp)))
            }
            if (url != null) {
                coil3.compose.AsyncImage(
                    model = url, contentDescription = channel.name, contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize().clip(CircleShape).alpha(if (loaded) 1f else 0f),
                    onSuccess = { loaded = true }, onError = { loaded = false },
                )
            }
        }
    }
}

@Composable
private fun OverviewContentLine(state: AppUiState, type: ContentType, symbol: String) {
    val label = contentTypeLabel(type)
    val section = (if (state.isScanning) state.scanSections[type] else state.lastCheck?.sections?.get(type)) ?: SectionResult()
    val active = state.downloadJobs.firstOrNull { it.contentType == type && it.status.isActive && it.status != com.liberivixer.youtubeharvester.model.DownloadStatus.QUEUED }
    var dots by androidx.compose.runtime.remember { androidx.compose.runtime.mutableIntStateOf(1) }
    val checking = state.isScanning && section.status == SectionStatus.CHECKING
    LaunchedEffect(checking) {
        while (checking) { delay(400); dots = dots % 3 + 1 }
    }
    val status = if (active != null) {
        "${downloadStatusLabel(active.status)}: ${active.progress}%"
    } else if (checking) {
        stringResource(R.string.overview_scanning) + ".".repeat(dots)
    } else {
        stringResource(when (section.status) {
            SectionStatus.CHECKED -> R.string.channel_checked
            SectionStatus.DISABLED -> R.string.disabled
            SectionStatus.FAILED -> R.string.status_failed
            SectionStatus.CHECKING -> R.string.channel_scan_stopped
            else -> R.string.status_queued
        })
    }
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
        Text(symbol, fontSize = 16.sp)
        Spacer(Modifier.size(7.dp))
        Text("$label: ${section.count} · $status", modifier = Modifier.weight(1f), fontSize = 16.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun OverviewCheckReport(state: AppUiState, now: Long) {
    val report = state.lastCheck
    val today = dailyDownloads(state.downloadJobs, state.archive, now, ZoneId.systemDefault())
    val errors = if (state.isScanning) state.sessionErrors else report?.errors ?: 0
    val heading = when {
        state.isScanning -> when (state.harvestPhase) {
            HarvestPhase.QUEUE_BEFORE -> R.string.harvest_queue_before
            HarvestPhase.QUEUE_AFTER -> R.string.harvest_queue_after
            else -> R.string.harvest_channels
        }
        report == null -> R.string.channel_not_checked
        report.outcome == CheckOutcome.STOPPED -> R.string.channel_scan_stopped
        report.outcome == CheckOutcome.FAILED -> R.string.channel_check_failed
        else -> R.string.overview_check_completed
    }
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f)).padding(6.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("${if (state.isScanning) "⏳" else if (report == null) "⏱" else if (errors > 0 || report.outcome != CheckOutcome.COMPLETED) "⚠" else "✅"} ${stringResource(heading)}",
            fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            report?.let {
                val date = java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")
                    .withZone(ZoneId.systemDefault()).format(Instant.ofEpochMilli(it.finishedAt))
                Text("⏱ $date", fontSize = 14.sp)
            }
            val downloaded = if (state.isScanning) state.sessionDownloads.values.sum() else report?.downloaded ?: 0
            val result = when {
                downloaded > 0 -> stringResource(R.string.overview_downloaded, downloaded)
                !state.isScanning && report?.outcome == CheckOutcome.COMPLETED && errors == 0 && report.attempted == 0 -> stringResource(R.string.overview_no_new)
                else -> stringResource(R.string.overview_downloaded, 0)
            }
            Text("📥 $result", fontSize = 14.sp)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("📅 ${stringResource(R.string.overview_today, today.values.sum())}", fontSize = 14.sp)
            Text("🎬 ${today[ContentType.Video] ?: 0}", fontSize = 14.sp)
            Text("⚡ ${today[ContentType.Shorts] ?: 0}", fontSize = 14.sp)
            Text("🔴 ${today[ContentType.Stream] ?: 0}", fontSize = 14.sp)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("📺 ${stringResource(R.string.overview_checked, if (state.isScanning) state.scannedChannels else report?.checkedChannels ?: 0,
                if (state.isScanning) state.scanTotalChannels else report?.totalChannels ?: state.channels.size)}", fontSize = 14.sp)
            Text("⚠ ${stringResource(R.string.overview_errors, errors)}", fontSize = 14.sp,
                color = if (errors > 0) ErrorRed else MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun OverviewPreview(state: AppUiState, viewModel: AppViewModel) {
    val preview = state.mediaPreview
    val activeDownload = state.downloadJobs.firstOrNull { it.status.isActive && it.status != com.liberivixer.youtubeharvester.model.DownloadStatus.QUEUED }
        ?: state.downloadJobs.lastOrNull { it.status.isActive }
    Column(modifier = Modifier.padding(12.dp)) {
        when {
            activeDownload != null -> {
                RemoteThumbnail(
                    url = activeDownload.thumbnailUrl,
                    fallbackText = activeDownload.source.label,
                    contentDescription = activeDownload.title,
                    modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f),
                )
                Spacer(Modifier.height(10.dp))
                Text(activeDownload.title, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, maxLines = 3, overflow = TextOverflow.Ellipsis)
                Text("${activeDownload.source.symbol}  ${activeDownload.channel}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
                Spacer(Modifier.height(9.dp))
                LinearProgressIndicator(
                    progress = { activeDownload.progress / 100f },
                    modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)),
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    stringResource(R.string.download_progress, downloadStatusLabel(activeDownload.status), activeDownload.progress),
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 14.sp,
                )
                Spacer(Modifier.height(8.dp))
                com.liberivixer.youtubeharvester.ui.DownloadJobControls(activeDownload, viewModel::pauseDownload, viewModel::resumeDownload, viewModel::cancelDownload)
            }
            state.isPreviewLoading -> {
                Box(
                    modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f).clip(RoundedCornerShape(6.dp)).background(MaterialTheme.colorScheme.surfaceVariant),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator()
                }
                Spacer(Modifier.height(10.dp))
                Text(stringResource(R.string.preview_loading), fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
            }
            preview != null -> {
                RemoteThumbnail(
                    url = preview.thumbnailUrl,
                    fallbackText = preview.source.label,
                    contentDescription = preview.title,
                    modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f),
                )
                Spacer(Modifier.height(10.dp))
                Text(preview.title, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, maxLines = 3, overflow = TextOverflow.Ellipsis)
                Text("${preview.source.symbol}  ${preview.channel}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
                preview.notice?.let {
                    Spacer(Modifier.height(5.dp))
                    Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                }
            }
            state.previewError != null -> {
                Image(
                    painter = painterResource(R.drawable.video_placeholder),
                    contentDescription = null,
                    modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f).clip(RoundedCornerShape(6.dp)),
                    contentScale = ContentScale.Crop,
                )
                Spacer(Modifier.height(10.dp))
                Text(stringResource(R.string.preview_unavailable), fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                Text(state.previewError, color = ErrorRed, fontSize = 14.sp)
            }
            else -> {
                Image(
                    painter = painterResource(R.drawable.video_placeholder),
                    contentDescription = stringResource(R.string.waiting_for_download),
                    modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f).clip(RoundedCornerShape(6.dp)),
                    contentScale = ContentScale.Crop,
                )
                Spacer(Modifier.height(10.dp))
                Text(stringResource(R.string.waiting_for_download), fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                Text(stringResource(R.string.add_link_or_scan), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
            }
        }
    }
}

@Composable
private fun StatusChip(symbol: String, label: String) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(6.dp),
    ) {
        Row(modifier = Modifier.padding(horizontal = 10.dp, vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(symbol)
            Spacer(Modifier.size(5.dp))
            Text(label, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}
