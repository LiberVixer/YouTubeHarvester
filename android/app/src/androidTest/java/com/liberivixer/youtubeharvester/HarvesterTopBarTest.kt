package com.liberivixer.youtubeharvester

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import com.liberivixer.youtubeharvester.model.AppThemeMode
import com.liberivixer.youtubeharvester.ui.HarvesterTopBar
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class HarvesterTopBarTest {
    @get:Rule val compose = createComposeRule()

    @Test fun versionAndActionsRemainVisibleOnNarrowScreen() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        var settingsOpened = false
        compose.setContent {
            MaterialTheme {
                Box(Modifier.width(320.dp)) {
                    HarvesterTopBar(AppThemeMode.System, {},
                        onSettings = { settingsOpened = true }, onLogs = {}, onDiagnostics = {})
                }
            }
        }
        val layouts = mutableListOf<TextLayoutResult>()
        val version = BuildConfig.VERSION_NAME
        compose.onNodeWithText(version)
            .assertIsDisplayed()
            .performSemanticsAction(SemanticsActions.GetTextLayoutResult) { it(layouts) }
        assertEquals(1, layouts.single().lineCount)
        val layout = layouts.single()
        assertFalse(layout.didOverflowHeight)
        assertFalse(layout.isLineEllipsized(0))
        assertEquals(version.length, layout.getLineEnd(0, visibleEnd = true))
        // The cached paragraph can be wider than its text; check the occupied line bounds.
        assertTrue(layout.getLineLeft(0) >= 0f)
        assertTrue("Version right=${layout.getLineRight(0)}, width=${layout.size.width}",
            layout.getLineRight(0) <= layout.size.width + 0.5f)
        compose.onNodeWithText(context.getString(R.string.beta)).assertDoesNotExist()
        compose.onNodeWithContentDescription(context.getString(R.string.theme)).assertIsDisplayed()
        compose.onNodeWithContentDescription(context.getString(R.string.menu))
            .assertIsDisplayed().performClick()
        compose.onNodeWithText(context.getString(R.string.settings)).performClick()
        compose.runOnIdle { assertTrue(settingsOpened) }
    }
}
