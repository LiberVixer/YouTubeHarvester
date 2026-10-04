package com.liberivixer.youtubeharvester.update

import org.junit.Assert.*
import org.junit.Test

class AndroidAppUpdaterTest {
    private fun release(assets: String, version: String = "1.3.0") = """[{"tag_name":"android-v$version","assets":[$assets]}]"""
    private fun asset(name: String, digest: String = "sha256:" + "a".repeat(64)) =
        """{"name":"$name","digest":"$digest","browser_download_url":"https://github.com/LiberVixer/YouTubeHarvester/releases/download/test/$name"}"""

    @Test fun selectsCompatibleSignedRelease() {
        val payload = release(asset("app-x86-release.apk") + "," + asset("app-arm64-v8a-release.apk"))
        assertTrue(AndroidAppUpdater.selectRelease(payload, listOf("arm64-v8a"), "1.2.0")!!.url.contains("arm64-v8a"))
    }
    @Test fun rejectsUnsignedDebugAndMissingDigest() {
        listOf(asset("app-arm64-v8a-release-unsigned.apk"), asset("app-arm64-v8a-debug.apk"), asset("app-arm64-v8a-release.apk", "")).forEach {
            assertNull(AndroidAppUpdater.selectRelease(release(it), listOf("arm64-v8a"), "1.2.0"))
        }
    }
    @Test fun rejectsOldAndWrongArchitecture() {
        assertNull(AndroidAppUpdater.selectRelease(release(asset("app-x86-release.apk")), listOf("arm64-v8a"), "1.2.0"))
        assertNull(AndroidAppUpdater.selectRelease(release(asset("app-arm64-v8a-release.apk"), "1.1.0"), listOf("arm64-v8a"), "1.2.0"))
    }
    @Test fun comparesNumbersNumerically() {
        assertTrue(AndroidAppUpdater.compareVersions("1.10.0", "1.9.0") > 0)
        assertTrue(AndroidAppUpdater.compareVersions("1.2.0-beta-android-dev25", "1.2.0-beta-android-dev24") > 0)
        assertTrue(AndroidAppUpdater.compareVersions("1.2.0", "1.2.0-beta-android-dev24") > 0)
        assertTrue(AndroidAppUpdater.compareVersions("1.2.0-beta-android-dev24", "1.2.0") < 0)
    }
}
