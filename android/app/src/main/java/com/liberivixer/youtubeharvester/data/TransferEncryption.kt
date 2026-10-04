package com.liberivixer.youtubeharvester.data

import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec

internal object TransferEncryption {
    const val MAX_BYTES = 32 * 1024 * 1024
    private val magic = "YTHXFER1".toByteArray(Charsets.US_ASCII)
    private const val HEADER_BYTES = 36
    private const val ITERATIONS = 600_000

    fun encrypt(plain: ByteArray, password: CharArray): ByteArray {
        require(plain.size <= MAX_BYTES - HEADER_BYTES - 16)
        require(password.size in 12..1024)
        val random = SecureRandom()
        val salt = ByteArray(16).also(random::nextBytes)
        val iv = ByteArray(12).also(random::nextBytes)
        val header = magic + salt + iv
        return crypt(Cipher.ENCRYPT_MODE, plain, password, salt, iv, header).let { header + it }
    }

    fun decrypt(file: ByteArray, password: CharArray): ByteArray {
        require(file.size in (HEADER_BYTES + 16)..MAX_BYTES)
        require(password.size in 12..1024)
        require(file.copyOfRange(0, magic.size).contentEquals(magic))
        val header = file.copyOfRange(0, HEADER_BYTES)
        return crypt(Cipher.DECRYPT_MODE, file.copyOfRange(HEADER_BYTES, file.size), password,
            file.copyOfRange(8, 24), file.copyOfRange(24, 36), header)
    }

    fun readBounded(input: InputStream): ByteArray {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            require(output.size() + count <= MAX_BYTES)
            output.write(buffer, 0, count)
        }
        return output.toByteArray()
    }

    private fun crypt(mode: Int, input: ByteArray, password: CharArray, salt: ByteArray,
        iv: ByteArray, header: ByteArray): ByteArray {
        val spec = PBEKeySpec(password, salt, ITERATIONS, 256)
        val key = try { SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded }
            finally { spec.clearPassword() }
        try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(mode, SecretKeySpec(key, "AES"), GCMParameterSpec(128, iv))
            cipher.updateAAD(header)
            return cipher.doFinal(input)
        } finally { key.fill(0) }
    }
}
