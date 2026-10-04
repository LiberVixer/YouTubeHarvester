package com.liberivixer.youtubeharvester.notifications

import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URLDecoder
import java.nio.charset.StandardCharsets
import org.junit.Assert.assertEquals
import org.junit.Test

class TelegramNotifierTest {
    @Test
    fun formBodyEscapesChannelAndMessage() {
        val body = TelegramNotifier.telegramFormBody("@test channel", "Ready & done").decodeToString()
        val values = body.split('&').associate { part ->
            val (key, value) = part.split('=', limit = 2)
            decode(key) to decode(value)
        }

        assertEquals("@test channel", values["chat_id"])
        assertEquals("Ready & done", values["text"])
        assertEquals("true", values["disable_web_page_preview"])
    }

    @Test
    fun proxySupportsHttpAndSocks() {
        val http = TelegramNotifier.telegramProxy("http://proxy.example:3128")
        val socks = TelegramNotifier.telegramProxy("socks5://localhost:1081")

        assertEquals(Proxy.Type.HTTP, http.type())
        assertEquals(3128, (http.address() as InetSocketAddress).port)
        assertEquals(Proxy.Type.SOCKS, socks.type())
        assertEquals(1081, (socks.address() as InetSocketAddress).port)
    }

    @Test
    fun blankProxyUsesDirectConnection() {
        assertEquals(Proxy.NO_PROXY, TelegramNotifier.telegramProxy(""))
    }

    @Test
    fun proxyRejectsSilentlyUnsupportedOptions() {
        listOf("https://proxy.example", "http://user:password@proxy.example", "socks5://user@proxy.example",
            "http://proxy.example:0", "http://proxy.example:70000", "http://proxy.example/path",
            "http://proxy.example?password=secret").forEach {
            assertEquals(it, false, TelegramNotifier.isConfigurationValid("12345:abc", "-100123", it))
        }
    }

    @Test
    fun configurationRejectsMalformedSecretsAndProxy() {
        assertEquals(true, TelegramNotifier.isConfigurationValid("12345:abc_DEF-9", "-100123", ""))
        assertEquals(false, TelegramNotifier.isConfigurationValid("not-a-token", "-100123", ""))
        assertEquals(false, TelegramNotifier.isConfigurationValid("12345:abc", "", ""))
        assertEquals(false, TelegramNotifier.isConfigurationValid("12345:abc", "-100123", "ftp://proxy"))
    }

    private fun decode(value: String): String = URLDecoder.decode(value, StandardCharsets.UTF_8.name())
}
