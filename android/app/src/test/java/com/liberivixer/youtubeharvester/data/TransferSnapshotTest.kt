package com.liberivixer.youtubeharvester.data

import com.liberivixer.youtubeharvester.model.AppSettings
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class TransferSnapshotTest {
    private fun empty() = TransferSnapshot(AppSettings(telegramEnabled = true,
        telegramBotToken = "QA-token", telegramChannelId = "QA-channel", telegramProxyUrl = "http://qa:pass@example.org:8080"),
        TransferSnapshot.schema.associate { it.name to emptyList<JSONObject>() })

    @Test fun allSettingsIncludingCredentialsRoundTrip() {
        val snapshot = empty()
        val decoded = TransferSnapshot.decode(snapshot.encode())
        assertEquals(snapshot.settings, decoded.settings)
        assertEquals(snapshot.tables, decoded.tables)
        val portable = TransferSettings.forImport(snapshot.settings.copy(downloadDirectoryUri = "content://old-tree", tempDirectory = "old-cache"))
        assertNull(portable.downloadDirectoryUri)
        assertEquals("internal-cache", portable.tempDirectory)
        assertEquals(snapshot.settings.telegramBotToken, portable.telegramBotToken)
    }

    @Test fun foreignVersionMissingFieldsAndInvalidSettingsFailClosed() {
        val valid = JSONObject(empty().encode().toString(Charsets.UTF_8))
        fails { decode(JSONObject(valid.toString()).put("version", 2)) }
        fails { decode(JSONObject(valid.toString()).put("version", 1.5)) }
        fails { decode(JSONObject(valid.toString()).put("unexpected", "value")) }
        val missing = JSONObject(valid.toString())
        missing.getJSONObject("tables").remove("marked_media")
        fails { decode(missing) }
        val badSettings = JSONObject(valid.toString())
        badSettings.getJSONObject("settings").put("videoLimit", 100)
        fails { decode(badSettings) }
        val badFlag = JSONObject(valid.toString())
        badFlag.getJSONObject("settings").put("telegramEnabled", "true")
        fails { decode(badFlag) }
        val unreadable = AppSettings(telegramCredentialError = true)
        fails { TransferSettings.encode(unreadable) }
    }

    @Test fun duplicateAndMalformedRecordsDoNotGetSilentlySkipped() {
        val valid = JSONObject(empty().encode().toString(Charsets.UTF_8))
        val row = JSONObject().put("source", "YouTube").put("media_id", "jNQXAC9IVRw").put("marked_at_epoch_ms", 123L)
        valid.getJSONObject("tables").put("marked_media", JSONArray().put(row).put(row))
        fails { decode(valid) }
        valid.getJSONObject("tables").put("marked_media", JSONArray().put(JSONObject(row.toString()).put("marked_at_epoch_ms", 1.5)))
        fails { decode(valid) }
        valid.getJSONObject("tables").put("marked_media", JSONArray().put(JSONObject(row.toString()).put("source", "ForeignSource")))
        fails { decode(valid) }
    }

    @Test fun importedRowsCannotRestartDownloadsOrReusePublicationOwnership() {
        val jobTable = TransferSnapshot.schema.single { it.name == "download_jobs" }
        val job = JSONObject().put("status", "PUBLISHING").put("file_uri", "content://old-document")
            .put("progress", 91).put("eta_seconds", 12).put("retry_count", 3).put("message", "old").put("error_message", "old")
        val imported = TransferSnapshot.importedRow(jobTable, job)
        assertEquals("PAUSED", imported.getString("status"))
        assertEquals(0, imported.getInt("progress"))
        assertTrue(imported.isNull("file_uri"))
        assertTrue(imported.isNull("eta_seconds"))
        assertEquals("PUBLISHING", job.getString("status"))
        val schedule = TransferSnapshot.importedRow(TransferSnapshot.schema.single { it.name == "check_schedules" },
            JSONObject().put("enabled", 1))
        assertEquals(0, schedule.getInt("enabled"))
    }

    @Test fun archiveMetadataDoesNotGrantPrivateFileAccess() {
        val table = TransferSnapshot.schema.single { it.name == "archive_items" }
        for (uri in listOf("file:///data/data/app/private", "content://com.liberivixer.youtubeharvester.downloads/file",
            "https://example.org/video", "file:///storage/%2e%2e/data/private")) {
            val row = TransferSnapshot.importedRow(table, JSONObject().put("file_uri", uri).put("file_exists", 1))
            assertTrue(uri, row.isNull("file_uri"))
            assertEquals(0, row.getInt("file_exists"))
        }
        val media = "content://media/external/video/media/123"
        assertTrue(TransferSnapshot.importedRow(table, JSONObject().put("file_uri", media)).isNull("file_uri"))
    }

    @Test fun hostileNestingAndInvalidUtf8AreRejected() {
        fails { TransferSnapshot.decode(("[".repeat(1000) + "]".repeat(1000)).toByteArray()) }
        fails { TransferSnapshot.decode(byteArrayOf(0xc0.toByte(), 0xaf.toByte())) }
        val token = "escaped\\\"{[value]}"
        val j = JSONObject(empty().encode().toString(Charsets.UTF_8))
        j.getJSONObject("settings").put("telegramBotToken", token)
        assertEquals(token, decode(j).settings.telegramBotToken)
    }

    private fun decode(j: JSONObject) = TransferSnapshot.decode(j.toString().toByteArray(Charsets.UTF_8))
    private fun fails(block: () -> Unit) {
        try { block(); fail("Expected rejection") } catch (_: Exception) { }
    }
}
