package com.liberivixer.youtubeharvester

import android.Manifest
import android.content.ClipboardManager
import android.content.pm.PackageManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.LaunchedEffect
import androidx.core.content.ContextCompat
import androidx.core.content.edit
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.liberivixer.youtubeharvester.quick.QuickDownloadIntegration
import com.liberivixer.youtubeharvester.ui.YouTubeHarvesterApp
import com.liberivixer.youtubeharvester.ui.LocaleController
import com.liberivixer.youtubeharvester.ui.theme.YouTubeHarvesterTheme
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val viewModel: AppViewModel by viewModels()
    private val permissionLauncher = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { }
    private val clipboardManager by lazy { getSystemService(ClipboardManager::class.java) }
    private val clipboardPreferences by lazy { getSharedPreferences(CLIPBOARD_PREFERENCES, Context.MODE_PRIVATE) }
    private val clipboardListener = ClipboardManager.OnPrimaryClipChangedListener {
        if (viewModel.state.value.settingsLoaded && viewModel.state.value.settings.watchClipboard) {
            processClipboard()
        }
    }

    override fun attachBaseContext(newBase: Context) {
        super.attachBaseContext(LocaleController.wrap(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestDownloadPermissions()
        handleIncomingIntent(intent)
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.state
                    .map { it.settingsLoaded && it.settings.watchClipboard }
                    .distinctUntilChanged()
                    .collect { enabled -> if (enabled) processClipboard() }
            }
        }
        enableEdgeToEdge()
        setContent {
            val state by viewModel.state.collectAsState()
            LaunchedEffect(state.settingsLoaded, state.settings.language) {
                if (state.settingsLoaded) {
                    LocaleController.apply(this@MainActivity, state.settings.language)
                }
            }
            YouTubeHarvesterTheme(state.settings.themeMode) {
                YouTubeHarvesterApp(state = state, viewModel = viewModel)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIncomingIntent(intent)
    }

    override fun onStart() {
        super.onStart()
        viewModel.syncSystemLanguage()
        clipboardManager.addPrimaryClipChangedListener(clipboardListener)
    }

    override fun onPostResume() {
        super.onPostResume()
        if (viewModel.state.value.settingsLoaded && viewModel.state.value.settings.watchClipboard) {
            processClipboard()
        }
    }

    override fun onStop() {
        clipboardManager.removePrimaryClipChangedListener(clipboardListener)
        super.onStop()
    }

    private fun handleIncomingIntent(incoming: Intent?) {
        when (incoming?.action) {
            Intent.ACTION_SEND -> {
                incoming.getCharSequenceExtra(Intent.EXTRA_TEXT)?.toString()?.let(viewModel::requestQuickDownload)
                incoming.action = null
                incoming.removeExtra(Intent.EXTRA_TEXT)
            }
            QuickDownloadIntegration.ACTION_QUICK_DOWNLOAD -> {
                viewModel.openQuickDownloadScreen()
                incoming.action = null
            }
        }
    }

    private fun processClipboard() {
        if (!viewModel.state.value.settingsLoaded || !viewModel.state.value.settings.watchClipboard) return
        val text = QuickDownloadIntegration.clipboardText(this) ?: return
        val signature = QuickDownloadIntegration.clipboardSignature(this, text)
        if (clipboardPreferences.getString(LAST_CLIPBOARD_SIGNATURE, null) == signature) return
        clipboardPreferences.edit { putString(LAST_CLIPBOARD_SIGNATURE, signature) }
        viewModel.requestQuickDownload(text)
    }

    private fun requestDownloadPermissions() {
        val permissions = buildList {
            if (
                Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                ContextCompat.checkSelfPermission(this@MainActivity, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
            ) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
            if (
                Build.VERSION.SDK_INT <= Build.VERSION_CODES.P &&
                ContextCompat.checkSelfPermission(this@MainActivity, Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED
            ) {
                add(Manifest.permission.WRITE_EXTERNAL_STORAGE)
            }
        }
        if (permissions.isNotEmpty()) permissionLauncher.launch(permissions.toTypedArray())
    }

    private companion object {
        const val CLIPBOARD_PREFERENCES = "yth_clipboard"
        const val LAST_CLIPBOARD_SIGNATURE = "last_signature"
    }
}
