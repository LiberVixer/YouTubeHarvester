package com.liberivixer.youtubeharvester.logging

import java.nio.file.Files
import java.time.Instant
import java.time.LocalDate
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AppLogStoreTest {
    @Test
    fun appendUsesUtf8SingleLinesAndRedactsTelegramTokens() {
        runBlocking {
            val directory = Files.createTempDirectory("yth-log").toFile()
            val token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
            val store = AppLogStore(directory) { Instant.parse("2026-09-02T12:34:56Z") }

            store.append(AppLogLevel.ERROR, "Telegram\nclient", "Не удалось: bot$token\nretry")
            val text = store.readLatest()

            assertTrue(text.contains("2026-09-02T12:34:56Z\tERROR\tTelegram client"))
            assertTrue(text.contains("Не удалось: [REDACTED] retry"))
            assertFalse(text.contains(token))
            assertFalse(text.substringAfter("Telegram client").contains('\n'))
            directory.deleteRecursively()
        }
    }

    @Test
    fun pruneKeepsOnlyConfiguredCalendarDays() {
        runBlocking {
            val directory = Files.createTempDirectory("yth-log-prune").toFile()
            listOf("2026-08-29.log", "2026-08-31.log", "2026-09-01.log", "2026-09-02.log").forEach {
                directory.resolve(it).writeText(it)
            }
            val store = AppLogStore(directory)

            store.prune(retentionDays = 3, today = LocalDate.of(2026, 9, 2))

            assertFalse(directory.resolve("2026-08-29.log").exists())
            assertTrue(directory.resolve("2026-08-31.log").exists())
            assertTrue(directory.resolve("2026-09-01.log").exists())
            assertTrue(directory.resolve("2026-09-02.log").exists())
            directory.deleteRecursively()
        }
    }

    @Test
    fun readLatestReturnsBoundedNewestTextAcrossFiles() {
        runBlocking {
            val directory = Files.createTempDirectory("yth-log-tail").toFile()
            directory.resolve("2026-09-01.log").writeText("older\n")
            directory.resolve("2026-09-02.log").writeText("newest\n")
            val store = AppLogStore(directory)

            val text = store.readLatest(maxChars = 8)

            assertFalse(text.contains("older"))
            assertTrue(text.contains("newest"))
            directory.deleteRecursively()
        }
    }
}
