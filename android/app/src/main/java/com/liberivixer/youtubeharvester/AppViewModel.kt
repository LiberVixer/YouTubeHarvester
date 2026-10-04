package com.liberivixer.youtubeharvester

import android.app.Application
import android.content.Intent
import android.net.Uri
import android.os.Environment
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.core.net.toUri
import com.liberivixer.youtubeharvester.data.AndroidAppRepository
import com.liberivixer.youtubeharvester.data.DataTransferStore
import com.liberivixer.youtubeharvester.data.DataTransferBusyException
import com.liberivixer.youtubeharvester.data.DataTransferNotEmptyException
import com.liberivixer.youtubeharvester.data.DataTransferCredentialsException
import com.liberivixer.youtubeharvester.data.DataTransferArchiveException
import com.liberivixer.youtubeharvester.data.DataTransferPendingException
import com.liberivixer.youtubeharvester.data.TransferEncryption
import com.liberivixer.youtubeharvester.diagnostics.AndroidDiagnosticsProbe
import com.liberivixer.youtubeharvester.download.DownloadServiceController
import com.liberivixer.youtubeharvester.download.archiveUriExists
import com.liberivixer.youtubeharvester.logging.AppLogLevel
import com.liberivixer.youtubeharvester.logging.AppLogStore
import com.liberivixer.youtubeharvester.media.EngineResult
import com.liberivixer.youtubeharvester.media.ChannelUrlParser
import com.liberivixer.youtubeharvester.media.RutubeChannelResolver
import com.liberivixer.youtubeharvester.media.ChannelCheckRunner
import com.liberivixer.youtubeharvester.media.MediaEngine
import com.liberivixer.youtubeharvester.media.MediaUrlParser
import com.liberivixer.youtubeharvester.media.PublicMetadataMediaEngine
import com.liberivixer.youtubeharvester.media.YtDlpMetadataDecoder
import com.liberivixer.youtubeharvester.media.YtDlpMetadataInspector
import com.liberivixer.youtubeharvester.model.AudioTrackOption
import com.liberivixer.youtubeharvester.model.AppSettings
import com.liberivixer.youtubeharvester.model.AppLanguage
import com.liberivixer.youtubeharvester.model.AppUiState
import com.liberivixer.youtubeharvester.model.ChannelItem
import com.liberivixer.youtubeharvester.model.ContentType
import com.liberivixer.youtubeharvester.model.MediaSource
import com.liberivixer.youtubeharvester.model.QueueItem
import com.liberivixer.youtubeharvester.model.ScheduleItem
import com.liberivixer.youtubeharvester.notifications.TelegramNotifier
import com.liberivixer.youtubeharvester.scheduler.DailyCheckScheduler
import com.liberivixer.youtubeharvester.ui.LocaleController
import coil3.SingletonImageLoader
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID

class AppViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = AndroidAppRepository(application)
    private val mediaEngine: MediaEngine = PublicMetadataMediaEngine(application)
    private val metadataInspector = YtDlpMetadataInspector(application)
    private val channelCheckRunner = ChannelCheckRunner(application, repository)
    private val appLog = AppLogStore(application)
    private val diagnosticsProbe = AndroidDiagnosticsProbe(application)
    private val harvestStore = com.liberivixer.youtubeharvester.download.HarvestSessionStore(application)
    private var harvestSession: com.liberivixer.youtubeharvester.download.HarvestSession? = null
    private var previewJob: Job? = null
    private var metadataGeneration = 0L
    private var downloadOptionsJob: Job? = null
    private var channelScanJob: Job? = null
    private var settingsDraft = false
    private val pendingRutubeChannels = mutableSetOf<String>()
    private val _state = MutableStateFlow(
        AppUiState(
            queue = emptyList(),
            archive = emptyList(),
            statusMessage = localizedText(R.string.ready),
        ),
    )
    val state: StateFlow<AppUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            appLog.append(AppLogLevel.INFO, "Application", "Started ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
            try {
                repository.initialize()
                com.liberivixer.youtubeharvester.download.HarvestCoordinator.ensure(application)
                repository.getSchedules().forEach { DailyCheckScheduler.ensure(application, it) }
                appLog.append(AppLogLevel.INFO, "Application", "Local data initialized")
            } catch (error: Exception) {
                appLog.append(AppLogLevel.ERROR, "Application", "Local data initialization failed: ${error.safeLogMessage()}")
                _state.update { it.copy(statusMessage = localizedText(R.string.data_migration_error)) }
            }
            if (runCatching { repository.hasPendingDownloads() }.getOrDefault(false)) {
                runCatching { DownloadServiceController.start(application) }.onFailure { error ->
                    appLog.append(AppLogLevel.ERROR, "Download", "Could not resume downloads: ${error.safeLogMessage()}")
                    _state.update { it.copy(statusMessage = localizedText(R.string.download_start_error)) }
                }
            }
            launch {
                repository.settings.collect { settings ->
                    val localizedSettings = if (android.os.Build.VERSION.SDK_INT >= 33) {
                        settings.copy(language = com.liberivixer.youtubeharvester.ui.LocaleController.currentTag(application))
                    } else settings
                    _state.update { it.copy(settings = if (settingsDraft) it.settings else localizedSettings, settingsLoaded = true) }
                    runCatching { appLog.prune(settings.logRetentionDays) }
                }
            }
            launch {
                repository.lastCheck.collect { report ->
                    _state.update { it.copy(lastCheck = report) }
                }
            }
            launch {
                repository.queue.collect { queue ->
                    _state.update { it.copy(queue = queue) }
                }
            }
            launch {
                repository.archive.collect { archive ->
                    _state.update { it.copy(archive = archive) }
                }
            }
            launch {
                repository.downloadJobs.collect { jobs ->
                    _state.update { it.copy(downloadJobs = jobs) }
                }
            }
            launch {
                repository.channels.collect { channels ->
                    _state.update { it.copy(channels = channels) }
                }
            }
            launch {
                repository.schedules.collect { schedules ->
                    _state.update { it.copy(schedule = schedules) }
                }
            }
            launch {
                harvestStore.sessions.catch { error ->
                    if (error is CancellationException) throw error
                    appLog.append(AppLogLevel.ERROR, "Harvest", "Session observation failed: ${error.javaClass.simpleName}")
                    _state.update { it.copy(statusMessage = localizedText(R.string.channel_check_failed)) }
                }.collect { session ->
                    harvestSession = session
                    applyHarvestProgress(com.liberivixer.youtubeharvester.download.HarvestCoordinator.progress.value)
                }
            }
            launch {
                com.liberivixer.youtubeharvester.download.HarvestCoordinator.progress.collect(::applyHarvestProgress)
            }
        }
    }

    fun inspectUrl(rawUrl: String) {
        val request = rawUrl.trim()
        if (_state.value.isDownloadOptionsLoading && _state.value.previewRequestUrl == request) return
        val generation = ++metadataGeneration
        previewJob?.cancel()
        downloadOptionsJob?.cancel()
        if (request.isBlank()) {
            _state.update {
                it.copy(
                    previewRequestUrl = "",
                    mediaPreview = null,
                    isPreviewLoading = false,
                    previewError = null,
                    downloadMediaOptions = null,
                    isDownloadOptionsLoading = false,
                    downloadOptionsError = null,
                )
            }
            return
        }

        _state.update {
            it.copy(
                previewRequestUrl = request,
                mediaPreview = null,
                isPreviewLoading = true,
                previewError = null,
                downloadMediaOptions = null,
                isDownloadOptionsLoading = false,
                downloadOptionsError = null,
            )
        }
        previewJob = viewModelScope.launch {
            delay(PREVIEW_DEBOUNCE_MS)
            val parsed = MediaUrlParser.parse(request)
            if (parsed == null) {
                _state.update {
                    it.copy(
                        isPreviewLoading = false,
                        previewError = localizedText(R.string.invalid_media_link),
                    )
                }
                return@launch
            }
            var resolvedOptions: com.liberivixer.youtubeharvester.model.DownloadMediaOptions? = null
            val result = if (parsed.source == MediaSource.Vk) {
                when (val inspected = metadataInspector.inspect(parsed)) {
                    is EngineResult.Success -> {
                        resolvedOptions = inspected.value
                        EngineResult.Success(inspected.value.preview)
                    }
                    is EngineResult.Failure -> inspected
                }
            } else {
                mediaEngine.inspect(parsed)
            }
            if (generation != metadataGeneration || _state.value.previewRequestUrl != request) return@launch
            when (result) {
                is EngineResult.Success -> _state.update {
                    it.copy(
                        mediaPreview = result.value,
                        isPreviewLoading = false,
                        previewError = null,
                        downloadMediaOptions = resolvedOptions,
                        statusMessage = localizedText(R.string.preview_loaded),
                    )
                }
                is EngineResult.Failure -> _state.update {
                    it.copy(
                        mediaPreview = null,
                        isPreviewLoading = false,
                        previewError = result.message,
                        statusMessage = result.message,
                    )
                }
            }
        }
    }

    fun addToQueue(url: String): Boolean {
        val parsed = MediaUrlParser.parse(url)
        val preview = _state.value.mediaPreview?.takeIf {
            parsed != null && it.source == parsed.source && it.mediaId == parsed.mediaId
        }
        val item = repository.queueItemFromUrl(url, _state.value.settings.maxResolution, preview)
        if (item == null) {
            _state.update { it.copy(statusMessage = localizedText(R.string.invalid_media_link)) }
            return false
        }
        if (_state.value.queue.any { it.source == item.source && it.id == item.id }) {
            _state.update { it.copy(statusMessage = localizedText(R.string.already_in_queue)) }
            return false
        }
        val queue = _state.value.queue + item
        metadataGeneration++
        previewJob?.cancel()
        _state.update {
            it.copy(
                queue = queue,
                statusMessage = localizedText(R.string.queue_item_added),
                previewRequestUrl = "",
                mediaPreview = null,
                isPreviewLoading = false,
                previewError = null,
            )
        }
        persist(localizedText(R.string.queue_save_error)) {
            repository.upsertQueueItem(item, queue.lastIndex)
        }
        return true
    }

    fun prepareDownloadOptions(rawUrl: String): Boolean {
        val parsed = MediaUrlParser.parse(rawUrl)
        if (parsed == null) {
            _state.update { it.copy(statusMessage = localizedText(R.string.invalid_media_link)) }
            return false
        }
        val cached = _state.value.downloadMediaOptions?.takeIf {
            it.preview.source == parsed.source && it.preview.mediaId == parsed.mediaId
        }
        if (cached != null) {
            _state.update { it.copy(statusMessage = localizedText(R.string.download_options_loaded)) }
            return true
        }
        downloadOptionsJob?.cancel()
        previewJob?.cancel()
        val generation = ++metadataGeneration
        _state.update {
            it.copy(
                previewRequestUrl = rawUrl.trim(),
                isPreviewLoading = false,
                isDownloadOptionsLoading = true,
                downloadMediaOptions = null,
                downloadOptionsError = null,
                statusMessage = localizedText(R.string.loading_tracks),
            )
        }
        downloadOptionsJob = viewModelScope.launch {
            val result = metadataInspector.inspect(parsed)
            if (generation != metadataGeneration || _state.value.previewRequestUrl != rawUrl.trim()) return@launch
            when (result) {
                is EngineResult.Success -> _state.update {
                    it.copy(
                        isDownloadOptionsLoading = false,
                        downloadMediaOptions = result.value,
                        mediaPreview = result.value.preview,
                        previewError = null,
                        statusMessage = localizedText(R.string.download_options_loaded),
                    )
                }
                is EngineResult.Failure -> _state.update {
                    it.copy(
                        isDownloadOptionsLoading = false,
                        downloadOptionsError = result.message,
                        statusMessage = localizedText(R.string.tracks_fallback_status),
                    )
                }
            }
        }
        return true
    }

    fun clearDownloadOptions() {
        metadataGeneration++
        downloadOptionsJob?.cancel()
        _state.update {
            it.copy(
                downloadMediaOptions = null,
                isDownloadOptionsLoading = false,
                downloadOptionsError = null,
            )
        }
    }

    fun downloadWithOptions(
        url: String,
        resolution: String,
        audioOptions: List<AudioTrackOption>,
        subtitleSelections: List<String>,
    ): Boolean {
        val item = queueItemWithOptions(url, resolution, audioOptions, subtitleSelections) ?: return false
        resetPreviewAfterAction(localizedText(R.string.download_started))
        viewModelScope.launch {
            try {
                repository.enqueueDownload(item, fromQueue = false)
                DownloadServiceController.start(getApplication())
            } catch (_: Exception) {
                _state.update { it.copy(statusMessage = localizedText(R.string.download_start_error)) }
            }
        }
        return true
    }

    fun downloadQuickLink(url: String): Boolean = downloadWithOptions(
        url, _state.value.settings.maxResolution, emptyList(), emptyList(),
    )

    fun downloadClipboardLink(text: String): Boolean {
        if (!_state.value.settingsLoaded) return false
        val parsed = MediaUrlParser.extract(text)
        if (parsed == null) {
            reportStatus(localizedText(R.string.invalid_media_link))
            return false
        }
        return downloadQuickLink(parsed.normalizedUrl)
    }

    fun addToQueueWithOptions(
        url: String,
        resolution: String,
        audioOptions: List<AudioTrackOption>,
        subtitleSelections: List<String>,
    ): Boolean {
        val item = queueItemWithOptions(url, resolution, audioOptions, subtitleSelections) ?: return false
        if (_state.value.queue.any { it.source == item.source && it.id == item.id }) {
            _state.update { it.copy(statusMessage = localizedText(R.string.already_in_queue)) }
            return false
        }
        val queue = _state.value.queue + item
        resetPreviewAfterAction(localizedText(R.string.queue_item_added))
        _state.update { it.copy(queue = queue) }
        persist(localizedText(R.string.queue_save_error)) {
            repository.upsertQueueItem(item, queue.lastIndex)
        }
        return true
    }

    fun startSelectedDownloads() {
        if (_state.value.queue.none { it.selected }) {
            _state.update { it.copy(statusMessage = localizedText(R.string.select_downloads)) }
            return
        }
        viewModelScope.launch {
            try {
                val added = repository.enqueueSelectedDownloads()
                DownloadServiceController.start(getApplication())
                _state.update {
                    it.copy(
                        statusMessage = if (added > 0) {
                            localizedText(R.string.downloads_started, added)
                        } else {
                            localizedText(R.string.downloads_already_running)
                        },
                    )
                }
            } catch (_: Exception) {
                _state.update { it.copy(statusMessage = localizedText(R.string.queue_start_error)) }
            }
        }
    }

    fun cancelDownload(jobId: String) {
        runCatching { DownloadServiceController.cancel(getApplication(), jobId) }
            .onSuccess { reportStatus(localizedText(R.string.download_cancelling)) }
            .onFailure { reportStatus(localizedText(R.string.download_start_error)) }
    }

    fun pauseDownload(jobId: String) {
        runCatching { DownloadServiceController.pause(getApplication(), jobId) }
            .onFailure { reportStatus(localizedText(R.string.download_start_error)) }
    }

    fun resumeDownload(jobId: String) {
        runCatching { DownloadServiceController.resume(getApplication(), jobId) }
            .onFailure { reportStatus(localizedText(R.string.download_start_error)) }
    }

    fun startQueueItem(item: QueueItem) {
        viewModelScope.launch {
            try {
                repository.enqueueDownload(item, fromQueue = true)
                DownloadServiceController.start(getApplication())
            } catch (_: Exception) { reportStatus(localizedText(R.string.download_start_error)) }
        }
    }

    fun openDownloadFolder(fileUri: String? = null) {
        viewModelScope.launch {
            val context = getApplication<Application>()
            val uri = withContext(Dispatchers.IO) {
                com.liberivixer.youtubeharvester.download.DownloadFolderNavigator.directoryUri(
                    context, _state.value.settings.downloadDirectoryUri, fileUri,
                )
            }
            val result = com.liberivixer.youtubeharvester.download.DownloadFolderNavigator.open(context, uri)
            if (result != com.liberivixer.youtubeharvester.download.FolderOpenResult.DIRECT) {
                reportStatus(localizedText(if (result == com.liberivixer.youtubeharvester.download.FolderOpenResult.FALLBACK)
                    R.string.folder_open_fallback else R.string.downloads_open_error))
            }
        }
    }

    fun toggleQueueItem(source: MediaSource, id: String) {
        val queue = _state.value.queue.map { item ->
            if (item.source == source && item.id == id) item.copy(selected = !item.selected) else item
        }
        _state.update { it.copy(queue = queue) }
        val selected = queue.firstOrNull { it.source == source && it.id == id }?.selected ?: return
        persist(localizedText(R.string.queue_selection_save_error)) {
            repository.setQueueSelected(source, id, selected)
        }
    }

    fun removeSelectedQueueItems() {
        val active = _state.value.downloadJobs.filter { it.status.retainsFiles }
            .mapTo(mutableSetOf()) { it.source to it.mediaId }
        val removable = _state.value.queue.filter { it.selected && (it.source to it.id) !in active }
        if (removable.isEmpty()) {
            _state.update { it.copy(statusMessage = localizedText(R.string.queue_active_items_kept)) }
            return
        }
        val keys = removable.mapTo(mutableSetOf()) { it.source to it.id }
        val queue = _state.value.queue.filterNot { (it.source to it.id) in keys }
        _state.update { it.copy(queue = queue, statusMessage = localizedText(R.string.queue_items_removed)) }
        persist(localizedText(R.string.queue_remove_error)) {
            repository.removeQueueItems(removable)
        }
    }

    fun removeQueueItem(item: QueueItem) {
        if (_state.value.downloadJobs.any { it.status.retainsFiles && it.source == item.source && it.mediaId == item.id }) {
            _state.update { it.copy(statusMessage = localizedText(R.string.queue_active_items_kept)) }
            return
        }
        _state.update { state ->
            state.copy(
                queue = state.queue.filterNot { it.source == item.source && it.id == item.id },
                statusMessage = localizedText(R.string.queue_items_removed),
            )
        }
        persist(localizedText(R.string.queue_remove_error)) {
            repository.removeQueueItems(listOf(item))
        }
    }

    fun moveQueueItem(item: QueueItem, offset: Int) {
        val queue = _state.value.queue.toMutableList()
        val currentIndex = queue.indexOfFirst { it.source == item.source && it.id == item.id }
        val targetIndex = currentIndex + offset
        if (currentIndex < 0 || targetIndex !in queue.indices) return
        queue.add(targetIndex, queue.removeAt(currentIndex))
        _state.update { it.copy(queue = queue) }
        persist(localizedText(R.string.queue_save_error)) {
            repository.moveQueueItem(item.source, item.id, offset)
        }
    }

    fun setSettings(settings: AppSettings) {
        settingsDraft = true
        _state.update { it.copy(settings = settings) }
    }

    fun exportData(uri: Uri, password: CharArray) = transferData(password) {
        val context = getApplication<Application>()
        val file = DataTransferStore(context).export(password)
        try {
            requireNotNull(context.contentResolver.openOutputStream(uri, "wt")).use { it.write(file) }
            // Read back the provider's bytes; a returned stream alone does not prove a usable backup.
            val readBack = requireNotNull(context.contentResolver.openInputStream(uri)).use(TransferEncryption::readBounded)
            try { check(file.contentEquals(readBack)) } finally { readBack.fill(0) }
            localizedText(R.string.transfer_exported)
        } finally { file.fill(0) }
    }

    fun importData(uri: Uri, password: CharArray) = transferData(password) {
        val context = getApplication<Application>()
        val file = requireNotNull(context.contentResolver.openInputStream(uri)).use(TransferEncryption::readBounded)
        try { DataTransferStore(context).import(file, password) } finally { file.fill(0) }
        settingsDraft = false
        localizedText(R.string.transfer_imported)
    }

    private fun transferData(password: CharArray, action: suspend () -> String) {
        if (_state.value.isDataTransferBusy) { password.fill('\u0000'); return }
        _state.update { it.copy(isDataTransferBusy = true, dataTransferMessage = "") }
        viewModelScope.launch {
            try {
                if (_state.value.isScanning) throw DataTransferBusyException()
                val message = withContext(Dispatchers.IO) { action() }
                _state.update { it.copy(statusMessage = message, dataTransferMessage = message) }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                val resource = when (error) {
                    is DataTransferNotEmptyException -> R.string.transfer_not_empty
                    is DataTransferBusyException -> R.string.transfer_stop_downloads
                    is DataTransferCredentialsException -> R.string.transfer_credentials_error
                    is DataTransferArchiveException -> R.string.transfer_archive_error
                    is DataTransferPendingException -> R.string.transfer_pending
                    else -> R.string.transfer_failed
                }
                // Never include provider paths, payloads, passwords or exception messages in logs.
                appLog.append(AppLogLevel.ERROR, "DataTransfer", "Transfer failed: ${error.javaClass.simpleName}")
                val message = localizedText(resource)
                _state.update { it.copy(statusMessage = message, dataTransferMessage = message) }
            } finally {
                password.fill('\u0000')
                _state.update { it.copy(isDataTransferBusy = false) }
            }
        }
    }

    fun setTheme(mode: com.liberivixer.youtubeharvester.model.AppThemeMode) {
        val settings = _state.value.settings.copy(themeMode = mode)
        _state.update { it.copy(settings = settings) }
        persist(localizedText(R.string.settings_save_error)) {
            repository.saveSettings(settings)
        }
    }

    fun saveSettings() {
        _state.update { it.copy(statusMessage = localizedText(R.string.settings_saved)) }
        persist(localizedText(R.string.settings_save_error)) {
            val settings = _state.value.settings
            repository.saveSettings(settings)
            if (_state.value.settings == settings) settingsDraft = false
            runCatching { appLog.prune(settings.logRetentionDays) }
            appLog.append(AppLogLevel.INFO, "Settings", "Settings saved")
        }
    }

    fun saveTelegramSettings(botToken: String, channelId: String, proxyUrl: String) {
        if (!TelegramNotifier.isConfigurationValid(botToken, channelId, proxyUrl)) {
            _state.update { it.copy(statusMessage = localizedText(R.string.telegram_credentials_invalid)) }
            return
        }
        val settings = _state.value.settings.copy(
            telegramEnabled = botToken.isNotBlank() && channelId.isNotBlank(),
            telegramBotToken = botToken.trim(),
            telegramChannelId = channelId.trim(),
            telegramProxyUrl = proxyUrl.trim(),
            telegramCredentialError = false,
        )
        _state.update { it.copy(settings = settings, statusMessage = localizedText(R.string.telegram_settings_saved)) }
        persist(localizedText(R.string.settings_save_error)) {
            repository.saveSettings(settings, replaceSecrets = true)
            appLog.append(AppLogLevel.INFO, "Telegram", "Connection settings saved")
        }
    }

    fun testTelegramSettings(botToken: String, channelId: String, proxyUrl: String) {
        if (botToken.isBlank() || channelId.isBlank()) {
            _state.update { it.copy(statusMessage = localizedText(R.string.telegram_credentials_required)) }
            return
        }
        val candidate = _state.value.settings.copy(
            telegramBotToken = botToken.trim(),
            telegramChannelId = channelId.trim(),
            telegramProxyUrl = proxyUrl.trim(),
            telegramCredentialError = false,
        )
        viewModelScope.launch {
            _state.update { it.copy(statusMessage = localizedText(R.string.telegram_testing)) }
            val result = TelegramNotifier.send(candidate, localizedText(R.string.telegram_test_message))
            appLog.append(
                if (result.isSuccess) AppLogLevel.IMPORTANT else AppLogLevel.ERROR,
                "Telegram",
                if (result.isSuccess) "Test message delivered" else "Test message failed: ${result.exceptionOrNull().safeLogMessage()}",
            )
            _state.update {
                it.copy(
                    statusMessage = localizedText(
                        if (result.isSuccess) R.string.telegram_test_success else R.string.telegram_test_failed,
                    ),
                )
            }
        }
    }

    fun clearThumbnailCache() {
        viewModelScope.launch {
            withContext(Dispatchers.IO) {
                val imageLoader = SingletonImageLoader.get(getApplication())
                imageLoader.memoryCache?.clear()
                imageLoader.diskCache?.clear()
            }
            _state.update { it.copy(statusMessage = localizedText(R.string.thumbnail_cache_cleared)) }
            appLog.append(AppLogLevel.INFO, "Cache", "Thumbnail cache cleared")
        }
    }

    fun loadLogs() {
        viewModelScope.launch {
            _state.update { it.copy(isLogLoading = true, logLoadError = null) }
            try {
                appLog.prune(_state.value.settings.logRetentionDays)
                val text = appLog.readLatest()
                _state.update { it.copy(logText = text, isLogLoading = false) }
            } catch (error: Exception) {
                _state.update {
                    it.copy(
                        isLogLoading = false,
                        logLoadError = localizedText(R.string.log_load_error),
                    )
                }
            }
        }
    }

    fun clearLogs() {
        viewModelScope.launch {
            try {
                appLog.clear()
                _state.update {
                    it.copy(
                        logText = "",
                        logLoadError = null,
                        statusMessage = localizedText(R.string.logs_cleared),
                    )
                }
            } catch (_: Exception) {
                _state.update { it.copy(logLoadError = localizedText(R.string.log_load_error)) }
            }
        }
    }

    fun refreshDiagnostics() {
        if (_state.value.isDiagnosticsLoading) return
        viewModelScope.launch {
            _state.update { it.copy(isDiagnosticsLoading = true, diagnosticsError = null) }
            try {
                val snapshot = diagnosticsProbe.run(_state.value.settings)
                _state.update {
                    it.copy(
                        diagnostics = snapshot,
                        isDiagnosticsLoading = false,
                        diagnosticsError = null,
                    )
                }
                appLog.append(
                    if (snapshot.runtimeReady && snapshot.downloadDestinationAccessible) {
                        AppLogLevel.INFO
                    } else {
                        AppLogLevel.IMPORTANT
                    },
                    "Diagnostics",
                    "Completed runtime=${snapshot.runtimeReady} network=${snapshot.networkValidated} notifications=${snapshot.notificationsAllowed} destination=${snapshot.downloadDestinationAccessible}",
                )
            } catch (error: Exception) {
                appLog.append(AppLogLevel.ERROR, "Diagnostics", "Failed: ${error.safeLogMessage()}")
                _state.update {
                    it.copy(
                        isDiagnosticsLoading = false,
                        diagnosticsError = localizedText(R.string.diagnostics_run_error),
                    )
                }
            }
        }
    }

    fun openQuickDownloadScreen() {
        _state.update { it.copy(openOverviewRequestId = it.openOverviewRequestId + 1) }
    }

    fun setLogRetentionDays(days: Int) {
        val normalizedDays = days.coerceIn(1, 30)
        val settings = _state.value.settings.copy(logRetentionDays = normalizedDays)
        _state.update {
            it.copy(
                settings = settings,
                statusMessage = localizedText(R.string.logs_retention_saved),
            )
        }
        persist(localizedText(R.string.settings_save_error)) {
            repository.saveSettings(settings)
            runCatching { appLog.prune(normalizedDays) }
            loadLogs()
        }
    }

    fun setLanguage(language: AppLanguage) {
        val settings = _state.value.settings.copy(language = language.tag)
        viewModelScope.launch {
            try {
                repository.saveSettings(settings)
                com.liberivixer.youtubeharvester.ui.LocaleController.setLanguage(getApplication(), language.tag)
                _state.update { it.copy(settings = settings) }
            } catch (error: Exception) {
                appLog.append(AppLogLevel.ERROR, "Persistence", error.safeLogMessage())
                _state.update { it.copy(statusMessage = localizedText(R.string.language_save_error)) }
            }
        }
    }

    fun syncSystemLanguage() {
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            val tag = com.liberivixer.youtubeharvester.ui.LocaleController.currentTag(getApplication())
            _state.update { it.copy(settings = it.settings.copy(language = tag)) }
        }
    }

    fun setDownloadDirectory(directory: String, treeUri: String) {
        saveDownloadDirectory(directory, treeUri, R.string.download_folder_selected)
    }

    fun resetDownloadDirectory() {
        val defaults = AppSettings()
        saveDownloadDirectory(defaults.downloadDirectory, null, R.string.default_download_folder)
    }

    private val directoryMutex = kotlinx.coroutines.sync.Mutex()

    private fun saveDownloadDirectory(directory: String, treeUri: String?, messageId: Int) {
        viewModelScope.launch {
            directoryMutex.lock()
            try {
                val previous = _state.value.settings
                val settings = previous.copy(downloadDirectory = directory, downloadDirectoryUri = treeUri)
                try {
                    repository.saveSettings(settings)
                    _state.update { it.copy(settings = settings, statusMessage = localizedText(messageId)) }
                    // Archive documents and in-flight publications may still need the old grant.
                } catch (error: Exception) {
                    // The selected tree may already be referenced by an older archive item.
                    appLog.append(AppLogLevel.ERROR, "Persistence", error.safeLogMessage())
                    _state.update { it.copy(statusMessage = localizedText(if (treeUri == null) R.string.download_folder_reset_error else R.string.download_folder_save_error)) }
                }
            } finally {
                directoryMutex.unlock()
            }
        }
    }

    fun reportStatus(message: String) {
        _state.update { it.copy(statusMessage = message) }
    }

    fun requestQuickDownload(rawText: String): Boolean {
        val parsed = MediaUrlParser.extract(rawText)
        if (parsed == null) {
            _state.update { it.copy(statusMessage = localizedText(R.string.invalid_media_link)) }
            return false
        }
        _state.update {
            it.copy(
                pendingQuickDownloadUrl = parsed.normalizedUrl,
                quickDownloadRequestId = it.quickDownloadRequestId + 1,
                statusMessage = localizedText(R.string.quick_link_ready),
            )
        }
        return true
    }

    fun consumeQuickDownloadRequest(requestId: Long) {
        _state.update { state ->
            if (state.quickDownloadRequestId == requestId) {
                state.copy(pendingQuickDownloadUrl = null)
            } else {
                state
            }
        }
    }

    fun cleanupTemporaryFiles() {
        viewModelScope.launch {
            val removed = withContext(Dispatchers.IO) {
                val root = getApplication<Application>().getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
                    ?: getApplication<Application>().filesDir
                val staging = File(root, "staging")
                staging.listFiles().orEmpty()
                    .filter { repository.canDeleteTemporaryFiles(it.name) }
                    .count { it.deleteRecursively() }
            }
            _state.update { it.copy(statusMessage = localizedText(R.string.temporary_cleaned, removed)) }
        }
    }

    fun refreshArchiveAvailability() {
        if (_state.value.isDataTransferBusy) return
        viewModelScope.launch {
            var available = 0
            try {
                val total = withContext(Dispatchers.IO) {
                    repository.relinkImportedArchive(_state.value.settings)
                    val items = repository.archive.first()
                    items.forEach { item ->
                        val exists = archiveUriExists(getApplication(), item.fileUri)
                        if (exists == true) available += 1
                        if (exists != null && exists != item.fileExists) repository.setArchiveFileExists(item, exists)
                    }
                    items.size
                }
                _state.update { it.copy(statusMessage = localizedText(R.string.archive_refresh_result, available, total)) }
            } catch (cancelled: CancellationException) { throw cancelled
            } catch (_: Exception) {
                _state.update { it.copy(statusMessage = localizedText(R.string.folder_access_failed)) }
            }
        }
    }

    fun deleteArchiveItem(item: com.liberivixer.youtubeharvester.model.ArchiveItem) {
        persist(localizedText(R.string.archive_delete_error)) {
            repository.deleteArchiveItem(item)
            _state.update { it.copy(statusMessage = localizedText(R.string.archive_record_removed)) }
        }
    }

    fun addChannel(rawUrl: String): Boolean {
        val parsed = ChannelUrlParser.parse(rawUrl)
        if (parsed == null) {
            _state.update { it.copy(statusMessage = localizedText(R.string.invalid_channel_url)) }
            return false
        }
        if (_state.value.channels.any { it.id == parsed.id }) {
            _state.update { it.copy(statusMessage = localizedText(R.string.channel_already_added)) }
            return false
        }
        if (parsed.source == MediaSource.Rutube) {
            if (!pendingRutubeChannels.add(parsed.id)) return false
            _state.update { it.copy(statusMessage = localizedText(R.string.channel_resolving)) }
            viewModelScope.launch {
                try {
                    val resolved = RutubeChannelResolver(getApplication()).resolve(parsed)
                    val canonical = resolved.channel
                    val added = repository.insertChannel(ChannelItem(
                        id = canonical.id, url = canonical.normalizedUrl, name = resolved.title,
                        handle = canonical.handle, thumbnailUrl = resolved.thumbnailUrl,
                        shortsEnabled = ContentType.Shorts in canonical.sections,
                        streamsEnabled = false,
                    ))
                    _state.update { it.copy(statusMessage = localizedText(if (added) R.string.channel_added else R.string.channel_already_added)) }
                } catch (error: CancellationException) {
                    throw error
                } catch (error: Exception) {
                    appLog.append(AppLogLevel.ERROR, "Rutube channel", error.safeLogMessage())
                    _state.update { it.copy(statusMessage = localizedText(R.string.channel_save_error)) }
                } finally {
                    pendingRutubeChannels.remove(parsed.id)
                }
            }
            return true
        }
        val channel = ChannelItem(
            id = parsed.id,
            url = parsed.normalizedUrl,
            name = parsed.displayName,
            handle = parsed.handle,
        )
        _state.update {
            it.copy(
                channels = it.channels + channel,
                statusMessage = localizedText(R.string.channel_added),
            )
        }
        persist(localizedText(R.string.channel_save_error)) {
            repository.insertChannel(channel)
        }
        return true
    }

    fun deleteChannel(channel: ChannelItem) {
        _state.update {
            it.copy(
                channels = it.channels.filterNot { item -> item.id == channel.id },
                statusMessage = localizedText(R.string.channel_removed),
            )
        }
        persist(localizedText(R.string.channel_delete_error)) {
            repository.deleteChannel(channel.id)
        }
    }

    fun updateChannelContentSelection(channel: ChannelItem) {
        _state.update { state ->
            state.copy(channels = state.channels.map { if (it.id == channel.id) channel else it })
        }
        persist(localizedText(R.string.channel_save_error)) {
            repository.updateChannelContentSelection(channel)
        }
    }

    fun runChannelCheck() {
        if (!_state.value.settingsLoaded) return
        if (harvestSession != null) {
            persist(localizedText(R.string.channel_check_failed)) {
                com.liberivixer.youtubeharvester.download.HarvestCoordinator.stop(getApplication())
            }
            return
        }
        if (channelScanJob != null) {
            toggleChannelCheck(checkPaidContent = false)
            return
        }
        persist(localizedText(R.string.channel_check_failed)) {
            com.liberivixer.youtubeharvester.download.HarvestCoordinator.start(getApplication())
        }
    }

    private fun applyHarvestProgress(progress: com.liberivixer.youtubeharvester.download.HarvestProgress?) {
        val session = harvestSession
        if (session == null) {
            _state.update { if (it.harvestPhase == null) it else it.copy(isScanning = channelScanJob != null,
                harvestPhase = null, activeScanChannelId = null, scanChannel = null, activeScanContentType = null) }
            return
        }
        val checkpoint = session.checkpoint
        val phase = progress?.phase ?: checkpoint.phase
        _state.update { old -> old.copy(isScanning = true, harvestPhase = phase,
            scanTotalChannels = session.channels.size,
            scannedChannels = progress?.channel?.completedChannels ?: checkpoint.completedChannels,
            sessionDownloads = progress?.downloaded ?: checkpoint.downloaded,
            sessionErrors = progress?.errors ?: (checkpoint.scanErrors + checkpoint.downloadErrors),
            scanSections = progress?.channel?.sections ?: checkpoint.sections,
            activeScanChannelId = progress?.channel?.channelId, scanChannel = progress?.channel?.channelInfo,
            activeScanContentType = progress?.channel?.contentType,
            statusMessage = localizedText(when (phase) {
                com.liberivixer.youtubeharvester.download.HarvestPhase.QUEUE_BEFORE -> R.string.harvest_queue_before
                com.liberivixer.youtubeharvester.download.HarvestPhase.CHANNELS -> R.string.harvest_channels
                com.liberivixer.youtubeharvester.download.HarvestPhase.QUEUE_AFTER -> R.string.harvest_queue_after
            })) }
    }

    fun markChannelArchived(channel: ChannelItem) {
        if (_state.value.isScanning) return
        if (_state.value.downloadJobs.any { it.status.isActive }) {
            reportStatus(localizedText(R.string.channel_mark_stop_downloads))
            return
        }
        startChannelCheck(listOf(channel), checkPaidContent = false, markOnly = true)
    }

    fun toggleChannelCheck(checkPaidContent: Boolean) {
        if (harvestSession != null) { runChannelCheck(); return }
        if (_state.value.isScanning) {
            channelCheckRunner.cancel()
            val runningJob = channelScanJob
            runningJob?.cancel()
            _state.update { it.copy(statusMessage = localizedText(R.string.channel_scan_stopped)) }
            viewModelScope.launch {
                appLog.append(AppLogLevel.INFO, "Channel check", "Manual check cancelled")
            }
            return
        }

        val channels = _state.value.channels
        if (channels.isEmpty()) return
        startChannelCheck(channels, checkPaidContent)
    }

    private fun startChannelCheck(channels: List<ChannelItem>, checkPaidContent: Boolean, markOnly: Boolean = false) {
        val scanJob = viewModelScope.launch {
            val runningJob = kotlinx.coroutines.currentCoroutineContext()[Job]
            _state.update {
                it.copy(
                    isScanning = true,
                    scannedChannels = 0,
                    scanTotalChannels = channels.size,
                    scanQueuedItems = 0,
                    scanSections = emptyMap(),
                    sessionErrors = 0,
                    statusMessage = localizedText(R.string.channel_scan_started),
                )
            }
            appLog.append(
                AppLogLevel.INFO,
                "Channel check",
                "Manual check started: channels=${channels.size}, paidContent=$checkPaidContent, markOnly=$markOnly",
            )
            try {
                val summary = channelCheckRunner.run(
                    channels = channels,
                    settings = _state.value.settings,
                    checkPaidContent = checkPaidContent,
                    sectionResultDelayMs = CHANNEL_SECTION_RESULT_DELAY_MS,
                    markOnly = markOnly,
                ) { progress ->
                    _state.update {
                        it.copy(
                            scannedChannels = progress.completedChannels,
                            scanQueuedItems = progress.queuedItems,
                            scanSections = progress.sections,
                            sessionErrors = progress.errors,
                            activeScanChannelId = progress.channelId,
                            scanChannel = progress.channelInfo,
                            activeScanContentType = progress.contentType,
                            statusMessage = if (progress.errorMessage != null) {
                                localizedText(R.string.channel_check_failed)
                            } else {
                                it.statusMessage
                            },
                        )
                    }
                }
                _state.update { it.copy(statusMessage = if (markOnly) {
                    localizedText(R.string.channel_mark_result, summary.markedItems, summary.failedChannels)
                } else localizedText(R.string.channel_validation_completed, summary.completedChannels, summary.failedChannels)) }
                appLog.append(
                    AppLogLevel.IMPORTANT,
                    "Channel check",
                    "Manual check completed: channels=${summary.completedChannels}, queued=${summary.queuedItems}, marked=${summary.markedItems}, failed=${summary.failedChannels}",
                )
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                appLog.append(AppLogLevel.ERROR, "Channel check", "Manual check failed: ${error.safeLogMessage()}")
                _state.update { it.copy(statusMessage = localizedText(R.string.channel_check_failed)) }
            } finally {
                if (channelScanJob == runningJob) {
                    _state.update {
                        it.copy(
                            isScanning = false,
                            activeScanChannelId = null,
                            scanChannel = null,
                            activeScanContentType = null,
                        )
                    }
                    channelScanJob = null
                }
            }
        }
        channelScanJob = scanJob
    }

    fun addSchedule(hour: Int, minute: Int) {
        val normalizedHour = hour.coerceIn(0, 23)
        val normalizedMinute = minute.coerceIn(0, 59)
        if (_state.value.schedule.any { it.hour == normalizedHour && it.minute == normalizedMinute }) {
            _state.update { it.copy(statusMessage = localizedText(R.string.schedule_time_exists)) }
            return
        }
        val item = ScheduleItem(
            id = UUID.randomUUID().toString(),
            hour = normalizedHour,
            minute = normalizedMinute,
            enabled = true,
            createdAtEpochMs = System.currentTimeMillis(),
        )
        persist(localizedText(R.string.schedule_save_error)) {
            repository.upsertSchedule(item)
            DailyCheckScheduler.replace(getApplication(), item)
        }
    }

    fun toggleSchedule(item: ScheduleItem) {
        val updated = item.copy(enabled = !item.enabled)
        persist(localizedText(R.string.schedule_save_error)) {
            repository.setScheduleEnabled(item.id, updated.enabled)
            DailyCheckScheduler.replace(getApplication(), updated)
        }
    }

    fun deleteSchedule(item: ScheduleItem) {
        persist(localizedText(R.string.schedule_delete_error)) {
            repository.deleteSchedule(item.id)
            DailyCheckScheduler.cancel(getApplication(), item.id)
        }
    }

    private fun persist(errorMessage: String, action: suspend () -> Unit) {
        viewModelScope.launch {
            try {
                action()
            } catch (error: Exception) {
                appLog.append(AppLogLevel.ERROR, "Persistence", error.safeLogMessage())
                _state.update { it.copy(statusMessage = errorMessage) }
            }
        }
    }

    private fun localizedText(resourceId: Int, vararg arguments: Any): String =
        LocaleController.wrap(getApplication()).getString(resourceId, *arguments)

    private fun Throwable?.safeLogMessage(): String = this?.message
        .orEmpty()
        .replace(Regex("\\s+"), " ")
        .trim()
        .take(500)
        .ifBlank { this?.javaClass?.simpleName ?: "Unknown error" }

    private fun queueItemWithOptions(
        url: String,
        resolution: String,
        audioOptions: List<AudioTrackOption>,
        subtitleSelections: List<String>,
    ): QueueItem? {
        val parsed = MediaUrlParser.parse(url)
        if (parsed == null) {
            _state.update { it.copy(statusMessage = localizedText(R.string.invalid_media_link)) }
            return null
        }
        val preview = _state.value.downloadMediaOptions?.preview
            ?.takeIf { it.source == parsed.source && it.mediaId == parsed.mediaId }
            ?: _state.value.mediaPreview?.takeIf { it.source == parsed.source && it.mediaId == parsed.mediaId }
        val audioTracks = audioOptions.mapNotNull { YtDlpMetadataDecoder.resolveAudioTrack(it, resolution) }
        return repository.queueItemFromUrl(
            rawUrl = url,
            resolution = resolution,
            preview = preview,
            audioTracks = audioTracks,
            subtitleSelections = subtitleSelections.distinct(),
        )
    }

    private fun resetPreviewAfterAction(statusMessage: String) {
        metadataGeneration++
        previewJob?.cancel()
        downloadOptionsJob?.cancel()
        _state.update {
            it.copy(
                statusMessage = statusMessage,
                previewRequestUrl = "",
                mediaPreview = null,
                isPreviewLoading = false,
                previewError = null,
                downloadMediaOptions = null,
                isDownloadOptionsLoading = false,
                downloadOptionsError = null,
            )
        }
    }

    private companion object {
        const val PREVIEW_DEBOUNCE_MS = 450L
        const val CHANNEL_SECTION_RESULT_DELAY_MS = 650L
    }
}
