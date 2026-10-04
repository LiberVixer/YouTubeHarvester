package com.liberivixer.youtubeharvester.media

import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import java.security.MessageDigest

internal object BundledRuntimeFile {
    private const val MAX_BYTES = 32L * 1024 * 1024

    fun ensure(target: File, expectedSha256: String, openBundled: () -> InputStream) {
        require(expectedSha256.matches(Regex("[a-f0-9]{64}")))
        val path = target.toPath()
        if (Files.isRegularFile(path, NOFOLLOW_LINKS) && target.length() in 1..MAX_BYTES &&
            target.inputStream().use { digest(it) } == expectedSha256) return

        Files.createDirectories(path.parent)
        val temporary = Files.createTempFile(path.parent, ".bundled-", ".tmp")
        try {
            openBundled().use { input ->
                FileOutputStream(temporary.toFile()).use { output ->
                    val buffer = ByteArray(8192)
                    var total = 0L
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        total += count
                        check(total <= MAX_BYTES) { "Bundled runtime exceeds size limit" }
                        output.write(buffer, 0, count)
                    }
                    output.fd.sync()
                }
            }
            check(temporary.toFile().inputStream().use { digest(it) } == expectedSha256) {
                "Bundled runtime checksum mismatch"
            }
            // Do not initialize the old runtime if the verified replacement fails.
            Files.move(temporary, path, ATOMIC_MOVE, REPLACE_EXISTING)
        } finally {
            Files.deleteIfExists(temporary)
        }
    }

    private fun digest(input: InputStream): String {
        val hash = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(8192)
        var total = 0L
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            total += count
            check(total <= MAX_BYTES) { "Runtime exceeds size limit" }
            hash.update(buffer, 0, count)
        }
        return hash.digest().joinToString("") { "%02x".format(it) }
    }
}
