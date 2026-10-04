package com.liberivixer.youtubeharvester.data

import com.liberivixer.youtubeharvester.media.ChannelUrlParser
import com.liberivixer.youtubeharvester.media.MediaUrlParser
import com.liberivixer.youtubeharvester.model.AppSettings
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.DownloadStatus
import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.model.PaidContentStatus
import org.json.JSONArray
import org.json.JSONObject
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction

internal data class TransferTable(val name: String, val columns: List<String>, val primaryKey: List<String>)

internal data class TransferSnapshot(val settings: AppSettings, val tables: Map<String, List<JSONObject>>) {
    fun encode(): ByteArray = JSONObject().put("format", "YouTubeHarvesterTransfer").put("version", 1)
        .put("settings", TransferSettings.encode(settings))
        .put("tables", JSONObject(tables.mapValues { JSONArray(it.value) })).toString().toByteArray(Charsets.UTF_8)

    companion object {
        private fun table(name: String, columns: String, primaryKey: String) = TransferTable(name,
            columns.split(' '), primaryKey.split(' '))

        val schema = listOf(
            table("channels", "id url name handle thumbnail_url videos_enabled shorts_enabled streams_enabled paid_content status last_checked_epoch_ms sort_order", "id"),
            table("queue_items", "source media_id url title channel content_type origin_channel_id thumbnail_url resolution selected status audio_json subtitles_json sort_order", "source media_id"),
            table("archive_items", "source media_id title channel thumbnail_url content_type resolution variant_key downloaded_at downloaded_at_epoch_ms file_exists file_uri audio_json subtitles_json", "source media_id resolution variant_key"),
            table("archive_relinks", "source media_id resolution variant_key file_name file_size sha256", "source media_id resolution variant_key"),
            table("marked_media", "source media_id marked_at_epoch_ms", "source media_id"),
            table("check_schedules", "id hour minute enabled last_run_epoch_ms created_at_epoch_ms", "id"),
            table("download_jobs", "job_id source media_id url title channel content_type origin_channel_id thumbnail_url resolution status progress eta_seconds message created_at_epoch_ms updated_at_epoch_ms file_uri error_message from_queue audio_json subtitles_json retry_count", "job_id"),
        )
        private val integers = setOf("videos_enabled", "shorts_enabled", "streams_enabled", "last_checked_epoch_ms",
            "sort_order", "selected", "downloaded_at_epoch_ms", "file_exists", "marked_at_epoch_ms", "hour", "minute",
            "enabled", "last_run_epoch_ms", "created_at_epoch_ms", "updated_at_epoch_ms", "progress", "eta_seconds",
            "from_queue", "retry_count", "file_size")
        private val flags = setOf("videos_enabled", "shorts_enabled", "streams_enabled", "selected", "file_exists", "enabled", "from_queue")
        private val nullable = setOf("thumbnail_url", "last_checked_epoch_ms", "origin_channel_id", "file_uri",
            "last_run_epoch_ms", "eta_seconds", "error_message")
        const val MAX_ROWS = 50_000

        fun decode(bytes: ByteArray): TransferSnapshot {
            require(bytes.size <= TransferEncryption.MAX_BYTES)
            val text = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString()
            checkJsonDepth(text)
            val j = JSONObject(text)
            require(j.keys().asSequence().toSet() == setOf("format", "version", "settings", "tables"))
            require(j.get("format") == "YouTubeHarvesterTransfer" && j.get("version") == 1)
            val tables = j.getJSONObject("tables")
            require(tables.keys().asSequence().toSet() == schema.map { it.name }.toSet())
            var total = 0
            val decoded = schema.associate { table ->
                val array = tables.getJSONArray(table.name)
                total += array.length()
                require(total <= MAX_ROWS)
                val keys = mutableSetOf<List<Any>>()
                table.name to List(array.length()) { i ->
                    val row = array.getJSONObject(i)
                    validateRow(table, row)
                    require(keys.add(table.primaryKey.map(row::get))) { "Duplicate record" }
                    row
                }
            }
            val archives = decoded.getValue("archive_items").map { row ->
                listOf("source", "media_id", "resolution", "variant_key").map(row::getString)
            }.toSet()
            require(decoded.getValue("archive_relinks").all { row ->
                listOf("source", "media_id", "resolution", "variant_key").map(row::getString) in archives
            })
            return TransferSnapshot(TransferSettings.decode(j.getJSONObject("settings")), decoded)
        }

        private fun checkJsonDepth(text: String) {
            // Bound recursion before Android's JSON parser; syntax is still checked by the parser.
            var depth = 0
            var quoted = false
            var escaped = false
            for (character in text) {
                if (quoted) {
                    if (escaped) escaped = false
                    else if (character == '\\') escaped = true
                    else if (character == '"') quoted = false
                } else when (character) {
                    '"' -> quoted = true
                    '{', '[' -> { depth++; require(depth <= 16) }
                    '}', ']' -> depth--
                }
            }
        }

        private fun validateRow(table: TransferTable, row: JSONObject) {
            require(row.keys().asSequence().toSet() == table.columns.toSet())
            for (column in table.columns) {
                val value = row.get(column)
                if (value == JSONObject.NULL) {
                    require(column in nullable)
                } else if (column in integers) {
                    require(value is Int || value is Long)
                    val n = (value as Number).toLong()
                    require(n >= 0)
                    if (column in flags) require(n <= 1)
                    if (column in setOf("sort_order", "retry_count")) require(n <= Int.MAX_VALUE)
                    if (column == "hour") require(n <= 23)
                    if (column == "minute") require(n <= 59)
                    if (column == "progress") require(n <= 100)
                } else {
                    require(value is String && value.length <= 65_536 && '\u0000' !in value)
                }
            }
            table.primaryKey.forEach { require(row.getString(it).isNotBlank()) }
            if (row.has("source")) MediaSource.valueOf(row.getString("source"))
            if (row.has("content_type")) ContentType.valueOf(row.getString("content_type"))
            if (table.name == "channels") {
                require(ChannelUrlParser.parse(row.getString("url")) != null)
                PaidContentStatus.valueOf(row.getString("paid_content"))
            }
            if (table.name in setOf("queue_items", "download_jobs")) {
                val parsed = requireNotNull(MediaUrlParser.parse(row.getString("url")))
                require(parsed.mediaId == row.getString("media_id") && parsed.source.name == row.getString("source"))
                DownloadStatus.valueOf(row.getString("status"))
            }
            if (table.name == "download_jobs") {
                require(Regex("[A-Za-z0-9._:-]{1,200}").matches(row.getString("job_id")))
                require(row.getString("job_id") !in setOf(".", ".."))
            }
            if (table.name == "archive_relinks") {
                require(validTransferFileName(row.getString("file_name")))
                require(Regex("[0-9a-f]{64}").matches(row.getString("sha256")))
            }
            for (column in listOf("audio_json", "subtitles_json")) {
                if (!row.has(column)) continue
                val raw = row.getString(column)
                checkJsonDepth(raw)
                val values = JSONArray(raw)
                require(values.length() <= 100)
                for (i in 0 until values.length()) {
                    if (column == "audio_json" && table.name != "archive_items") {
                        val audio = values.getJSONObject(i)
                        val fields = setOf("format_id", "format_kind", "language", "name")
                        require(audio.keys().asSequence().toSet() == fields)
                        fields.forEach { require(audio.get(it) is String && audio.getString(it).length <= 1024) }
                        require(audio.getString("format_id").isNotBlank())
                    } else require(values.get(i) is String && values.getString(i).length <= 1024)
                }
            }
        }

        fun importedRow(table: TransferTable, original: JSONObject): JSONObject {
            val row = JSONObject(original.toString())
            when (table.name) {
                // Old MediaStore IDs may name a different file on the destination device.
                // Only the explicitly granted folder and a matching digest can relink it.
                "archive_items" -> row.put("file_exists", 0).put("file_uri", JSONObject.NULL)
                "check_schedules" -> row.put("enabled", 0)
                "queue_items" -> if (DownloadStatus.valueOf(row.getString("status")).isActive) row.put("status", "PAUSED")
                "download_jobs" -> {
                    val status = DownloadStatus.valueOf(row.getString("status"))
                    // Staging files and publication ownership are not portable across installs.
                    row.put("file_uri", JSONObject.NULL).put("eta_seconds", JSONObject.NULL).put("retry_count", 0)
                    if (status.retainsFiles) row.put("status", "PAUSED").put("progress", 0)
                        .put("message", "PAUSED").put("error_message", JSONObject.NULL)
                }
            }
            return row
        }

    }
}
