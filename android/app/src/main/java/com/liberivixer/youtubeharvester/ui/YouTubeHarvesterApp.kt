package com.liberivixer.youtubeharvester.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.liberivixer.youtubeharvester.AppViewModel
import com.liberivixer.youtubeharvester.model.AppTab
import com.liberivixer.youtubeharvester.model.AppUiState
import com.liberivixer.youtubeharvester.ui.screens.ArchiveScreen
import com.liberivixer.youtubeharvester.ui.screens.ChannelsScreen
import com.liberivixer.youtubeharvester.ui.screens.OverviewScreen
import com.liberivixer.youtubeharvester.ui.screens.QueueScreen
import com.liberivixer.youtubeharvester.ui.screens.SettingsScreen
import com.liberivixer.youtubeharvester.ui.screens.SettingsTool

@Composable
fun YouTubeHarvesterApp(
    state: AppUiState,
    viewModel: AppViewModel,
) {
    var selectedTab by rememberSaveable { mutableStateOf(AppTab.Overview) }
    var requestedTool by rememberSaveable { mutableStateOf<SettingsTool?>(null) }
    var handledOverviewRequest by rememberSaveable { mutableLongStateOf(0L) }

    androidx.compose.runtime.LaunchedEffect(state.openOverviewRequestId) {
        if (state.openOverviewRequestId != handledOverviewRequest) {
            selectedTab = AppTab.Overview
            handledOverviewRequest = state.openOverviewRequestId
        }
    }

    androidx.compose.runtime.LaunchedEffect(state.quickDownloadRequestId, state.pendingQuickDownloadUrl) {
        if (state.pendingQuickDownloadUrl != null) selectedTab = AppTab.Overview
    }

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        topBar = {
            HarvesterTopBar(
                themeMode = state.settings.themeMode,
                onThemeSelected = viewModel::setTheme,
                onSettings = { selectedTab = AppTab.Settings },
                onLogs = { requestedTool = SettingsTool.Logs; selectedTab = AppTab.Settings },
                onDiagnostics = { requestedTool = SettingsTool.Diagnostics; selectedTab = AppTab.Settings },
            )
        },
        bottomBar = {
            HarvesterBottomBar(
                selected = selectedTab,
                queueCount = state.queue.size,
                onOpenDownloads = viewModel::openDownloadFolder,
                onSelect = { selectedTab = it },
            )
        },
    ) { padding ->
        Box(Modifier.padding(PaddingValues(top = padding.calculateTopPadding(), bottom = padding.calculateBottomPadding()))) {
            when (selectedTab) {
                AppTab.Overview -> OverviewScreen(state, viewModel)
                AppTab.Channels -> ChannelsScreen(state, viewModel)
                AppTab.Queue -> QueueScreen(state, viewModel)
                AppTab.Archive -> ArchiveScreen(state, viewModel)
                AppTab.Settings -> SettingsScreen(state, viewModel, requestedTool) { requestedTool = null }
            }
        }
    }
}
