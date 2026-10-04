package com.liberivixer.youtubeharvester.update

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import androidx.core.net.toUri
import com.liberivixer.youtubeharvester.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import org.json.JSONArray
import java.io.File
import java.net.HttpURLConnection
import java.net.URI
import java.security.MessageDigest

internal data class AndroidRelease(val title: String, val url: String, val sha256: String)

internal class AndroidAppUpdater(private val context: Context) {
    suspend fun check(): AndroidRelease? = withContext(Dispatchers.IO) {
        val payload = connection("https://api.github.com/repos/LiberVixer/YouTubeHarvester/releases?per_page=30").let { connection ->
            try { connection.inputStream.use { input ->
                val bytes = input.readBytesBounded(2 * 1024 * 1024)
                bytes.toString(Charsets.UTF_8)
            } } finally { connection.disconnect() }
        }
        selectRelease(payload, Build.SUPPORTED_ABIS.toList(), BuildConfig.VERSION_NAME)
    }

    suspend fun download(release: AndroidRelease): File = withContext(Dispatchers.IO) {
        val directory = File(context.cacheDir, "updates").apply { mkdirs() }
        val output = File(directory, "update.apk")
        val partial = File(directory, "update.part")
        val connection = connection(release.url)
        try {
            val digest = MessageDigest.getInstance("SHA-256")
            connection.inputStream.use { input ->
                partial.outputStream().use { target ->
                    val buffer = ByteArray(64 * 1024)
                    var size = 0L
                    while (true) {
                        currentCoroutineContext().ensureActive()
                        val count = input.read(buffer)
                        if (count < 0) break
                        size += count
                        check(size <= 256L * 1024 * 1024) { "APK exceeds size limit" }
                        digest.update(buffer, 0, count)
                        target.write(buffer, 0, count)
                    }
                }
            }
            check(digest.digest().joinToString("") { "%02x".format(it) }.equals(release.sha256, true)) { "APK checksum mismatch" }
            verifyPackage(partial)
            check(!output.exists() || output.delete()) { "Could not replace cached update" }
            check(partial.renameTo(output)) { "Could not finalize update" }
            output
        } finally {
            partial.delete()
            connection.disconnect()
        }
    }

    @Suppress("DEPRECATION")
    private fun verifyPackage(file: File) {
        val pm = context.packageManager
        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        val candidate = checkNotNull(pm.getPackageArchiveInfo(file.path, flags)) { "Invalid APK" }
        val installed = pm.getPackageInfo(context.packageName, flags)
        check(candidate.packageName == installed.packageName) { "Unexpected application package" }
        val candidateCode = if (Build.VERSION.SDK_INT >= 28) candidate.longVersionCode else candidate.versionCode.toLong()
        check(candidateCode > BuildConfig.VERSION_CODE) { "Update is not newer than installed version" }
        val candidateSignatures = if (Build.VERSION.SDK_INT >= 28) candidate.signingInfo?.apkContentsSigners else candidate.signatures
        val installedSignatures = if (Build.VERSION.SDK_INT >= 28) installed.signingInfo?.apkContentsSigners else installed.signatures
        check(!candidateSignatures.isNullOrEmpty() && !installedSignatures.isNullOrEmpty() &&
            candidateSignatures.toSet() == installedSignatures.toSet()) { "APK signing certificate mismatch" }
    }

    fun canInstall(): Boolean = context.packageManager.canRequestPackageInstalls()

    fun requestInstallPermission() {
        context.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, "package:${context.packageName}".toUri()))
    }

    fun install(file: File) {
        verifyPackage(file)
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.updates", file)
        context.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
    }

    private fun connection(url: String): HttpURLConnection {
        var current = url
        repeat(6) {
            val uri = URI(current)
            check(uri.scheme == "https" && uri.host in TRUSTED_HOSTS && uri.userInfo == null && uri.port == -1) { "Untrusted update URL" }
            val connection = uri.toURL().openConnection() as HttpURLConnection
            connection.connectTimeout = 15_000
            connection.readTimeout = 30_000
            connection.instanceFollowRedirects = false
            connection.setRequestProperty("User-Agent", "YouTubeHarvester-Android/${BuildConfig.VERSION_NAME}")
            val status = connection.responseCode
            if (status in 300..399) {
                val redirect = connection.getHeaderField("Location")
                connection.disconnect()
                current = uri.resolve(checkNotNull(redirect)).toString()
            } else {
                if (status !in 200..299) { connection.disconnect(); error("GitHub HTTP $status") }
                return connection
            }
        }
        error("Too many update redirects")
    }

    companion object {
        private val TRUSTED_HOSTS = setOf("api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

        internal fun selectRelease(payload: String, abis: List<String>, installed: String): AndroidRelease? {
            val releases = JSONArray(payload)
            for (index in 0 until releases.length()) {
                val release = releases.getJSONObject(index)
                if (release.optBoolean("draft")) continue
                if (release.optBoolean("prerelease") && !installed.contains("beta", true)) continue
                val title = release.optString("tag_name").removePrefix("android-v").removePrefix("v")
                if (compareVersions(title, installed) <= 0) continue
                val assets = release.optJSONArray("assets") ?: continue
                for (abi in abis) {
                    for (assetIndex in 0 until assets.length()) {
                        val asset = assets.getJSONObject(assetIndex)
                        val name = asset.optString("name")
                        if (!name.endsWith(".apk") || !name.contains("-$abi-") || name.contains("unsigned") || name.contains("debug")) continue
                        val hash = asset.optString("digest").removePrefix("sha256:")
                        if (!hash.matches(Regex("[a-fA-F0-9]{64}"))) continue
                        return AndroidRelease(title, asset.getString("browser_download_url"), hash)
                    }
                }
            }
            return null
        }

        internal fun compareVersions(left: String, right: String): Int {
            fun numbers(value: String) = Regex("\\d+").findAll(value).map { it.value.toIntOrNull() ?: 0 }.toList()
            val a = numbers(left)
            val b = numbers(right)
            for (index in 0 until maxOf(3, a.size, b.size)) {
                if (index == 3) {
                    val aPreview = left.contains("beta", true) || left.contains("dev", true)
                    val bPreview = right.contains("beta", true) || right.contains("dev", true)
                    if (aPreview != bPreview) return if (aPreview) -1 else 1
                }
                val diff = (a.getOrNull(index) ?: 0).compareTo(b.getOrNull(index) ?: 0)
                if (diff != 0) return diff
            }
            val aPreview = left.contains("beta", true) || left.contains("dev", true)
            val bPreview = right.contains("beta", true) || right.contains("dev", true)
            if (aPreview != bPreview) return if (aPreview) -1 else 1
            return 0
        }
    }
}

private fun java.io.InputStream.readBytesBounded(limit: Int): ByteArray {
    val out = java.io.ByteArrayOutputStream()
    val buffer = ByteArray(8192)
    while (true) {
        val count = read(buffer)
        if (count < 0) return out.toByteArray()
        check(out.size() + count <= limit) { "Release metadata exceeds size limit" }
        out.write(buffer, 0, count)
    }
}
