package com.liberivixer.youtubeharvester.media

import android.content.Context
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.model.MediaPreview
import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.ui.LocaleController
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONException
import org.json.JSONObject

/** Fast oEmbed preview for services that expose public metadata without starting yt-dlp. */
class PublicMetadataMediaEngine(context: Context) : MediaEngine {
    private val appContext = context.applicationContext
    override suspend fun inspect(url: ParsedMediaUrl): EngineResult<MediaPreview> =
        withContext(Dispatchers.IO) {
            if (url.source == MediaSource.Vk) return@withContext EngineResult.Failure(text(R.string.preview_service_error))

            try {
                val endpoint = when (url.source) {
                    MediaSource.YouTube -> oEmbedEndpoint("https://www.youtube.com/oembed", url)
                    MediaSource.Rutube -> oEmbedEndpoint("https://rutube.ru/api/oembed/", url)
                    MediaSource.Vk -> error("VK is handled above")
                }
                val payload = readJson(endpoint)
                EngineResult.Success(OEmbedMetadataDecoder.decode(payload, url))
            } catch (error: CancellationException) {
                throw error
            } catch (error: MetadataHttpException) {
                EngineResult.Failure(
                    message = when (error.statusCode) {
                        401, 403 -> text(R.string.preview_access_restricted)
                        404 -> text(R.string.preview_video_unavailable)
                        429 -> text(R.string.preview_rate_limited)
                        else -> text(R.string.preview_service_error)
                    },
                    retryable = error.statusCode == 408 || error.statusCode == 429 || error.statusCode >= 500,
                )
            } catch (error: JSONException) {
                EngineResult.Failure(text(R.string.preview_incomplete_data))
            } catch (error: IOException) {
                EngineResult.Failure(text(R.string.preview_network_error), retryable = true)
            }
        }

    private fun oEmbedEndpoint(baseUrl: String, url: ParsedMediaUrl): URI {
        val encoded = URLEncoder.encode(url.normalizedUrl, StandardCharsets.UTF_8.name())
        return URI.create("$baseUrl?url=$encoded&format=json")
    }

    private fun readJson(endpoint: URI): String {
        val connection = (endpoint.toURL().openConnection() as HttpURLConnection).apply {
            connectTimeout = CONNECT_TIMEOUT_MS
            readTimeout = READ_TIMEOUT_MS
            instanceFollowRedirects = true
            requestMethod = "GET"
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Accept-Language", LocaleController.wrap(appContext).resources.configuration.locales[0].toLanguageTag())
            setRequestProperty("User-Agent", USER_AGENT)
        }

        return try {
            val status = connection.responseCode
            if (status !in 200..299) throw MetadataHttpException(status)
            connection.inputStream.bufferedReader(StandardCharsets.UTF_8).use { reader ->
                val result = StringBuilder()
                val buffer = CharArray(4_096)
                while (true) {
                    val count = reader.read(buffer)
                    if (count < 0) break
                    result.append(buffer, 0, count)
                    if (result.length > MAX_RESPONSE_CHARS) {
                        throw IOException("Metadata response is too large")
                    }
                }
                result.toString()
            }
        } finally {
            connection.disconnect()
        }
    }

    private fun text(resourceId: Int, vararg arguments: Any): String =
        LocaleController.wrap(appContext).getString(resourceId, *arguments)

    private companion object {
        const val CONNECT_TIMEOUT_MS = 10_000
        const val READ_TIMEOUT_MS = 15_000
        const val MAX_RESPONSE_CHARS = 256 * 1_024
        const val USER_AGENT = "YouTubeHarvester-Android/1.2"
    }
}

internal object OEmbedMetadataDecoder {
    fun decode(payload: String, url: ParsedMediaUrl): MediaPreview {
        val json = JSONObject(payload)
        return MediaPreview(
            normalizedUrl = url.normalizedUrl,
            mediaId = url.mediaId,
            source = url.source,
            title = json.optionalString("title") ?: throw JSONException("Empty title"),
            channel = json.optionalString("author_name") ?: url.source.label,
            thumbnailUrl = json.optionalString("thumbnail_url"),
        )
    }

    private fun JSONObject.optionalString(key: String): String? =
        if (isNull(key)) null else optString(key).trim().takeIf { it.isNotBlank() && it != "null" }
}

private class MetadataHttpException(val statusCode: Int) : IOException()
