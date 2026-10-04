package com.liberivixer.youtubeharvester.data

import com.liberivixer.youtubeharvester.model.AppLanguage
import com.liberivixer.youtubeharvester.model.AppSettings
import com.liberivixer.youtubeharvester.model.AppThemeMode
import org.json.JSONObject

internal object TransferSettings {
    fun encode(s: AppSettings): JSONObject {
        check(!s.telegramCredentialError) { "Unreadable credentials" }
        return JSONObject()
            .put("downloadDirectory", s.downloadDirectory)
            .put("downloadDirectoryUri", s.downloadDirectoryUri ?: JSONObject.NULL)
            .put("tempDirectory", s.tempDirectory).put("maxResolution", s.maxResolution)
            .put("videoLimit", s.videoLimit).put("shortsLimit", s.shortsLimit).put("streamsLimit", s.streamsLimit)
            .put("language", s.language).put("themeMode", s.themeMode.name)
            .put("watchClipboard", s.watchClipboard).put("systemNotifications", s.systemNotifications)
            .put("telegramEnabled", s.telegramEnabled).put("telegramBotToken", s.telegramBotToken)
            .put("telegramChannelId", s.telegramChannelId).put("telegramProxyUrl", s.telegramProxyUrl)
            .put("logRetentionDays", s.logRetentionDays)
    }

    fun decode(j: JSONObject): AppSettings {
        val expected = encode(AppSettings()).keys().asSequence().toSet()
        require(j.keys().asSequence().toSet() == expected)
        fun text(name: String): String = (j.get(name) as? String)?.also { require(it.length <= 8192) }
            ?: error("Invalid setting")
        fun flag(name: String): Boolean = j.get(name) as? Boolean ?: error("Invalid setting")
        fun number(name: String, range: IntRange): Int {
            val n = j.get(name)
            require(n is Int || n is Long)
            val value = (n as Number).toLong()
            require(value in range.first.toLong()..range.last.toLong())
            return value.toInt()
        }
        val language = text("language")
        require(AppLanguage.entries.any { it.tag == language })
        val resolution = text("maxResolution")
        require(resolution in setOf("best", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p"))
        val uri = j.get("downloadDirectoryUri")
        require(uri == JSONObject.NULL || uri is String && uri.length <= 8192)
        return AppSettings(downloadDirectory = text("downloadDirectory"),
            downloadDirectoryUri = if (uri == JSONObject.NULL) null else uri as String,
            tempDirectory = text("tempDirectory"), maxResolution = resolution,
            videoLimit = number("videoLimit", 1..99), shortsLimit = number("shortsLimit", 1..99),
            streamsLimit = number("streamsLimit", 1..99), language = language,
            themeMode = AppThemeMode.valueOf(text("themeMode")), watchClipboard = flag("watchClipboard"),
            systemNotifications = flag("systemNotifications"), telegramEnabled = flag("telegramEnabled"),
            telegramBotToken = text("telegramBotToken"), telegramChannelId = text("telegramChannelId"),
            telegramProxyUrl = text("telegramProxyUrl"), logRetentionDays = number("logRetentionDays", 1..30))
    }

    fun forImport(settings: AppSettings): AppSettings = settings.copy(
        downloadDirectory = AppSettings().downloadDirectory, downloadDirectoryUri = null,
        tempDirectory = "internal-cache", telegramCredentialError = false,
    )
}
