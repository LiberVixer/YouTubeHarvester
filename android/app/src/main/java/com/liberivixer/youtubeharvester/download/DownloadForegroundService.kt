package com.liberivixer.youtubeharvester.download

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Environment
import android.os.IBinder
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.text.format.DateUtils
import androidx.core.app.NotificationCompat
import androidx.room.withTransaction
import com.liberivixer.youtubeharvester.MainActivity
import com.liberivixer.youtubeharvester.R
import com.liberivixer.youtubeharvester.data.SettingsDataStore
import com.liberivixer.youtubeharvester.data.db.ArchiveEntity
import com.liberivixer.youtubeharvester.data.db.DownloadJobEntity
import com.liberivixer.youtubeharvester.data.db.HarvesterDatabase
import com.liberivixer.youtubeharvester.data.db.toModel
import com.liberivixer.youtubeharvester.logging.AppLogLevel
import com.liberivixer.youtubeharvester.logging.AppLogStore
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.DownloadStatus
import com.liberivixer.youtubeharvester.model.PaidContentStatus
import com.liberivixer.youtubeharvester.model.stringResource
import com.liberivixer.youtubeharvester.notifications.TelegramNotifier
import com.liberivixer.youtubeharvester.media.AndroidYtDlpRuntime
import com.liberivixer.youtubeharvester.ui.LocaleController
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.isActive
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.runInterruptible
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.security.MessageDigest
import java.util.Collections

class DownloadForegroundService : Service() {
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate +
        CoroutineExceptionHandler { _, error ->
            CoroutineScope(Dispatchers.IO).launch {
                runCatching { appLog.append(AppLogLevel.ERROR, "Download", "Processor stopped: ${safeLogMessage(error)}") }
            }
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        })
    private val cancelledJobs = Collections.synchronizedSet(mutableSetOf<String>())
    private val pausedJobs = Collections.synchronizedSet(mutableSetOf<String>())
    private val phaseLock = Any()
    private var currentPhase = DownloadStatus.INITIALIZING
    private lateinit var database: HarvesterDatabase
    private lateinit var settingsStore: SettingsDataStore
    private lateinit var appLog: AppLogStore
    private lateinit var notifications: NotificationManager
    private var processor: Job? = null
    private var recovered = false
    private var latestStartId = 0
    private var pendingCommands = 0
    @Volatile private var currentJobId: String? = null

    override fun onCreate() {
        super.onCreate()
        database = HarvesterDatabase.getInstance(this)
        settingsStore = SettingsDataStore(this)
        appLog = AppLogStore(this)
        notifications = getSystemService(NotificationManager::class.java)
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        latestStartId = startId
        startForeground(NOTIFICATION_ID, waitingNotification())
        DownloadBootNotification.clear(this)
        pendingCommands += 1
        serviceScope.launch {
            try {
                when (intent?.action ?: ACTION_RUN) {
                    ACTION_CANCEL -> intent?.getStringExtra(EXTRA_JOB_ID)?.let { cancelJob(it) }
                    ACTION_PAUSE -> intent?.getStringExtra(EXTRA_JOB_ID)?.let { pauseJob(it) }
                    ACTION_RESUME -> intent?.getStringExtra(EXTRA_JOB_ID)?.let { id ->
                        withContext(Dispatchers.IO) {
                            val saved = database.downloadJobDao().get(id)
                            if (saved?.toModel()?.status?.isResumable == true && rollbackPublication(id, saved.fileUri)) {
                                com.liberivixer.youtubeharvester.data.AndroidAppRepository(this@DownloadForegroundService)
                                    .resumeDownload(id)
                                notifications.cancel(id.hashCode())
                            }
                        }
                    }
                }
            } finally {
                pendingCommands -= 1
                startProcessor()
            }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        currentJobId?.let { jobId ->
            CoroutineScope(Dispatchers.IO).launch { runCatching { YoutubeDL.destroyProcessById(jobId) } }
        }
        serviceScope.cancel()
        super.onDestroy()
    }

    override fun onTimeout(startId: Int, fgsType: Int) {
        try {
            currentJobId?.let { DownloadTimeoutWorker.enqueue(this, it) }
        } finally {
            serviceScope.cancel()
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun startProcessor() {
        if (processor?.isActive == true) return
        processor = serviceScope.launch(start = CoroutineStart.LAZY) {
            if (!recovered) {
                withContext(Dispatchers.IO) { recoverPublications() }
                database.downloadJobDao().resetInterrupted(System.currentTimeMillis())
                recovered = true
            }
            while (true) {
                val observedStartId = latestStartId
                val job = database.downloadJobDao().claimNext(System.currentTimeMillis())
                if (job == null) {
                    if (pendingCommands > 0) {
                        delay(50)
                        continue
                    }
                    if (observedStartId != latestStartId) continue
                    currentJobId = null
                    processor = null
                    stopForeground(STOP_FOREGROUND_REMOVE)
                    stopSelf(observedStartId)
                    return@launch
                }
                currentJobId = job.jobId
                synchronized(phaseLock) { currentPhase = DownloadStatus.INITIALIZING }
                withContext(Dispatchers.IO) { process(job) }
            }
        }
        processor?.start()
    }

    private suspend fun recoverPublications() {
        database.downloadJobDao().unfinishedPublications().forEach { job ->
            if (!rollbackPublication(job.jobId, job.fileUri)) {
                database.downloadJobDao().markFailed(job.jobId, statusText(DownloadStatus.FAILED),
                    text(R.string.download_start_error), System.currentTimeMillis())
                updateQueueStatus(job, DownloadStatus.FAILED)
            }
        }
    }

    private suspend fun updateQueueStatus(job: DownloadJobEntity, status: DownloadStatus) {
        database.queueDao().updateFromJob(job, status.name)
    }

    private suspend fun rollbackPublication(jobId: String, uri: String?): Boolean {
        if (uri == null) return true
        return runCatching {
            DownloadOutputPublisher(this).deletePublished(uri)
            database.downloadJobDao().recordPublication(jobId, null)
        }.onFailure { error ->
            runCatching { appLog.append(AppLogLevel.ERROR, "Download", "Publication cleanup failed: ${safeLogMessage(error)}") }
        }.isSuccess
    }

    private suspend fun process(job: DownloadJobEntity) {
        currentJobId = job.jobId
        val jobDao = database.downloadJobDao()
        val now = System.currentTimeMillis()
        val initializing = statusText(DownloadStatus.INITIALIZING)
        jobDao.updateProgress(job.jobId, DownloadStatus.INITIALIZING.name, job.progress, null, initializing, now)
        updateQueueStatus(job, DownloadStatus.INITIALIZING)
        notifications.notify(NOTIFICATION_ID, progressNotification(job, 0, initializing, null))
        appLog.append(
            AppLogLevel.INFO,
            "Download",
            "Started job=${safeJobId(job.jobId)} source=${job.source} media=${job.mediaId} resolution=${job.resolution}",
        )

        val stagingDirectory = jobStagingDirectory(job.jobId)
        var publishedFileUri: String? = null
        try {
            ensureRuntime()
            if (cancelledJobs.remove(job.jobId)) {
                markCancelled(job)
                return
            }
            if (job.jobId in pausedJobs) {
                markPaused(job)
                return
            }
            check(stagingDirectory.isDirectory || stagingDirectory.mkdirs()) { text(R.string.service_error_prepare_temp) }
            var lastPersistedProgress = -1
            var lastPersistedAt = 0L
            val progressCallback: (Float, Long, String) -> Unit = { rawProgress, rawEta, line ->
                synchronized(phaseLock) {
                    if (job.jobId !in pausedJobs && job.jobId !in cancelledJobs) {
                        val progress = rawProgress.toInt().coerceIn(0, 100)
                        val phase = DownloadRetryPolicy.phaseForLine(currentPhase, line)
                        val phaseChanged = currentPhase != phase
                        currentPhase = phase
                        val time = System.currentTimeMillis()
                        if (phaseChanged || (progress != lastPersistedProgress && (progress >= lastPersistedProgress + 1 || time - lastPersistedAt >= 1_000))) {
                            lastPersistedProgress = progress
                            lastPersistedAt = time
                            val eta = rawEta.takeIf { it >= 0 }
                            val message = if (phase == DownloadStatus.PROCESSING) statusText(phase) else cleanProgressLine(line, progress)
                            runBlocking(Dispatchers.IO) {
                                jobDao.updateProgress(job.jobId, phase.name, progress, eta, message, time)
                                updateQueueStatus(job, phase)
                            }
                            notifications.notify(NOTIFICATION_ID, progressNotification(job, progress, message, eta, canPause = phase.canPause))
                        }
                    }
                }
            }
            var effectiveSubtitles = job.toModel().subtitleSelections
            while (true) {
                if (job.jobId in pausedJobs) throw DownloadPausedException()
                if (job.jobId in cancelledJobs) throw DownloadCancelledException()
                try {
                    File(stagingDirectory, "final-media.json").delete()
                    val response = coroutineScope {
                        // A command may arrive before the native process registers its ID.
                        val stopper = launch {
                            while (isActive) {
                                if (job.jobId in pausedJobs || job.jobId in cancelledJobs) {
                                    runCatching { YoutubeDL.destroyProcessById(job.jobId) }
                                }
                                delay(200)
                            }
                        }
                        try {
                            runInterruptible(Dispatchers.IO) {
                                YoutubeDL.execute(buildRequest(job, stagingDirectory, effectiveSubtitles), job.jobId, progressCallback)
                            }
                        } finally { stopper.cancelAndJoin() }
                    }
                    check(response.exitCode == 0) {
                        response.err.ifBlank { "yt-dlp download failed with code ${response.exitCode}" }
                    }
                    response.err.lineSequence().filter {
                        it.contains("WARNING", ignoreCase = true) && it.contains("subtitle", ignoreCase = true)
                    }.take(8).forEach { warning ->
                        appLog.append(AppLogLevel.IMPORTANT, "Download", "job=${safeJobId(job.jobId)} ${safeLogMessage(Exception(warning))}")
                    }
                    break
                } catch (error: Exception) {
                    if (error is CancellationException) throw error
                    if (job.jobId in pausedJobs) throw DownloadPausedException()
                    if (job.jobId in cancelledJobs) throw DownloadCancelledException()
                    if (DownloadRetryPolicy.isNetworkError(error.message.orEmpty()) &&
                        jobDao.scheduleRetry(job.jobId, DownloadRetryPolicy.MAX_RETRIES, System.currentTimeMillis()) == 1) {
                        synchronized(phaseLock) { currentPhase = DownloadStatus.WAITING_NETWORK }
                        updateQueueStatus(job, DownloadStatus.WAITING_NETWORK)
                        val waiting = statusText(DownloadStatus.WAITING_NETWORK)
                        notifications.notify(NOTIFICATION_ID, progressNotification(job, lastPersistedProgress.coerceAtLeast(0), waiting, null, indeterminate = true))
                        appLog.append(AppLogLevel.INFO, "Download", "Network retry job=${safeJobId(job.jobId)}: ${safeLogMessage(error)}")
                        awaitNetwork(job.jobId)
                        synchronized(phaseLock) { currentPhase = DownloadStatus.INITIALIZING }
                        jobDao.updateProgress(job.jobId, DownloadStatus.INITIALIZING.name, lastPersistedProgress.coerceAtLeast(0), null, initializing, System.currentTimeMillis())
                        continue
                    }
                    val failedLanguages = failedSubtitleLanguages(error.message.orEmpty())
                    val remaining = effectiveSubtitles.filterNot {
                        it.substringAfter(':', "").lowercase() in failedLanguages
                    }
                    if (failedLanguages.isEmpty() || remaining.size == effectiveSubtitles.size) throw error
                    effectiveSubtitles = remaining
                    val unavailable = failedLanguages.sorted().joinToString()
                    val message = text(R.string.service_subtitles_unavailable_retry, unavailable)
                    jobDao.updateSubtitleSelections(
                        job.jobId,
                        JSONArray(effectiveSubtitles).toString(),
                        message,
                        System.currentTimeMillis(),
                    )
                    notifications.notify(NOTIFICATION_ID, progressNotification(job, lastPersistedProgress.coerceAtLeast(0), message, null, indeterminate = true))
                }
            }

            val pauseBeforePublish = synchronized(phaseLock) {
                (job.jobId in pausedJobs).also { if (!it) currentPhase = DownloadStatus.PUBLISHING }
            }
            if (pauseBeforePublish) {
                markPaused(job)
                return
            }
            if (cancelledJobs.remove(job.jobId)) {
                markCancelled(job)
                return
            }
            val verified = VerifiedMedia.read(stagingDirectory)
            val output = verified.file
            val publishing = statusText(DownloadStatus.PUBLISHING)
            jobDao.updateProgress(job.jobId, DownloadStatus.PUBLISHING.name, 100, null, publishing, System.currentTimeMillis())
            updateQueueStatus(job, DownloadStatus.PUBLISHING)
            notifications.notify(NOTIFICATION_ID, progressNotification(job, 100, publishing, null, indeterminate = true, canPause = false))
            val settings = settingsStore.settings.first()
            val publisher = DownloadOutputPublisher(this@DownloadForegroundService)
            val fileUri = withContext(Dispatchers.IO) {
                publisher.publish(output, settings.downloadDirectoryUri, fileName = verified.publicationName(job.resolution), onCreated = { uri ->
                    publishedFileUri = uri
                    jobDao.recordPublication(job.jobId, uri)
                }, checkCancelled = {
                    if (job.jobId in cancelledJobs) throw DownloadCancelledException()
                })
            }
            publishedFileUri = fileUri
            if (cancelledJobs.remove(job.jobId)) {
                rollbackPublication(job.jobId, fileUri)
                publishedFileUri = null
                markCancelled(job)
                return
            }
            complete(job, fileUri, verified, settings.downloadDirectory)
            publishedFileUri = null
            stagingDirectory.deleteRecursively()
        } catch (error: CancellationException) {
            // Process shutdown leaves its durable job and publication journal for recovery.
            withContext(NonCancellable + Dispatchers.IO) { runCatching { YoutubeDL.destroyProcessById(job.jobId) } }
            throw error
        } catch (error: Exception) {
            if (jobDao.get(job.jobId)?.status == DownloadStatus.COMPLETED.name) {
                runCatching { appLog.append(AppLogLevel.ERROR, "Download", "Post-completion action failed: ${safeLogMessage(error)}") }
                return
            }
            withContext(NonCancellable) { rollbackPublication(job.jobId, publishedFileUri) }
            if (cancelledJobs.remove(job.jobId)) {
                markCancelled(job)
            } else if (job.jobId in pausedJobs) {
                markPaused(job)
            } else {
                val message = friendlyError(error)
                if (isMembersOnlyError(error.message.orEmpty())) {
                    job.originChannelId?.let { channelId ->
                        database.channelDao().updatePaidContent(channelId, PaidContentStatus.MembersOnly.name)
                    }
                }
                jobDao.markFailed(job.jobId, statusText(DownloadStatus.FAILED), message, System.currentTimeMillis())
                updateQueueStatus(job, DownloadStatus.FAILED)
                appLog.append(
                    if (isMembersOnlyError(error.message.orEmpty())) AppLogLevel.IMPORTANT else AppLogLevel.ERROR,
                    "Download",
                    "Failed job=${safeJobId(job.jobId)} source=${job.source} media=${job.mediaId}: ${safeLogMessage(error)}",
                )
                notifyTerminal(job, R.string.service_download_failed_title, message)
            }
            // Failed and paused jobs retain their partial files for an explicit resume.
        } finally {
            cancelledJobs.remove(job.jobId)
            pausedJobs.remove(job.jobId)
            currentJobId = null
        }
    }

    private fun ensureRuntime() {
        AndroidYtDlpRuntime.ensure(applicationContext, requireFfmpeg = true)
    }

    private fun buildRequest(
        job: DownloadJobEntity,
        directory: File,
        subtitleSelections: List<String> = job.toModel().subtitleSelections,
    ): YoutubeDLRequest {
        val height = job.resolution.filter(Char::isDigit).toIntOrNull()
        val model = job.toModel()
        val orderedAudioTracks = model.audioTracks.filter { it.formatKind == "combined" }.take(1) +
            model.audioTracks.filter { it.formatKind != "combined" }
        val combinedIds = orderedAudioTracks.filter { it.formatKind == "combined" }.map { it.formatId }
        val audioIds = orderedAudioTracks.filter { it.formatKind != "combined" }.map { it.formatId }
        val selector = if (combinedIds.isNotEmpty()) {
            (combinedIds.take(1) + audioIds).joinToString("+")
        } else if (audioIds.isNotEmpty()) {
            val audioSuffix = audioIds.joinToString("+")
            if (height == null) {
                "bv[ext=mp4]+$audioSuffix/bv+$audioSuffix/b+$audioSuffix"
            } else {
                "bv[height<=$height][ext=mp4]+$audioSuffix/bv[height<=$height]+$audioSuffix/b[height<=$height]+$audioSuffix"
            }
        } else if (height == null) {
            "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b"
        } else {
            "bv*[height<=$height][ext=mp4]+ba[ext=m4a]/bv*[height<=$height]+ba/b[height<=$height]"
        }
        val resolutionToken = job.resolution.replace(Regex("[^A-Za-z0-9_-]"), "_")
        val variantToken = mediaFileVariantToken(model.audioTracks.map { it.language }, subtitleSelections)
        val variantSuffix = variantToken.takeIf { it.isNotBlank() }?.let { " [$it]" }.orEmpty()
        val request = YoutubeDLRequest(job.url)
            .addOption("--no-playlist")
            .addOption("--no-mtime")
            .addOption("--newline")
            .addOption("--progress-template", "postprocess:YTH_POSTPROCESS")
            .addOption("--continue")
            .addOption("--part")
            .addOption("--socket-timeout", 15)
            .addOption("--retries", 1)
            .addOption("--fragment-retries", 1)
            .addOption("--abort-on-unavailable-fragments")
            .addOption("--trim-filenames", 180)
            .addOption("--merge-output-format", "mp4/mkv")
            .addOption("--embed-metadata")
            .addOption("--embed-chapters")
            .addOption("-f", selector)
            .addOption("-o", File(directory, "%(title).150B [%(id)s] [$resolutionToken]$variantSuffix.%(ext)s").absolutePath)
        if (orderedAudioTracks.isNotEmpty()) request.addOption("--audio-multistreams")
        val settings = JSONObject().put("audio", JSONArray(job.audioJson))
            .put("subtitles", JSONArray(subtitleSelections)).toString()
        val encoded = android.util.Base64.encodeToString(settings.toByteArray(Charsets.UTF_8), android.util.Base64.NO_WRAP or android.util.Base64.URL_SAFE)
        request.addOption("--no-write-subs").addOption("--no-write-auto-subs").addOption("--no-embed-subs")
            .addOption("--no-plugin-dirs")
            .addOption("--plugin-dirs", AndroidYtDlpRuntime.pluginDirectory(this).absolutePath)
            .addOption("--use-postprocessor", "HarvestTracks:when=after_move;settings=$encoded")
        return request
    }

    private suspend fun complete(
        job: DownloadJobEntity,
        fileUri: String,
        verified: VerifiedMedia,
        destinationLabel: String,
    ) {
        val timestamp = System.currentTimeMillis()
        val effectiveSubtitles = verified.selections
        val model = job.toModel()
        val audioLabels = verified.audio
        val subtitleLabels = verified.subtitles
        val missingSubtitles = verified.missingSubtitleSelections(model.subtitleSelections)
        val subtitleWarning = missingSubtitles.takeIf { it.isNotEmpty() }?.let {
            text(R.string.service_subtitles_omitted, it.joinToString())
        }
        val variantKey = mediaVariantKey(job.audioJson, JSONArray(effectiveSubtitles).toString())
        val replacedFileUri = database.archiveDao().get(
            job.source,
            job.mediaId,
            verified.resolution,
            variantKey,
        )?.fileUri?.takeIf { it != fileUri }
        database.withTransaction {
            database.downloadJobDao().markCompleted(job.jobId, fileUri, subtitleWarning ?: statusText(DownloadStatus.COMPLETED), timestamp)
            database.archiveDao().upsert(
                ArchiveEntity(
                    source = job.source,
                    mediaId = job.mediaId,
                    title = job.title,
                    channel = job.channel,
                    thumbnailUrl = job.thumbnailUrl,
                    contentType = model.contentType.name,
                    resolution = verified.resolution,
                    variantKey = variantKey,
                    downloadedAt = DATE_FORMATTER.format(Instant.ofEpochMilli(timestamp)),
                    downloadedAtEpochMs = timestamp,
                    fileExists = true,
                    fileUri = fileUri,
                    audioJson = JSONArray(audioLabels).toString(),
                    subtitlesJson = JSONArray(subtitleLabels).toString(),
                ),
            )
            if (job.fromQueue) database.queueDao().delete(job.source, job.mediaId)
        }
        replacedFileUri?.let { previousUri ->
            val cleanupError = withContext(Dispatchers.IO) {
                runCatching {
                    DownloadOutputPublisher(this@DownloadForegroundService).deletePublished(previousUri)
                }.exceptionOrNull()
            }
            cleanupError?.let { error ->
                appLog.append(
                    AppLogLevel.ERROR,
                    "Download",
                    "Could not remove replaced archive file: ${safeLogMessage(error)}",
                )
            }
        }
        appLog.append(
            AppLogLevel.IMPORTANT,
            "Download",
            "Completed job=${safeJobId(job.jobId)} source=${job.source} media=${job.mediaId} resolution=${verified.resolution}",
        )
        if (subtitleWarning != null) {
            appLog.append(AppLogLevel.IMPORTANT, "Download", "job=${safeJobId(job.jobId)} $subtitleWarning")
        }
        notifyTerminal(
            job,
            R.string.service_download_completed_title,
            listOfNotNull(text(R.string.service_saved_to, destinationLabel), subtitleWarning).joinToString("\n"),
        )
    }

    private suspend fun markCancelled(job: DownloadJobEntity) {
        database.downloadJobDao().markCancelled(
            job.jobId,
            statusText(DownloadStatus.CANCELLED),
            System.currentTimeMillis(),
        )
        updateQueueStatus(job, DownloadStatus.CANCELLED)
        jobStagingDirectory(job.jobId).deleteRecursively()
        appLog.append(AppLogLevel.INFO, "Download", "Cancelled job=${safeJobId(job.jobId)} media=${job.mediaId}")
        notifyTerminal(job, R.string.service_download_cancelled_title, job.title)
    }

    private suspend fun markPaused(job: DownloadJobEntity) {
        database.downloadJobDao().pause(job.jobId, System.currentTimeMillis())
        updateQueueStatus(job, DownloadStatus.PAUSED)
        notifications.notify(job.jobId.hashCode(), terminalNotification(job, statusText(DownloadStatus.PAUSED), job.title))
    }

    private suspend fun pauseJob(jobId: String) {
        val active = synchronized(phaseLock) {
            if (currentJobId == jobId) {
                if (!currentPhase.canPause) return
                pausedJobs += jobId
                true
            } else false
        }
        if (active) {
            withContext(Dispatchers.IO) { runCatching { YoutubeDL.destroyProcessById(jobId) } }
        } else {
            // The conditional update cannot pause a job claimed by the processor meanwhile.
            val dao = database.downloadJobDao()
            if (dao.pauseQueued(jobId, System.currentTimeMillis()) == 1) {
                dao.get(jobId)?.let { updateQueueStatus(it, DownloadStatus.PAUSED) }
            } else if (currentJobId == jobId) pauseJob(jobId)
        }
    }

    private suspend fun awaitNetwork(jobId: String) {
        val connectivity = getSystemService(ConnectivityManager::class.java)
        repeat(DownloadRetryPolicy.NETWORK_WAIT_SECONDS) { second ->
            if (jobId in pausedJobs) throw DownloadPausedException()
            if (jobId in cancelledJobs) throw DownloadCancelledException()
            delay(1_000)
            val capabilities = connectivity.getNetworkCapabilities(connectivity.activeNetwork)
            if (second >= 2 && capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true &&
                capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) return
        }
        throw java.io.IOException("Network is unreachable")
    }

    private suspend fun cancelJob(jobId: String) {
        cancelledJobs += jobId
        if (currentJobId == jobId) {
            withContext(Dispatchers.IO) { runCatching { YoutubeDL.destroyProcessById(jobId) } }
        } else {
            withContext(Dispatchers.IO) {
                val dao = database.downloadJobDao()
                if (dao.cancelQueued(jobId, System.currentTimeMillis()) == 1) {
                    dao.get(jobId)?.let { markCancelled(it) }
                    cancelledJobs.remove(jobId)
                } else {
                    val job = dao.get(jobId)
                    if (job == null || job.status in listOf("COMPLETED", "FAILED", "CANCELLED")) cancelledJobs.remove(jobId)
                }
            }
        }
    }

    private fun jobStagingDirectory(jobId: String): File {
        val root = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: filesDir
        return File(root, "staging/$jobId")
    }

    private fun cleanProgressLine(line: String, progress: Int): String {
        val cleaned = line.replace(Regex("\\s+"), " ").trim()
        return cleaned.takeIf { it.isNotBlank() }?.take(180)
            ?: text(R.string.download_progress, statusText(DownloadStatus.DOWNLOADING), progress)
    }

    private fun friendlyError(error: Exception): String {
        val raw = error.message.orEmpty().replace(Regex("\\s+"), " ").trim()
        return when {
            DownloadRetryPolicy.isNetworkError(raw) -> text(R.string.download_network_error)
            DownloadRetryPolicy.isStorageFullError(raw) -> text(R.string.service_error_storage_full)
            isMembersOnlyError(raw) ->
                text(R.string.service_error_members_only)
            raw.contains("Private video", ignoreCase = true) -> text(R.string.service_error_private_video)
            DownloadRetryPolicy.isUnavailableMediaError(raw) -> text(R.string.service_error_video_unavailable)
            raw.isNotBlank() -> raw.take(260)
            else -> text(R.string.service_error_unknown_engine)
        }
    }

    private fun isMembersOnlyError(message: String): Boolean =
        message.contains("members-only", ignoreCase = true) ||
            message.contains("Join this channel", ignoreCase = true) ||
            message.contains("subscriber_only", ignoreCase = true)

    private fun mediaVariantKey(audioJson: String, subtitlesJson: String): String {
        if (audioJson == "[]" && subtitlesJson == "[]") return "default"
        val bytes = MessageDigest.getInstance("SHA-256").digest("$audioJson|$subtitlesJson".toByteArray())
        return bytes.take(8).joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    private fun mediaFileVariantToken(audioLanguages: List<String>, subtitles: List<String>): String {
        val parts = buildList {
            if (audioLanguages.isNotEmpty()) {
                add("a-${audioLanguages.map(::safeLanguageToken).distinct().joinToString("+")}")
            }
            if (subtitles.isNotEmpty()) {
                add("s-${subtitles.map { safeLanguageToken(it.substringAfter(':', it)) }.distinct().joinToString("+")}")
            }
        }
        return parts.joinToString("_").take(54)
    }

    private fun safeLanguageToken(value: String): String =
        value.lowercase().replace(Regex("[^a-z0-9_-]"), "_").take(12).ifBlank { "und" }

    private fun failedSubtitleLanguages(message: String): Set<String> =
        SUBTITLE_ERROR.findAll(message).map { it.groupValues[1].trim().lowercase() }.toSet()

    private fun waitingNotification(): Notification = NotificationCompat.Builder(this, CHANNEL_ID)
        .setSmallIcon(R.drawable.ic_stat_download)
        .setContentTitle("YouTube Harvester")
        .setContentText(text(R.string.service_preparing_queue))
        .setOngoing(true)
        .setContentIntent(openAppPendingIntent())
        .build()

    private fun progressNotification(
        job: DownloadJobEntity,
        progress: Int,
        message: String,
        etaSeconds: Long?,
        indeterminate: Boolean = false,
        canPause: Boolean = true,
    ): Notification {
        val text = if (etaSeconds != null) {
            "$message · ${text(R.string.service_eta_remaining, formatEta(etaSeconds))}"
        } else {
            message
        }
        val cancelIntent = Intent(this, DownloadForegroundService::class.java)
            .setAction(ACTION_CANCEL)
            .putExtra(EXTRA_JOB_ID, job.jobId)
        val cancelPendingIntent = PendingIntent.getForegroundService(
            this,
            job.jobId.hashCode(),
            cancelIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_download)
            .setContentTitle(job.title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setProgress(100, progress, indeterminate)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(openAppPendingIntent())
            .addAction(R.drawable.ic_stat_download, text(R.string.service_cancel_action), cancelPendingIntent)
        if (canPause) builder.addAction(R.drawable.ic_stat_download, text(R.string.download_pause), jobActionIntent(job.jobId, ACTION_PAUSE))
        return builder.build()
    }

    private fun terminalNotification(job: DownloadJobEntity, title: String, message: String): Notification =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_download)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(NotificationCompat.BigTextStyle().bigText("${job.title}\n$message"))
            .setAutoCancel(true)
            .setContentIntent(openAppPendingIntent())
            .apply {
                if (title == statusText(DownloadStatus.PAUSED) || title == text(R.string.service_download_failed_title)) {
                    addAction(R.drawable.ic_stat_download, text(R.string.download_resume), jobActionIntent(job.jobId, ACTION_RESUME))
                }
            }
            .build()

    private fun jobActionIntent(jobId: String, action: String): PendingIntent = PendingIntent.getForegroundService(
        this, jobId.hashCode(),
        Intent(this, DownloadForegroundService::class.java).setAction(action).putExtra(EXTRA_JOB_ID, jobId),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

    private fun openAppPendingIntent(): PendingIntent = PendingIntent.getActivity(
        this,
        0,
        Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

    private fun createNotificationChannel() {
        notifications.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, text(R.string.service_download_channel_name), NotificationManager.IMPORTANCE_LOW).apply {
                description = text(R.string.service_download_channel_description)
            },
        )
    }

    private fun formatEta(seconds: Long): String = DateUtils.formatElapsedTime(seconds)

    private fun statusText(status: DownloadStatus): String = text(status.stringResource())

    private fun text(resourceId: Int, vararg arguments: Any): String {
        val localizedContext: Context = LocaleController.wrap(this)
        return localizedContext.resources.getString(resourceId, *arguments)
    }

    private suspend fun notifyTerminal(job: DownloadJobEntity, titleResource: Int, message: String) {
        val settings = try {
            settingsStore.settings.first()
        } catch (error: Exception) {
            appLog.append(AppLogLevel.ERROR, "Notifications", "Could not read settings: ${safeLogMessage(error)}")
            return
        }
        val title = text(titleResource)
        if (settings.systemNotifications) {
            runCatching {
                notifications.notify(job.jobId.hashCode(), terminalNotification(job, title, message))
            }.exceptionOrNull()?.let { error ->
                appLog.append(
                    AppLogLevel.ERROR,
                    "Notifications",
                    "Could not show terminal notification: ${safeLogMessage(error)}",
                )
            }
        }
        if (settings.telegramEnabled) {
            val result = TelegramNotifier.send(settings, "$title\n${job.title}\n$message")
            appLog.append(
                if (result.isSuccess) AppLogLevel.INFO else AppLogLevel.ERROR,
                "Telegram",
                if (result.isSuccess) {
                    "Download notification delivered job=${safeJobId(job.jobId)}"
                } else {
                    "Download notification failed job=${safeJobId(job.jobId)}: ${safeLogMessage(result.exceptionOrNull())}"
                },
            )
        }
    }

    private fun safeJobId(jobId: String): String = jobId.take(12)

    private fun safeLogMessage(error: Throwable?): String = error?.message
        .orEmpty()
        .replace(Regex("\\s+"), " ")
        .trim()
        .take(500)
        .ifBlank { error?.javaClass?.simpleName ?: "Unknown error" }

    companion object {
        const val ACTION_RUN = "com.liberivixer.youtubeharvester.action.RUN_DOWNLOADS"
        const val ACTION_CANCEL = "com.liberivixer.youtubeharvester.action.CANCEL_DOWNLOAD"
        const val ACTION_PAUSE = "com.liberivixer.youtubeharvester.action.PAUSE_DOWNLOAD"
        const val ACTION_RESUME = "com.liberivixer.youtubeharvester.action.RESUME_DOWNLOAD"
        const val EXTRA_JOB_ID = "download_job_id"
        private const val CHANNEL_ID = "video_downloads"
        private const val NOTIFICATION_ID = 41
        private val SUBTITLE_ERROR = Regex(
            "Unable to download video subtitles for ['\\\"]([^'\\\"]+)['\\\"]",
            RegexOption.IGNORE_CASE,
        )
        private val DATE_FORMATTER = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm").withZone(ZoneId.systemDefault())
    }
}

private class DownloadCancelledException : Exception("Download cancelled")
private class DownloadPausedException : Exception("Download paused")
