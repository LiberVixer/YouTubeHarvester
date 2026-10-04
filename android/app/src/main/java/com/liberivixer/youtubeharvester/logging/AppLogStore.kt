package com.liberivixer.youtubeharvester.logging

import android.content.Context
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

enum class AppLogLevel {
    INFO,
    IMPORTANT,
    ERROR,
}

class AppLogStore internal constructor(
    private val directory: File,
    private val now: () -> Instant = Instant::now,
) {
    constructor(context: Context) : this(File(context.noBackupFilesDir, "logs"))

    suspend fun append(level: AppLogLevel, component: String, message: String) {
        withContext(Dispatchers.IO) {
            runCatching {
                fileMutex.withLock {
                    check(directory.exists() || directory.mkdirs()) { "Could not create application log directory" }
                    val instant = now()
                    val file = File(directory, "${fileDate(instant)}.log")
                    val line = "${TIMESTAMP_FORMATTER.format(instant)}\t${level.name}\t${sanitize(component)}\t${sanitize(message)}\n"
                    file.appendText(line, Charsets.UTF_8)
                    if (file.length() > MAX_FILE_BYTES) compact(file)
                }
            }
        }
    }

    suspend fun readLatest(maxChars: Int = DEFAULT_READ_CHARS): String = withContext(Dispatchers.IO) {
        require(maxChars > 0) { "maxChars must be positive" }
        fileMutex.withLock {
            val chunks = mutableListOf<String>()
            var remaining = maxChars
            logFiles().asReversed().forEach { file ->
                if (remaining <= 0) return@forEach
                val text = file.readText(Charsets.UTF_8)
                val chunk = text.takeLast(remaining)
                chunks += chunk
                remaining -= chunk.length
            }
            chunks.asReversed().joinToString(separator = "").trimEnd()
        }
    }

    suspend fun clear() = withContext(Dispatchers.IO) {
        fileMutex.withLock {
            logFiles().forEach(File::delete)
        }
    }

    suspend fun prune(retentionDays: Int, today: LocalDate = LocalDate.now()) = withContext(Dispatchers.IO) {
        val normalizedDays = retentionDays.coerceIn(MIN_RETENTION_DAYS, MAX_RETENTION_DAYS)
        val oldestDate = today.minusDays((normalizedDays - 1).toLong())
        fileMutex.withLock {
            logFiles().forEach { file ->
                val date = runCatching { LocalDate.parse(file.nameWithoutExtension, FILE_DATE_FORMATTER) }.getOrNull()
                if (date != null && date.isBefore(oldestDate)) file.delete()
            }
        }
    }

    private fun logFiles(): List<File> = directory.listFiles()
        .orEmpty()
        .filter { it.isFile && LOG_FILE.matches(it.name) }
        .sortedBy(File::getName)

    private fun compact(file: File) {
        val tail = file.readText(Charsets.UTF_8).takeLast(COMPACT_TO_CHARS)
        val completeTail = tail.substringAfter('\n', tail)
        file.writeText(completeTail, Charsets.UTF_8)
    }

    private fun fileDate(instant: Instant): String =
        FILE_DATE_FORMATTER.format(instant.atZone(ZoneId.systemDefault()))

    private fun sanitize(value: String): String = value
        .replace(BOT_TOKEN, "[REDACTED]")
        .replace(CONTROL_WHITESPACE, " ")
        .replace(Regex(" +"), " ")
        .trim()
        .take(MAX_FIELD_CHARS)

    private companion object {
        const val MIN_RETENTION_DAYS = 1
        const val MAX_RETENTION_DAYS = 30
        const val DEFAULT_READ_CHARS = 60_000
        const val MAX_FILE_BYTES = 2L * 1024L * 1024L
        const val COMPACT_TO_CHARS = 400_000
        const val MAX_FIELD_CHARS = 2_000
        val fileMutex = Mutex()
        val FILE_DATE_FORMATTER: DateTimeFormatter = DateTimeFormatter.ISO_LOCAL_DATE
        val TIMESTAMP_FORMATTER: DateTimeFormatter = DateTimeFormatter.ISO_INSTANT
        val LOG_FILE = Regex("\\d{4}-\\d{2}-\\d{2}\\.log")
        val BOT_TOKEN = Regex("(?i)(?:bot)?\\d{5,12}:[A-Za-z0-9_-]{20,}")
        val CONTROL_WHITESPACE = Regex("[\\r\\n\\t]+")
    }
}
