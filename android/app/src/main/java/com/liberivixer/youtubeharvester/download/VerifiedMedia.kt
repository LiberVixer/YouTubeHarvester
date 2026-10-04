package com.liberivixer.youtubeharvester.download

import org.json.JSONObject
import java.io.File

internal data class VerifiedMedia(val file: File, val resolution: String, val audio: List<String>,
    val subtitles: List<String>, val selections: List<String>) {
    fun missingSubtitleSelections(requested: List<String>): List<String> = requested.distinct().filterNot { it in selections }

    fun publicationName(requestedResolution: String): String {
        val token = requestedResolution.replace(Regex("[^A-Za-z0-9_-]"), "_")
        val marker = Regex(" \\[${Regex.escape(token)}](?=(?: \\[[^\\[\\]]+])?(?:\\.tracks)?\\.[^.]+$)")
        val match = marker.findAll(file.name).lastOrNull()
        // Only replace the trailing quality marker, not similar text in the video title.
        if (match != null) return file.name.replaceRange(match.range, " [$resolution]")
        val extension = file.extension.takeIf(String::isNotBlank)?.let { ".$it" }.orEmpty()
        return "${file.nameWithoutExtension} [$resolution]$extension"
    }

    companion object {
        fun read(directory: File): VerifiedMedia {
            val report = File(directory, "final-media.json")
            check(report.length() in 1..1_048_576) { "Verified output metadata is missing" }
            val data = JSONObject(report.readText())
            val file = File(data.getString("path")).canonicalFile
            check(file.parentFile == directory.canonicalFile && file.isFile && file.length() > 0) { "Invalid verified output path" }
            val resolution = data.getString("resolution")
            check(resolution.matches(Regex("[1-9][0-9]{0,5}p"))) { "Invalid verified video resolution" }
            fun strings(key: String): List<String> = data.getJSONArray(key).let { a -> List(a.length()) { a.getString(it) } }
            return VerifiedMedia(file, resolution, strings("audio"), strings("subtitles"), strings("selections"))
        }
    }
}
