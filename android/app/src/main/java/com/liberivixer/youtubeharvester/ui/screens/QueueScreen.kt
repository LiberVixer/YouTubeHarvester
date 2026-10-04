package com.liberivixer.youtubeharvester.ui.screens

import android.app.TimePickerDialog
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.ClosedCaption
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.ArrowDownward
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Headphones
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.liberivixer.youtubeharvester.AppViewModel
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.model.AppUiState
import com.liberivixer.youtubeharvester.model.DownloadJob
import com.liberivixer.youtubeharvester.model.QueueItem
import com.liberivixer.youtubeharvester.model.ScheduleItem
import com.liberivixer.youtubeharvester.ui.BorderedPanel
import com.liberivixer.youtubeharvester.ui.Divider
import com.liberivixer.youtubeharvester.ui.RemoteThumbnail
import com.liberivixer.youtubeharvester.ui.ScreenTitle
import com.liberivixer.youtubeharvester.ui.SectionTitle
import com.liberivixer.youtubeharvester.ui.downloadStatusLabel
import com.liberivixer.youtubeharvester.ui.contentTypeLabel
import com.liberivixer.youtubeharvester.ui.queueStatusLabel
import java.text.DateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

@Composable
fun QueueScreen(state: AppUiState, viewModel: AppViewModel) {
    var url by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(url) { viewModel.inspectUrl(url) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 20.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            ScreenTitle(
                title = stringResource(R.string.queue_short),
                count = state.queue.size,
                trailing = {
                    IconButton(onClick = viewModel::startSelectedDownloads) {
                        Icon(Icons.Default.Download, contentDescription = stringResource(R.string.download_selected))
                    }
                },
            )
        }
        item {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                OutlinedTextField(
                    value = url,
                    onValueChange = { url = it },
                    placeholder = { Text(stringResource(R.string.url_hint)) },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                Button(
                    onClick = { if (viewModel.addToQueue(url)) url = "" },
                    enabled = !state.isPreviewLoading,
                    modifier = Modifier.height(56.dp),
                ) { Icon(Icons.Default.Add, contentDescription = stringResource(R.string.add)) }
            }
        }
        item {
            BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                QueuePreview(state)
            }
        }
        item { SectionTitle(stringResource(R.string.queued_videos)) }
        if (state.queue.isEmpty()) {
            item {
                BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                    Column(modifier = Modifier.padding(horizontal = 18.dp, vertical = 22.dp)) {
                        Text(stringResource(R.string.empty_queue), fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(4.dp))
                        Text(
                            stringResource(R.string.empty_queue_hint),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 14.sp,
                        )
                    }
                }
            }
        }
        itemsIndexed(state.queue, key = { _, item -> "${item.source.name}:${item.id}" }) { index, item ->
            val activeJob = state.downloadJobs.firstOrNull {
                it.fromQueue && it.source == item.source && it.mediaId == item.id && it.resolution == item.resolution && it.status.retainsFiles
            }
            QueueItemCard(
                item,
                activeJob,
                onToggle = { viewModel.toggleQueueItem(item.source, item.id) },
                onCancel = { jobId -> viewModel.cancelDownload(jobId) },
                onPause = viewModel::pauseDownload,
                onResume = viewModel::resumeDownload,
                onDownload = { viewModel.startQueueItem(item) },
                onMoveUp = { viewModel.moveQueueItem(item, -1) },
                onMoveDown = { viewModel.moveQueueItem(item, 1) },
                onDelete = { viewModel.removeQueueItem(item) },
                canMoveUp = index > 0,
                canMoveDown = index < state.queue.lastIndex,
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }
        item {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedButton(
                    onClick = viewModel::removeSelectedQueueItems,
                    enabled = state.queue.any { candidate ->
                        candidate.selected && state.downloadJobs.none {
                            it.status.retainsFiles && it.source == candidate.source && it.mediaId == candidate.id
                        }
                    },
                    modifier = Modifier.weight(1f).height(48.dp),
                ) {
                    Icon(Icons.Default.Delete, contentDescription = null)
                    Spacer(Modifier.size(7.dp))
                    Text(stringResource(R.string.delete_selected), maxLines = 1)
                }
                IconButton(onClick = viewModel::startSelectedDownloads, modifier = Modifier.size(48.dp)) {
                    Icon(Icons.Default.Download, contentDescription = stringResource(R.string.download_selected))
                }
            }
        }
        item { SectionTitle(stringResource(R.string.scheduler)) }
        item {
            SchedulerPanel(
                schedule = state.schedule,
                onAdd = viewModel::addSchedule,
                onToggle = viewModel::toggleSchedule,
                onDelete = viewModel::deleteSchedule,
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }
    }
}

@Composable
private fun QueuePreview(state: AppUiState) {
    val preview = state.mediaPreview
    Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
        when {
            state.isPreviewLoading -> Box(
                modifier = Modifier.size(width = 132.dp, height = 78.dp).clip(RoundedCornerShape(5.dp)).background(MaterialTheme.colorScheme.surfaceVariant),
                contentAlignment = Alignment.Center,
            ) { CircularProgressIndicator(modifier = Modifier.size(30.dp)) }
            preview != null -> RemoteThumbnail(
                url = preview.thumbnailUrl,
                fallbackText = preview.source.label,
                contentDescription = preview.title,
                modifier = Modifier.size(width = 132.dp, height = 78.dp),
            )
            else -> Box(
                modifier = Modifier.size(width = 132.dp, height = 78.dp).clip(RoundedCornerShape(5.dp)).background(MaterialTheme.colorScheme.surfaceVariant),
                contentAlignment = Alignment.Center,
            ) { Text(stringResource(R.string.preview), fontSize = 11.sp, fontWeight = FontWeight.Bold) }
        }
        Spacer(Modifier.size(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            when {
                state.isPreviewLoading -> {
                    Text(stringResource(R.string.loading_data), fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                    Text(stringResource(R.string.preview_title_hint), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
                }
                preview != null -> {
                    Text(preview.title, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text("${preview.source.symbol}  ${preview.channel}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(preview.notice ?: stringResource(R.string.ready_to_add), color = MaterialTheme.colorScheme.primary, fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                state.previewError != null -> {
                    Text(stringResource(R.string.preview_unavailable), fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                    Text(state.previewError, color = MaterialTheme.colorScheme.error, fontSize = 13.sp, maxLines = 3, overflow = TextOverflow.Ellipsis)
                }
                else -> {
                    Text(stringResource(R.string.preview_prompt), fontSize = 17.sp, fontWeight = FontWeight.SemiBold, maxLines = 2)
                    Text(stringResource(R.string.preview_metadata_hint), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
                    Text(stringResource(R.string.ready_to_add), color = MaterialTheme.colorScheme.primary, fontSize = 14.sp)
                }
            }
        }
    }
}

@Composable
private fun QueueItemCard(
    item: QueueItem,
    activeJob: DownloadJob?,
    onToggle: () -> Unit,
    onCancel: (String) -> Unit,
    onPause: (String) -> Unit,
    onResume: (String) -> Unit,
    onDownload: () -> Unit,
    onMoveUp: () -> Unit,
    onMoveDown: () -> Unit,
    onDelete: () -> Unit,
    canMoveUp: Boolean,
    canMoveDown: Boolean,
    modifier: Modifier = Modifier,
) {
    var menuExpanded by rememberSaveable(item.source.name, item.id) { mutableStateOf(false) }
    BorderedPanel(modifier) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                item.title,
                fontSize = 17.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                RemoteThumbnail(
                    url = item.thumbnailUrl,
                    fallbackText = item.source.label,
                    contentDescription = item.title,
                    modifier = Modifier.size(70.dp),
                )
                Spacer(Modifier.size(11.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text("${item.source.symbol}  ${item.channel}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "${item.contentType.symbol} ${contentTypeLabel(item.contentType)} · ◷ ${queueStatusLabel(item.status)}",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 14.sp,
                    )
                    if (item.audioTracks.isNotEmpty()) {
                        QueueMediaOptionLine(
                            Icons.Default.Headphones,
                            item.audioTracks.joinToString { it.name.ifBlank { it.language } },
                        )
                    }
                    if (item.subtitleSelections.isNotEmpty()) {
                        QueueMediaOptionLine(
                            Icons.Default.ClosedCaption,
                            item.subtitleSelections.joinToString { it.substringAfter(':') },
                        )
                    }
                }
                Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(5.dp)) {
                    Text(item.resolution, modifier = Modifier.padding(horizontal = 7.dp, vertical = 5.dp), fontSize = 13.sp)
                }
                Checkbox(checked = item.selected, onCheckedChange = { onToggle() })
                if (activeJob == null) {
                    Box {
                        IconButton(onClick = { menuExpanded = true }, modifier = Modifier.size(36.dp)) {
                            Icon(Icons.Default.MoreVert, contentDescription = stringResource(R.string.actions))
                        }
                        DropdownMenu(expanded = menuExpanded, onDismissRequest = { menuExpanded = false }) {
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.move_up)) },
                                leadingIcon = { Icon(Icons.Default.ArrowUpward, contentDescription = null) },
                                enabled = canMoveUp,
                                onClick = { menuExpanded = false; onMoveUp() },
                            )
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.move_down)) },
                                leadingIcon = { Icon(Icons.Default.ArrowDownward, contentDescription = null) },
                                enabled = canMoveDown,
                                onClick = { menuExpanded = false; onMoveDown() },
                            )
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.delete)) },
                                leadingIcon = { Icon(Icons.Default.Delete, contentDescription = null) },
                                onClick = { menuExpanded = false; onDelete() },
                            )
                        }
                    }
                }
            }
            if (activeJob != null) {
                Spacer(Modifier.height(9.dp))
                LinearProgressIndicator(
                    progress = { activeJob.progress / 100f },
                    modifier = Modifier.fillMaxWidth().height(5.dp).clip(RoundedCornerShape(3.dp)),
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    stringResource(R.string.download_progress, downloadStatusLabel(activeJob.status), activeJob.progress),
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 12.sp,
                )
                activeJob.errorMessage?.let { Text(it, fontSize = 12.sp) }
                com.liberivixer.youtubeharvester.ui.DownloadJobControls(activeJob, onPause, onResume, onCancel)
            } else {
                OutlinedButton(onClick = onDownload) {
                    Icon(Icons.Default.Download, contentDescription = null)
                    Spacer(Modifier.size(6.dp))
                    Text(stringResource(R.string.download))
                }
            }
        }
    }
}

@Composable
private fun QueueMediaOptionLine(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 3.dp)) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(14.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.size(5.dp))
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun SchedulerPanel(
    schedule: List<ScheduleItem>,
    onAdd: (Int, Int) -> Unit,
    onToggle: (ScheduleItem) -> Unit,
    onDelete: (ScheduleItem) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val activeLocale = LocalConfiguration.current.locales[0]
    val enabledCount = schedule.count { it.enabled }
    val showTimePicker = {
        val now = Calendar.getInstance()
        TimePickerDialog(
            context,
            { _, hour, minute -> onAdd(hour, minute) },
            now.get(Calendar.HOUR_OF_DAY),
            now.get(Calendar.MINUTE),
            android.text.format.DateFormat.is24HourFormat(context),
        ).show()
    }
    BorderedPanel(modifier) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Image(
                    painter = painterResource(R.drawable.queue_scheduler),
                    contentDescription = null,
                    modifier = Modifier.size(92.dp).clip(RoundedCornerShape(6.dp)),
                    contentScale = ContentScale.Fit,
                )
                Spacer(Modifier.size(14.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(stringResource(R.string.checks_schedule), fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        stringResource(R.string.enabled_of_total, enabledCount, schedule.size),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 14.sp,
                    )
                }
            }
            Text(
                stringResource(R.string.scheduler_android_hint),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 13.sp,
                lineHeight = 18.sp,
            )
            Button(onClick = showTimePicker, modifier = Modifier.fillMaxWidth().height(48.dp)) {
                Icon(Icons.Default.Add, contentDescription = null)
                Spacer(Modifier.size(7.dp))
                Text(stringResource(R.string.add_time))
            }
            if (schedule.isEmpty()) {
                Text(
                    stringResource(R.string.schedule_empty),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                )
            }
            schedule.forEach { item ->
                Divider()
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(5.dp)) {
                        Text(
                            formatScheduleTime(item, activeLocale),
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                            fontSize = 17.sp,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                    Spacer(Modifier.size(10.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            stringResource(if (item.enabled) R.string.enabled else R.string.disabled),
                            color = if (item.enabled) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 14.sp,
                        )
                        Text(
                            item.lastRunEpochMs?.let { epochMs ->
                                stringResource(
                                    R.string.last_run_value,
                                    DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT, activeLocale).format(Date(epochMs)),
                                )
                            } ?: stringResource(R.string.never_run),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 12.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    Switch(checked = item.enabled, onCheckedChange = { onToggle(item) })
                    IconButton(onClick = { onDelete(item) }, modifier = Modifier.size(40.dp)) {
                        Icon(Icons.Default.Delete, contentDescription = stringResource(R.string.delete_time))
                    }
                }
            }
        }
    }
}

private fun formatScheduleTime(item: ScheduleItem, locale: Locale): String {
    val calendar = Calendar.getInstance().apply {
        set(Calendar.HOUR_OF_DAY, item.hour)
        set(Calendar.MINUTE, item.minute)
        set(Calendar.SECOND, 0)
        set(Calendar.MILLISECOND, 0)
    }
    return DateFormat.getTimeInstance(DateFormat.SHORT, locale).format(calendar.time)
}
