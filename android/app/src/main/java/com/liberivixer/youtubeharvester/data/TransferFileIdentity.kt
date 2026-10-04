package com.liberivixer.youtubeharvester.data

import java.io.InputStream
import java.security.MessageDigest

internal data class TransferFileIdentity(val size: Long, val sha256: String)

internal fun validTransferFileName(name: String): Boolean = name.isNotBlank() && name.length <= 255 &&
    name !in setOf(".", "..") && name.none { it == '/' || it == '\\' || it.isISOControl() }

internal fun transferFileIdentity(input: InputStream, checkCancelled: () -> Unit = {}): TransferFileIdentity {
    val digest = MessageDigest.getInstance("SHA-256")
    val buffer = ByteArray(64 * 1024)
    var size = 0L
    while (true) {
        checkCancelled()
        val count = input.read(buffer)
        if (count < 0) break
        size += count
        digest.update(buffer, 0, count)
    }
    return TransferFileIdentity(size, digest.digest().joinToString("") { "%02x".format(it) })
}
