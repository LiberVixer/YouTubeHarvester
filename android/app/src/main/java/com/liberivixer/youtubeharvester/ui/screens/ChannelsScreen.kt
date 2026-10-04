package com.liberivixer.youtubeharvester.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
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
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.FilterList
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.DoneAll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.TextButton
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.liberivixer.youtubeharvester.AppViewModel
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.model.AppUiState
import com.liberivixer.youtubeharvester.model.ChannelItem
import com.liberivixer.youtubeharvester.model.ChannelFilter
import com.liberivixer.youtubeharvester.model.filterChannels
import com.liberivixer.youtubeharvester.media.ChannelUrlParser
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.CHANNEL_STATUS_CHECKED
import com.liberivixer.youtubeharvester.model.CHANNEL_STATUS_FAILED
import com.liberivixer.youtubeharvester.model.CHANNEL_STATUS_NOT_CHECKED
import com.liberivixer.youtubeharvester.ui.BorderedPanel
import com.liberivixer.youtubeharvester.ui.RemoteThumbnail
import com.liberivixer.youtubeharvester.ui.ScreenTitle
import androidx.compose.ui.res.stringResource
import kotlinx.coroutines.delay

@Composable
fun ChannelsScreen(state: AppUiState, viewModel: AppViewModel) {
    var channelUrl by rememberSaveable { mutableStateOf("") }
    var query by rememberSaveable { mutableStateOf("") }
    var checkPaid by rememberSaveable { mutableStateOf(false) }
    var channelFilter by rememberSaveable { mutableStateOf(ChannelFilter.All) }
    var filterExpanded by remember { mutableStateOf(false) }
    val visible = filterChannels(state.channels, query, channelFilter)

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 20.dp),
    ) {
        item {
            ScreenTitle(
                title = stringResource(R.string.channels),
                count = state.channels.size,
                trailing = {
                    Text(
                        stringResource(R.string.check_counter, state.scannedChannels, state.scanTotalChannels.takeIf { it > 0 } ?: state.channels.size),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 14.sp,
                    )
                },
            )
        }
        item {
            Text(state.statusMessage, modifier = Modifier.padding(horizontal = 16.dp),
                color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        }
        item {
            Column(modifier = Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = { viewModel.toggleChannelCheck(checkPaid) },
                    enabled = state.channels.isNotEmpty(),
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                ) {
                    Icon(Icons.Default.Search, contentDescription = null)
                    Spacer(Modifier.size(8.dp))
                    Text(stringResource(if (state.isScanning) R.string.stop_check else R.string.check_channels), fontSize = 17.sp)
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = checkPaid, onCheckedChange = { checkPaid = it }, enabled = !state.isScanning)
                    Text(stringResource(R.string.check_paid_content), fontSize = 16.sp)
                }
            }
        }
        item {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                OutlinedTextField(
                    value = channelUrl,
                    onValueChange = { channelUrl = it },
                    placeholder = { Text(stringResource(R.string.youtube_channel_url)) },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                IconButton(
                    onClick = { if (viewModel.addChannel(channelUrl)) channelUrl = "" },
                    enabled = channelUrl.isNotBlank(),
                    modifier = Modifier.size(54.dp),
                ) {
                    Icon(Icons.Default.Add, contentDescription = stringResource(R.string.add_channel), tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(32.dp))
                }
            }
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
                    placeholder = { Text(stringResource(R.string.search_channels)) },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                Box {
                    IconButton(onClick = { filterExpanded = true }, modifier = Modifier.size(54.dp)) {
                        Icon(
                            Icons.Default.FilterList,
                            contentDescription = stringResource(R.string.filter),
                            tint = if (channelFilter == ChannelFilter.All) MaterialTheme.colorScheme.onSurfaceVariant
                                   else MaterialTheme.colorScheme.primary,
                        )
                    }
                    DropdownMenu(expanded = filterExpanded, onDismissRequest = { filterExpanded = false }) {
                        ChannelFilter.entries.forEach { filter ->
                            DropdownMenuItem(
                                text = { Text(channelFilterLabel(filter)) },
                                trailingIcon = { if (channelFilter == filter) Icon(Icons.Default.Check, contentDescription = null) },
                                onClick = { channelFilter = filter; filterExpanded = false },
                            )
                        }
                    }
                }
            }
        }
        if (channelFilter != ChannelFilter.All) {
            item {
                FilterChip(
                    selected = true,
                    onClick = { channelFilter = ChannelFilter.All },
                    label = { Text("${channelFilterLabel(channelFilter)}: ${visible.size}") },
                    trailingIcon = { Icon(Icons.Default.Close, contentDescription = stringResource(R.string.clear_filter)) },
                    modifier = Modifier.padding(horizontal = 16.dp),
                )
            }
        }
        if (state.channels.isEmpty()) {
            item {
                BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                    Column(modifier = Modifier.padding(horizontal = 18.dp, vertical = 22.dp)) {
                        Text(stringResource(R.string.channels_empty), fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(4.dp))
                        Text(
                            stringResource(R.string.channels_empty_hint),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 14.sp,
                        )
                    }
                }
            }
        } else if (visible.isEmpty()) {
            item {
                BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                    Text(
                        stringResource(R.string.nothing_found),
                        modifier = Modifier.padding(horizontal = 18.dp, vertical = 22.dp),
                        fontSize = 17.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        } else {
            items(visible, key = { it.id }) { channel ->
                ChannelCard(
                    channel = channel,
                    activeContentType = state.activeScanContentType.takeIf { state.activeScanChannelId == channel.id },
                    isScanning = state.activeScanChannelId == channel.id,
                    onUpdate = viewModel::updateChannelContentSelection,
                    onDelete = viewModel::deleteChannel,
                    onMark = viewModel::markChannelArchived,
                    markingAllowed = !state.isScanning && state.downloadJobs.none { it.status.isActive },
                    limits = listOf(state.settings.videoLimit, state.settings.shortsLimit, state.settings.streamsLimit),
                    modifier = Modifier.padding(horizontal = 16.dp),
                )
            }
        }
    }
}

@Composable
private fun channelFilterLabel(filter: ChannelFilter): String = stringResource(
    when (filter) {
        ChannelFilter.All -> R.string.all
        ChannelFilter.Enabled -> R.string.enabled
        ChannelFilter.Disabled -> R.string.disabled
        ChannelFilter.NotChecked -> R.string.channel_not_checked
        ChannelFilter.Failed -> R.string.channel_check_failed
        ChannelFilter.MembersOnly -> R.string.channel_filter_members
        ChannelFilter.FreeOnly -> R.string.channel_filter_free
        ChannelFilter.UnknownPaid -> R.string.channel_filter_unknown_paid
    },
)

@Composable
private fun ChannelCard(
    channel: ChannelItem,
    activeContentType: ContentType?,
    isScanning: Boolean,
    onUpdate: (ChannelItem) -> Unit,
    onDelete: (ChannelItem) -> Unit,
    onMark: (ChannelItem) -> Unit,
    markingAllowed: Boolean,
    limits: List<Int>,
    modifier: Modifier = Modifier,
) {
    var menuExpanded by remember(channel.id) { mutableStateOf(false) }
    var confirmMark by rememberSaveable(channel.id) { mutableStateOf(false) }
    val supported = ChannelUrlParser.parse(channel.url)?.sections.orEmpty()
    if (confirmMark) {
        AlertDialog(
            onDismissRequest = { confirmMark = false },
            title = { Text(stringResource(R.string.channel_mark_recent)) },
            text = {
                Column {
                    Text(stringResource(R.string.channel_mark_confirm, channel.name))
                    listOf(ContentType.Video, ContentType.Shorts, ContentType.Stream).forEachIndexed { index, type ->
                        val enabled = when (type) {
                            ContentType.Video -> channel.videosEnabled
                            ContentType.Shorts -> channel.shortsEnabled
                            else -> channel.streamsEnabled
                        }
                        if (type in supported && enabled) {
                            val label = when (type) {
                                ContentType.Video -> R.string.video
                                ContentType.Shorts -> R.string.shorts
                                else -> R.string.streams
                            }
                            Text("${stringResource(label)}: ${limits[index]}")
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { confirmMark = false; onMark(channel) }, enabled = markingAllowed) {
                    Text(stringResource(R.string.channel_mark_recent))
                }
            },
            dismissButton = { TextButton(onClick = { confirmMark = false }) { Text(stringResource(R.string.cancel)) } },
        )
    }

    BorderedPanel(modifier) {
        Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            RemoteThumbnail(
                url = channel.thumbnailUrl,
                fallbackText = channel.name,
                contentDescription = channel.name,
                modifier = Modifier.size(72.dp),
            )
            Spacer(Modifier.size(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(channel.name, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(channel.handle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp, maxLines = 1)
                    }
                    Text(channel.paidContent.symbol, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
                    IconButton(onClick = { menuExpanded = true }, modifier = Modifier.size(36.dp)) {
                        Icon(Icons.Default.MoreVert, contentDescription = stringResource(R.string.actions))
                    }
                    DropdownMenu(expanded = menuExpanded, onDismissRequest = { menuExpanded = false }) {
                        DropdownMenuItem(
                            text = { Text(stringResource(R.string.channel_mark_recent)) },
                            leadingIcon = { Icon(Icons.Default.DoneAll, contentDescription = null) },
                            enabled = markingAllowed && (channel.videosEnabled || channel.shortsEnabled || channel.streamsEnabled),
                            onClick = { menuExpanded = false; confirmMark = true },
                        )
                        DropdownMenuItem(
                            text = { Text(stringResource(R.string.delete)) },
                            leadingIcon = { Icon(Icons.Default.Delete, contentDescription = null) },
                            onClick = {
                                menuExpanded = false
                                onDelete(channel)
                            },
                        )
                    }
                }
                ChannelStatus(channel, isScanning, activeContentType)
                Spacer(Modifier.height(7.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                    ContentChip(
                        "🎬",
                        stringResource(R.string.video),
                        channel.videosEnabled,
                        { onUpdate(channel.copy(videosEnabled = !channel.videosEnabled)) },
                        Modifier.weight(1f),
                        enabled = ContentType.Video in supported,
                    )
                    ContentChip(
                        "⚡",
                        stringResource(R.string.shorts),
                        channel.shortsEnabled,
                        { onUpdate(channel.copy(shortsEnabled = !channel.shortsEnabled)) },
                        Modifier.weight(1f),
                        enabled = ContentType.Shorts in supported,
                    )
                    ContentChip(
                        "●",
                        stringResource(R.string.streams),
                        channel.streamsEnabled,
                        { onUpdate(channel.copy(streamsEnabled = !channel.streamsEnabled)) },
                        Modifier.weight(1f),
                        enabled = ContentType.Stream in supported,
                    )
                }
            }
        }
    }
}

@Composable
private fun ChannelStatus(channel: ChannelItem, isScanning: Boolean, activeContentType: ContentType?) {
    if (isScanning) {
        var dotCount by remember(activeContentType) { mutableIntStateOf(1) }
        LaunchedEffect(activeContentType) {
            while (true) {
                delay(350)
                dotCount = dotCount % 3 + 1
            }
        }
        val section = when (activeContentType) {
            ContentType.Video -> stringResource(R.string.video)
            ContentType.Shorts -> stringResource(R.string.shorts)
            ContentType.Stream -> stringResource(R.string.streams)
            ContentType.Queue, null -> stringResource(R.string.check_paid_content)
        }
        Text(
            stringResource(R.string.channel_scanning_section, section, ".".repeat(dotCount)),
            color = MaterialTheme.colorScheme.primary,
            fontSize = 13.sp,
            maxLines = 1,
        )
        return
    }

    val status = when (channel.status) {
        CHANNEL_STATUS_NOT_CHECKED -> stringResource(R.string.channel_not_checked)
        CHANNEL_STATUS_CHECKED -> stringResource(R.string.channel_checked)
        CHANNEL_STATUS_FAILED -> stringResource(R.string.channel_check_failed)
        else -> channel.status
    }
    Text(
        status,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        fontSize = 13.sp,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
    )
}

@Composable
private fun ContentChip(symbol: String, label: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier, enabled: Boolean = true) {
    FilterChip(
        selected = selected && enabled,
        enabled = enabled,
        onClick = onClick,
        modifier = modifier,
        label = { Text(label, fontSize = 11.sp, maxLines = 1) },
        leadingIcon = { Text(symbol, fontSize = 12.sp) },
    )
}
