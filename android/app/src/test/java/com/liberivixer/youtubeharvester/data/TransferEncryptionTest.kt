package com.liberivixer.youtubeharvester.data

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.InputStream

class TransferEncryptionTest {
    private val password get() = "QA-only-transfer-passphrase".toCharArray()

    @Test fun roundTripIsRandomizedAndContainsNoPlainCredentials() {
        val plain = "QA_TOKEN_secret_0123456789".toByteArray()
        val first = TransferEncryption.encrypt(plain, password)
        val second = TransferEncryption.encrypt(plain, password)
        assertFalse(first.contentEquals(second))
        assertFalse(first.toString(Charsets.ISO_8859_1).contains("QA_TOKEN_secret"))
        assertArrayEquals(plain, TransferEncryption.decrypt(first, password))
        assertArrayEquals(plain, TransferEncryption.decrypt(second, password))
        assertArrayEquals(first, TransferEncryption.readBounded(ByteArrayInputStream(first)))
    }

    @Test fun wrongPasswordTamperingAndTruncationAreRejected() {
        val file = TransferEncryption.encrypt("payload".toByteArray(), password)
        fails { TransferEncryption.decrypt(file, "different-QA-passphrase".toCharArray()) }
        for (offset in listOf(0, 8, 24, 36, file.lastIndex)) {
            val changed = file.copyOf()
            changed[offset] = (changed[offset].toInt() xor 1).toByte()
            fails { TransferEncryption.decrypt(changed, password) }
        }
        fails { TransferEncryption.decrypt(file.copyOf(file.size - 1), password) }
        fails { TransferEncryption.decrypt(byteArrayOf(), password) }
    }

    @Test fun passwordAndInputLimitsFailBeforeUnboundedWork() {
        fails { TransferEncryption.encrypt(byteArrayOf(), "short".toCharArray()) }
        fails { TransferEncryption.encrypt(byteArrayOf(), CharArray(1025) { 'x' }) }
        val input = object : InputStream() {
            override fun read(): Int = 0
            override fun read(b: ByteArray, off: Int, len: Int): Int { b.fill(0, off, off + len); return len }
        }
        fails { TransferEncryption.readBounded(input) }
    }

    private fun fails(block: () -> Unit) {
        try { block(); fail("Expected rejection") } catch (_: Exception) { }
    }
}
