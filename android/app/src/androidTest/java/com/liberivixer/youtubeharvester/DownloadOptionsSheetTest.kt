package com.liberivixer.youtubeharvester

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasScrollAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isToggleable
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.test.platform.app.InstrumentationRegistry
import com.liberivixer.youtubeharvester.model.AppUiState
import com.liberivixer.youtubeharvester.model.AudioTrackOption
import com.liberivixer.youtubeharvester.model.DownloadMediaOptions
import com.liberivixer.youtubeharvester.model.MediaOptionSection
import com.liberivixer.youtubeharvester.model.MediaPreview
import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.ui.DownloadOptionsSheet
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class DownloadOptionsSheetTest {
    @get:Rule val compose = createComposeRule()

    @Test fun footerStaysVisibleAndSelectedTrackReachesBothActions() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val state = mutableStateOf(AppUiState(isDownloadOptionsLoading = true))
        var downloaded = emptyList<AudioTrackOption>()
        var queued = emptyList<AudioTrackOption>()
        val download = context.getString(R.string.download)
        val addToQueue = context.getString(R.string.add_to_queue)
        compose.setContent {
            MaterialTheme {
                DownloadOptionsSheet(state.value, "1080p", {},
                    onDownload = { _, audio, _ -> downloaded = audio },
                    onAddToQueue = { _, audio, _ -> queued = audio })
            }
        }
        compose.onNodeWithText(download).assertIsDisplayed().assertIsNotEnabled()
        compose.onNodeWithText(addToQueue).assertIsDisplayed().assertIsNotEnabled()

        val tracks = (0 until 40).map { index ->
            AudioTrackOption("audio:$index", "$index", "audio", "en", "Audio $index",
                false, MediaOptionSection.PREFERRED)
        }
        compose.runOnIdle {
            state.value = AppUiState(downloadMediaOptions = DownloadMediaOptions(
                MediaPreview("https://example.com/video", "fixture", MediaSource.YouTube,
                    "A long title to exercise wrapping in a compact download options sheet", "Test", null),
                tracks, emptyList()))
        }
        compose.onNode(hasScrollAction()).performScrollToNode(hasText("Audio 0"))
        compose.onAllNodes(isToggleable()).onFirst().performClick()
        compose.onNode(hasScrollAction()).performScrollToNode(hasText("Audio 39"))
        compose.onNodeWithText(download).assertIsDisplayed().performClick()
        compose.onNodeWithText(addToQueue).assertIsDisplayed().performClick()
        compose.runOnIdle {
            assertEquals(listOf(tracks.first()), downloaded)
            assertEquals(downloaded, queued)
        }
    }
}
