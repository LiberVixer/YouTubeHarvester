package com.liberivixer.youtubeharvester

import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.text.TextLayoutResult
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test

class OverviewAccessibilityTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test fun linkActionLabelsAreNotClipped() {
        for (resource in listOf(R.string.add_to_queue, R.string.quick, R.string.download)) {
            val label = compose.activity.getString(resource)
            val layouts = mutableListOf<TextLayoutResult>()
            compose.onNodeWithText(label).assertIsDisplayed()
                .performSemanticsAction(SemanticsActions.GetTextLayoutResult) { it(layouts) }
            val layout = layouts.single()
            assertFalse("Clipped label: $label", layout.didOverflowHeight)
            assertEquals(label.length, layout.getLineEnd(layout.lineCount - 1, visibleEnd = true))
        }
    }
}
