package com.liberivixer.youtubeharvester.model

enum class AppTab {
    Overview,
    Channels,
    Queue,
    Archive,
    Settings,
}

enum class MediaSource(val label: String, val symbol: String) {
    YouTube("YouTube", "▶"),
    Vk("VK", "Ⓥ"),
    Rutube("Rutube", "Ⓡ"),
}

enum class ContentType(val symbol: String) {
    Video("🎬"),
    Shorts("⚡"),
    Stream("●"),
    Queue("📥"),
}

enum class PaidContentStatus(val symbol: String) {
    Unknown("❔"),
    MembersOnly("🪙"),
    FreeOnly("🆓"),
}

enum class AppThemeMode {
    System,
    Light,
    Dark,
}

enum class AppLanguage(val tag: String, val nativeName: String, private vararg val legacyNames: String) {
    English("en", "English", "Английский"),
    Russian("ru", "Русский"),
    Ukrainian("uk", "Українська", "Украинский"),
    Belarusian("be", "Беларуская", "Белорусский"),
    French("fr", "Français", "Французский"),
    Spanish("es", "Español", "Испанский"),
    Hindi("hi", "हिन्दी", "Хинди"),
    Chinese("zh-CN", "中文", "Китайский"),
    Japanese("ja", "日本語", "Японский"),
    Arabic("ar", "العربية", "Арабский"),
    ;

    companion object {
        fun fromStored(value: String?): AppLanguage = entries.firstOrNull { language ->
            value.equals(language.tag, ignoreCase = true) ||
                value.equals(language.nativeName, ignoreCase = true) ||
                language.legacyNames.any { value.equals(it, ignoreCase = true) }
        } ?: English
    }
}

data class AppSettings(
    val downloadDirectory: String = "/storage/emulated/0/Download/YTH",
    val downloadDirectoryUri: String? = null,
    val tempDirectory: String = "internal-cache",
    val maxResolution: String = "1080p",
    val videoLimit: Int = 5,
    val shortsLimit: Int = 5,
    val streamsLimit: Int = 5,
    val language: String = AppLanguage.English.tag,
    val themeMode: AppThemeMode = AppThemeMode.System,
    val watchClipboard: Boolean = false,
    val systemNotifications: Boolean = true,
    val telegramEnabled: Boolean = false,
    val telegramBotToken: String = "",
    val telegramChannelId: String = "",
    val telegramProxyUrl: String = "",
    val telegramCredentialError: Boolean = false,
    val logRetentionDays: Int = 3,
)

data class ChannelItem(
    val id: String,
    val url: String,
    val name: String,
    val handle: String,
    val thumbnailUrl: String? = null,
    val videosEnabled: Boolean = true,
    val shortsEnabled: Boolean = true,
    val streamsEnabled: Boolean = true,
    val paidContent: PaidContentStatus = PaidContentStatus.Unknown,
    val status: String = CHANNEL_STATUS_NOT_CHECKED,
    val lastCheckedEpochMs: Long? = null,
)

data class QueueItem(
    val id: String,
    val url: String,
    val title: String,
    val channel: String,
    val source: MediaSource,
    val contentType: ContentType = ContentType.Video,
    val originChannelId: String? = null,
    val thumbnailUrl: String? = null,
    val resolution: String = "1080p",
    val selected: Boolean = true,
    val status: String = DownloadStatus.QUEUED.name,
    val audioTracks: List<SelectedAudioTrack> = emptyList(),
    val subtitleSelections: List<String> = emptyList(),
)

data class SelectedAudioTrack(
    val formatId: String,
    val formatKind: String,
    val language: String,
    val name: String,
)

data class AudioFormatVariant(
    val formatId: String,
    val height: Int,
    val extension: String,
    val bitrate: Double,
)

enum class MediaOptionSection {
    ORIGINAL,
    PREFERRED,
    OTHER,
    MANUAL_SUBTITLES,
    PREFERRED_AUTOMATIC,
    OTHER_AUTOMATIC,
}

data class AudioTrackOption(
    val key: String,
    val formatId: String,
    val formatKind: String,
    val language: String,
    val name: String,
    val isOriginal: Boolean,
    val section: MediaOptionSection,
    val variants: List<AudioFormatVariant> = emptyList(),
)

data class SubtitleTrackOption(
    val selection: String,
    val language: String,
    val name: String,
    val automatic: Boolean,
    val section: MediaOptionSection,
)

data class DownloadMediaOptions(
    val preview: MediaPreview,
    val audioTracks: List<AudioTrackOption>,
    val subtitleTracks: List<SubtitleTrackOption>,
)

enum class DownloadStatus {
    QUEUED,
    INITIALIZING,
    DOWNLOADING,
    PROCESSING,
    WAITING_NETWORK,
    PAUSED,
    PUBLISHING,
    COMPLETED,
    FAILED,
    CANCELLED,

    ;

    val isActive: Boolean
        get() = this == QUEUED || this == INITIALIZING || this == DOWNLOADING || this == PROCESSING || this == WAITING_NETWORK || this == PUBLISHING

    val isResumable: Boolean get() = this == PAUSED || this == FAILED
    val retainsFiles: Boolean get() = isActive || isResumable
    val canPause: Boolean get() = this == QUEUED || this == INITIALIZING || this == DOWNLOADING || this == WAITING_NETWORK
}

data class DownloadJob(
    val jobId: String,
    val mediaId: String,
    val url: String,
    val title: String,
    val channel: String,
    val source: MediaSource,
    val contentType: ContentType,
    val originChannelId: String?,
    val thumbnailUrl: String?,
    val resolution: String,
    val status: DownloadStatus,
    val progress: Int,
    val etaSeconds: Long?,
    val message: String,
    val createdAtEpochMs: Long,
    val updatedAtEpochMs: Long,
    val fileUri: String?,
    val errorMessage: String?,
    val fromQueue: Boolean,
    val audioTracks: List<SelectedAudioTrack>,
    val subtitleSelections: List<String>,
)

data class MediaPreview(
    val normalizedUrl: String,
    val mediaId: String,
    val source: MediaSource,
    val title: String,
    val channel: String,
    val thumbnailUrl: String?,
    val notice: String? = null,
)

data class ArchiveItem(
    val id: String,
    val title: String,
    val channel: String,
    val source: MediaSource,
    val type: ContentType,
    val resolution: String,
    val downloadedAt: String,
    val downloadedAtEpochMs: Long = 0L,
    val thumbnailUrl: String? = null,
    val fileExists: Boolean = true,
    val fileUri: String? = null,
    val audio: List<String> = emptyList(),
    val subtitles: List<String> = emptyList(),
    val variantKey: String = "default",
)

data class ScheduleItem(
    val id: String,
    val hour: Int,
    val minute: Int,
    val enabled: Boolean,
    val lastRunEpochMs: Long? = null,
    val createdAtEpochMs: Long = 0L,
)

data class DiagnosticsSnapshot(
    val checkedAtEpochMs: Long,
    val ytDlpVersion: String?,
    val runtimeReady: Boolean,
    val runtimeError: String?,
    val ffmpegBundled: Boolean,
    val quickJsBundled: Boolean,
    val networkConnected: Boolean,
    val networkValidated: Boolean,
    val notificationsAllowed: Boolean,
    val downloadDestinationAccessible: Boolean,
    val availableStorageBytes: Long?,
    val batteryOptimizationExempt: Boolean,
)

data class AppUiState(
    val settings: AppSettings = AppSettings(),
    val settingsLoaded: Boolean = false,
    val channels: List<ChannelItem> = emptyList(),
    val queue: List<QueueItem> = emptyList(),
    val archive: List<ArchiveItem> = emptyList(),
    val downloadJobs: List<DownloadJob> = emptyList(),
    val schedule: List<ScheduleItem> = emptyList(),
    val statusMessage: String = "",
    val isScanning: Boolean = false,
    val scannedChannels: Int = 0,
    val scanTotalChannels: Int = 0,
    val scanQueuedItems: Int = 0,
    val harvestPhase: com.liberivixer.youtubeharvester.download.HarvestPhase? = null,
    val sessionDownloads: Map<ContentType, Int> = emptyMap(),
    val sessionErrors: Int = 0,
    val lastCheck: CheckReport? = null,
    val scanSections: Map<ContentType, SectionResult> = emptyMap(),
    val activeScanChannelId: String? = null,
    val scanChannel: ChannelItem? = null,
    val activeScanContentType: ContentType? = null,
    val previewRequestUrl: String = "",
    val mediaPreview: MediaPreview? = null,
    val isPreviewLoading: Boolean = false,
    val previewError: String? = null,
    val downloadMediaOptions: DownloadMediaOptions? = null,
    val isDownloadOptionsLoading: Boolean = false,
    val downloadOptionsError: String? = null,
    val pendingQuickDownloadUrl: String? = null,
    val openOverviewRequestId: Long = 0,
    val quickDownloadRequestId: Long = 0L,
    val logText: String = "",
    val isLogLoading: Boolean = false,
    val logLoadError: String? = null,
    val diagnostics: DiagnosticsSnapshot? = null,
    val isDiagnosticsLoading: Boolean = false,
    val diagnosticsError: String? = null,
    val isDataTransferBusy: Boolean = false,
    val dataTransferMessage: String = "",
)

const val CHANNEL_STATUS_NOT_CHECKED = "NOT_CHECKED"
const val CHANNEL_STATUS_CHECKED = "CHECKED"
const val CHANNEL_STATUS_FAILED = "CHECK_FAILED"
