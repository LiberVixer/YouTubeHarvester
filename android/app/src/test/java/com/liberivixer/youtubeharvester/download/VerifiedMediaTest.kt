package com.liberivixer.youtubeharvester.download

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class VerifiedMediaTest {
    @get:Rule val temporary = TemporaryFolder()

    private fun report(directory: File, file: File, resolution: String = "720p") {
        File(directory, "final-media.json").writeText(JSONObject()
            .put("path", file.absolutePath).put("resolution", resolution)
            .put("audio", listOf("English")).put("subtitles", listOf("en (manual)"))
            .put("selections", listOf("manual:en")).toString())
    }

    @Test fun usesVerifiedFileAndActualResolution() {
        val directory = temporary.newFolder("staging")
        val file = File(directory, "video.mkv").apply { writeBytes(byteArrayOf(1)) }
        report(directory, file)
        val media = VerifiedMedia.read(directory)
        assertEquals(file.canonicalFile, media.file)
        assertEquals("720p", media.resolution)
        assertEquals(listOf("manual:en"), media.selections)
    }

    @Test fun refusesFilesOutsideJobDirectory() {
        val directory = temporary.newFolder("staging")
        val file = temporary.newFile("other-job.mkv").apply { writeBytes(byteArrayOf(1)) }
        report(directory, file)
        assertThrows(IllegalStateException::class.java) { VerifiedMedia.read(directory) }
    }

    @Test fun publicationNameUsesActualResolutionWithoutRenamingStagingFile() {
        val directory = temporary.newFolder("staging")
        val file = File(directory, "Video [id] [1080p].mp4").apply { writeBytes(byteArrayOf(1)) }
        report(directory, file, "240p")
        assertEquals("Video [id] [240p].mp4", VerifiedMedia.read(directory).publicationName("1080p"))
        assertTrue(file.isFile)
        assertEquals(1L, file.length())
    }

    @Test fun publicationNamePreservesTitleTagsTracksAndContainer() {
        val file = File("Review [1080p] [id] [1080p] [a-en_s-en].tracks.mkv")
        val media = VerifiedMedia(file, "720p", emptyList(), emptyList(), emptyList())
        assertEquals("Review [1080p] [id] [720p] [a-en_s-en].tracks.mkv", media.publicationName("1080p"))
        val repeated = media.copy(file = File("Review [1080p] [1080p].mp4"))
        assertEquals("Review [1080p] [720p].mp4", repeated.publicationName("1080p"))
    }

    @Test fun publicationNameHandlesBestAndMissingQualityMarker() {
        val media = VerifiedMedia(File("Video [id] [best].mp4"), "2160p", emptyList(), emptyList(), emptyList())
        assertEquals("Video [id] [2160p].mp4", media.publicationName("best"))
        assertEquals("Truncated title [2160p].mkv",
            media.copy(file = File("Truncated title.mkv")).publicationName("best"))
    }

    @Test fun publicationNameKeepsMatchingResolution() {
        val name = "Video [id] [720p].mp4"
        val media = VerifiedMedia(File(name), "720p", emptyList(), emptyList(), emptyList())
        assertEquals(name, media.publicationName("720p"))
    }

    @Test fun missingSubtitlesDistinguishManualAndAutomaticInTheSameLanguage() {
        val media = VerifiedMedia(File("video.mkv"), "240p", emptyList(),
            listOf("en (manual)", "de (manual)"), listOf("manual:en", "manual:de"))
        assertEquals(listOf("auto:en"), media.missingSubtitleSelections(listOf("manual:en", "auto:en", "manual:de", "auto:en")))
        assertTrue(media.missingSubtitleSelections(listOf("manual:en", "manual:de")).isEmpty())
        assertTrue(media.missingSubtitleSelections(emptyList()).isEmpty())
    }

    @Test fun refusesEmptyOutputAndUnverifiedResolution() {
        val directory = temporary.newFolder("staging")
        val file = File(directory, "video.mkv").apply { writeBytes(byteArrayOf()) }
        report(directory, file)
        assertThrows(IllegalStateException::class.java) { VerifiedMedia.read(directory) }
        file.writeBytes(byteArrayOf(1))
        report(directory, file, "best")
        assertThrows(IllegalStateException::class.java) { VerifiedMedia.read(directory) }
    }
}
