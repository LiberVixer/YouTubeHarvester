package com.liberivixer.youtubeharvester.media

import android.content.Context
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.model.AudioFormatVariant
import com.liberivixer.youtubeharvester.model.AudioTrackOption
import com.liberivixer.youtubeharvester.model.DownloadMediaOptions
import com.liberivixer.youtubeharvester.model.MediaOptionSection
import com.liberivixer.youtubeharvester.model.MediaPreview
import com.liberivixer.youtubeharvester.model.SelectedAudioTrack
import com.liberivixer.youtubeharvester.model.SubtitleTrackOption
import com.liberivixer.youtubeharvester.ui.LocaleController
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runInterruptible
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

class YtDlpMetadataInspector(private val context: Context) {
    suspend fun inspect(url: ParsedMediaUrl): EngineResult<DownloadMediaOptions> {
        val processId = "metadata-${UUID.randomUUID()}"
        return try {
            val response = runInterruptible(Dispatchers.IO) {
                AndroidYtDlpRuntime.ensure(context, requireFfmpeg = false)
                val request = YoutubeDLRequest(url.normalizedUrl)
                    .addOption("--dump-single-json")
                    .addOption("--skip-download")
                    .addOption("--no-playlist")
                    .addOption("--socket-timeout", 15)
                    .addOption("--extractor-retries", 2)
                YoutubeDL.execute(request, processId)
            }
            check(response.exitCode == 0) {
                response.err.ifBlank { "yt-dlp metadata inspection failed with code ${response.exitCode}" }
            }
            EngineResult.Success(
                YtDlpMetadataDecoder.decode(
                    response.out,
                    url,
                    LocaleController.wrap(context).getString(R.string.fallback_video_title, "", url.mediaId).trim(),
                ),
            )
        } catch (error: CancellationException) {
            runCatching { YoutubeDL.destroyProcessById(processId) }
            throw error
        } catch (error: Exception) {
            val message = error.message.orEmpty().replace(Regex("\\s+"), " ").trim()
            EngineResult.Failure(
                message = localizedMetadataError(message),
                retryable = true,
            )
        }
    }

    private fun localizedMetadataError(raw: String): String {
        val resources = LocaleController.wrap(context)
        val resource = when {
            raw.contains("members-only", ignoreCase = true) || raw.contains("Join this channel", ignoreCase = true) ->
                R.string.service_error_members_only
            raw.contains("Private video", ignoreCase = true) -> R.string.service_error_private_video
            raw.contains("Video unavailable", ignoreCase = true) || raw.contains("not available", ignoreCase = true) ->
                R.string.preview_video_unavailable
            raw.contains("429") || raw.contains("Too Many Requests", ignoreCase = true) -> R.string.preview_rate_limited
            else -> R.string.metadata_tracks_error
        }
        return resources.getString(resource)
    }
}

internal object YtDlpMetadataDecoder {
    private val validFormatId = Regex("[A-Za-z0-9._-]+")
    private val originalMarker = Regex("\\boriginal\\b|\\(default\\)", RegexOption.IGNORE_CASE)
    private val preferredLanguageRoots = setOf("ru", "en", "uk", "be", "fr", "es", "hi", "zh", "ja", "ar")

    fun decode(payload: String, url: ParsedMediaUrl, fallbackTitle: String = "Video ${url.mediaId}"): DownloadMediaOptions {
        val data = JSONObject(payload.trim())
        val preview = MediaPreview(
            normalizedUrl = data.optionalString("webpage_url") ?: url.normalizedUrl,
            mediaId = data.optionalString("id") ?: url.mediaId,
            source = url.source,
            title = data.optionalString("title") ?: fallbackTitle,
            channel = data.optionalString("channel") ?: data.optionalString("uploader") ?: url.source.label,
            thumbnailUrl = data.optionalString("thumbnail"),
        )
        return DownloadMediaOptions(
            preview = preview,
            audioTracks = parseAudioTracks(data.optJSONArray("formats") ?: JSONArray()),
            subtitleTracks = parseSubtitleTracks(data),
        )
    }

    fun resolveAudioTrack(option: AudioTrackOption, resolution: String): SelectedAudioTrack? {
        if (option.formatKind != "combined") {
            return option.formatId.takeIf { it.isNotBlank() }?.let {
                SelectedAudioTrack(it, option.formatKind, option.language, option.name)
            }
        }
        val targetHeight = resolution.filter(Char::isDigit).toIntOrNull()
        val eligible = option.variants.filter { targetHeight == null || (it.height in 1..targetHeight) }
        val selected = when {
            eligible.isNotEmpty() -> eligible.maxWithOrNull(compareBy<AudioFormatVariant>({ it.height }, { it.extension == "mp4" }, { it.bitrate }))
            option.variants.isNotEmpty() -> option.variants.minByOrNull { it.height.takeIf { height -> height > 0 } ?: Int.MAX_VALUE }
            else -> null
        } ?: return null
        return SelectedAudioTrack(selected.formatId, option.formatKind, option.language, option.name)
    }

    private fun parseAudioTracks(formats: JSONArray): List<AudioTrackOption> {
        data class Candidate(val score: List<Double>, val option: AudioTrackOption)
        val audioOnly = linkedMapOf<String, Candidate>()
        forEachObject(formats) { format ->
            if (format.optionalString("vcodec") != "none" || format.optionalString("acodec") in setOf(null, "none")) return@forEachObject
            val formatId = format.optionalString("format_id") ?: return@forEachObject
            if (!validFormatId.matches(formatId)) return@forEachObject
            val language = format.optionalString("language") ?: "und"
            val name = audioTrackName(format)
            val note = format.optionalString("format_note").orEmpty()
            val original = originalMarker.containsMatchIn(note) || format.optDouble("language_preference", 0.0) > 0
            val key = "${language.lowercase()}|${name.lowercase()}"
            val option = AudioTrackOption(
                key = "audio:$key",
                formatId = formatId,
                formatKind = "audio",
                language = language,
                name = name,
                isOriginal = original,
                section = sectionForAudio(original, language),
            )
            val score = listOf(
                if (note.contains("DRC", ignoreCase = true)) 0.0 else 1.0,
                if (format.optString("ext").equals("m4a", ignoreCase = true)) 1.0 else 0.0,
                format.optDouble("abr", format.optDouble("tbr", 0.0)),
                format.optDouble("asr", 0.0),
            )
            val current = audioOnly[key]
            if (current == null || compareScore(score, current.score) > 0) audioOnly[key] = Candidate(score, option)
        }

        val audioRoots = audioOnly.keys.map { it.substringBefore('|').substringBefore('-') }.toSet()
        val combined = linkedMapOf<String, AudioTrackOption>()
        forEachObject(formats) { format ->
            if (format.optionalString("vcodec") in setOf(null, "none") || format.optionalString("acodec") in setOf(null, "none")) return@forEachObject
            val formatId = format.optionalString("format_id") ?: return@forEachObject
            val language = format.optionalString("language") ?: return@forEachObject
            if (language.isBlank() || !validFormatId.matches(formatId)) return@forEachObject
            val name = audioTrackName(format)
            if (name.isBlank() && languageRoot(language) in audioRoots) return@forEachObject
            val key = "${language.lowercase()}|${name.lowercase()}"
            val note = format.optionalString("format_note").orEmpty()
            val existing = combined[key]
            val variant = AudioFormatVariant(
                formatId = formatId,
                height = format.optInt("height", 0),
                extension = format.optString("ext").lowercase(),
                bitrate = format.optDouble("tbr", 0.0),
            )
            combined[key] = (existing ?: AudioTrackOption(
                key = "combined:$key",
                formatId = "",
                formatKind = "combined",
                language = language,
                name = name,
                isOriginal = originalMarker.containsMatchIn(note) || format.optDouble("language_preference", 0.0) > 0,
                section = sectionForAudio(
                    originalMarker.containsMatchIn(note) || format.optDouble("language_preference", 0.0) > 0,
                    language,
                ),
            )).let { it.copy(variants = it.variants + variant) }
        }

        return (audioOnly.values.map { it.option } + combined.values).sortedWith(optionComparator())
    }

    private fun parseSubtitleTracks(data: JSONObject): List<SubtitleTrackOption> {
        val result = mutableListOf<SubtitleTrackOption>()
        listOf(false to "subtitles", true to "automatic_captions").forEach { (automatic, key) ->
            val tracks = data.optJSONObject(key) ?: return@forEach
            tracks.keys().forEach { language ->
                if (language.isBlank() || language == "live_chat") return@forEach
                val formats = tracks.optJSONArray(language)
                val name = formats?.optJSONObject(0)?.optionalString("name").orEmpty()
                val section = when {
                    !automatic -> MediaOptionSection.MANUAL_SUBTITLES
                    languageRoot(language) in preferredLanguageRoots -> MediaOptionSection.PREFERRED_AUTOMATIC
                    else -> MediaOptionSection.OTHER_AUTOMATIC
                }
                result += SubtitleTrackOption(
                    selection = "${if (automatic) "auto" else "manual"}:$language",
                    language = language,
                    name = name,
                    automatic = automatic,
                    section = section,
                )
            }
        }
        return result.distinctBy { it.selection }.sortedWith(optionComparator())
    }

    private fun audioTrackName(format: JSONObject): String {
        val audioTrack = format.optJSONObject("audio_track")
        val explicit = audioTrack?.optionalString("display_name") ?: audioTrack?.optionalString("name").orEmpty()
        if (explicit.isNotBlank()) return explicit
        return format.optionalString("format_note").orEmpty().split(',').map(String::trim).firstOrNull { part ->
            part.isNotBlank() && part.lowercase() !in setOf("low", "medium", "high", "default") &&
                !Regex("\\d{3,4}p(?:\\d+)?", RegexOption.IGNORE_CASE).matches(part)
        }.orEmpty()
    }

    private fun sectionForAudio(original: Boolean, language: String): MediaOptionSection = when {
        original -> MediaOptionSection.ORIGINAL
        languageRoot(language) in preferredLanguageRoots -> MediaOptionSection.PREFERRED
        else -> MediaOptionSection.OTHER
    }

    private fun languageRoot(language: String): String =
        language.trim().lowercase().replace('_', '-').substringBefore('-').ifBlank { "und" }

    private fun languagePriority(language: String): Int = when (languageRoot(language)) {
        "ru" -> 0
        "en" -> 1
        "uk" -> 2
        in preferredLanguageRoots -> 3
        else -> 4
    }

    private fun <T> optionComparator(): Comparator<T> = Comparator { left, right ->
        val leftData = optionSortData(left)
        val rightData = optionSortData(right)
        compareValuesBy(leftData, rightData, { it.first }, { it.second }, { it.third })
    }

    private fun optionSortData(option: Any?): Triple<Int, Int, String> = when (option) {
        is AudioTrackOption -> Triple(option.section.ordinal, languagePriority(option.language), "${option.name} ${option.language}".lowercase())
        is SubtitleTrackOption -> Triple(option.section.ordinal, languagePriority(option.language), "${option.name} ${option.language}".lowercase())
        else -> Triple(Int.MAX_VALUE, Int.MAX_VALUE, "")
    }

    private fun compareScore(left: List<Double>, right: List<Double>): Int {
        for (index in left.indices) {
            val comparison = left[index].compareTo(right[index])
            if (comparison != 0) return comparison
        }
        return 0
    }

    private inline fun forEachObject(array: JSONArray, block: (JSONObject) -> Unit) {
        repeat(array.length()) { index -> array.optJSONObject(index)?.let(block) }
    }

    private fun JSONObject.optionalString(key: String): String? =
        if (isNull(key)) null else optString(key).trim().takeIf { it.isNotBlank() && it != "null" }
}
