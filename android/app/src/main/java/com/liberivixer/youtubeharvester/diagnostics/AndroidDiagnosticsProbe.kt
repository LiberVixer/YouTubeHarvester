package com.liberivixer.youtubeharvester.diagnostics

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.os.Environment
import android.os.PowerManager
import android.os.StatFs
import android.provider.DocumentsContract
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import com.liberivixer.youtubeharvester.media.AndroidYtDlpRuntime
import com.liberivixer.youtubeharvester.model.AppSettings
import com.liberivixer.youtubeharvester.model.DiagnosticsSnapshot
import com.liberivixer.youtubeharvester.BuildConfig
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class AndroidDiagnosticsProbe(context: Context) {
    private val appContext = context.applicationContext

    suspend fun run(settings: AppSettings): DiagnosticsSnapshot = withContext(Dispatchers.IO) {
        val runtime = runCatching {
            AndroidYtDlpRuntime.ensure(appContext, requireFfmpeg = true)
            BuildConfig.YTDLP_VERSION
        }
        val network = networkStatus()
        DiagnosticsSnapshot(
            checkedAtEpochMs = System.currentTimeMillis(),
            ytDlpVersion = runtime.getOrNull()?.takeIf(String::isNotBlank),
            runtimeReady = runtime.isSuccess,
            runtimeError = runtime.exceptionOrNull()?.safeMessage(),
            ffmpegBundled = nativeLibraryExists("libffmpeg.so"),
            quickJsBundled = nativeLibraryExists("libqjs.so"),
            networkConnected = network.first,
            networkValidated = network.second,
            notificationsAllowed = notificationsAllowed(),
            downloadDestinationAccessible = destinationAccessible(settings.downloadDirectoryUri),
            availableStorageBytes = availableStorageBytes(),
            batteryOptimizationExempt = batteryOptimizationExempt(),
        )
    }

    @SuppressLint("MissingPermission")
    private fun networkStatus(): Pair<Boolean, Boolean> = runCatching {
        val manager = appContext.getSystemService(ConnectivityManager::class.java)
        val capabilities = manager.getNetworkCapabilities(manager.activeNetwork)
        val connected = capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
        val validated = capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true
        connected to validated
    }.getOrDefault(false to false)

    private fun notificationsAllowed(): Boolean {
        val runtimePermission = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(appContext, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        return runtimePermission && NotificationManagerCompat.from(appContext).areNotificationsEnabled()
    }

    private fun destinationAccessible(rawTreeUri: String?): Boolean {
        if (rawTreeUri.isNullOrBlank()) {
            val legacyPermission = Build.VERSION.SDK_INT > Build.VERSION_CODES.P ||
                ContextCompat.checkSelfPermission(appContext, Manifest.permission.WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED
            return legacyPermission && Environment.getExternalStorageState() == Environment.MEDIA_MOUNTED
        }
        return runCatching {
            val treeUri = rawTreeUri.toUri()
            val permission = appContext.contentResolver.persistedUriPermissions.firstOrNull {
                it.uri == treeUri && it.isReadPermission && it.isWritePermission
            } ?: return@runCatching false
            val documentId = DocumentsContract.getTreeDocumentId(permission.uri)
            val documentUri = DocumentsContract.buildDocumentUriUsingTree(permission.uri, documentId)
            appContext.contentResolver.query(
                documentUri,
                arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID),
                null,
                null,
                null,
            )?.use { cursor -> cursor.moveToFirst() } == true
        }.getOrDefault(false)
    }

    private fun availableStorageBytes(): Long? = runCatching {
        val location = appContext.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: return@runCatching null
        StatFs(location.absolutePath).availableBytes
    }.getOrNull()

    private fun batteryOptimizationExempt(): Boolean = runCatching {
        appContext.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(appContext.packageName)
    }.getOrDefault(false)

    private fun nativeLibraryExists(name: String): Boolean {
        val directory = appContext.applicationInfo.nativeLibraryDir?.let(::File) ?: return false
        return File(directory, name).isFile
    }

    private fun Throwable.safeMessage(): String = message
        .orEmpty()
        .replace(Regex("\\s+"), " ")
        .trim()
        .take(300)
        .ifBlank { javaClass.simpleName }
}
