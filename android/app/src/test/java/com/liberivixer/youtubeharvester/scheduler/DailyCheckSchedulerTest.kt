package com.liberivixer.youtubeharvester.scheduler

import java.time.Instant
import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Test

class DailyCheckSchedulerTest {
    private val utc = ZoneId.of("UTC")

    @Test
    fun `day after spring gap returns to requested wall clock time`() {
        val now = Instant.parse("2026-03-29T10:00:00Z").toEpochMilli()
        val expected = Instant.parse("2026-03-30T00:30:00Z").toEpochMilli()
        assertEquals(expected - now, nextRunDelayMillis(2, 30, now, ZoneId.of("Europe/Berlin")))
    }

    @Test
    fun `upcoming spring gap shifts nonexistent time forward`() {
        val now = Instant.parse("2026-03-29T00:00:00Z").toEpochMilli()
        assertEquals(90 * 60 * 1_000L, nextRunDelayMillis(2, 30, now, ZoneId.of("Europe/Berlin")))
    }

    @Test
    fun `autumn clock change preserves next days requested time`() {
        val now = Instant.parse("2026-10-24T12:00:00Z").toEpochMilli()
        val expected = Instant.parse("2026-10-25T08:00:00Z").toEpochMilli()
        assertEquals(expected - now, nextRunDelayMillis(9, 0, now, ZoneId.of("Europe/Berlin")))
    }

    @Test
    fun `next time later today uses same day`() {
        val now = Instant.parse("2026-08-31T12:00:00Z").toEpochMilli()

        val delay = nextRunDelayMillis(13, 30, now, utc)

        assertEquals(90 * 60 * 1_000L, delay)
    }

    @Test
    fun `time that has passed is scheduled tomorrow`() {
        val now = Instant.parse("2026-08-31T18:15:00Z").toEpochMilli()

        val delay = nextRunDelayMillis(9, 0, now, utc)

        assertEquals((14 * 60 + 45) * 60 * 1_000L, delay)
    }

    @Test
    fun `exact current minute is scheduled tomorrow`() {
        val now = Instant.parse("2026-08-31T09:00:00Z").toEpochMilli()

        val delay = nextRunDelayMillis(9, 0, now, utc)

        assertEquals(24 * 60 * 60 * 1_000L, delay)
    }
}
