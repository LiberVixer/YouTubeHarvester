package com.liberivixer.youtubeharvester.media

import android.content.Context
import com.liberivixer.youtubeharvester.BuildConfig
import com.liberivixer.youtubeharvester.R
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import java.io.File
import java.security.MessageDigest

object AndroidYtDlpRuntime {
    @Volatile private var youtubeDlReady = false
    @Volatile private var ffmpegReady = false

    // Initialization is local only. Engine updates arrive through signed APK updates.
    @Synchronized
    fun ensure(context: Context, requireFfmpeg: Boolean) {
        val appContext = context.applicationContext
        if (!youtubeDlReady) {
            BundledRuntimeFile.ensure(
                File(appContext.noBackupFilesDir, "youtubedl-android/yt-dlp/yt-dlp"),
                BuildConfig.YTDLP_SHA256,
            ) { appContext.resources.openRawResource(R.raw.ytdlp) }
            val plugin = appContext.resources.openRawResource(R.raw.harvest_tracks).use { it.readBytes() }
            val digest = MessageDigest.getInstance("SHA-256").digest(plugin).joinToString("") { "%02x".format(it) }
            BundledRuntimeFile.ensure(File(pluginDirectory(appContext), "yth/yt_dlp_plugins/postprocessor/harvest_tracks.py"), digest) {
                plugin.inputStream()
            }
            YoutubeDL.init(appContext)
            youtubeDlReady = true
        }
        if (requireFfmpeg && !ffmpegReady) {
            FFmpeg.init(appContext)
            ffmpegReady = true
        }
    }

    fun pluginDirectory(context: Context): File = File(context.noBackupFilesDir, "harvest-plugins")
}
