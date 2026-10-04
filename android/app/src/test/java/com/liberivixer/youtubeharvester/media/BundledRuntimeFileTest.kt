package com.liberivixer.youtubeharvester.media

import java.io.IOException
import java.io.InputStream
import java.security.MessageDigest
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class BundledRuntimeFileTest {
    @get:Rule val temporary = TemporaryFolder()
    private val bundled = "verified bundled engine".toByteArray()
    private val hash = MessageDigest.getInstance("SHA-256").digest(bundled)
        .joinToString("") { "%02x".format(it) }

    @Test fun installsFreshRuntime() {
        val target = temporary.root.resolve("runtime/yt-dlp")
        BundledRuntimeFile.ensure(target, hash) { bundled.inputStream() }
        assertArrayEquals(bundled, target.readBytes())
        assertEquals(listOf("yt-dlp"), requireNotNull(target.parentFile).list()?.toList())
    }

    @Test fun replacesPreviouslyDownloadedRuntime() {
        val target = temporary.newFile("yt-dlp").apply { writeText("unverified downloaded code") }
        BundledRuntimeFile.ensure(target, hash) { bundled.inputStream() }
        assertArrayEquals(bundled, target.readBytes())
    }

    @Test fun keepsMatchingRuntimeWithoutRewriting() {
        val target = temporary.newFile("yt-dlp").apply { writeBytes(bundled) }
        BundledRuntimeFile.ensure(target, hash) { error("Must not reopen APK when installed file matches") }
        assertArrayEquals(bundled, target.readBytes())
    }

    @Test fun corruptedBundleDoesNotReplaceOldFile() {
        val target = temporary.newFile("yt-dlp").apply { writeText("old file") }
        assertThrows(IllegalStateException::class.java) {
            BundledRuntimeFile.ensure(target, hash) { "wrong bytes".byteInputStream() }
        }
        assertEquals("old file", target.readText())
        assertEquals(listOf("yt-dlp"), temporary.root.list()?.toList())
    }

    @Test fun interruptedCopyPreservesOldFileAndCanRetry() {
        val target = temporary.newFile("yt-dlp").apply { writeText("old file") }
        assertThrows(IOException::class.java) {
            BundledRuntimeFile.ensure(target, hash) {
                object : InputStream() {
                    override fun read(): Int = throw IOException("Simulated read failure")
                }
            }
        }
        assertEquals("old file", target.readText())
        assertEquals(listOf("yt-dlp"), temporary.root.list()?.toList())
        BundledRuntimeFile.ensure(target, hash) { bundled.inputStream() }
        assertArrayEquals(bundled, target.readBytes())
    }

    @Test fun emptyBundleIsRejected() {
        val target = temporary.root.resolve("yt-dlp")
        assertThrows(IllegalStateException::class.java) {
            BundledRuntimeFile.ensure(target, hash) { byteArrayOf().inputStream() }
        }
        assertFalse(target.exists())
    }
}
