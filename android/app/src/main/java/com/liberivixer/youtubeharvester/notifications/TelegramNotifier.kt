package com.liberivixer.youtubeharvester.notifications

import com.liberivixer.youtubeharvester.model.AppSettings
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URI
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

object TelegramNotifier {
    fun isConfigurationValid(botToken: String, channelId: String, proxyUrl: String): Boolean =
        botToken.trim().matches(BOT_TOKEN) &&
            channelId.isNotBlank() &&
            runCatching { telegramProxy(proxyUrl) }.isSuccess

    suspend fun send(settings: AppSettings, message: String): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            require(!settings.telegramCredentialError) { "Telegram credentials must be entered again" }
            require(settings.telegramBotToken.matches(BOT_TOKEN)) { "Invalid Telegram bot token" }
            require(settings.telegramChannelId.isNotBlank()) { "Telegram channel is missing" }
            val endpoint = URL("https://api.telegram.org/bot${settings.telegramBotToken}/sendMessage")
            val connection = endpoint.openConnection(telegramProxy(settings.telegramProxyUrl)) as HttpURLConnection
            try {
                val body = telegramFormBody(settings.telegramChannelId, message)
                connection.requestMethod = "POST"
                connection.connectTimeout = CONNECT_TIMEOUT_MS
                connection.readTimeout = READ_TIMEOUT_MS
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                connection.setFixedLengthStreamingMode(body.size)
                connection.outputStream.use { it.write(body) }
                check(connection.responseCode in 200..299) { "Telegram HTTP ${connection.responseCode}" }
                connection.inputStream.use { it.readBytes() }
                Unit
            } finally {
                connection.disconnect()
            }
        }
    }

    internal fun telegramFormBody(channelId: String, message: String): ByteArray {
        val text = message.take(MAX_MESSAGE_LENGTH)
        return listOf(
            "chat_id" to channelId,
            "text" to text,
            "disable_web_page_preview" to "true",
        ).joinToString("&") { (key, value) ->
            "${encode(key)}=${encode(value)}"
        }.toByteArray(StandardCharsets.UTF_8)
    }

    internal fun telegramProxy(rawUrl: String): Proxy {
        if (rawUrl.isBlank()) return Proxy.NO_PROXY
        val uri = URI(rawUrl.trim())
        val type = when (uri.scheme?.lowercase()) {
            "http" -> Proxy.Type.HTTP
            "socks", "socks5" -> Proxy.Type.SOCKS
            else -> error("Unsupported proxy protocol")
        }
        require(!uri.host.isNullOrBlank()) { "Proxy host is missing" }
        require(uri.rawUserInfo == null) { "Proxy authentication is not supported" }
        require(uri.rawQuery == null && uri.rawFragment == null && uri.rawPath.orEmpty() in setOf("", "/")) {
            "Proxy URL must contain only the server and port"
        }
        require(uri.port == -1 || uri.port in 1..65535) { "Invalid proxy port" }
        val port = uri.port.takeIf { it > 0 } ?: when (type) {
            Proxy.Type.HTTP -> 8080
            Proxy.Type.SOCKS -> 1080
            else -> error("Unsupported proxy type")
        }
        return Proxy(type, InetSocketAddress.createUnresolved(uri.host, port))
    }

    private fun encode(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8.name())

    private val BOT_TOKEN = Regex("^[0-9]+:[A-Za-z0-9_-]+$")
    private const val CONNECT_TIMEOUT_MS = 12_000
    private const val READ_TIMEOUT_MS = 18_000
    private const val MAX_MESSAGE_LENGTH = 4_000
}
