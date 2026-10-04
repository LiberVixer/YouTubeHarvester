package com.liberivixer.youtubeharvester

import android.content.res.Configuration
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import com.liberivixer.youtubeharvester.model.AppTab
import com.liberivixer.youtubeharvester.ui.HarvesterBottomBar
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.util.Locale

class HarvesterBottomBarTest {
    @get:Rule val compose = createComposeRule()

    @Test fun downloadsLabelFitsAllLocalesAndOpensFolderOnNarrowScreen() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val locales = listOf("en", "ru", "be", "uk", "fr", "es", "hi", "ar", "ja", "zh-CN")
        val locale = mutableStateOf("en")
        var folderOpens = 0
        compose.setContent {
            val configuration = Configuration(context.resources.configuration).apply {
                setLocale(Locale.forLanguageTag(locale.value))
                screenWidthDp = 320
            }
            val localized = context.createConfigurationContext(configuration)
            CompositionLocalProvider(
                LocalContext provides localized,
                LocalConfiguration provides configuration,
                LocalLayoutDirection provides if (locale.value == "ar") LayoutDirection.Rtl else LayoutDirection.Ltr,
            ) {
                MaterialTheme {
                    Box(Modifier.width(320.dp)) {
                        HarvesterBottomBar(AppTab.Overview, 2, { folderOpens++ }, {})
                    }
                }
            }
        }
        for ((index, tag) in locales.withIndex()) {
            compose.runOnIdle { locale.value = tag }
            val configuration = Configuration(context.resources.configuration).apply {
                setLocale(Locale.forLanguageTag(tag))
            }
            val localized = context.createConfigurationContext(configuration)
            val label = localized.getString(R.string.downloads_short)
            val layouts = mutableListOf<TextLayoutResult>()
            compose.onNodeWithText(label, useUnmergedTree = true).assertIsDisplayed()
                .performSemanticsAction(SemanticsActions.GetTextLayoutResult) { it(layouts) }
            val layout = layouts.single()
            assertEquals(tag, 1, layout.lineCount)
            assertFalse(tag, layout.didOverflowHeight)
            assertFalse(tag, layout.isLineEllipsized(0))
            assertEquals(tag, label.length, layout.getLineEnd(0, visibleEnd = true))
            val textWidth = layout.getLineRight(0) - layout.getLineLeft(0)
            assertTrue("$tag: text width=$textWidth, available=${layout.size.width}",
                textWidth <= layout.size.width + 0.5f)
            compose.onNodeWithContentDescription(localized.getString(R.string.downloads))
                .assertIsDisplayed().performClick()
            compose.runOnIdle { assertEquals(index + 1, folderOpens) }
        }
    }

    @Test fun allEnglishLabelsStayOnOneLineWithLargeFont() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val configuration = Configuration(context.resources.configuration).apply {
            setLocale(Locale.ENGLISH)
            screenWidthDp = 320
            fontScale = 1.3f
        }
        val localized = context.createConfigurationContext(configuration)
        compose.setContent {
            CompositionLocalProvider(
                LocalContext provides localized,
                LocalConfiguration provides configuration,
            ) {
                MaterialTheme {
                    Box(Modifier.width(320.dp)) {
                        HarvesterBottomBar(AppTab.Overview, 0, {}, {})
                    }
                }
            }
        }

        listOf(
            R.string.overview,
            R.string.channels,
            R.string.queue_short,
            R.string.archive,
            R.string.downloads_short,
            R.string.settings,
        ).forEach { resourceId ->
            val label = localized.getString(resourceId)
            val layouts = mutableListOf<TextLayoutResult>()
            compose.onNodeWithText(label, useUnmergedTree = true).assertIsDisplayed()
                .performSemanticsAction(SemanticsActions.GetTextLayoutResult) { it(layouts) }
            val layout = layouts.single()
            assertEquals(label, 1, layout.lineCount)
            assertFalse(label, layout.didOverflowHeight)
            assertFalse(label, layout.isLineEllipsized(0))
            assertEquals(label, label.length, layout.getLineEnd(0, visibleEnd = true))
        }
    }
}
