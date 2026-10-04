package com.liberivixer.youtubeharvester.media

import java.net.URI
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.MediaSource

data class ParsedChannelUrl(
    val id: String,
    val normalizedUrl: String,
    val displayName: String,
    val handle: String,
    val source: MediaSource = MediaSource.YouTube,
    val collection: Boolean = false,
) {
    val sections: List<ContentType> get() = when {
        collection -> listOf(ContentType.Video)
        source == MediaSource.Rutube -> listOf(ContentType.Video, ContentType.Shorts)
        else -> listOf(ContentType.Video, ContentType.Shorts, ContentType.Stream)
    }

    fun sectionUrl(type: ContentType): String {
        require(type in sections)
        if (collection) return normalizedUrl
        val section = when (type) {
            ContentType.Video -> "videos"
            ContentType.Shorts -> "shorts"
            ContentType.Stream -> "streams"
            ContentType.Queue -> error("Not a channel section")
        }
        return "$normalizedUrl/$section"
    }

    fun recentItems(limit: Int): String = if (collection) "-1:-${limit.coerceAtLeast(1)}:-1" else "1-${limit.coerceAtLeast(1)}"
}

object ChannelUrlParser {
    private val handle = Regex("^[A-Za-z0-9._-]{3,100}$")
    private val channelId = Regex("^UC[A-Za-z0-9_-]{20,}$")
    private val legacyName = Regex("^[A-Za-z0-9._-]{1,100}$")
    private val channelTabs = setOf("featured", "videos", "shorts", "streams", "live")

    fun parse(raw: String): ParsedChannelUrl? {
        val trimmed = raw.trim()
        if (trimmed.startsWith('@')) return fromHandle(trimmed.drop(1))

        val candidate = if (trimmed.startsWith("http://", true) || trimmed.startsWith("https://", true)) {
            trimmed
        } else {
            "https://$trimmed"
        }
        val uri = runCatching { URI(candidate) }.getOrNull() ?: return null
        if (uri.scheme?.lowercase() !in setOf("http", "https") || uri.rawUserInfo != null || uri.port != -1) return null
        if (Regex("%(2f|5c|00)", RegexOption.IGNORE_CASE).containsMatchIn(uri.rawPath.orEmpty())) return null
        val host = uri.host?.lowercase()?.removePrefix("www.") ?: return null
        if (host == "rutube.ru") return fromRutube(uri.path.trimEnd('/'))
        if (host != "youtube.com" && !host.endsWith(".youtube.com")) return null
        val parts = uri.path.split('/').filter(String::isNotBlank)
        val path = parts.dropLastWhile { it.lowercase() in channelTabs }

        return when {
            path.size == 1 && path[0].startsWith('@') -> fromHandle(path[0].drop(1))
            path.size == 2 && path[0].equals("channel", ignoreCase = true) -> fromChannelId(path[1])
            path.size == 2 && path[0].equals("user", ignoreCase = true) -> fromLegacy("user", path[1])
            path.size == 2 && path[0].equals("c", ignoreCase = true) -> fromLegacy("c", path[1])
            else -> null
        }
    }

    private fun fromRutube(path: String): ParsedChannelUrl? {
        val show = Regex("^/metainfo/tv/([0-9]+)$").matchEntire(path)
        val channel = Regex("^/channel/([0-9]+)(?:/(?:videos|shorts))?$").matchEntire(path)
        val slug = Regex("^/u/([A-Za-z0-9_]+)(?:/(?:videos|shorts))?$").matchEntire(path)
        val match = show ?: channel ?: slug ?: return null
        val value = if (slug != null) match.groupValues[1] else match.groupValues[1].trimStart('0').ifEmpty { "0" }
        val kind = when { show != null -> "show"; slug != null -> "slug"; else -> "channel" }
        val root = when (kind) { "show" -> "metainfo/tv"; "slug" -> "u"; else -> "channel" }
        return ParsedChannelUrl("rutube:$kind:$value", "https://rutube.ru/$root/$value", "Rutube $value", value,
            MediaSource.Rutube, show != null)
    }

    private fun fromHandle(value: String): ParsedChannelUrl? = value.takeIf(handle::matches)?.let {
        ParsedChannelUrl(
            id = "handle:${it.lowercase()}",
            normalizedUrl = "https://www.youtube.com/@$it",
            displayName = it,
            handle = "@$it",
        )
    }

    private fun fromChannelId(value: String): ParsedChannelUrl? = value.takeIf(channelId::matches)?.let {
        ParsedChannelUrl(
            id = "channel:${it.lowercase()}",
            normalizedUrl = "https://www.youtube.com/channel/$it",
            displayName = it,
            handle = it,
        )
    }

    private fun fromLegacy(kind: String, value: String): ParsedChannelUrl? = value.takeIf(legacyName::matches)?.let {
        ParsedChannelUrl(
            id = "$kind:${it.lowercase()}",
            normalizedUrl = "https://www.youtube.com/$kind/$it",
            displayName = it,
            handle = it,
        )
    }
}
