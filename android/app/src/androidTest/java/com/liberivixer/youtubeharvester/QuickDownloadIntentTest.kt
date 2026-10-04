package com.liberivixer.youtubeharvester

import android.app.Application
import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.ParcelFileDescriptor
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.liberivixer.youtubeharvester.data.SettingsDataStore
import com.liberivixer.youtubeharvester.quick.QuickDownloadIntegration
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class QuickDownloadIntentTest {
    @Before fun grantStartupPermissions() {
        val context = ApplicationProvider.getApplicationContext<Application>()
        val permission = when {
            Build.VERSION.SDK_INT >= 33 -> Manifest.permission.POST_NOTIFICATIONS
            Build.VERSION.SDK_INT <= 28 -> Manifest.permission.WRITE_EXTERNAL_STORAGE
            else -> return
        }
        if (context.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED) return
        // A fresh install must not let the startup permission dialog intercept the quick intent.
        val result = InstrumentationRegistry.getInstrumentation().uiAutomation
            .executeShellCommand("pm grant ${context.packageName} $permission")
        ParcelFileDescriptor.AutoCloseInputStream(result).use { it.readBytes() }
        assertEquals(PackageManager.PERMISSION_GRANTED, context.checkSelfPermission(permission))
    }

    @Test fun externalQuickActionDoesNotUseClipboardWhenWatchingIsOff(): Unit = runBlocking {
        val context = ApplicationProvider.getApplicationContext<Application>()
        val store = SettingsDataStore(context)
        val settings = store.settings.first()
        store.save(settings.copy(watchClipboard = false))
        try {
            // Consumed quick intents have no action; keep ActivityScenario's filter aligned.
            ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java)).use { scenario ->
                lateinit var viewModel: AppViewModel
                scenario.onActivity { activity -> viewModel = ViewModelProvider(activity)[AppViewModel::class.java] }
                withTimeout(10_000) { viewModel.state.first { it.settingsLoaded && !it.settings.watchClipboard } }
                val before = viewModel.state.value.quickDownloadRequestId
                scenario.onActivity { activity ->
                    activity.getSystemService(ClipboardManager::class.java).setPrimaryClip(
                        ClipData.newPlainText("Test", "https://youtu.be/dQw4w9WgXcQ"),
                    )
                    activity.startActivity(Intent(activity, MainActivity::class.java).apply {
                        action = QuickDownloadIntegration.ACTION_QUICK_DOWNLOAD
                        flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
                    })
                }
                withTimeout(10_000) { viewModel.state.first { it.openOverviewRequestId > 0 } }
                scenario.onActivity {
                    assertTrue(viewModel.state.value.openOverviewRequestId > 0)
                    assertEquals(before, viewModel.state.value.quickDownloadRequestId)
                    assertNull(viewModel.state.value.pendingQuickDownloadUrl)
                }
            }
        } finally { store.save(settings) }
    }
}
