package com.liberivixer.youtubeharvester.data

import com.liberivixer.youtubeharvester.data.db.QueueEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class QueueOrderingTest {
    @Test
    fun movesOnlyTheRequestedSourceAndNormalizesOrder() {
        val items = listOf(
            item("YouTube", "same", 4),
            item("Vk", "same", 9),
            item("Rutube", "last", 12),
        )

        val moved = reorderQueueEntities(items, "Vk", "same", -1)!!

        assertEquals(listOf("Vk:same", "YouTube:same", "Rutube:last"), moved.map { "${it.source}:${it.mediaId}" })
        assertEquals(listOf(0, 1, 2), moved.map { it.sortOrder })
    }

    @Test
    fun rejectsMissingItemsAndOutOfBoundsMoves() {
        val items = listOf(item("YouTube", "first", 0), item("YouTube", "second", 1))

        assertNull(reorderQueueEntities(items, "YouTube", "missing", 1))
        assertNull(reorderQueueEntities(items, "YouTube", "first", -1))
        assertNull(reorderQueueEntities(items, "YouTube", "second", 1))
    }

    private fun item(source: String, id: String, order: Int) = QueueEntity(
        source = source,
        mediaId = id,
        url = "https://example.test/$id",
        title = id,
        channel = source,
        contentType = "Video",
        originChannelId = null,
        thumbnailUrl = null,
        resolution = "1080p",
        selected = true,
        status = "QUEUED",
        audioJson = "[]",
        subtitlesJson = "[]",
        sortOrder = order,
    )
}
