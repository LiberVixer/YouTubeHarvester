package com.liberivixer.youtubeharvester.data

// An unreadable optional credential must not prevent access to the archive or queue.
internal fun recoverSecret(decrypt: () -> String): String = try {
    decrypt()
} catch (_: java.security.GeneralSecurityException) {
    ""
} catch (_: IllegalArgumentException) {
    ""
} catch (_: java.security.ProviderException) {
    ""
} catch (_: java.io.IOException) {
    ""
}
