package com.liberivixer.youtubeharvester.media

import com.liberivixer.youtubeharvester.model.MediaPreview

/** Android-only boundary for lightweight media inspection. */
interface MediaEngine {
    suspend fun inspect(url: ParsedMediaUrl): EngineResult<MediaPreview>
}

sealed interface EngineResult<out T> {
    data class Success<T>(val value: T) : EngineResult<T>
    data class Failure(val message: String, val retryable: Boolean = false) : EngineResult<Nothing>
}
