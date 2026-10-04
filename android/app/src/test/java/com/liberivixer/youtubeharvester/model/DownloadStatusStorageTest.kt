package com.liberivixer.youtubeharvester.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DownloadStatusStorageTest {
    @Test
    fun stableStatusNamesAreParsedWithoutLocaleDependency() {
        DownloadStatus.entries.forEach { status ->
            assertEquals(status, storedDownloadStatus(status.name))
            assertEquals(status, storedDownloadStatus(status.name.lowercase()))
        }
    }

    @Test
    fun legacyRussianQueueStatusesRemainReadable() {
        assertEquals(DownloadStatus.QUEUED, storedDownloadStatus("Ожидает"))
        assertEquals(DownloadStatus.QUEUED, storedDownloadStatus("В очереди загрузки"))
        assertEquals(DownloadStatus.DOWNLOADING, storedDownloadStatus("Скачивание: 42%"))
        assertEquals(DownloadStatus.PUBLISHING, storedDownloadStatus("Сохранение файла"))
        assertEquals(DownloadStatus.FAILED, storedDownloadStatus("Ошибка: сеть недоступна"))
        assertEquals(DownloadStatus.CANCELLED, storedDownloadStatus("Скачивание отменено"))
    }

    @Test
    fun unknownEngineMessageIsPreservedByTheUi() {
        assertNull(storedDownloadStatus("Extractor returned an unknown state"))
    }
}
