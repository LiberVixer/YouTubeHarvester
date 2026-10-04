package com.liberivixer.youtubeharvester.model

import androidx.annotation.StringRes
import com.liberivixer.youtubeharvester.R

@StringRes
fun DownloadStatus.stringResource(): Int = when (this) {
    DownloadStatus.QUEUED -> R.string.status_queued
    DownloadStatus.INITIALIZING -> R.string.status_initializing
    DownloadStatus.DOWNLOADING -> R.string.status_downloading
    DownloadStatus.PROCESSING -> R.string.status_processing
    DownloadStatus.WAITING_NETWORK -> R.string.status_waiting_network
    DownloadStatus.PAUSED -> R.string.status_paused
    DownloadStatus.PUBLISHING -> R.string.status_publishing
    DownloadStatus.COMPLETED -> R.string.status_completed
    DownloadStatus.FAILED -> R.string.status_failed
    DownloadStatus.CANCELLED -> R.string.status_cancelled
}

fun storedDownloadStatus(value: String): DownloadStatus? {
    val normalized = value.trim()
    DownloadStatus.entries.firstOrNull { it.name.equals(normalized, ignoreCase = true) }?.let { return it }
    return when {
        normalized in setOf("Ожидает", "В очереди", "В очереди загрузки") -> DownloadStatus.QUEUED
        normalized == "Подготовка движка" -> DownloadStatus.INITIALIZING
        normalized.startsWith("Скачивание") && normalized != "Скачивание отменено" -> DownloadStatus.DOWNLOADING
        normalized == "Сохранение файла" -> DownloadStatus.PUBLISHING
        normalized.startsWith("Ошибка") -> DownloadStatus.FAILED
        normalized in setOf("Отменено", "Скачивание отменено") -> DownloadStatus.CANCELLED
        else -> null
    }
}
