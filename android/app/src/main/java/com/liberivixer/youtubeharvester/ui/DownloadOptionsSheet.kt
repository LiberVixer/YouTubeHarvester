package com.liberivixer.youtubeharvester.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.PlaylistAdd
import androidx.compose.material.icons.filled.ClosedCaption
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Headphones
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.res.stringResource
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.model.AppUiState
import com.liberivixer.youtubeharvester.model.AudioTrackOption
import com.liberivixer.youtubeharvester.model.MediaOptionSection
import com.liberivixer.youtubeharvester.model.SubtitleTrackOption

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DownloadOptionsSheet(
    state: AppUiState,
    defaultResolution: String,
    onDismiss: () -> Unit,
    onDownload: (String, List<AudioTrackOption>, List<String>) -> Unit,
    onAddToQueue: (String, List<AudioTrackOption>, List<String>) -> Unit,
) {
    var resolution by rememberSaveable { mutableStateOf(defaultResolution) }
    var selectedAudioKeys by rememberSaveable { mutableStateOf(emptyList<String>()) }
    var selectedSubtitles by rememberSaveable { mutableStateOf(emptyList<String>()) }
    val mediaOptions = state.downloadMediaOptions
    val selectedAudio = mediaOptions?.audioTracks.orEmpty().filter { it.key in selectedAudioKeys }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(
            modifier = Modifier.fillMaxWidth().fillMaxHeight(0.92f).navigationBarsPadding().padding(horizontal = 18.dp, vertical = 8.dp),
        ) {
            LazyColumn(modifier = Modifier.fillMaxWidth().weight(1f)) {
                item {
                    Text(stringResource(R.string.download_options), fontSize = 22.sp, fontWeight = FontWeight.Bold)
                    mediaOptions?.preview?.let { preview ->
                        Spacer(Modifier.height(4.dp))
                        Text(preview.title, maxLines = 2, overflow = TextOverflow.Ellipsis, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Spacer(Modifier.height(14.dp))
                    Text(stringResource(R.string.resolution), fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(7.dp))
                    FlowRow(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(7.dp),
                        verticalArrangement = Arrangement.spacedBy(2.dp),
                    ) {
                        listOf("480p", "720p", "1080p", "1440p", "2160p", "best").forEach { value ->
                            FilterChip(
                                selected = resolution == value,
                                onClick = { resolution = value },
                                label = { Text(if (value == "best") "MAX" else value.removeSuffix("p"), fontSize = 12.sp) },
                            )
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                }
                if (state.isDownloadOptionsLoading) {
                    item {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 32.dp),
                            horizontalArrangement = Arrangement.Center,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            CircularProgressIndicator(modifier = Modifier.size(28.dp))
                            Spacer(Modifier.size(12.dp))
                            Text(stringResource(R.string.loading_tracks))
                        }
                    }
                } else if (state.downloadOptionsError != null) {
                    item {
                        Text(stringResource(R.string.tracks_unavailable), fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.error)
                        Spacer(Modifier.height(4.dp))
                        Text(state.downloadOptionsError, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                        Spacer(Modifier.height(8.dp))
                        Text(stringResource(R.string.tracks_fallback), fontSize = 13.sp)
                    }
                } else if (mediaOptions != null) {
                    item {
                        OptionHeading(Icons.Default.Headphones, stringResource(R.string.audio_tracks), if (selectedAudioKeys.isEmpty()) stringResource(R.string.automatic) else stringResource(R.string.selected_count, selectedAudioKeys.size))
                    }
                    if (mediaOptions.audioTracks.isEmpty()) {
                        item { EmptyOptionsText(stringResource(R.string.audio_tracks_missing)) }
                    } else {
                        var previousAudioSection: MediaOptionSection? = null
                        mediaOptions.audioTracks.forEach { option ->
                            if (option.section != previousAudioSection) {
                                previousAudioSection = option.section
                                item(key = "audio-section-${option.section}") { OptionSectionLabel(audioSectionLabel(option.section)) }
                            }
                            item(key = "audio-${option.key}") {
                                AudioOptionRow(
                                    option = option,
                                    checked = option.key in selectedAudioKeys,
                                    onChecked = { checked ->
                                        selectedAudioKeys = if (checked) {
                                            val withoutOtherCombined = if (option.formatKind == "combined") {
                                                selectedAudioKeys.filterNot { key ->
                                                    mediaOptions.audioTracks.firstOrNull { it.key == key }?.formatKind == "combined"
                                                }
                                            } else {
                                                selectedAudioKeys
                                            }
                                            (withoutOtherCombined + option.key).distinct()
                                        } else {
                                            selectedAudioKeys - option.key
                                        }
                                    },
                                )
                            }
                        }
                    }

                    item {
                        Spacer(Modifier.height(9.dp))
                        OptionHeading(Icons.Default.ClosedCaption, stringResource(R.string.subtitles), if (selectedSubtitles.isEmpty()) stringResource(R.string.subtitles_not_selected) else stringResource(R.string.selected_count, selectedSubtitles.size))
                    }
                    if (mediaOptions.subtitleTracks.isEmpty()) {
                        item { EmptyOptionsText(stringResource(R.string.subtitles_missing)) }
                    } else {
                        var previousSubtitleSection: MediaOptionSection? = null
                        mediaOptions.subtitleTracks.forEach { option ->
                            if (option.section != previousSubtitleSection) {
                                previousSubtitleSection = option.section
                                item(key = "subtitle-section-${option.section}") { OptionSectionLabel(subtitleSectionLabel(option.section)) }
                            }
                            item(key = "subtitle-${option.selection}") {
                                SubtitleOptionRow(
                                    option = option,
                                    checked = option.selection in selectedSubtitles,
                                    onChecked = { checked ->
                                        selectedSubtitles = if (checked) {
                                            (selectedSubtitles + option.selection).distinct()
                                        } else {
                                            selectedSubtitles - option.selection
                                        }
                                    },
                                )
                            }
                        }
                    }
                }
            }

            Spacer(Modifier.height(12.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                OutlinedButton(
                    onClick = { onAddToQueue(resolution, selectedAudio, selectedSubtitles) },
                    enabled = !state.isDownloadOptionsLoading,
                    modifier = Modifier.weight(1f).heightIn(min = 50.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 8.dp, vertical = 8.dp),
                ) {
                    Icon(Icons.AutoMirrored.Filled.PlaylistAdd, contentDescription = null)
                    Spacer(Modifier.size(6.dp))
                    Text(stringResource(R.string.add_to_queue), modifier = Modifier.weight(1f), maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                Button(
                    onClick = { onDownload(resolution, selectedAudio, selectedSubtitles) },
                    enabled = !state.isDownloadOptionsLoading,
                    modifier = Modifier.weight(1f).heightIn(min = 50.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 8.dp, vertical = 8.dp),
                ) {
                    Icon(Icons.Default.Download, contentDescription = null)
                    Spacer(Modifier.size(6.dp))
                    Text(stringResource(R.string.download), modifier = Modifier.weight(1f), maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}

@Composable
private fun OptionHeading(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, summary: String) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.size(9.dp))
        Text(title, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
        Text(summary, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
    }
}

@Composable
private fun OptionSectionLabel(label: String) {
    Column(modifier = Modifier.fillMaxWidth().padding(top = 5.dp)) {
        HorizontalDivider()
        Text(label, color = MaterialTheme.colorScheme.primary, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 7.dp, bottom = 2.dp))
    }
}

@Composable
private fun AudioOptionRow(option: AudioTrackOption, checked: Boolean, onChecked: (Boolean) -> Unit) {
    val originalLabel = stringResource(R.string.track_original)
    val combinedLabel = stringResource(R.string.track_combined)
    val details = buildList {
        add(option.language)
        if (option.isOriginal) add(originalLabel)
        if (option.formatKind == "combined") add(combinedLabel)
    }.joinToString(" · ")
    TrackOptionRow(
        title = option.name.ifBlank { option.language },
        secondary = details,
        checked = checked,
        onChecked = onChecked,
    )
}

@Composable
private fun SubtitleOptionRow(option: SubtitleTrackOption, checked: Boolean, onChecked: (Boolean) -> Unit) {
    TrackOptionRow(
        title = option.name.ifBlank { option.language },
        secondary = "${option.language} · ${stringResource(if (option.automatic) R.string.track_auto else R.string.track_manual)}",
        checked = checked,
        onChecked = onChecked,
    )
}

@Composable
private fun TrackOptionRow(title: String, secondary: String, checked: Boolean, onChecked: (Boolean) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = checked, onCheckedChange = onChecked)
        Spacer(Modifier.size(5.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(title, fontSize = 15.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text(secondary, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        }
    }
}

@Composable
private fun EmptyOptionsText(text: String) {
    Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(vertical = 9.dp), fontSize = 13.sp)
}

@Composable
private fun audioSectionLabel(section: MediaOptionSection): String = stringResource(
    when (section) {
        MediaOptionSection.ORIGINAL -> R.string.original_tracks
        MediaOptionSection.PREFERRED -> R.string.preferred_languages
        else -> R.string.other_languages
    },
)

@Composable
private fun subtitleSectionLabel(section: MediaOptionSection): String = stringResource(
    when (section) {
        MediaOptionSection.MANUAL_SUBTITLES -> R.string.manual_subtitles
        MediaOptionSection.PREFERRED_AUTOMATIC -> R.string.preferred_auto_subtitles
        else -> R.string.other_auto_subtitles
    },
)
