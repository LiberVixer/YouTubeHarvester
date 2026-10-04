package com.liberivixer.youtubeharvester.download

import org.junit.Assert.assertEquals
import org.junit.Test

class DownloadOutputPublisherTest {
    @Test
    fun uniqueNameKeepsUnusedFileName() {
        assertEquals("Video [1080p].mp4", uniqueDocumentName("Video [1080p].mp4", emptySet()))
    }

    @Test
    fun uniqueNameAddsFirstAvailableSuffix() {
        val existing = setOf(
            "Video.mp4",
            "Video (2).mp4",
            "Video (3).mp4",
        )

        assertEquals("Video (4).mp4", uniqueDocumentName("Video.mp4", existing))
    }

    @Test
    fun uniqueNameTreatsProviderNamesCaseInsensitively() {
        assertEquals("Video (2).mkv", uniqueDocumentName("Video.mkv", setOf("video.MKV")))
    }

    @Test
    fun primaryTreeIdBecomesReadableStoragePath() {
        assertEquals(
            "/storage/emulated/0/Movies/YouTube Harvester",
            displayPathForTreeDocumentId("primary:Movies/YouTube Harvester"),
        )
    }

    @Test
    fun removableVolumeKeepsItsProviderName() {
        assertEquals("7A1B-2C3D:/Video/YTH", displayPathForTreeDocumentId("7A1B-2C3D:Video/YTH"))
    }

    @Test
    fun systemRestrictedFoldersAreRejectedButNestedFolderIsAllowed() {
        assertEquals(true, isRestrictedDirectoryDocumentId("primary:"))
        assertEquals(true, isRestrictedDirectoryDocumentId("7A1B-2C3D:"))
        assertEquals(true, isRestrictedDirectoryDocumentId("primary:Download"))
        assertEquals(false, isRestrictedDirectoryDocumentId("primary:Download/YTH"))
    }
}
