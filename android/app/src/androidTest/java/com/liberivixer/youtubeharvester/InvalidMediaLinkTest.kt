package com.liberivixer.youtubeharvester

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onLast
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import androidx.test.espresso.Espresso.closeSoftKeyboard
import org.junit.Rule
import org.junit.Test

class InvalidMediaLinkTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test fun overviewExplainsInvalidLinkAndClearsError() {
        assertValidation()
    }

    @Test fun queueExplainsInvalidLinkAndClearsError() {
        compose.onAllNodesWithText(compose.activity.getString(R.string.queue_short))
            .onLast().performClick()
        assertValidation()
    }

    private fun assertValidation() {
        val error = compose.activity.getString(R.string.invalid_media_link)
        val field = compose.onNode(hasSetTextAction())
        compose.onNodeWithText(error).assertDoesNotExist()
        field.performTextInput("https://example.com/video")
        compose.waitUntil(timeoutMillis = 5000) {
            compose.onAllNodesWithText(error).fetchSemanticsNodes().isNotEmpty()
        }
        closeSoftKeyboard()
        compose.onAllNodesWithText(error).onFirst().performScrollTo().assertIsDisplayed()
        field.performTextClearance()
        compose.onNodeWithText(error).assertDoesNotExist()
        field.performTextInput("https://www.youtube.com/watch?v=jNQXAC9IVRw")
        compose.onNodeWithText(error).assertDoesNotExist()
        field.performTextClearance()
    }
}
