package com.liberivixer.youtubeharvester.ui.screens

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.InsertDriveFile
import androidx.compose.material.icons.automirrored.filled.Launch
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.FilterList
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.res.stringResource
import androidx.compose.foundation.rememberScrollState
import androidx.core.net.toUri
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.AppViewModel
import com.liberivixer.youtubeharvester.model.AppUiState
import com.liberivixer.youtubeharvester.model.ArchiveItem
import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.ui.BorderedPanel
import com.liberivixer.youtubeharvester.ui.Divider
import com.liberivixer.youtubeharvester.ui.RemoteThumbnail
import com.liberivixer.youtubeharvester.ui.ScreenTitle
import com.liberivixer.youtubeharvester.ui.theme.ErrorRed
import com.liberivixer.youtubeharvester.ui.theme.SuccessGreen

@Composable
fun ArchiveScreen(state: AppUiState, viewModel: AppViewModel) {
    val context = LocalContext.current
    var query by rememberSaveable { mutableStateOf("") }
    var sourceFilter by rememberSaveable { mutableStateOf<String?>(null) }
    var availabilityFilter by rememberSaveable { mutableStateOf(ArchiveAvailabilityFilter.All) }
    var filterExpanded by rememberSaveable { mutableStateOf(false) }
    var expandedId by rememberSaveable { mutableStateOf<String?>(null) }
    var pendingDelete by remember { mutableStateOf<ArchiveItem?>(null) }
    val fileOpenError = stringResource(R.string.archive_file_open_error)
    val sourceOpenError = stringResource(R.string.archive_source_open_error)
    val shareError = stringResource(R.string.archive_share_error)
    val shareVideo = stringResource(R.string.share_video)
    val visible = state.archive.filter { item ->
        val matchesQuery = item.title.contains(query, true) || item.channel.contains(query, true) || item.id.contains(query, true)
        val matchesSource = sourceFilter == null || item.source.name == sourceFilter
        val matchesAvailability = when (availabilityFilter) {
            ArchiveAvailabilityFilter.All -> true
            ArchiveAvailabilityFilter.Available -> item.fileExists
            ArchiveAvailabilityFilter.Missing -> !item.fileExists
        }
        matchesQuery && matchesSource && matchesAvailability
    }

    pendingDelete?.let { item ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text(stringResource(R.string.remove_archive_record)) },
            text = { Text(stringResource(R.string.remove_archive_record_hint, item.title)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        pendingDelete = null
                        viewModel.deleteArchiveItem(item)
                    },
                ) { Text(stringResource(R.string.remove_record), color = ErrorRed) }
            },
            dismissButton = {
                TextButton(onClick = { pendingDelete = null }) { Text(stringResource(R.string.cancel)) }
            },
        )
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 20.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
    ) {
        item {
            ScreenTitle(
                title = stringResource(R.string.archive),
                count = state.archive.size,
                trailing = {
                    IconButton(onClick = viewModel::refreshArchiveAvailability) {
                        Icon(Icons.Default.Refresh, contentDescription = stringResource(R.string.refresh))
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
                    value = query,
                    onValueChange = { query = it },
                    leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                    placeholder = { Text(stringResource(R.string.search_archive)) },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                Box {
                    IconButton(onClick = { filterExpanded = true }, modifier = Modifier.size(54.dp)) {
                        Icon(
                            Icons.Default.FilterList,
                            contentDescription = stringResource(R.string.filter),
                            tint = if (availabilityFilter == ArchiveAvailabilityFilter.All) {
                                MaterialTheme.colorScheme.onSurface
                            } else {
                                MaterialTheme.colorScheme.primary
                            },
                        )
                    }
                    DropdownMenu(expanded = filterExpanded, onDismissRequest = { filterExpanded = false }) {
                        ArchiveAvailabilityFilter.entries.forEach { filter ->
                            DropdownMenuItem(
                                text = { Text(archiveAvailabilityLabel(filter)) },
                                onClick = {
                                    availabilityFilter = filter
                                    filterExpanded = false
                                },
                                leadingIcon = {
                                    if (availabilityFilter == filter) Text("✓", color = MaterialTheme.colorScheme.primary)
                                },
                            )
                        }
                    }
                }
            }
        }
        item {
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                ArchiveFilter(stringResource(R.string.all), sourceFilter == null, { sourceFilter = null })
                MediaSource.entries.forEach { source ->
                    ArchiveFilter(source.label, sourceFilter == source.name, { sourceFilter = source.name })
                }
            }
        }
        if (visible.isEmpty()) {
            item {
                BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                    Column(modifier = Modifier.padding(horizontal = 18.dp, vertical = 22.dp)) {
                        Text(
                            stringResource(if (state.archive.isEmpty()) R.string.archive_empty else R.string.nothing_found),
                            fontSize = 18.sp,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            stringResource(if (state.archive.isEmpty()) R.string.archive_empty_hint else R.string.nothing_found_hint),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 14.sp,
                        )
                    }
                }
            }
        }
        items(visible, key = { it.storageKey() }) { item ->
            ArchiveCard(
                item = item,
                expanded = expandedId == item.storageKey(),
                onToggle = { expandedId = if (expandedId == item.storageKey()) null else item.storageKey() },
                onOpenSource = {
                    launchArchiveIntent(context, Intent(Intent.ACTION_VIEW, archiveSourceUri(item)), sourceOpenError, viewModel::reportStatus)
                },
                onOpenFile = {
                    item.fileUri?.let(Uri::parse)?.let { uri ->
                        runCatching { com.liberivixer.youtubeharvester.download.shareableArchiveUri(context, uri) }
                            .onSuccess { launchArchiveIntent(context, videoViewIntent(it), fileOpenError, viewModel::reportStatus) }
                            .onFailure { viewModel.reportStatus(fileOpenError) }
                    }
                },
                onShare = {
                    item.fileUri?.let(Uri::parse)?.let { uri ->
                        runCatching { com.liberivixer.youtubeharvester.download.shareableArchiveUri(context, uri) }.onSuccess { sharedUri -> launchArchiveIntent(
                            context,
                            Intent.createChooser(videoShareIntent(sharedUri, item.title), shareVideo),
                            shareError,
                            viewModel::reportStatus,
                        ) }.onFailure { viewModel.reportStatus(shareError) }
                    }
                },
                onOpenFolder = {
                    viewModel.openDownloadFolder(item.fileUri)
                },
                onDelete = { pendingDelete = item },
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }
    }
}

private fun ArchiveItem.storageKey(): String = "${source.name}:$id:$resolution:$variantKey"

@Composable
private fun ArchiveFilter(label: String, selected: Boolean, onClick: () -> Unit) {
    FilterChip(selected = selected, onClick = onClick, label = { Text(label, fontSize = 13.sp) })
}

@Composable
private fun ArchiveCard(
    item: ArchiveItem,
    expanded: Boolean,
    onToggle: () -> Unit,
    onOpenSource: () -> Unit,
    onOpenFile: () -> Unit,
    onShare: () -> Unit,
    onOpenFolder: () -> Unit,
    onDelete: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val automaticLabel = stringResource(R.string.automatic)
    val noneLabel = stringResource(R.string.none)
    BorderedPanel(modifier) {
        Column(modifier = Modifier.clickable(onClick = onToggle)) {
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
                        fallbackText = item.channel,
                        contentDescription = item.title,
                        modifier = Modifier.size(width = 86.dp, height = 68.dp),
                    )
                    Spacer(Modifier.size(11.dp))
                    Column(modifier = Modifier.weight(1f)) {
                    Text("${item.source.symbol}  ${item.channel}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp, maxLines = 1)
                    Text("${item.type.symbol} ${contentTypeLabel(item.type)}  •  ${item.resolution}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
                        Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(if (item.fileExists) "●" else "×", color = if (item.fileExists) SuccessGreen else ErrorRed, fontSize = 18.sp)
                        Spacer(Modifier.size(5.dp))
                            Text(item.downloadedAt, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp, maxLines = 1)
                        }
                    }
                    IconButton(onClick = onToggle, modifier = Modifier.size(36.dp)) {
                        Icon(Icons.Default.MoreVert, contentDescription = stringResource(R.string.actions))
                    }
                }
                Text(
                    "ID: ${item.id}",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 11.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.fillMaxWidth().padding(top = 7.dp),
                )
            }
            if (expanded) {
                Divider()
                Column(modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    Text(stringResource(R.string.audio_details, item.audio.joinToString().ifBlank { automaticLabel }), color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(stringResource(R.string.subtitle_details, item.subtitles.joinToString().ifBlank { noneLabel }), color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        ArchiveAction(Icons.AutoMirrored.Filled.Launch, stringResource(R.string.source), onOpenSource, Modifier.weight(1f))
                        ArchiveAction(
                            Icons.AutoMirrored.Filled.InsertDriveFile,
                            stringResource(R.string.file),
                            onOpenFile,
                            Modifier.weight(1f),
                            enabled = item.fileExists && !item.fileUri.isNullOrBlank(),
                        )
                        ArchiveAction(
                            Icons.Default.Share,
                            stringResource(R.string.share),
                            onShare,
                            Modifier.weight(1f),
                            enabled = item.fileExists && !item.fileUri.isNullOrBlank(),
                        )
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        ArchiveAction(Icons.Default.Folder, stringResource(R.string.folder), onOpenFolder, Modifier.weight(1f))
                        ArchiveAction(Icons.Default.Delete, stringResource(R.string.delete), onDelete, Modifier.weight(1f), ErrorRed)
                    }
                }
            }
        }
    }
}

@Composable
private fun contentTypeLabel(type: ContentType): String = stringResource(
    when (type) {
        ContentType.Video -> R.string.video
        ContentType.Shorts -> R.string.shorts
        ContentType.Stream -> R.string.streams
        ContentType.Queue -> R.string.queue_short
    },
)

@Composable
private fun ArchiveAction(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    onClick: () -> Unit,
    modifier: Modifier,
    tint: Color = MaterialTheme.colorScheme.onSurface,
    enabled: Boolean = true,
) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        colors = ButtonDefaults.outlinedButtonColors(
            contentColor = tint,
            disabledContentColor = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.32f),
        ),
        modifier = modifier.height(48.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(3.dp),
    ) {
        Icon(icon, contentDescription = label, modifier = Modifier.size(18.dp))
        Spacer(Modifier.size(3.dp))
        Text(label, fontSize = 10.sp, maxLines = 1)
    }
}

private enum class ArchiveAvailabilityFilter {
    All,
    Available,
    Missing,
}

@Composable
private fun archiveAvailabilityLabel(filter: ArchiveAvailabilityFilter): String = stringResource(
    when (filter) {
        ArchiveAvailabilityFilter.All -> R.string.all_files
        ArchiveAvailabilityFilter.Available -> R.string.available_files
        ArchiveAvailabilityFilter.Missing -> R.string.missing_files
    },
)

private fun archiveSourceUri(item: ArchiveItem): Uri = when (item.source) {
        MediaSource.YouTube -> "https://www.youtube.com/watch?v=${item.id}"
        MediaSource.Vk -> "https://vk.com/video${item.id.removePrefix("video")}"
        MediaSource.Rutube -> "https://rutube.ru/video/${item.id}/"
    }.toUri()

private fun videoViewIntent(uri: Uri) = Intent(Intent.ACTION_VIEW).apply {
    setDataAndType(uri, "video/*")
    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
}

private fun videoShareIntent(uri: Uri, title: String) = Intent(Intent.ACTION_SEND).apply {
    type = "video/*"
    putExtra(Intent.EXTRA_STREAM, uri)
    putExtra(Intent.EXTRA_TITLE, title)
    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
}

private fun launchArchiveIntent(
    context: Context,
    intent: Intent,
    errorMessage: String,
    onError: (String) -> Unit,
) {
    runCatching { context.startActivity(intent) }.onFailure { onError(errorMessage) }
}
