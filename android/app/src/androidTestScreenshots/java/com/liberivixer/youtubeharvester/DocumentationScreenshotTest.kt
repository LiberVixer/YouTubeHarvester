package com.liberivixer.youtubeharvester

import android.app.Application
import android.content.res.Configuration
import android.graphics.Bitmap
import android.os.SystemClock
import androidx.activity.ComponentActivity
import androidx.activity.compose.LocalActivityResultRegistryOwner
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.LayoutDirection
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.test.platform.app.InstrumentationRegistry
import com.liberivixer.youtubeharvester.model.AppLanguage
import com.liberivixer.youtubeharvester.model.AppSettings
import com.liberivixer.youtubeharvester.model.AppTab
import com.liberivixer.youtubeharvester.model.AppThemeMode
import com.liberivixer.youtubeharvester.model.AppUiState
import com.liberivixer.youtubeharvester.model.ArchiveItem
import com.liberivixer.youtubeharvester.model.ChannelItem
import com.liberivixer.youtubeharvester.model.CheckOutcome
import com.liberivixer.youtubeharvester.model.CheckReport
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.model.QueueItem
import com.liberivixer.youtubeharvester.model.ScheduleItem
import com.liberivixer.youtubeharvester.model.SectionResult
import com.liberivixer.youtubeharvester.model.SectionStatus
import com.liberivixer.youtubeharvester.model.CHANNEL_STATUS_CHECKED
import com.liberivixer.youtubeharvester.ui.HarvesterBottomBar
import com.liberivixer.youtubeharvester.ui.HarvesterTopBar
import com.liberivixer.youtubeharvester.ui.screens.ArchiveScreen
import com.liberivixer.youtubeharvester.ui.screens.ChannelsScreen
import com.liberivixer.youtubeharvester.ui.screens.OverviewScreen
import com.liberivixer.youtubeharvester.ui.screens.QueueScreen
import com.liberivixer.youtubeharvester.ui.screens.SettingsScreen
import com.liberivixer.youtubeharvester.ui.theme.YouTubeHarvesterTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.json.JSONObject
import java.io.File
import java.time.LocalDate
import java.util.Locale

/** Only compiled for the isolated screenshots test variant. */
class DocumentationScreenshotTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun captureAllLanguages() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        assertEquals("com.liberivixer.youtubeharvester.screenshots", context.packageName)
        assertEquals("1.2.1", BuildConfig.VERSION_NAME)
        val store = ViewModelStore()
        val viewModel = ViewModelProvider(store,
            ViewModelProvider.AndroidViewModelFactory(context.applicationContext as Application))[AppViewModel::class.java]
        val language = mutableStateOf(AppLanguage.English)
        val tab = mutableStateOf(AppTab.Overview)
        val state = fixture(context)
        val screens = linkedMapOf(AppTab.Overview to "overview", AppTab.Channels to "channels",
            AppTab.Queue to "queue", AppTab.Archive to "archive", AppTab.Settings to "settings")
        val previousLocale = Locale.getDefault()
        try {
            compose.setContent {
                val configuration = Configuration(context.resources.configuration).apply {
                    setLocale(Locale.forLanguageTag(language.value.tag))
                    setLayoutDirection(Locale.forLanguageTag(language.value.tag))
                    fontScale = 1f
                }
                val localized = context.createConfigurationContext(configuration)
                CompositionLocalProvider(LocalContext provides localized,
                    LocalConfiguration provides configuration,
                    LocalLayoutDirection provides if (language.value == AppLanguage.Arabic) LayoutDirection.Rtl else LayoutDirection.Ltr,
                    LocalActivityResultRegistryOwner provides compose.activity) {
                    YouTubeHarvesterTheme(AppThemeMode.Dark) {
                        key(language.value, tab.value) {
                            Scaffold(modifier = Modifier.fillMaxSize(),
                                topBar = { HarvesterTopBar(AppThemeMode.Dark, {}, {}, {}, {}) },
                                bottomBar = { HarvesterBottomBar(tab.value, state.queue.size, {}, { tab.value = it }) }) { padding ->
                                Box(Modifier.padding(padding)) {
                                    val localizedState = state.copy(settings = state.settings.copy(language = language.value.tag),
                                        statusMessage = localized.getString(R.string.ready))
                                    when (tab.value) {
                                        AppTab.Overview -> OverviewScreen(localizedState, viewModel)
                                        AppTab.Channels -> ChannelsScreen(localizedState, viewModel)
                                        AppTab.Queue -> QueueScreen(localizedState, viewModel)
                                        AppTab.Archive -> ArchiveScreen(localizedState, viewModel)
                                        AppTab.Settings -> SettingsScreen(localizedState, viewModel)
                                    }
                                }
                            }
                        }
                    }
                }
            }
            for (locale in AppLanguage.entries) {
                for ((screen, filename) in screens) {
                    compose.runOnIdle {
                        Locale.setDefault(Locale.forLanguageTag(locale.tag))
                        language.value = locale
                        tab.value = screen
                    }
                    compose.waitForIdle()
                    SystemClock.sleep(350)
                    compose.waitForIdle()
                    compose.onNodeWithText(BuildConfig.VERSION_NAME).assertIsDisplayed()
                    val image = compose.onRoot().captureToImage().asAndroidBitmap()
                    val folder = File(context.filesDir, "readme-screenshots/${locale.tag.substringBefore('-')}").apply { mkdirs() }
                    File(folder, "$filename.png").outputStream().use {
                        check(image.compress(Bitmap.CompressFormat.PNG, 100, it))
                    }
                    println("README_SCREENSHOT ${locale.tag} $filename ${image.width}x${image.height}")
                }
            }
        } finally {
            Locale.setDefault(previousLocale)
            compose.runOnIdle { store.clear() }
        }
    }

    private fun fixture(context: android.content.Context): AppUiState {
        val folder = File(context.filesDir, "readme-assets")
        val igm = File(folder, "igm.jpg").takeIf { it.exists() }?.toURI()?.toString()
        val tech = File(folder, "prohitec.jpg").takeIf { it.exists() }?.toURI()?.toString()
        val video = File(folder, "video.jpg").takeIf { it.exists() }?.toURI()?.toString()
        val metadata = JSONObject(File(folder, "video.json").readText())
        val now = System.currentTimeMillis()
        val channels = listOf(
            ChannelItem("igm", "https://www.youtube.com/@onlinegamercentral", "IGM", "@onlinegamercentral", igm,
                status = CHANNEL_STATUS_CHECKED, lastCheckedEpochMs = now - 420_000),
            ChannelItem("tech", "https://www.youtube.com/@prohitec", "Pro Hi-Tech", "@prohitec", tech,
                status = CHANNEL_STATUS_CHECKED, lastCheckedEpochMs = now - 420_000))
        val titles = listOf(metadata.getString("title"))
        val queue = titles.mapIndexed { index, title ->
            QueueItem("queue-$index", "https://www.youtube.com/watch?v=tYh-7USx09E", title,
                channels[index].name, MediaSource.YouTube, thumbnailUrl = if (index == 0) video else tech)
        }
        val archive = titles.mapIndexed { index, title ->
            ArchiveItem("archive-$index", title, channels[index].name, MediaSource.YouTube,
                ContentType.Video, "1080p", "${LocalDate.now()} 10:0$index", now - 600_000 - index * 60_000,
                thumbnailUrl = if (index == 0) video else tech, audio = listOf("en"), subtitles = listOf("en"))
        }
        return AppUiState(settings = AppSettings(themeMode = AppThemeMode.Dark), settingsLoaded = true,
            channels = channels, queue = queue, archive = archive, scannedChannels = 2, scanTotalChannels = 2,
            schedule = listOf(ScheduleItem("morning", 9, 0, true), ScheduleItem("evening", 18, 0, true)),
            lastCheck = CheckReport(now - 420_000, CheckOutcome.COMPLETED, 2, 2, 0, 1,
                sections = mapOf(ContentType.Video to SectionResult(1, SectionStatus.CHECKED),
                    ContentType.Shorts to SectionResult(0, SectionStatus.CHECKED),
                    ContentType.Stream to SectionResult(0, SectionStatus.CHECKED)), attempted = 1))
    }
}
