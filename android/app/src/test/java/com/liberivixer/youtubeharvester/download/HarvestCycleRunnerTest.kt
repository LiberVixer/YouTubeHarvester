package com.liberivixer.youtubeharvester.download

import com.liberivixer.youtubeharvester.media.ChannelCheckSummary
import com.liberivixer.youtubeharvester.model.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class HarvestCycleRunnerTest {
    @Test fun interruptedWorkerResumesPendingDownloadWithoutEnqueueingAgain() = runBlocking {
        pending += item("quick")
        var saved = HarvestCheckpoint()
        cancelOnAwait = true
        val runner = HarvestCycleRunner(gateway) { _, _, _, _ -> ChannelCheckSummary(0, 0, 0) }
        try {
            runner.run(emptyList(), AppSettings(), saveCheckpoint = { saved = it }, cancelOnInterruption = false)
            fail("Expected interruption")
        } catch (_: CancellationException) { }
        assertEquals("quick", saved.pending?.jobId)
        assertFalse(events.any { it.startsWith("cancel:") })
        cancelOnAwait = false
        val result = runner.run(emptyList(), AppSettings(), checkpoint = saved, saveCheckpoint = { saved = it })
        assertEquals(1, events.count { it.startsWith("start:") })
        assertEquals(1, result.downloaded[ContentType.Video])
        assertEquals(null, saved.pending)
    }

    @Test fun completedChannelsAreSkippedAfterRecovery() = runBlocking {
        val a = ChannelItem("a", "https://example.test/a", "A", "")
        val b = a.copy(id = "b")
        val seen = mutableListOf<String>()
        val runner = HarvestCycleRunner(gateway) { channels, _, _, _ ->
            seen += channels.map { it.id }
            ChannelCheckSummary(channels.size, 0, 0)
        }
        val result = runner.run(listOf(a, b), AppSettings(), checkpoint = HarvestCheckpoint(
            phase = HarvestPhase.CHANNELS, completedChannels = 1, scanErrors = 2))
        assertEquals(listOf("b"), seen)
        assertEquals(2, result.channels.completedChannels)
        assertEquals(2, result.errors)
    }

    @Test fun completedReportPersistsDownloadAndScanErrorTotals() = runBlocking {
        val reports = mutableListOf<CheckReport>()
        pending += item("quick")
        val runner = HarvestCycleRunner(gateway, { reports += it }) { _, _, _, progress ->
            progress(com.liberivixer.youtubeharvester.media.ChannelCheckProgress(null, null, 1, 1, 0, errors = 2))
            ChannelCheckSummary(1, 0, 1, errors = 2)
        }
        runner.run(listOf(ChannelItem("channel", "https://example.test", "Channel", "")), AppSettings())
        val report = reports.single()
        assertEquals(CheckOutcome.COMPLETED, report.outcome)
        assertEquals(1, report.downloaded)
        assertEquals(1, report.attempted)
        assertEquals(2, report.errors)
        assertEquals(1, report.checkedChannels)
        assertTrue(report.finishedAt > 0)
    }

    @Test fun stoppedCycleDoesNotSaveSuccessfulReport() = runBlocking {
        val reports = mutableListOf<CheckReport>()
        pending += item("quick")
        cancelOnAwait = true
        val runner = HarvestCycleRunner(gateway, { reports += it }) { _, _, _, _ -> error("Not reached") }
        try { runner.run(emptyList(), AppSettings()); fail("Expected stop") } catch (_: CancellationException) { }
        assertEquals(CheckOutcome.STOPPED, reports.single().outcome)
        assertEquals(0, reports.single().downloaded)
        assertEquals(1, reports.single().attempted)
    }

    @Test fun unexpectedFailureSavesFailedReport() = runBlocking {
        val reports = mutableListOf<CheckReport>()
        val runner = HarvestCycleRunner(gateway, { reports += it }) { _, _, _, _ -> error("Scanner crashed") }
        try { runner.run(emptyList(), AppSettings()); fail("Expected failure") } catch (_: IllegalStateException) { }
        assertEquals(CheckOutcome.FAILED, reports.single().outcome)
        assertEquals(1, reports.single().errors)
    }

    private fun item(id: String) = QueueItem(id, "https://example.test/$id", id, "Channel", MediaSource.YouTube)
    private val events = mutableListOf<String>()
    private val pending = mutableListOf<QueueItem>()
    private var outcome = DownloadStatus.COMPLETED
    private var cancelOnAwait = false
    private val gateway = object : HarvestDownloads {
        override suspend fun queue() = pending.toList()
        override suspend fun enqueue(item: QueueItem, fromQueue: Boolean): String? {
            if (!fromQueue && pending.any { it.id == item.id }) return null
            events += "start:${item.id}:$fromQueue"
            return item.id
        }
        override suspend fun await(jobId: String): DownloadStatus {
            events += "finish:$jobId"
            if (cancelOnAwait) throw CancellationException("stop")
            if (outcome == DownloadStatus.COMPLETED) pending.removeAll { it.id == jobId }
            return outcome
        }
        override suspend fun cancel(jobId: String) { events += "cancel:$jobId" }
    }

    @Test fun queueThenEachChannelVideoThenNewQueueLink() = runBlocking {
        pending += item("quick1")
        val phases = mutableListOf<HarvestPhase>()
        val runner = HarvestCycleRunner(gateway) { _, _, found, _ ->
            events += "scan:1"
            found(listOf(item("channel1")))
            events += "scan:2"
            pending += item("quick2")
            found(listOf(item("channel2"), item("quick2")))
            ChannelCheckSummary(2, 2, 0)
        }
        val summary = runner.run(emptyList(), AppSettings()) { phases += it.phase }
        assertEquals(listOf("start:quick1:true", "finish:quick1", "scan:1", "start:channel1:false", "finish:channel1",
            "scan:2", "start:channel2:false", "finish:channel2", "start:quick2:true", "finish:quick2"), events)
        assertEquals(listOf(HarvestPhase.QUEUE_BEFORE, HarvestPhase.CHANNELS, HarvestPhase.QUEUE_AFTER), phases.distinct())
        assertEquals(4, summary.downloaded[ContentType.Video])
    }

    @Test fun failureIsNotRetriedAgainInFinalQueuePass() = runBlocking {
        pending += item("failed")
        outcome = DownloadStatus.FAILED
        val runner = HarvestCycleRunner(gateway) { _, _, _, _ -> ChannelCheckSummary(0, 0, 0) }
        val summary = runner.run(emptyList(), AppSettings())
        assertEquals(listOf("start:failed:true", "finish:failed"), events)
        assertEquals(1, summary.errors)
        assertEquals(1, pending.size)
    }

    @Test fun cancellationStopsOwnedDownloadAndDoesNotScanNext() = runBlocking {
        pending += item("quick")
        cancelOnAwait = true
        val runner = HarvestCycleRunner(gateway) { _, _, _, _ -> error("Must not scan after stop") }
        try { runner.run(emptyList(), AppSettings()); fail("Expected cancellation") }
        catch (_: CancellationException) { }
        assertEquals(listOf("start:quick:true", "finish:quick", "cancel:quick"), events)
    }

    @Test fun linksAddedDuringInitialQueueAreDrainedBeforeScanning() = runBlocking {
        pending += item("a")
        val runner = HarvestCycleRunner(gateway) { _, _, _, _ ->
            assertTrue(pending.isEmpty())
            ChannelCheckSummary(0, 0, 0)
        }
        var added = false
        runner.run(emptyList(), AppSettings()) {
            if (!added && it.downloaded.values.sum() == 1) { pending += item("b"); added = true }
        }
        assertEquals(listOf("start:a:true", "finish:a", "start:b:true", "finish:b"), events)
    }
}
