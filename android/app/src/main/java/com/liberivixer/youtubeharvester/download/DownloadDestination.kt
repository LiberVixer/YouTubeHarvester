package com.liberivixer.youtubeharvester.download

internal fun displayPathForTreeDocumentId(documentId: String): String {
    val volume = documentId.substringBefore(':', documentId)
    val relativePath = documentId.substringAfter(':', "").trim('/')
    return when {
        volume.equals("primary", ignoreCase = true) ->
            "/storage/emulated/0" + relativePath.takeIf(String::isNotBlank)?.let { "/$it" }.orEmpty()
        relativePath.isNotBlank() -> "$volume:/$relativePath"
        else -> volume
    }
}

internal fun isRestrictedDirectoryDocumentId(documentId: String): Boolean {
    if (!documentId.contains(':')) return false
    val volume = documentId.substringBefore(':')
    val relativePath = documentId.substringAfter(':').trim('/')
    return relativePath.isBlank() || (
        volume.equals("primary", ignoreCase = true) &&
            relativePath.equals("Download", ignoreCase = true)
        )
}

internal fun uniqueDocumentName(fileName: String, existingNames: Set<String>): String {
    val occupied = existingNames.mapTo(hashSetOf()) { it.lowercase() }
    if (fileName.lowercase() !in occupied) return fileName
    val extension = fileName.substringAfterLast('.', "").takeIf(String::isNotBlank)?.let { ".$it" }.orEmpty()
    val base = fileName.removeSuffix(extension)
    var number = 2
    while (true) {
        val candidate = "$base ($number)$extension"
        if (candidate.lowercase() !in occupied) return candidate
        number += 1
    }
}
