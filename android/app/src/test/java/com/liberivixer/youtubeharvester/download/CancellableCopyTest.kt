package com.liberivixer.youtubeharvester.download

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class CancellableCopyTest {
    @Test fun cancelledCopyStopsBeforeWritingTheNextChunk() = runBlocking {
        val bytes = ByteArray(200_000) { 42 }
        val output = ByteArrayOutputStream()
        var calls = 0
        try {
            copyCancellable(ByteArrayInputStream(bytes), output) { if (++calls == 2) throw IllegalStateException("cancel") }
            fail("copy should be cancelled")
        } catch (_: IllegalStateException) {
            assertEquals(65_536, output.size())
        }
    }
    @Test fun fullCopyPreservesBytes() = runBlocking {
        val bytes = ByteArray(150_001) { (it % 251).toByte() }
        val output = ByteArrayOutputStream()
        copyCancellable(ByteArrayInputStream(bytes), output) {}
        assertArrayEquals(bytes, output.toByteArray())
    }
}
