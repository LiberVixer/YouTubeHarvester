package com.liberivixer.youtubeharvester.media

import com.liberivixer.youtubeharvester.model.AppSettings
import com.liberivixer.youtubeharvester.model.CHANNEL_STATUS_FAILED
import com.liberivixer.youtubeharvester.model.ChannelItem
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.model.PaidContentStatus
import com.liberivixer.youtubeharvester.model.QueueItem
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ChannelCheckRunnerTest {
    @Test fun reportsFreshChannelMetadataBeforeDownloadingDiscoveredVideo() = runBlocking {
        val channel = channel("https://www.youtube.com/@Example").copy(name = "Old name", shortsEnabled = false, streamsEnabled = false)
        var current: ChannelCheckProgress? = null
        runner.run(listOf(channel), AppSettings(), false,
            onDiscovered = { items ->
                assertEquals(channel.id, current?.channelInfo?.id)
                assertEquals("Channel", current?.channelInfo?.name)
                items.size
            }, onProgress = { current = it })
        assertEquals(null, current?.channelId)
        assertEquals(null, current?.channelInfo)
    }

    @Test fun sectionProgressReportsRealCountsAndOnlyActiveSectionChecks() = runBlocking {
        val progress = mutableListOf<ChannelCheckProgress>()
        engine.failSection = ContentType.Shorts
        runner.run(listOf(channel("https://www.youtube.com/@Example").copy(streamsEnabled = false)),
            AppSettings(), checkPaidContent = false, onProgress = { progress += it })
        val last = progress.last()
        assertEquals(1, last.sections[ContentType.Video]?.count)
        assertEquals(com.liberivixer.youtubeharvester.model.SectionStatus.CHECKED, last.sections[ContentType.Video]?.status)
        assertEquals(com.liberivixer.youtubeharvester.model.SectionStatus.FAILED, last.sections[ContentType.Shorts]?.status)
        assertEquals(com.liberivixer.youtubeharvester.model.SectionStatus.DISABLED, last.sections[ContentType.Stream]?.status)
        assertEquals(1, last.errors)
        assertTrue(progress.all { p -> p.sections.values.count { it.status == com.liberivixer.youtubeharvester.model.SectionStatus.CHECKING } <= 1 })
    }

    @Test fun scanErrorCountIncludesEveryFailedSectionNotJustChannels() = runBlocking {
        val failing = object : ChannelScanEngine {
            override suspend fun scanSection(channelUrl: String, contentType: ContentType, limit: Int) = EngineResult.Failure("offline")
            override suspend fun checkPaidContent(channelUrl: String, sections: List<ContentType>) = EngineResult.Success(false)
            override fun cancel() = Unit
        }
        val summary = ChannelCheckRunner(failing, store) {}.run(listOf(channel("https://www.youtube.com/@Example")), AppSettings(), false)
        assertEquals(1, summary.failedChannels)
        assertEquals(3, summary.errors)
    }

    private val store = MemoryStore()
    private val engine = ScanEngine()
    private val runner = ChannelCheckRunner(engine, store) {}

    @Test
    fun rutubeShowDeliversVideosToDownloaderWithSourceAndOrigin() = runBlocking {
        val channel = channel("https://rutube.ru/metainfo/tv/405933")
        val result = runner.run(listOf(channel), AppSettings(videoLimit = 3), checkPaidContent = true,
            onDiscovered = store::acceptDownloads)
        assertEquals(listOf(ContentType.Video to 3), engine.calls)
        assertEquals(0, engine.paidProbes)
        assertEquals(1, result.queuedItems)
        assertEquals(MediaSource.Rutube, store.queued.single().source)
        assertEquals(channel.id, store.queued.single().originChannelId)
    }

    @Test
    fun markingDoesNotQueueOrProbeAndWaitsForAllSections() = runBlocking {
        val channel = channel("https://rutube.ru/channel/23704195")
        val result = runner.run(listOf(channel), AppSettings(), checkPaidContent = true, markOnly = true,
            onDiscovered = store::acceptDownloads)
        assertEquals(listOf(ContentType.Video, ContentType.Shorts), engine.calls.map { it.first })
        assertEquals(0, engine.paidProbes)
        assertEquals(2, result.markedItems)
        assertEquals(1, store.markCalls)
        assertTrue(store.queued.isEmpty())
    }

    @Test
    fun sectionFailurePreventsAllMarksForThatChannel() = runBlocking {
        engine.failSection = ContentType.Shorts
        val result = runner.run(listOf(channel("https://rutube.ru/channel/23704195")),
            AppSettings(), checkPaidContent = false, markOnly = true)
        assertEquals(1, result.failedChannels)
        assertEquals(0, result.markedItems)
        assertEquals(0, store.markCalls)
        assertTrue(store.queued.isEmpty())
        assertEquals(CHANNEL_STATUS_FAILED, store.updated.single().status)
    }

    @Test
    fun cancellationDoesNotSavePartialMarks() {
        engine.cancelSection = ContentType.Shorts
        var cancelled = false
        try {
            runBlocking {
                runner.run(listOf(channel("https://rutube.ru/channel/23704195")),
                    AppSettings(), checkPaidContent = false, markOnly = true)
            }
        } catch (_: CancellationException) {
            cancelled = true
        }
        assertTrue(cancelled)
        assertEquals(0, store.markCalls)
        assertTrue(store.updated.isEmpty())
    }

    @Test
    fun disabledSectionsAreNotScanned() = runBlocking {
        val channel = channel("https://www.youtube.com/@Example").copy(shortsEnabled = false, streamsEnabled = false)
        runner.run(listOf(channel), AppSettings(), checkPaidContent = false)
        assertEquals(listOf(ContentType.Video), engine.calls.map { it.first })
    }

    @Test
    fun observedMembersOnlyIsRememberedWithoutExtraProbe() = runBlocking {
        engine.membersOnly = true
        val channel = channel("https://www.youtube.com/@Example").copy(shortsEnabled = false, streamsEnabled = false)
        runner.run(listOf(channel), AppSettings(), checkPaidContent = false)
        assertEquals(0, engine.paidProbes)
        assertTrue(store.queued.isEmpty())
        assertEquals(PaidContentStatus.MembersOnly, store.updated.single().paidContent)
    }

    private fun channel(url: String): ChannelItem {
        val parsed = requireNotNull(ChannelUrlParser.parse(url))
        return ChannelItem(parsed.id, parsed.normalizedUrl, parsed.displayName, parsed.handle)
    }

    private class ScanEngine : ChannelScanEngine {
        val calls = mutableListOf<Pair<ContentType, Int>>()
        var paidProbes = 0
        var failSection: ContentType? = null
        var cancelSection: ContentType? = null
        var membersOnly = false

        override suspend fun scanSection(channelUrl: String, contentType: ContentType, limit: Int): EngineResult<ChannelSectionScan> {
            calls += contentType to limit
            if (contentType == cancelSection) throw CancellationException("Stopped")
            if (contentType == failSection) return EngineResult.Failure("Timeout on page 3", retryable = true)
            val source = requireNotNull(ChannelUrlParser.parse(channelUrl)).source
            val entry = ChannelScanEntry(contentType.name, "https://example.test/video", "Video", "Channel",
                null, contentType, membersOnly, source)
            return EngineResult.Success(ChannelSectionScan(contentType, "Channel", "", null, listOf(entry), true, membersOnly))
        }

        override suspend fun checkPaidContent(channelUrl: String, sections: List<ContentType>): EngineResult<Boolean> {
            paidProbes += 1
            return EngineResult.Success(false)
        }

        override fun cancel() = Unit
    }

    private class MemoryStore : ChannelCheckStorage {
        val queued = mutableListOf<QueueItem>()
        val updated = mutableListOf<ChannelItem>()
        var markCalls = 0

        suspend fun acceptDownloads(items: List<QueueItem>): Int {
            queued += items
            return items.size
        }

        override suspend fun markDiscoveredItems(items: List<ChannelScanEntry>): Int {
            markCalls += 1
            return items.size
        }

        override suspend fun updateChannelScanResult(channel: ChannelItem, checkedAt: Long, status: String) {
            updated += channel.copy(status = status)
        }
    }

    @Test fun validationDoesNotQueueOrDownloadDiscoveredItems() = runBlocking {
        runner.run(listOf(channel("https://www.youtube.com/@Example")), AppSettings(), checkPaidContent = false)
        assertTrue(store.queued.isEmpty())
    }

    @Test fun discoveriesAreHandledBeforeTheNextSectionIsScanned() = runBlocking {
        var handledSections = 0
        runner.run(listOf(channel("https://www.youtube.com/@Example")), AppSettings(), checkPaidContent = false,
            onDiscovered = { items ->
                assertEquals(handledSections + 1, engine.calls.size)
                handledSections++
                items.size
            })
        assertEquals(3, handledSections)
    }
}
