package com.liberivixer.youtubeharvester

import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
import androidx.test.platform.app.InstrumentationRegistry
import com.liberivixer.youtubeharvester.ui.screens.TransferPasswordDialog
import com.liberivixer.youtubeharvester.ui.screens.DataTransferResult
import com.liberivixer.youtubeharvester.ui.theme.YouTubeHarvesterTheme
import com.liberivixer.youtubeharvester.ui.LocaleController
import com.liberivixer.youtubeharvester.model.AppThemeMode
import org.junit.Assert.assertArrayEquals
import org.junit.Rule
import org.junit.Test

class TransferPasswordDialogTest {
    @get:Rule val compose = createComposeRule()
    private fun text(id: Int) = LocaleController.wrap(InstrumentationRegistry.getInstrumentation().targetContext).getString(id)

    @Test fun transferResultIsVisibleForSuccessAndFailure() {
        val message = androidx.compose.runtime.mutableStateOf("")
        compose.setContent { YouTubeHarvesterTheme(AppThemeMode.System) { DataTransferResult(message.value) } }
        val success = text(R.string.transfer_exported)
        val failure = text(R.string.transfer_not_empty)
        compose.onNodeWithText(success).assertDoesNotExist()
        compose.runOnIdle { message.value = success }
        compose.onNodeWithText(success).assertIsDisplayed()
        compose.runOnIdle { message.value = failure }
        compose.onNodeWithText(success).assertDoesNotExist()
        compose.onNodeWithText(failure).assertIsDisplayed()
        compose.runOnIdle { message.value = "" }
        compose.onNodeWithText(failure).assertDoesNotExist()
    }

    @Test fun exportRequiresStrongMatchingPasswordBeforeConfirmation() {
        var confirmed: CharArray? = null
        compose.setContent { YouTubeHarvesterTheme(AppThemeMode.System) {
            TransferPasswordDialog(true, {}, { confirmed = it })
        } }
        val confirm = compose.onNode(hasText(text(R.string.transfer_export)) and hasClickAction())
        confirm.assertIsNotEnabled()
        compose.onNodeWithText(text(R.string.transfer_password)).performTextInput("short")
        compose.onNodeWithText(text(R.string.transfer_password_repeat)).performTextInput("short")
        confirm.assertIsNotEnabled()
        val password = "QA-only-dialog-passphrase"
        compose.onNodeWithText(text(R.string.transfer_password)).performTextReplacement(password)
        confirm.assertIsNotEnabled()
        compose.onNodeWithText(text(R.string.transfer_password_repeat)).performTextReplacement(password)
        confirm.assertIsEnabled().performClick()
        compose.runOnIdle {
            assertArrayEquals(password.toCharArray(), confirmed)
            confirmed?.fill('\u0000')
        }
    }

    @Test fun importAcceptsPasswordWithoutExportConfirmationField() {
        var confirmed: CharArray? = null
        compose.setContent { YouTubeHarvesterTheme(AppThemeMode.System) {
            TransferPasswordDialog(false, {}, { confirmed = it })
        } }
        val confirm = compose.onNode(hasText(text(R.string.transfer_import)) and hasClickAction())
        confirm.assertIsNotEnabled()
        val password = "QA-only-import-passphrase"
        compose.onNodeWithText(text(R.string.transfer_password)).performTextInput(password)
        confirm.assertIsEnabled().performClick()
        compose.runOnIdle {
            assertArrayEquals(password.toCharArray(), confirmed)
            confirmed?.fill('\u0000')
        }
    }
}
