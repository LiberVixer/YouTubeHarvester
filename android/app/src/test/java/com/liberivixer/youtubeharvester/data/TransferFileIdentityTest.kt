package com.liberivixer.youtubeharvester.data

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.util.concurrent.CancellationException

class TransferFileIdentityTest {
    @Test fun identityIsContentBoundAndStreamsAcrossBlocks() {
        val identity = transferFileIdentity(ByteArrayInputStream("abc".toByteArray()))
        assertEquals(3L, identity.size)
        assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", identity.sha256)
        val bytes = ByteArray(200_000) { (it % 251).toByte() }
        val original = transferFileIdentity(ByteArrayInputStream(bytes))
        bytes[bytes.lastIndex] = (bytes.last().toInt() xor 1).toByte()
        val altered = transferFileIdentity(ByteArrayInputStream(bytes))
        assertEquals(original.size, altered.size)
        assertNotEquals(original.sha256, altered.sha256)
        assertEquals(bytes.size.toLong(), original.size)
    }

    @Test fun hashingHonoursCancellation() {
        var calls = 0
        try {
            transferFileIdentity(ByteArrayInputStream(ByteArray(200_000))) {
                if (++calls == 2) throw CancellationException("QA cancellation")
            }
            fail("Expected cancellation")
        } catch (_: CancellationException) { assertEquals(2, calls) }
    }

    @Test fun onlyBasenamesCanBeUsedToRelinkFiles() {
        for (name in listOf("", " ", ".", "..", "../file.mp4", "a/b.mp4", "a\\b.mp4", "a\u0000b", "a\nb", "a".repeat(256))) {
            assertFalse(name, validTransferFileName(name))
        }
        assertTrue(validTransferFileName("Video (2).mp4"))
        assertTrue(validTransferFileName("QA-video.webm"))
    }
}
