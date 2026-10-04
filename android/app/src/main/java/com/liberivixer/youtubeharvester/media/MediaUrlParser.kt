package com.liberivixer.youtubeharvester.media

import com.liberivixer.youtubeharvester.model.MediaSource
import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

data class ParsedMediaUrl(
    val normalizedUrl: String,
    val source: MediaSource,
    val mediaId: String,
)

object MediaUrlParser {
    private val webUrl = Regex("https?://[^\\s]+", RegexOption.IGNORE_CASE)
    private val youtubeId = Regex("^[A-Za-z0-9_-]{11}$")
    private val vkVideoId = Regex("(?:video|clip)(-?\\d+_\\d+)", RegexOption.IGNORE_CASE)
    private val rutubeId = Regex(
        "^/(?:live/)?video(?:/private)?/([A-Za-z0-9-]{8,64})(?:/|$)|^/(?:play/)?embed/([A-Za-z0-9-]{8,64})(?:/|$)",
        RegexOption.IGNORE_CASE,
    )

    fun parse(raw: String): ParsedMediaUrl? {
        val candidate = raw.trim().let {
            if (it.startsWith("http://", true) || it.startsWith("https://", true)) it else "https://$it"
        }
        val uri = runCatching { URI(candidate) }.getOrNull() ?: return null
        if (uri.scheme?.lowercase() !in setOf("http", "https") || uri.rawUserInfo != null || uri.port != -1) return null
        val host = uri.host?.lowercase()?.removePrefix("www.") ?: return null

        return when {
            host == "youtu.be" -> youtube(uri.path.trim('/'))
            host.matchesDomain("youtube.com") -> {
                val queryId = queryParameters(uri)["v"]
                val pathId = uri.path.split('/').filter(String::isNotBlank).let { parts ->
                    if (parts.firstOrNull() in setOf("shorts", "live", "embed")) parts.getOrNull(1) else null
                }
                youtube(queryId ?: pathId.orEmpty())
            }
            host.matchesDomain("vk.com") || host.matchesDomain("vk.ru") || host.matchesDomain("vkvideo.ru") -> {
                val decodedUrl = decode(uri.toString())
                val query = queryParameters(uri)
                val id = vkVideoId.find(decodedUrl)?.groupValues?.getOrNull(1)
                    ?: query["oid"]?.takeIf { it.matches(Regex("^-?\\d+$")) }?.let { ownerId ->
                        query["id"]?.takeIf { it.matches(Regex("^\\d+$")) }?.let { videoId -> "${ownerId}_$videoId" }
                    }
                    ?: return null
                ParsedMediaUrl("https://vk.com/video$id", MediaSource.Vk, id)
            }
            host.matchesDomain("rutube.ru") -> {
                val match = rutubeId.find(uri.path) ?: return null
                val id = match.groupValues.drop(1).firstOrNull(String::isNotBlank) ?: return null
                val query = uri.rawQuery?.let { "?$it" }.orEmpty()
                ParsedMediaUrl("https://rutube.ru${uri.rawPath}$query", MediaSource.Rutube, id)
            }
            else -> null
        }
    }

    fun extract(raw: String): ParsedMediaUrl? {
        parse(raw)?.let { return it }
        return webUrl.findAll(raw).firstNotNullOfOrNull { match ->
            parse(match.value.trimEnd(*TRAILING_URL_PUNCTUATION))
        }
    }

    private fun youtube(id: String): ParsedMediaUrl? =
        id.takeIf(youtubeId::matches)?.let {
            ParsedMediaUrl("https://www.youtube.com/watch?v=$it", MediaSource.YouTube, it)
        }

    private fun String.matchesDomain(domain: String): Boolean =
        this == domain || endsWith(".$domain")

    private fun queryParameters(uri: URI): Map<String, String> = uri.rawQuery
        ?.split('&')
        ?.mapNotNull { part ->
            part.split('=', limit = 2).takeIf { it.size == 2 }?.let { decode(it[0]) to decode(it[1]) }
        }
        ?.toMap()
        .orEmpty()

    private fun decode(value: String): String =
        runCatching { URLDecoder.decode(value, StandardCharsets.UTF_8.name()) }.getOrDefault(value)

    private val TRAILING_URL_PUNCTUATION = charArrayOf('.', ',', ';', ':', '!', '?', ')', ']', '}', '>', '\'', '"', '»')
}
