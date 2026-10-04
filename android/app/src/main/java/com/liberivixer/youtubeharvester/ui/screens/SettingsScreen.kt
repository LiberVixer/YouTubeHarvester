package com.liberivixer.youtubeharvester.ui.screens

import android.content.Context
import android.content.Intent
import android.provider.DocumentsContract
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.filled.Restore
import androidx.compose.material.icons.filled.Save
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException
import com.liberivixer.youtubeharvester.update.AndroidAppUpdater
import com.liberivixer.youtubeharvester.update.AndroidRelease
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.net.toUri
import com.liberivixer.youtubeharvester.AppViewModel
import com.liberivixer.youtubeharvester.BuildConfig
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.download.displayPathForTreeDocumentId
import com.liberivixer.youtubeharvester.download.isRestrictedDirectoryDocumentId
import com.liberivixer.youtubeharvester.model.AppSettings
import com.liberivixer.youtubeharvester.model.AppLanguage
import com.liberivixer.youtubeharvester.model.AppThemeMode
import com.liberivixer.youtubeharvester.model.AppUiState
import com.liberivixer.youtubeharvester.quick.QuickDownloadIntegration
import com.liberivixer.youtubeharvester.quick.ShortcutRequestResult
import com.liberivixer.youtubeharvester.ui.BorderedPanel
import com.liberivixer.youtubeharvester.ui.Divider
import com.liberivixer.youtubeharvester.ui.ScreenTitle
import com.liberivixer.youtubeharvester.ui.SectionTitle
import com.liberivixer.youtubeharvester.ui.SettingsRow
import com.liberivixer.youtubeharvester.ui.theme.SuccessGreen
import com.liberivixer.youtubeharvester.ui.theme.ErrorRed
import com.liberivixer.youtubeharvester.ui.themeModeLabel
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.saveable.rememberSaveable

enum class SettingsTool { Logs, Diagnostics }

@Composable
fun SettingsScreen(
    state: AppUiState,
    viewModel: AppViewModel,
    requestedTool: SettingsTool? = null,
    onToolOpened: () -> Unit = {},
) {
    val settings = state.settings
    val update: ((AppSettings) -> AppSettings) -> Unit = { transform -> viewModel.setSettings(transform(settings)) }
    val context = LocalContext.current
    val configuration = LocalConfiguration.current
    val windowWidthDp = with(LocalDensity.current) { LocalWindowInfo.current.containerSize.width.toDp() }
    val compactText = windowWidthDp < 400.dp || configuration.fontScale > 1.15f
    val updateFailedMessage = stringResource(R.string.app_update_failed)
    val updateCurrentMessage = stringResource(R.string.app_update_current)
    val updateScope = rememberCoroutineScope()
    val appUpdater = remember(context) { AndroidAppUpdater(context) }
    var appUpdateBusy by remember { mutableStateOf(false) }
    var availableRelease by remember { mutableStateOf<AndroidRelease?>(null) }
    var updateApk by remember { mutableStateOf<java.io.File?>(null) }
    val installerPermission = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        updateApk?.let { apk ->
            if (appUpdater.canInstall()) {
                runCatching { appUpdater.install(apk) }.onFailure { viewModel.reportStatus(updateFailedMessage) }
            }
        }
    }
    availableRelease?.let { release ->
        AlertDialog(
            onDismissRequest = { availableRelease = null },
            title = { Text(stringResource(R.string.app_update_available, release.title)) },
            text = { Text(stringResource(R.string.app_update_confirmation)) },
            dismissButton = { TextButton(onClick = { availableRelease = null }) { Text(stringResource(R.string.cancel)) } },
            confirmButton = {
                TextButton(onClick = {
                    availableRelease = null
                    appUpdateBusy = true
                    updateScope.launch {
                        try {
                            val apk = appUpdater.download(release)
                            updateApk = apk
                            if (appUpdater.canInstall()) appUpdater.install(apk) else {
                                installerPermission.launch(Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                    "package:${context.packageName}".toUri()))
                            }
                        } catch (cancelled: CancellationException) { throw cancelled
                        } catch (_: Exception) { viewModel.reportStatus(updateFailedMessage)
                        } finally { appUpdateBusy = false }
                    }
                }) { Text(stringResource(R.string.update_now)) }
            },
        )
    }
    val folderSelectionRestricted = stringResource(R.string.folder_selection_restricted)
    val folderAccessFailed = stringResource(R.string.folder_access_failed)
    val folderPickerHint = stringResource(R.string.folder_picker_hint)
    val shortcutRequested = stringResource(R.string.shortcut_requested)
    val shortcutUnsupported = stringResource(R.string.shortcut_unsupported)
    val shortcutRejected = stringResource(R.string.shortcut_rejected)
    val bestResolution = stringResource(R.string.best)
    val language = AppLanguage.fromStored(settings.language)
    val openLinkError = stringResource(R.string.open_link_error)
    val shareReportTitle = stringResource(R.string.share_diagnostics)
    val shareLogsTitle = stringResource(R.string.share_logs)
    val applicationLogsTitle = stringResource(R.string.application_logs)
    val emptyLogText = stringResource(R.string.log_empty)
    var showDirectoryChoice by remember { mutableStateOf(false) }
    var showTelegramSettings by remember { mutableStateOf(false) }
    var showDiagnostics by rememberSaveable { mutableStateOf(false) }
    var showLogs by rememberSaveable { mutableStateOf(false) }
    var showLicenses by remember { mutableStateOf(false) }
    LaunchedEffect(requestedTool) {
        when (requestedTool) {
            SettingsTool.Logs -> {
                showDiagnostics = false
                showLogs = true
                viewModel.loadLogs()
            }
            SettingsTool.Diagnostics -> {
                showLogs = false
                showDiagnostics = true
                viewModel.refreshDiagnostics()
                viewModel.loadLogs()
            }
            null -> return@LaunchedEffect
        }
        onToolOpened()
    }
    val directoryPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { treeUri ->
        if (treeUri != null) {
            val flags = Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            runCatching {
                val documentId = DocumentsContract.getTreeDocumentId(treeUri)
                check(!isRestrictedDirectoryDocumentId(documentId)) {
                    folderSelectionRestricted
                }
                context.contentResolver.takePersistableUriPermission(treeUri, flags)
                viewModel.setDownloadDirectory(displayPathForTreeDocumentId(documentId), treeUri.toString())
            }.onFailure { error ->
                val message = error.message ?: folderAccessFailed
                viewModel.reportStatus(message)
                Toast.makeText(context, message, Toast.LENGTH_LONG).show()
            }
        }
    }
    val launchDirectoryPicker = {
        Toast.makeText(
            context,
            folderPickerHint,
            Toast.LENGTH_LONG,
        ).show()
        val initialUri = settings.downloadDirectoryUri?.toUri()
            ?: DocumentsContract.buildDocumentUri(
                "com.android.externalstorage.documents",
                "primary:Download",
            )
        directoryPicker.launch(initialUri)
    }

    if (showDirectoryChoice) {
        AlertDialog(
            onDismissRequest = { showDirectoryChoice = false },
            title = { Text(stringResource(R.string.downloads_folder_title)) },
            text = {
                Text(stringResource(R.string.folder_restriction))
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showDirectoryChoice = false
                        launchDirectoryPicker()
                    },
                ) {
                    Text(stringResource(R.string.choose_subfolder))
                }
            },
            dismissButton = {
                TextButton(
                    onClick = {
                        showDirectoryChoice = false
                        viewModel.resetDownloadDirectory()
                    },
                ) {
                    Text("Download/YTH")
                }
            },
        )
    }

    if (showTelegramSettings) {
        TelegramSettingsDialog(
            settings = settings,
            statusMessage = state.statusMessage,
            onDismiss = { showTelegramSettings = false },
            onSave = { token, channel, proxy ->
                showTelegramSettings = false
                viewModel.saveTelegramSettings(token, channel, proxy)
            },
            onTest = viewModel::testTelegramSettings,
        )
    }

    if (showDiagnostics) {
        DiagnosticsDialog(
            state = state,
            onDismiss = { showDiagnostics = false },
            onRefresh = {
                viewModel.refreshDiagnostics()
                viewModel.loadLogs()
            },
            onShare = { report ->
                val sharedReport = "$report\n\n$applicationLogsTitle\n${state.logText.ifBlank { emptyLogText }}"
                shareText(context, sharedReport, shareReportTitle, openLinkError, viewModel::reportStatus)
            },
        )
    }

    if (showLogs) {
        LogsDialog(
            logText = state.logText,
            loading = state.isLogLoading,
            error = state.logLoadError,
            retentionDays = settings.logRetentionDays,
            onRefresh = viewModel::loadLogs,
            onClear = viewModel::clearLogs,
            onRetentionChanged = viewModel::setLogRetentionDays,
            onShare = {
                shareText(context, state.logText, shareLogsTitle, openLinkError, viewModel::reportStatus)
            },
            onDismiss = { showLogs = false },
        )
    }

    if (showLicenses) {
        AlertDialog(
            onDismissRequest = { showLicenses = false },
            title = { Text(stringResource(R.string.licenses_title)) },
            text = { Text(stringResource(R.string.licenses_text)) },
            confirmButton = {
                TextButton(onClick = { showLicenses = false }) { Text(stringResource(R.string.close)) }
            },
        )
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 24.dp),
    ) {
        item {
            ScreenTitle(
                title = stringResource(R.string.settings),
                trailing = {
                    OutlinedButton(onClick = viewModel::saveSettings) {
                        Icon(Icons.Default.Save, contentDescription = null)
                        Spacer(Modifier.size(6.dp))
                        Text(stringResource(R.string.save))
                    }
                },
            )
        }

        item { SectionTitle(stringResource(R.string.loading_section)) }
        item {
            BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                Column {
                    SettingsRow(
                        icon = "📁",
                        label = stringResource(R.string.downloads),
                        secondary = settings.downloadDirectory,
                        onClick = { showDirectoryChoice = true },
                        trailing = {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                if (settings.downloadDirectoryUri != null) {
                                    IconButton(onClick = viewModel::resetDownloadDirectory) {
                                        Icon(Icons.Default.Restore, contentDescription = stringResource(R.string.restore_default_folder))
                                    }
                                }
                                Icon(Icons.Default.Folder, contentDescription = stringResource(R.string.choose_folder))
                            }
                        },
                    )
                    Divider()
                    SettingsRow("⌛", stringResource(R.string.temporary_files), if (settings.tempDirectory == "internal-cache") stringResource(R.string.internal_app_cache) else settings.tempDirectory, onClick = viewModel::cleanupTemporaryFiles, trailing = {
                        Icon(Icons.Default.ChevronRight, contentDescription = null)
                    })
                    Divider()
                    SettingsRow("🎚", stringResource(R.string.resolution), trailing = {
                        OptionMenu(
                            value = if (settings.maxResolution == "best") bestResolution else settings.maxResolution,
                            options = listOf("480p", "720p", "1080p", "1440p", "2160p", bestResolution),
                            onSelect = { value -> update { it.copy(maxResolution = if (value == bestResolution) "best" else value) } },
                        )
                    })
                    Divider()
                    Column(modifier = Modifier.padding(vertical = 8.dp)) {
                        Text(stringResource(R.string.channel_limits), modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp), fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                        LimitRow("🎬", stringResource(R.string.video), settings.videoLimit) { value -> update { it.copy(videoLimit = value) } }
                        LimitRow("⚡", stringResource(R.string.shorts), settings.shortsLimit) { value -> update { it.copy(shortsLimit = value) } }
                        LimitRow("🔴", stringResource(R.string.streams), settings.streamsLimit) { value -> update { it.copy(streamsLimit = value) } }
                    }
                }
            }
        }

        item { SectionTitle(stringResource(R.string.interface_section)) }
        item {
            BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                Column {
                    SettingsRow("🌐", stringResource(R.string.language), trailing = {
                        OptionMenu(
                            value = language.nativeName,
                            options = AppLanguage.entries.map { it.nativeName },
                            onSelect = { value -> viewModel.setLanguage(AppLanguage.fromStored(value)) },
                        )
                    })
                    Divider()
                    Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
                        Text(stringResource(R.string.theme), fontSize = 18.sp)
                        Spacer(Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                            AppThemeMode.entries.forEach { mode ->
                                FilterChip(
                                    selected = settings.themeMode == mode,
                                    onClick = { viewModel.setTheme(mode) },
                                    label = { Text(themeModeLabel(mode), fontSize = 13.sp) },
                                    modifier = Modifier.weight(1f),
                                )
                            }
                        }
                    }
                }
            }
        }

        item { SectionTitle(stringResource(R.string.behavior)) }
        item {
            BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                Column {
                    SwitchSetting("◉", stringResource(R.string.watch_clipboard), stringResource(R.string.watch_clipboard_hint), settings.watchClipboard) { value -> update { it.copy(watchClipboard = value) } }
                    Divider()
                    SwitchSetting("♢", stringResource(R.string.system_notifications), null, settings.systemNotifications) { value -> update { it.copy(systemNotifications = value) } }
                }
            }
        }

        item { SectionTitle(stringResource(R.string.quick_download)) }
        item {
            BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                Column {
                    SettingsRow(
                        "⌨",
                        stringResource(R.string.app_shortcut),
                        stringResource(R.string.app_shortcut_hint),
                        onClick = {
                            val message = when (QuickDownloadIntegration.requestPinnedShortcut(context)) {
                                ShortcutRequestResult.Requested -> shortcutRequested
                                ShortcutRequestResult.Unsupported -> shortcutUnsupported
                                ShortcutRequestResult.Rejected -> shortcutRejected
                            }
                            viewModel.reportStatus(message)
                            Toast.makeText(context, message, Toast.LENGTH_LONG).show()
                        },
                        trailing = { Icon(Icons.Default.ChevronRight, contentDescription = null) },
                    )
                }
            }
        }

        item { SectionTitle(stringResource(R.string.telegram)) }
        item {
            BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                Column {
                    SwitchSetting(
                        "➤",
                        stringResource(R.string.notifications),
                        stringResource(when {
                            settings.telegramCredentialError -> R.string.telegram_credentials_invalid
                            settings.telegramBotToken.isNotBlank() && settings.telegramChannelId.isNotBlank() -> R.string.telegram_configured
                            else -> R.string.telegram_not_configured
                        }),
                        settings.telegramEnabled,
                    ) { value ->
                        if (value && (settings.telegramBotToken.isBlank() || settings.telegramChannelId.isBlank())) {
                            showTelegramSettings = true
                        } else {
                            update { it.copy(telegramEnabled = value) }
                        }
                    }
                    Divider()
                    SettingsRow("⌁", stringResource(R.string.connection_settings), "BOT_TOKEN · CHANNEL_ID · PROXY_URL", onClick = { showTelegramSettings = true }, trailing = {
                        Icon(Icons.Default.ChevronRight, contentDescription = null)
                    })
                }
            }
        }

        item { SectionTitle(stringResource(R.string.updates)) }
        item {
            BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                Column {
                    UpdateRow("📺", stringResource(R.string.app_name), BuildConfig.VERSION_NAME,
                        stringResource(if (appUpdateBusy) R.string.ytdlp_updating else R.string.update_now), enabled = !appUpdateBusy) {
                        appUpdateBusy = true
                        updateScope.launch {
                            try {
                                availableRelease = appUpdater.check()
                                if (availableRelease == null) viewModel.reportStatus(updateCurrentMessage)
                            } catch (cancelled: CancellationException) { throw cancelled
                            } catch (_: Exception) { viewModel.reportStatus(updateFailedMessage)
                            } finally { appUpdateBusy = false }
                        }
                    }
                    Divider()
                    ComponentStatus(
                        "📄",
                        "yt-dlp",
                        BuildConfig.YTDLP_VERSION + " · " + stringResource(R.string.embedded_apk),
                        state.diagnostics?.runtimeReady,
                    )
                    Text(stringResource(R.string.engine_updates_with_app),
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                        style = MaterialTheme.typography.bodySmall)
                    TextButton(onClick = { openUrl(context, RELEASES_URL, openLinkError, viewModel::reportStatus) }) {
                        Text(stringResource(R.string.releases))
                    }
                    Divider()
                    ComponentStatus(
                        "FF",
                        "FFmpeg / ffprobe",
                        componentStatusText(state.diagnostics?.ffmpegBundled, R.string.embedded_apk_plural),
                        state.diagnostics?.ffmpegBundled,
                    )
                    Divider()
                    ComponentStatus(
                        "JS",
                        "QuickJS",
                        componentStatusText(state.diagnostics?.quickJsBundled, R.string.embedded_apk),
                        state.diagnostics?.quickJsBundled,
                    )
                }
            }
        }

        item { SectionTitle(stringResource(R.string.data_diagnostics)) }
        item { DataTransferControls(viewModel, state.isDataTransferBusy, state.dataTransferMessage) }
        item {
            BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                Column {
                    SettingsRow("♨", stringResource(R.string.clear_thumbnail_cache), onClick = viewModel::clearThumbnailCache, trailing = { Icon(Icons.Default.ChevronRight, null) })
                    Divider()
                    SettingsRow(
                        "≡",
                        stringResource(R.string.application_logs),
                        pluralStringResource(
                            R.plurals.logs_retention_summary,
                            settings.logRetentionDays,
                            settings.logRetentionDays,
                        ),
                        onClick = {
                            showLogs = true
                            viewModel.loadLogs()
                        },
                        trailing = { Icon(Icons.Default.ChevronRight, null) },
                    )
                    Divider()
                    SettingsRow(
                        "〽",
                        stringResource(R.string.diagnostics),
                        stringResource(R.string.system_components),
                        onClick = {
                            showDiagnostics = true
                            viewModel.refreshDiagnostics()
                            viewModel.loadLogs()
                        },
                        trailing = { Icon(Icons.Default.ChevronRight, null) },
                    )
                    Divider()
                    SettingsRow("📄", stringResource(R.string.terms), onClick = { openUrl(context, TERMS_URL, openLinkError, viewModel::reportStatus) }, trailing = { Icon(Icons.Default.ChevronRight, null) })
                }
            }
        }

        item { SectionTitle(stringResource(R.string.about)) }
        item {
            BorderedPanel(Modifier.padding(horizontal = 16.dp)) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(stringResource(R.string.app_name), fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                    Text(
                        BuildConfig.VERSION_NAME,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontFamily = FontFamily.Monospace,
                        fontSize = if (compactText) 10.sp else 14.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(stringResource(R.string.development_build), color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Divider()
                    TextButton(onClick = { openUrl(context, PROJECT_URL, openLinkError, viewModel::reportStatus) }) {
                        Text("GitHub ↗", fontSize = 17.sp)
                    }
                    TextButton(onClick = { showLicenses = true }) {
                        Text(stringResource(R.string.licenses), fontSize = 17.sp)
                    }
                }
            }
        }
        item {
            Button(onClick = viewModel::saveSettings, modifier = Modifier.fillMaxWidth().padding(16.dp).height(54.dp)) {
                Icon(Icons.Default.Save, contentDescription = null)
                Spacer(Modifier.size(8.dp))
                Text(stringResource(R.string.save_settings), fontSize = 17.sp)
            }
        }
    }
}

@Composable
private fun LimitRow(icon: String, label: String, value: Int, onValue: (Int) -> Unit) {
    Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(icon, fontSize = 21.sp)
        Spacer(Modifier.size(9.dp))
        Text(label, fontSize = 17.sp, modifier = Modifier.weight(1f))
        IconButton(onClick = { onValue((value - 1).coerceAtLeast(1)) }) { Icon(Icons.Default.Remove, contentDescription = stringResource(R.string.decrease)) }
        Surface(shape = RoundedCornerShape(5.dp), color = MaterialTheme.colorScheme.surfaceVariant) {
            Text(value.toString(), modifier = Modifier.padding(horizontal = 18.dp, vertical = 9.dp), fontSize = 18.sp)
        }
        IconButton(onClick = { onValue((value + 1).coerceAtMost(99)) }) { Icon(Icons.Default.Add, contentDescription = stringResource(R.string.increase)) }
    }
}

@Composable
private fun SwitchSetting(icon: String, label: String, secondary: String?, checked: Boolean, onChecked: (Boolean) -> Unit) {
    SettingsRow(
        icon,
        label,
        secondary,
        trailing = {
            Switch(
                checked = checked,
                onCheckedChange = onChecked,
                colors = SwitchDefaults.colors(
                    checkedThumbColor = MaterialTheme.colorScheme.onPrimary,
                    checkedTrackColor = MaterialTheme.colorScheme.primary,
                    checkedBorderColor = MaterialTheme.colorScheme.primary,
                    uncheckedThumbColor = MaterialTheme.colorScheme.onSurfaceVariant,
                    uncheckedTrackColor = MaterialTheme.colorScheme.surfaceVariant,
                    uncheckedBorderColor = MaterialTheme.colorScheme.outline,
                ),
            )
        },
    )
}

@Composable
private fun OptionMenu(
    value: String,
    options: List<String>,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
    compact: Boolean = true,
) {
    var expanded by remember { mutableStateOf(false) }
    val configuration = LocalConfiguration.current
    val windowWidthDp = with(LocalDensity.current) { LocalWindowInfo.current.containerSize.width.toDp() }
    val compactWidth = if (windowWidthDp < 400.dp || configuration.fontScale > 1.15f) 128.dp else 160.dp
    Box(modifier = if (compact) modifier.width(compactWidth) else modifier) {
        OutlinedButton(onClick = { expanded = true }, modifier = Modifier.fillMaxWidth()) {
            Text(value, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option) },
                    onClick = {
                        expanded = false
                        onSelect(option)
                    },
                )
            }
        }
    }
}

@Composable
private fun UpdateRow(
    icon: String,
    name: String,
    version: String,
    action: String,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    SettingsRow(icon, name, version, trailing = {
        OutlinedButton(onClick = onClick, enabled = enabled) { Text(action) }
    })
}

@Composable
private fun ComponentStatus(icon: String, name: String, status: String, available: Boolean?) {
    val symbol = when (available) {
        true -> "✓"
        false -> "×"
        null -> "?"
    }
    val color = when (available) {
        true -> SuccessGreen
        false -> ErrorRed
        null -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    SettingsRow(icon, name, status, trailing = { Text(symbol, color = color, fontSize = 26.sp, fontWeight = FontWeight.Bold) })
}

@Composable
private fun componentStatusText(available: Boolean?, availableText: Int): String = when (available) {
    true -> stringResource(availableText)
    false -> stringResource(R.string.diagnostic_unavailable)
    null -> stringResource(R.string.diagnostics_not_run)
}

@Composable
private fun TelegramSettingsDialog(
    settings: AppSettings,
    statusMessage: String,
    onDismiss: () -> Unit,
    onSave: (String, String, String) -> Unit,
    onTest: (String, String, String) -> Unit,
) {
    var botToken by remember(settings.telegramBotToken) { mutableStateOf(settings.telegramBotToken) }
    var channelId by remember(settings.telegramChannelId) { mutableStateOf(settings.telegramChannelId) }
    var proxyUrl by remember(settings.telegramProxyUrl) { mutableStateOf(settings.telegramProxyUrl) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.telegram_connection_title)) },
        text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                OutlinedTextField(
                    value = botToken,
                    onValueChange = { botToken = it },
                    label = { Text(stringResource(R.string.bot_token)) },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(9.dp))
                OutlinedTextField(
                    value = channelId,
                    onValueChange = { channelId = it },
                    label = { Text(stringResource(R.string.channel_id)) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(9.dp))
                OutlinedTextField(
                    value = proxyUrl,
                    onValueChange = { proxyUrl = it },
                    label = { Text(stringResource(R.string.proxy_url_optional)) },
                    supportingText = { Text(stringResource(R.string.proxy_url_hint)) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(10.dp))
                OutlinedButton(
                    onClick = { onTest(botToken, channelId, proxyUrl) },
                    enabled = botToken.isNotBlank() && channelId.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(stringResource(R.string.test_connection))
                }
                if (statusMessage.isNotBlank()) {
                    Spacer(Modifier.height(7.dp))
                    Text(statusMessage, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onSave(botToken, channelId, proxyUrl) },
                enabled = botToken.isNotBlank() && channelId.isNotBlank(),
            ) { Text(stringResource(R.string.save)) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) }
        },
    )
}

private fun openUrl(context: Context, url: String, errorMessage: String, onError: (String) -> Unit) {
    runCatching {
        context.startActivity(Intent(Intent.ACTION_VIEW, url.toUri()))
    }.onFailure { onError(errorMessage) }
}

private fun shareText(context: Context, text: String, title: String, errorMessage: String, onError: (String) -> Unit) {
    runCatching {
        val shareIntent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, text)
        }
        context.startActivity(Intent.createChooser(shareIntent, title))
    }.onFailure { onError(errorMessage) }
}

private const val PROJECT_URL = "https://github.com/LiberVixer/YouTubeHarvester"
private const val RELEASES_URL = "$PROJECT_URL/releases"
private const val TERMS_URL = "$PROJECT_URL#responsible-use"
