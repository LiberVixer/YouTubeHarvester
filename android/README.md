# YouTube Harvester for Android

This directory contains an isolated native Android port. It does not import or modify the
desktop PyQt launcher, Python downloader, Windows packaging, or Linux packaging.

Current application version: `1.2.1` (version code `120100`). See
[the checkpoint and resume checklist](PROGRESS.md) before continuing the port.

### Documentation screenshots

All ten localized project READMEs now include five Android 1.2.1 screens in dark
theme. The [screenshot catalog](../docs/screenshots/README.md) documents the 50
LDPlayer captures, isolated demonstration package, checksums, and repeat-capture
commands. The installed user/tester applications and their data are untouched.

### 1.2.1: version alignment

All four ABI variants now use `1.2.1` without beta/prerelease suffixes. The top
bar shows the application version instead of the beta badge. All four private
tester APKs are verified; 149 JVM, 31 Python, and 36 selected LDPlayer tests pass.
Reports: `build/qa-1.2.1/`. The installed main dev33 app is untouched; only the
separate debug package was updated. Public-release acceptance gates remain open.

### dev34: component update (historical)

AndroidX, Compose, Room, WorkManager, Coil, Jackson, and the build toolchain are
updated. QuickJS `2026-06-04` is rebuilt for all four ABIs with 16 KB alignment.
All four private tester APKs are verified; 149 JVM, 30 Python, and 36 selected
LDPlayer device tests pass. Strict offline Gradle validation succeeds; all 304
new dependency artifacts were checked against official repository checksums.
The installed main beta remains dev33; only the separate debug app was upgraded.
Android Python/OpenSSL/FFmpeg rebuilds and public-release gates remain pending.
See [the component update record](../docs/component-update-20261003.md).

### dev33: encrypted beta data transfer

- Settings can export/import a password-protected `.ythbackup` containing local
  records and settings. Videos and temporary files are not included. Imports
  refuse nonempty databases; downloads are paused and schedules disabled.
- Archive relinking requires a newly selected folder and matching name, size
  and SHA-256. Telegram credentials are re-encrypted with the destination Keystore.
- Transfer success/failure is visible beside the Settings controls, with a polite
  accessibility announcement. See [transfer instructions](DATA-TRANSFER.ru.md).
- The optimized old-certificate beta was updated from dev32 on LDPlayer without
  uninstalling. Existing records and settings were verified unchanged. All 149
  JVM and 36 selected debug device tests pass. Follow-up: 27 Python tests and
  six transfer tests in a separate permanent-key QA package pass; actual beta
  export/import and file relinking were verified across installations. This is
  not final public-candidate acceptance. See [acceptance](RELEASE-FIXES-dev33.ru.md)
  and [cross-identity evidence](MIGRATION-QA-dev33.ru.md).

### dev32: pre-release audit fixes

- Manual and scheduled harvests share a WorkManager-owned session, persisted
  phase/channel cursor and pending job. Closing the screen no longer cancels
  the cycle. Overview and the background notification control the same session.
  Recovery reuses stable job IDs; Android force-stop still requires reopening.
- Changing the destination retains existing SAF grants. A temporarily inaccessible
  provider no longer marks old archive files as deleted. Android 8/9 file sharing
  uses a restricted content provider for `Download/YTH` instead of `file://`.
- Five WebP dependencies per ABI are rebuilt from pinned libwebp sources with
  16 KB ELF alignment. APK checks now inspect the nested FFmpeg runtime archives.
  See [native provenance and rebuild instructions](native/README.md).
- A bundled yt-dlp postprocessor maps the selected audio explicitly and supports
  manual and automatic subtitles of the same language together. Unavailable
  subtitles are reported and omitted, never silently substituted. The final
  video is checked with ffprobe before publication; new archive entries show
  actual resolution and embedded tracks. Old archive entries are not rewritten.
- Telegram decryption failures disable only Telegram and preserve ciphertext
  during unrelated saves. Explicitly saving Telegram replaces the credentials.
  Unsupported authenticated/TLS proxy URLs are rejected; unauthenticated HTTP
  CONNECT and SOCKS proxies remain supported. The Telegram endpoint stays HTTPS.
- Background check reports no longer overwrite unsaved settings. Schedule
  timers are recalculated after system time/timezone changes.
- A members-only overwrite alleged in the audit was not reproduced: the DAO
  already preserves positive status. An Android regression test covers it.

Use the matching current `legacyBeta` APK to update existing testers without
uninstalling. The version has no beta suffix, but these signature-compatible
private tester APKs are not a published public release. See
[the dev32 acceptance record](RELEASE-FIXES-dev32.ru.md) for checks and remaining
device/signing/source/license requirements.

### dev31: security hardening

- yt-dlp 2026.08.19 is pinned in the APK; its SHA-256 is checked at build time
  and before runtime initialization. A previously downloaded or damaged engine
  is replaced atomically with the verified bundle before execution. Standalone
  engine updates and network calls under the initialization lock are removed.
  Update the application to update its engine. The Settings notice is translated
  into all ten languages.
- The exported quick-download action only opens Overview. With clipboard watching
  disabled, it cannot read the clipboard. The visible Quick button still reads
  and immediately downloads on a user tap; Share uses explicitly supplied text.
- HTTP/HTTPS schemes are case-insensitive for video and channel links, without
  changing case-sensitive IDs or weakening host/userinfo/port validation.
- Internal debug builds use a separate `.debug` application ID. `legacyBeta`
  is a non-debuggable, optimized migration build signed with the old development
  key so current testers can update without uninstalling. It is **not a public
  release** and does not solve permanent release-key migration.
- Public packaging checks the actual APK manifest, approved signing fingerprint,
  package/version and ZIP alignment. Debug certificates and debug tooling activities
  are rejected. BUILD-INFO records the source commit, tag, runtime and certificate.

Do not uninstall an existing test build to install dev31. Use the matching
`legacyBeta` APK, not the separate internal debug APK. Device upgrade, clipboard
and live download acceptance still need testing; see [release policy](RELEASING.md).

### dev30

- The Overview Quick button now immediately starts a supported link from the
  clipboard using the configured resolution and automatic audio, without an
  options dialog. Invalid clipboard text cannot start a download. Links embedded
  in surrounding text are accepted. Existing active downloads are not interrupted.
- Share intents and the launcher quick-download shortcut retain their media
  options dialog. The Overview Download button still uses the entered URL.

### dev29

- Quick download is now between Add to queue and Download below the URL field.
  It still reads the clipboard and opens media options, without downloading
  automatically.
- Downloads is a folder action in the bottom navigation, between Archive and
  Settings. It opens the configured destination without changing the active tab.
- The former Temp button is now a full-width Clear temporary files action with
  a broom icon. Existing protection of resumable download files is unchanged.
  The new label is translated into all ten interface languages.

### dev28

- The Overview panel now starts with the current channel avatar, name and
  checking status, with the circular start/stop button at the right. The check
  heading, channel count and last-check time are below this identity row.
- The desktop Overview mascot is shown while idle, during quick-link queue
  passes, or when the channel avatar is unavailable. It is fitted without
  cropping. Image state is reset on channel changes, and fresh channel metadata
  is displayed before downloading the discovered videos.
- Channel avatars remain circular; the idle mascot keeps its full square
  composition. Labels wrap on narrow screens and are localized in all ten
  interface languages. Download sequencing is unchanged.

### dev27

- Overview now shows a dedicated check report below the three content-section
  rows: completion state, timestamp, downloads/no-new-videos result, daily total
  with Video/Shorts/Streams breakdown, checked/total channels, and error count.
  The report is stored independently of transient URL-preview messages and is
  restored after restarting the app. Scheduled harvests save the same report.
- Section rows show the current channel's actual inspected-item count and
  waiting/checking/checked/disabled/error state. Only the checking section has
  animated dots; active downloads show their own status and percentage.
- Stops and unexpected failures are not reported as successful checks. Errors
  count failed sections and downloads, not only channels with any failure.
  A zero-download run with errors does not claim that no new videos exist.
- Daily totals use completed download jobs, with deduplicated legacy-archive
  fallback. Failed and pending jobs are excluded; deleting an archive row does
  not remove today's completed download from the count. Local midnight resets
  the display, including when the Overview remains open.
- Compact report rows wrap on narrow screens, and new labels are translated
  into all ten interface languages.

### dev26

- Overview now has a full-width URL field and separate Add to queue / Download
  buttons. Download starts the entered link immediately with the configured
  resolution and automatic audio, without opening a second confirmation sheet.
  Advanced audio/subtitle selection remains available through Quick download.
- The round button in the channel-check panel runs a full harvest cycle:
  selected quick-link queue, channel discovery with sequential downloads, then
  a fresh pass over selected quick links added during the check. An existing
  download is not interrupted; direct quick-link jobs have priority among
  jobs that have not started yet.
- Each discovered channel video is downloaded before scanning the next section.
  Channel discoveries never populate the visible quick-link queue. Archive,
  invisible marks and manually queued links are checked before scheduling.
- A failed item is attempted only once per cycle (the download service still
  performs its bounded network retries). Pausing the current cycle download
  holds the cycle until resume or cancellation. Stop cancels the cycle and its
  current download, without starting the remaining items.
- The Channels tab remains a section-validation tool; it does not download or
  enqueue discovered media. Scheduled runs use the same full harvest cycle as
  the round button, including queue-only runs when no channels are configured.
- Older channel-derived queue entries are preserved as paused internal jobs
  during initialization, rather than discarded or downloaded without consent.
  They remain accessible from Overview. User-added queue links are unchanged.

### dev25

- Failed downloads stay visible on Overview with a retry action and their saved
  media options. Partial files survive failures, pauses and service timeouts.
- Temporary network errors trigger up to three automatic retries per attempt,
  with a bounded network wait (60 seconds). The retry budget survives service
  restart. Manual retry resets the budget; unavailable/private videos are not
  treated as network failures.
- Pause/resume controls are available on Overview, queue cards and download
  notifications. Resume reuses the same job and staging directory. Pausing is
  disabled during post-processing and publication. Byte-level continuation
  depends on the source protocol and server; a source may require a restart.
- Each queue card has a download action for that item without changing other
  selection checkboxes. Already scheduled work is not interrupted.
- Folder buttons target the selected SAF folder or the archived file's actual
  parent location. Unsupported directory intents fall back to the system file
  browser with an initial-folder hint and a visible explanation.
- Temporary cleanup preserves resumable jobs. Cancel a retained job to discard
  its partial files. Room schema 10 preserves existing data and adds retry counts.
- Added all-language labels and regression tests for retry classification,
  processing phases, persisted pause/retry state and schema migration.

### dev24

- Immediate downloads no longer mutate an unrelated queue entry. Jobs are claimed
  transactionally and the service has one main-thread-owned processor.
- Publication URIs are journaled before copying. Interrupted output is reconciled
  on restart, failed rollback preserves the original error, cancellation stops
  copying between chunks, and completed archive files survive notification errors.
- Android foreground-service timeout cleanup runs as durable background work.
- Folder changes save successfully before releasing the previous SAF permission.
- Late metadata results are ignored after the URL changes.
- Telegram credentials use authenticated Android Keystore encryption; existing
  settings are migrated and legacy plaintext credential fields are removed.
- Android 13+ app-language preferences use the system LocaleManager.
- Settings can check GitHub for a compatible Android APK, verify its SHA-256,
  package, version and signing certificate, and open the system installer.
- Updated Commons Compress, Commons IO, Jackson and Coil; enabled release R8
  optimization and committed Gradle dependency verification.
- Added Android CI, device integration tests, all-schema migration tests and
  release signing/source packaging. See [RELEASING.md](RELEASING.md).
- Paid-content detection remains unchanged by explicit request.

### dev23

- Removed the remaining mock data from Overview. Channel-check progress, queue
  counts by content type, the most recent download time, and today's Video,
  Shorts, and Stream totals now come from persisted application data.
- Queue cards now have working Move up, Move down, and Delete actions. Active
  jobs cannot be removed accidentally, and queue order is normalized and saved
  transactionally.
- Newly completed archive entries retain their real thumbnail URL. Room schema
  9 adds the nullable thumbnail column without replacing existing data and
  backfills it from matching download jobs when possible. Missing or failed
  artwork falls back to initials instead of an empty frame.
- VK links now use embedded yt-dlp for real title, channel, thumbnail, audio,
  and subtitle metadata instead of a generic preview. Cancelled metadata
  requests terminate their yt-dlp process, non-zero extractor exits are handled,
  and malformed JSON null values cannot leak into the interface as text.
- Download completion, archive insertion, and removal of a completed queue item
  are now one Room transaction. Failed downloads clean their staging directory,
  non-zero yt-dlp exits cannot publish a partial media file, and a published file
  is rolled back if the archive transaction cannot be completed. Re-downloading
  the same resolution and track combination also replaces its previous managed
  file instead of leaving an unreferenced duplicate.
- Temporary-file cleanup is a real Settings action; FFmpeg and QuickJS show an
  unknown state until diagnostics run and an unavailable state if validation
  fails. Limits are consistently constrained to 1-99, and schedule times follow
  the device's 12/24-hour preference.
- Removed obsolete preview/movement strings and stale documentation references.
  Automated coverage now includes queue ordering, archive schema migration,
  thumbnail persistence, and null metadata fallbacks.
- Historical dev23 behavior (replaced by APK-only updates in dev31): the yt-dlp row performed a stable-channel update inside
  the application, prevents duplicate update requests, refreshes the displayed
  version, and reports the result in every interface language. Automatic checks
  remain throttled after failures instead of suppressing retries for a full day.

### dev22

- Rutube channels (`/channel/<id>` and `/u/<name>`) and show collections
  (`/metainfo/tv/<id>`) can be added on the Channels screen. Channel aliases are
  resolved to numeric IDs to avoid adding the same channel twice. Show IDs have
  a separate namespace, even if their number matches a channel ID.
- Channel names and avatars, or the show's own title and poster, are loaded from
  public metadata. Failure to obtain optional artwork does not prevent adding
  an otherwise valid channel.
- Both manual and scheduled checks send discovered Rutube videos to the existing
  queue and download pipeline. Normal channels support Videos and Shorts;
  shows support Videos only. Unsupported section controls are disabled.
  Members-only probing remains specific to YouTube. VK channel monitoring and
  arbitrary Rutube playlists are not included in this milestone.
- Shows are enumerated from the end of their oldest-first list to find the
  latest items. This can require loading the entire list. A failed page or
  incomplete extractor response is not accepted as a successful check.
- Each channel's menu now offers **Mark latest...**, with confirmation and the
  configured per-section limits. Marks are committed only after every enabled
  section of that channel succeeds; failure or cancellation leaves no partial
  marks. Additional members-only probing is not performed while marking.
- Marks live in a separate Room table, not in the visible file archive. Later
  channel checks skip marked media. Matching automatically discovered queue
  entries are removed; explicitly added queue entries are kept. Explicitly
  submitting a video link still permits a manual download.
- Marking is blocked while download jobs are active or pending. Starting the
  selected queue and saving marks use database transactions, so neither can
  operate on a partially changed queue. Queue insertion also checks both the
  file archive and hidden marks in the same transaction.
- Room schema 8 adds the source-aware marks table without replacing existing
  queue, archive, job, channel, or schedule data. New UI text is translated into
  all ten interface languages.
- Regression coverage includes source/URL handling, incomplete lists, cancelled
  and failed marking, disabled sections, and the non-destructive schema update.
  Physical-device acceptance remains deferred at the user's request.

### dev21

- Working top-bar theme menu with System, Light, and Dark options. Selection is
  saved immediately from both the top bar and Settings.
- Working top-bar menu for Settings, application logs, and diagnostics. Log and
  diagnostic tools reuse the existing refresh, clear, and share actions.
- Channel filters for enabled/disabled sections, unchecked/failed checks, and
  members-only/free/unknown content status. Filters combine with name, handle,
  and URL search; the active filter can be cleared with one tap.
- Filter selection survives screen recreation; menus use all ten UI locales.
- Device testing is deferred at the user's request until feature completion.

### dev20

- Scheduled checks append the next daily run only after completion, not on every
  retry or cancellation. This avoids accumulating successor jobs during failures.
- Daily schedules return to the requested local time after a daylight-saving gap.
- Added clock-change regression tests. Physical-device checks remain necessary.

## Current milestone

- Native Kotlin and Jetpack Compose application with five bottom-navigation screens.
- Overview, Channels, Queue, Archive, and scrollable Settings layouts based on the approved
  mockups in [`../docs/android-ui-reference`](../docs/android-ui-reference/README.md).
- Persistent queue and archive tables using Room, with exported schemas for future migrations.
- Transactional settings storage using Preferences DataStore.
- One-time migration of settings and queue entries saved by earlier Android development builds.
- Durable Room download jobs with automatic recovery after an interrupted app process.
- URL recognition for individual YouTube, VK Video, and Rutube links.
- Live title, channel, and thumbnail previews for public YouTube and Rutube videos,
  plus full embedded yt-dlp metadata inspection for VK links.
- Embedded yt-dlp, FFmpeg/ffprobe, and QuickJS runtime in separate `arm64-v8a`,
  `armeabi-v7a`, `x86`, and `x86_64` APKs.
- Sequential foreground downloads with Android progress and cancellation notifications.
- Scoped-storage-safe publication from per-job staging into `Download/YTH` through MediaStore.
- Optional destination selection through Android's Storage Access Framework, with persisted folder
  permission and collision-safe file names.
- APK-only yt-dlp updates, with a pinned bundled engine and local SHA-256 verification.
- Full yt-dlp metadata inspection before immediate downloads.
- Multiple audio-track and subtitle selection with deterministic language grouping.
- Persisted track selections in queued jobs and readable audio/subtitle details in the archive.
- Unit-tested media URL parser and metadata decoders.
- A lightweight public-metadata preview boundary with embedded yt-dlp inspection
  for formats, tracks, subtitles, and VK metadata.

The dev10 build added a real resource-backed interface locale switcher for English, Russian,
Ukrainian, Belarusian, French, Spanish, Hindi, Simplified Chinese, Japanese, and Arabic. Language
selection is persisted, migrates legacy display names to stable language tags, supports Android's
per-app language list, and applies right-to-left layout direction for Arabic.

The dev11 build extends the selected language to foreground-service notifications, download
errors, progress timing, and completion messages. Queue states are now stored as stable status codes
instead of translated phrases, while legacy Russian development-build states remain readable. The
System notifications switch now controls completion, failure, and cancellation notifications;
Android's mandatory foreground progress notification remains visible while a download is running.

The dev12 build replaces the sample Channels screen with a persistent Room-backed channel registry.
It accepts YouTube `@handle`, `/channel/UC…`, `/user/…`, and `/c/…` links, normalizes channel-tab
URLs, rejects video and playlist links, prevents duplicates, and saves Video/Shorts/Streams choices.
Channels can be searched and deleted, and database version 5 migrates existing Android installs
without removing their queue, archive, download jobs, or settings. This storage boundary is the
foundation used by the dev13 network scanner.

The dev13 build adds cancellable channel discovery through the embedded yt-dlp runtime. Enabled
Videos, Shorts, and Streams sections are checked sequentially with the configured per-section
limits. Since dev26 the harvest cycle downloads new public entries directly, while manual queue
duplicates and media already present in the archive are skipped. Channel names, handles, and avatars are refreshed from
real playlist metadata. Optional paid-content probing stops at the first members-only marker, and a
later members-only download failure updates the originating channel. Room database version 6 stores
content type and channel origin through queue, download job, and archive publication so Shorts and
Streams are no longer archived as ordinary Videos.

The dev14 build turns the Queue scheduler into a real persistent feature. Daily check times are
stored in Room, can be enabled, disabled, or deleted independently, and are restored after app and
device restarts. WorkManager 2.11.2 waits for network access and runs the full harvest cycle in a
long-running data-sync task. It downloads selected quick links, then channel discoveries, checks
the quick-link queue again, records the last run, and schedules the next local-day execution. Android power management
may defer a check slightly beyond the selected time. Room database version 7 adds the schedule
table without replacing existing app data.

The dev15 build adds Android-native quick download entry points. YouTube, VK, and Rutube links
shared as text from another application open the existing download-options sheet on Overview. The
Quick button reads the clipboard only after an explicit tap, and optional clipboard watching works
while the app is visible, remembering the last handled clipboard item so the same link cannot reopen
the sheet repeatedly. Settings can request a pinned home-screen shortcut that opens quick download
from the clipboard. The Overview Downloads button opens Android's system downloads, and the
Temporary button removes only inactive staging folders while preserving current download jobs.

The dev16 build makes the Archive screen operational. Archive models retain their persisted
`content://` file URI, availability refresh verifies each file through Android's content resolver,
and records can be filtered by source and by available or missing file state. Expanded cards can
open the original media page, open or share the local video with another Android app, open system
downloads, or remove only the archive record after confirmation while keeping the video file.

The dev17 build replaces desktop-only and decorative settings with Android behavior. System tray,
taskbar, and desktop autostart choices are no longer shown. Telegram completion, failure, and
cancellation notices use the Bot API with optional HTTP or SOCKS5 proxy support and a test action;
credentials remain in app-private DataStore, are excluded from diagnostics, and app-data backup is
disabled. Thumbnail-cache clearing, GitHub/release links, local third-party license information,
and a shareable device/component diagnostics report now perform real actions. Runtime status,
preview, metadata, and storage errors use all ten interface locales, while legacy Russian strings
are retained only as migration aliases for data written by earlier development builds.

The dev18 build adds a persistent UTF-8 application log for physical-device diagnostics. It records
application startup, manual and scheduled channel-check summaries, section failures, download
start/completion/cancellation/errors, and Telegram delivery results without logging per-percent
progress. Logs live in the private no-backup directory, redact Telegram bot tokens, rotate by a
user-selectable 1/3/7/14/30-day retention period, and cap oversized daily files. Settings can view,
refresh, select, clear with confirmation, or share the latest bounded log text in every interface
language. Log-writing failures are deliberately non-fatal and cannot interrupt downloads or checks.

The dev19 build replaces the static diagnostics text with an asynchronous on-device health check.
It reports the installed yt-dlp version, initializes the embedded downloader and FFmpeg without
triggering an update, verifies that the current ABI contains FFmpeg and QuickJS, and inspects
validated network access, notification permission, download-folder access, available shared-storage
space, and Android battery optimization. Refreshing or opening diagnostics also loads the latest
private log, and the system share action combines both into one support report without credentials.
All new diagnostics text is available in the app's ten interface languages.

The build also provides architecture-specific APKs without combining four large native runtimes into
one package. Use `arm64-v8a` for almost every current physical phone, `armeabi-v7a` for older
32-bit phones, and `x86`/`x86_64` for matching emulators or ChromeOS devices.

The app includes a real system directory picker and publishes completed downloads either to the
selected document tree or, by default, to `Download/YTH`. Revoked directory access produces a
clear error and never causes a silent fallback to an unexpected location. The picker opens in
`Download` and asks for a nested folder because modern Android intentionally blocks granting an
application access to the entire shared-storage root. `PublicMetadataMediaEngine` still performs
bounded HTTPS preview requests, while
the download service owns the embedded runtime and never invokes desktop scripts.

## Toolchain

- JDK 17
- Android Gradle Plugin 9.4.0
- Gradle 9.6.0
- compileSdk / targetSdk 37
- minSdk 26 (Android 8.0)
- Compose BOM 2026.08.00
- WorkManager 2.11.2

Open the `android` directory directly in Android Studio, or build from the command line:

```bash
cd android
./gradlew testDebugUnitTest lintDebug assembleDebug
```

Architecture-specific debug APKs are written to `app/build/outputs/apk/debug/`.

## Architecture boundary

The UI talks to `MediaEngine` for inspection and to `DownloadServiceController` for durable
downloads. The Android implementation owns:

1. yt-dlp running through an Android Python runtime.
2. Bundled FFmpeg/ffprobe for the selected APK ABI.
3. Bundled QuickJS for the selected APK ABI and current YouTube extraction.
4. A foreground download service with progress, cancellation, and process recovery.
5. MediaStore or persisted SAF publication selected by the user in Android settings.

Desktop modules must not depend on Android code. Shared formats such as archive records should be
ported through explicit serializers and compatibility tests rather than direct filesystem sharing.

## Next milestone

- Verify Rutube channel aliases and show collections, recent-item order, and
  hidden marking across app restart and subsequent scheduled checks.
- Exercise interrupted metadata requests while marking; confirm existing
  archive records and explicitly queued videos remain unchanged.
- Verify channel discovery, paid-content detection, and cancellation using a physical arm64 device.
- Verify scheduled checks across app restart, device reboot, and Android battery-saving modes.
- Verify Share to YouTube Harvester and the pinned quick-download shortcut on common launchers.
- Verify opening and sharing archive files from both MediaStore and a user-selected SAF folder.
- Verify multi-audio and embedded subtitles on YouTube, VK, and Rutube using a physical arm64 device.
- Verify all translated layouts on physical phones, especially Arabic RTL and long French labels.
- Verify application-log viewing, clearing, retention, and sharing on a physical phone.
- Run the UI on physical Android devices and verify real/fallback channel artwork.

## Third-party runtime notice

The Android download build links `youtubedl-android` and its FFmpeg module, distributed under
GPL-3.0. yt-dlp itself is Unlicense software; FFmpeg and the bundled codecs retain their upstream
licenses. The Android module must have a GPL-compatible release license before a public binary is
published. This does not change the desktop application's runtime or packaging.
