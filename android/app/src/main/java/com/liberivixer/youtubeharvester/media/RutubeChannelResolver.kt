package com.liberivixer.youtubeharvester.media

import android.content.Context
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runInterruptible
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI
import java.util.UUID

data class ResolvedRutubeChannel(val channel: ParsedChannelUrl, val title: String, val thumbnailUrl: String?)

class RutubeChannelResolver(private val context: Context) {
    suspend fun resolve(channel: ParsedChannelUrl): ResolvedRutubeChannel {
        val processId = "rutube-channel-${UUID.randomUUID()}"
        return try {
            runInterruptible(Dispatchers.IO) {
                AndroidYtDlpRuntime.ensure(context, requireFfmpeg = false)
                val response = YoutubeDL.execute(
                    YoutubeDLRequest(channel.normalizedUrl)
                        .addOption("--flat-playlist").addOption("--playlist-items", "1")
                        .addOption("--dump-single-json").addOption("--skip-download")
                        .addOption("--abort-on-error").addOption("--socket-timeout", 15)
                        .addOption("--extractor-retries", 1),
                    processId,
                )
                check(response.exitCode == 0 && response.err.lineSequence().none {
                    it.trimStart().startsWith("ERROR:", ignoreCase = true)
                }) { response.err.ifBlank { "Incomplete Rutube channel metadata" } }
                val playlist = JSONObject(response.out)
                val canonical = RutubeChannelMetadataDecoder.canonical(channel, playlist)
                val id = canonical.normalizedUrl.substringAfterLast('/')
                val endpoint = if (canonical.collection) "https://rutube.ru/api/metainfo/tv/$id/?format=json"
                               else "https://rutube.ru/api/video/person/$id/?page=1&format=json"
                val artwork = try {
                    readMetadata(endpoint)
                } catch (error: CancellationException) {
                    throw error
                } catch (_: Exception) {
                    null
                }
                RutubeChannelMetadataDecoder.decode(canonical, playlist, artwork)
            }
        } catch (error: CancellationException) {
            runCatching { YoutubeDL.destroyProcessById(processId) }
            throw error
        }
    }

    private fun readMetadata(endpoint: String): JSONObject {
        val connection = (URI(endpoint).toURL().openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 15_000
            instanceFollowRedirects = false
            setRequestProperty("User-Agent", "Mozilla/5.0")
            setRequestProperty("Referer", "https://rutube.ru/")
        }
        return try {
            check(connection.responseCode == 200) { "Rutube artwork unavailable" }
            val data = connection.inputStream.use { it.readBytesLimited(2 * 1024 * 1024) }
            JSONObject(data.toString(Charsets.UTF_8))
        } finally {
            connection.disconnect()
        }
    }

    private fun java.io.InputStream.readBytesLimited(limit: Int): ByteArray {
        val output = java.io.ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (true) {
            val count = read(buffer)
            if (count < 0) return output.toByteArray()
            check(output.size() + count <= limit) { "Rutube metadata too large" }
            output.write(buffer, 0, count)
        }
    }
}

internal object RutubeChannelMetadataDecoder {
    fun canonical(requested: ParsedChannelUrl, playlist: JSONObject): ParsedChannelUrl {
        val id = text(playlist, "id")
        require(Regex("^[0-9]+$").matches(id)) { "Invalid Rutube channel ID" }
        val numeric = id.trimStart('0').ifEmpty { "0" }
        if (requested.collection) {
            require(requested.normalizedUrl.substringAfterLast('/') == numeric) { "Different Rutube show ID" }
            return requested
        }
        if (requested.id.startsWith("rutube:channel:")) {
            require(requested.normalizedUrl.substringAfterLast('/') == numeric) { "Different Rutube channel ID" }
        }
        return requireNotNull(ChannelUrlParser.parse("https://rutube.ru/channel/$numeric"))
    }

    fun decode(channel: ParsedChannelUrl, playlist: JSONObject, artwork: JSONObject?): ResolvedRutubeChannel {
        val id = channel.normalizedUrl.substringAfterLast('/')
        var title = if (channel.collection) text(playlist, "title")
                    else text(playlist.optJSONArray("entries")?.optJSONObject(0), "uploader")
        var thumbnail: String? = null
        if (channel.collection) {
            if (text(artwork, "id") == id) {
                title = text(artwork, "name").ifBlank { title }
                thumbnail = listOf("picture", "poster_url", "vertical_poster_url")
                    .firstNotNullOfOrNull { safeImage(text(artwork, it)) }
            }
        } else {
            val entries = artwork?.optJSONArray("results")
            for (index in 0 until (entries?.length() ?: 0)) {
                val author = entries?.optJSONObject(index)?.optJSONObject("author") ?: continue
                if (text(author, "id") != id) continue
                title = text(author, "name").ifBlank { title }
                thumbnail = safeImage(text(author, "avatar_url"))
                break
            }
        }
        return ResolvedRutubeChannel(channel, title.ifBlank { channel.displayName }, thumbnail)
    }

    private fun text(data: JSONObject?, key: String): String =
        data?.takeUnless { it.isNull(key) }?.optString(key)?.trim().orEmpty()

    private fun safeImage(value: String): String? {
        val uri = runCatching { URI(value) }.getOrNull() ?: return null
        val host = uri.host?.lowercase() ?: return null
        return value.takeIf {
            uri.scheme == "https" && uri.rawUserInfo == null && uri.port == -1 &&
                listOf("rutube.ru", "rtbcdn.ru", "rutubelist.ru").any { host == it || host.endsWith(".$it") }
        }
    }
}
