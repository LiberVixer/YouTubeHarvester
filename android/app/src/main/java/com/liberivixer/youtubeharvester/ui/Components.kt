package com.liberivixer.youtubeharvester.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.QueueMusic
import androidx.compose.material.icons.filled.Archive
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Groups
import androidx.compose.material.icons.filled.LightMode
import androidx.compose.material.icons.filled.DarkMode
import androidx.compose.material.icons.filled.BrightnessAuto
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.automirrored.filled.Article
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.BuildConfig
import com.liberivixer.youtubeharvester.model.AppTab
import com.liberivixer.youtubeharvester.model.AppThemeMode
import coil3.compose.AsyncImage

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HarvesterTopBar(
    themeMode: AppThemeMode,
    onThemeSelected: (AppThemeMode) -> Unit,
    onSettings: () -> Unit,
    onLogs: () -> Unit,
    onDiagnostics: () -> Unit,
) {
    var themeExpanded by remember { mutableStateOf(false) }
    var menuExpanded by remember { mutableStateOf(false) }
    TopAppBar(
        colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Image(
                    painter = painterResource(R.drawable.overview_logo),
                    contentDescription = null,
                    modifier = Modifier.size(42.dp).clip(RoundedCornerShape(8.dp)),
                    contentScale = ContentScale.Crop,
                )
                Spacer(Modifier.size(10.dp))
                Text(
                    stringResource(R.string.app_name),
                    modifier = Modifier.weight(1f),
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 20.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.size(8.dp))
                Text(
                    BuildConfig.VERSION_NAME,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    maxLines = 1,
                )
            }
        },
        actions = {
            Box {
                IconButton(onClick = { themeExpanded = true }) {
                    Icon(
                        when (themeMode) {
                            AppThemeMode.System -> Icons.Default.BrightnessAuto
                            AppThemeMode.Light -> Icons.Default.LightMode
                            AppThemeMode.Dark -> Icons.Default.DarkMode
                        },
                        contentDescription = stringResource(R.string.theme),
                    )
                }
                DropdownMenu(expanded = themeExpanded, onDismissRequest = { themeExpanded = false }) {
                    AppThemeMode.entries.forEach { mode ->
                        DropdownMenuItem(
                            text = { Text(themeModeLabel(mode)) },
                            trailingIcon = { if (mode == themeMode) Icon(Icons.Default.Check, contentDescription = null) },
                            onClick = {
                                themeExpanded = false
                                onThemeSelected(mode)
                            },
                        )
                    }
                }
            }
            Box {
                IconButton(onClick = { menuExpanded = true }) {
                    Icon(Icons.Default.MoreVert, contentDescription = stringResource(R.string.menu))
                }
                DropdownMenu(expanded = menuExpanded, onDismissRequest = { menuExpanded = false }) {
                    listOf(
                        Triple(R.string.settings, Icons.Default.Settings, onSettings),
                        Triple(R.string.application_logs, Icons.AutoMirrored.Filled.Article, onLogs),
                        Triple(R.string.diagnostics, Icons.Default.BugReport, onDiagnostics),
                    ).forEach { (label, icon, action) ->
                        DropdownMenuItem(
                            text = { Text(stringResource(label)) },
                            leadingIcon = { Icon(icon, contentDescription = null) },
                            onClick = { menuExpanded = false; action() },
                        )
                    }
                }
            }
        },
    )
}

@Composable
fun themeModeLabel(mode: AppThemeMode): String = stringResource(
    when (mode) {
        AppThemeMode.System -> R.string.system_theme
        AppThemeMode.Light -> R.string.light_theme
        AppThemeMode.Dark -> R.string.dark_theme
    },
)

@Composable
fun HarvesterBottomBar(
    selected: AppTab,
    queueCount: Int,
    onOpenDownloads: () -> Unit,
    onSelect: (AppTab) -> Unit,
) {
    val configuration = LocalConfiguration.current
    val windowWidthDp = with(LocalDensity.current) { LocalWindowInfo.current.containerSize.width.toDp() }
    val compactLabels = windowWidthDp.value / (AppTab.entries.size + 1) < 64f ||
        configuration.fontScale > 1.15f
    val labelFontSize = if (compactLabels) 8.sp else 10.sp
    NavigationBar(containerColor = MaterialTheme.colorScheme.background) {
        AppTab.entries.forEach { tab ->
            if (tab == AppTab.Settings) {
                val downloads = stringResource(R.string.downloads)
                NavigationBarItem(
                    modifier = Modifier.semantics { contentDescription = downloads },
                    selected = false,
                    onClick = onOpenDownloads,
                    icon = { Icon(Icons.Default.Folder, contentDescription = downloads) },
                    label = { Text(stringResource(R.string.downloads_short), fontSize = labelFontSize, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center) },
                )
            }
            val label = tabLabel(tab)
            val icon = when (tab) {
                AppTab.Overview -> Icons.Default.Dashboard
                AppTab.Channels -> Icons.Default.Groups
                AppTab.Queue -> Icons.AutoMirrored.Filled.QueueMusic
                AppTab.Archive -> Icons.Default.Archive
                AppTab.Settings -> Icons.Default.Settings
            }
            NavigationBarItem(
                selected = tab == selected,
                onClick = { onSelect(tab) },
                icon = {
                    BadgedBox(
                        badge = {
                            if (tab == AppTab.Queue && queueCount > 0) {
                                Badge { Text(queueCount.coerceAtMost(99).toString()) }
                            }
                        },
                    ) {
                        Icon(icon, contentDescription = label)
                    }
                },
                label = { Text(label, fontSize = labelFontSize, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center) },
            )
        }
    }
}

@Composable
private fun tabLabel(tab: AppTab): String = stringResource(
    when (tab) {
        AppTab.Overview -> R.string.overview
        AppTab.Channels -> R.string.channels
        AppTab.Queue -> R.string.queue_short
        AppTab.Archive -> R.string.archive
        AppTab.Settings -> R.string.settings
    },
)

@Composable
fun ScreenTitle(
    title: String,
    count: Int? = null,
    trailing: @Composable (() -> Unit)? = null,
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(title, fontSize = 26.sp, fontWeight = FontWeight.Bold)
        if (count != null) {
            Spacer(Modifier.size(10.dp))
            Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(7.dp)) {
                Text(count.toString(), modifier = Modifier.padding(horizontal = 9.dp, vertical = 4.dp), fontSize = 18.sp)
            }
        }
        Spacer(Modifier.weight(1f))
        trailing?.invoke()
    }
}

@Composable
fun SectionTitle(title: String, modifier: Modifier = Modifier) {
    Text(
        title,
        fontSize = 20.sp,
        fontWeight = FontWeight.SemiBold,
        modifier = modifier.padding(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 8.dp),
    )
}

@Composable
fun BorderedPanel(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(7.dp),
        color = MaterialTheme.colorScheme.surface,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        content()
    }
}

@Composable
fun MetadataLine(symbol: String, text: String, modifier: Modifier = Modifier) {
    Row(modifier = modifier, verticalAlignment = Alignment.CenterVertically) {
        Text(symbol, fontSize = 16.sp)
        Spacer(Modifier.size(7.dp))
        Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
fun SettingsRow(
    icon: String,
    label: String,
    secondary: String? = null,
    onClick: (() -> Unit)? = null,
    trailing: @Composable () -> Unit,
) {
    val configuration = LocalConfiguration.current
    val windowWidthDp = with(LocalDensity.current) { LocalWindowInfo.current.containerSize.width.toDp() }
    val compactText = windowWidthDp < 400.dp || configuration.fontScale > 1.15f
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(icon, fontSize = 23.sp, modifier = Modifier.size(36.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                label,
                fontSize = if (compactText) 16.sp else 18.sp,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            if (!secondary.isNullOrBlank()) {
                Spacer(Modifier.height(3.dp))
                Text(secondary, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
        }
        Spacer(Modifier.size(12.dp))
        trailing()
    }
}

@Composable
fun Divider() {
    HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.7f))
}

@Composable
fun RemoteThumbnail(
    url: String?,
    fallbackText: String,
    contentDescription: String?,
    modifier: Modifier = Modifier,
) {
    var imageFailed by remember(url) { mutableStateOf(false) }
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(6.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(6.dp)),
        contentAlignment = Alignment.Center,
    ) {
        if (url.isNullOrBlank() || imageFailed) {
            Text(fallbackText.take(2).uppercase(), fontWeight = FontWeight.Bold, fontSize = 20.sp)
        } else {
            AsyncImage(
                model = url,
                contentDescription = contentDescription,
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Crop,
                onError = { imageFailed = true },
            )
        }
    }
}
