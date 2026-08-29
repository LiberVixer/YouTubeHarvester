# Changelog

<p align="center">
  <a href="CHANGELOG.md">🇺🇸 🇬🇧 English</a> ·
  <a href="CHANGELOG.ru.md">🇷🇺 Русский</a> ·
  <a href="CHANGELOG.uk.md">🇺🇦 Українська</a> ·
  <a href="CHANGELOG.be.md">🇧🇾 Беларуская</a> ·
  <a href="CHANGELOG.fr.md">🇫🇷 Français</a> ·
  <a href="CHANGELOG.es.md">🇪🇸 Español</a> ·
  <a href="CHANGELOG.hi.md">🇮🇳 हिन्दी</a> ·
  <a href="CHANGELOG.zh.md">🇨🇳 中文</a> ·
  <a href="CHANGELOG.ja.md">🇯🇵 日本語</a> ·
  <a href="CHANGELOG.ar.md">🇸🇦 العربية</a>
</p>

All notable changes to **YouTube Harvester** are documented here.

## [1.2.0-beta] - 2026-08-29

### Added

- Optional individual-video downloads from YouTube, Rutube, and VK in the
  Overview URL field, Quick Download, clipboard watcher, manual queue, and
  archive.
- Source-aware archive records, canonical source links, and monochrome `Ⓥ`
  and `Ⓡ` service symbols for VK and Rutube entries.
- A close button beside the theme selector and bounded archive columns of
  160 px for channels and 155 px for media IDs.
- Automated tests for supported media URLs, archive compatibility and
  migration, file moves, and safe preview image downloads.
- A fully pinned Windows dependency lock and Dependabot configuration.

### Changed

- The application and release toolchain now identify this version as the
  `1.2.0-beta` prerelease; Debian uses `1.2.0~beta1` for correct version order.
- Runtime and build components are pinned to `yt-dlp 2026.08.19`,
  `yt-dlp-ejs 0.8.0`, Deno `2.9.6`, Windows FFmpeg/FFprobe `9.0.1`,
  PyQt5 `5.15.11`, pynput `1.8.2`, PyInstaller `6.22.2`, and Pillow `12.3.0`.
- Windows online and offline builds verify exact component versions and
  checksums, run `pip check`, and use a complete transitive dependency lock.
- GitHub Actions are pinned to exact reviewed commits, and Windows offline
  build documentation now targets the pinned tools and Inno Setup 7.1.
- Linux package metadata now describes a general video downloader with a
  manual YouTube, Rutube, and VK queue.
- All supported interface languages now include the new source-aware URL and
  archive labels.

### Fixed

- Application update comparison now orders alpha, beta, release candidate,
  and stable versions correctly, preventing a beta build from downgrading to
  an older stable release.
- Queue, duplicate checks, quality/track variants, archive deletion, reports,
  and migrations now use `source + media ID`, so equal IDs from different
  services cannot collide.
- Existing archive records remain compatible as YouTube entries; migration
  avoids guessing when an ID is ambiguous, and source markers are removed
  from final user-facing filenames.
- YouTube-specific metadata and HTTP 403 fallbacks are no longer applied to
  Rutube or VK, and a missing `yt-dlp` output stream is handled gracefully.
- Channel callbacks bind the current channel and media type instead of stale
  loop values; settings command output is decoded explicitly as UTF-8.
- Windows builds ignore incompatible FFmpeg or Deno found in `PATH` and fetch
  the verified pinned component in online mode.

### Security

- Preview images are downloaded atomically with HTTP(S)-only URLs, credential
  rejection, redirect validation, timeouts, a 12 MiB limit, and cleanup of
  incomplete temporary files.
- Pinned FFmpeg and Deno packages are verified with SHA-256 before use, and
  SHA-256 replaces SHA-1 in generated variant and filename digests.
- Release source archives now include the dependency locks, tests, and other
  required newly tracked files even when built before a commit.

## [1.1.3] - 2026-08-20

### Added

- A built-in application updater downloads the matching installer, portable
  archive, Linux package, or source archive from official GitHub Releases.
- Update downloads support resume and are verified against published SHA-256
  checksums and GitHub asset digests before they can be opened.
- Complete Belarusian interface, usage rules, README, changelog, desktop
  metadata, and localized screenshots.
- Secure single-instance integration actions and native completion
  notifications for desktop integrations such as FriendsHub.

### Changed

- Bundled `yt-dlp` was updated to `2026.08.19`; Windows build dependencies and
  GitHub Actions were refreshed to their current stable versions.
- The `yt-dlp` updater now installs a verified managed executable atomically
  and can be run directly from Settings.
- YouTube media HTTP 403 failures refresh the media URL and retry through a
  fallback player client before reporting a final error.

### Fixed

- Tray, taskbar, and combined display modes are applied consistently to the
  main and Quick Download windows.
- Archive records are committed only after the completed file reaches its
  final destination, avoiding false successful entries.
- Runtime locks, launcher requests, and completion-event files use private
  per-user locations and reject unsafe files on Linux.

## [1.1.2] - 2026-08-01

### Added

- Quick Download can select and embed multiple audio tracks and multiple manual
  or automatic subtitle tracks into one MP4.
- Full Japanese interface, Japanese usage rules, localized README, changelog,
  and interface screenshots.
- Audio and subtitle menus prioritize original/manual tracks, followed by
  Russian, English, Ukrainian, and the other interface languages; remaining
  languages are shown alphabetically in a separate group.

### Changed

- The archive treats each resolution, audio-track set, and subtitle-track set
  as a separate variant of the same video.
- The archive quality column shows only the video resolution; its tooltip lists
  the selected audio and subtitle tracks line by line.
- Merged MP4 audio streams receive ISO 639 language metadata.
- The subtitle selector uses a font-compatible `🔤` icon.
- Manual/original subtitles and automatic subtitles are separated visually in
  the track menu.

### Fixed

- Quick Download uses an additional YouTube metadata client to discover
  alternate dubbed tracks, including tracks that the default client omits.
- When an individual subtitle fails to download, including HTTP 429 responses,
  `yt-dlp` retries without that track; if every subtitle fails, video and audio
  still download normally.
- Saving the Quick Download window position is debounced on Windows, preventing
  the window from jerking while it is dragged.
- Multiple-track selections and older single-track archive records are compared
  correctly, and Windows-safe variant filenames remain within practical limits.
- The tray Stop action uses the clearly rendered `🛑` icon in every language.

## [1.1.1] - 2026-07-25

### Fixed

- Each completed channel video is now moved from the temporary directory to
  the download directory before the next playlist item starts.
- A soft stop now preserves and moves the item that has already finished.
- The active channel image is shown during downloads even after the hidden
  Harvester game has unlocked its victory logo.
- Minor interface and runtime inconsistencies were corrected.

## [1.1.0] - 2026-07-25

### Added

- Complete interface localization for English, Russian, Ukrainian, French,
  Spanish, Hindi, Chinese, and Arabic; English is the default for new installs.
- Separate localized README files, changelogs, and UI screenshots for every
  supported language.
- Diagnostics view for the operating system, X11/Wayland session, system tray,
  hotkey, clipboard, bundled tools, paths, cache, permissions, and disk space.
- Built-in current/latest `yt-dlp` version check.
- Paid-content status on every channel and optional members-only probing during
  explicit channel checks.
- Daily download report split into Videos, Shorts, streams, and queue items.
- All, Important, and Errors filters in the log viewer.
- Immediate Download button and Quick Download shortcut on the Overview tab.
- Reproducible localized README screenshot generator using cached channel art.

### Changed

- Application and release-build defaults now use version `1.1.0`.
- The queue is processed both before channel scanning and after all channels
  have been checked.
- Members-only items are treated as important access information instead of a
  red download error.
- Channel checks show the active section, animate its progress, and can be
  stopped from the same button.
- Interface spacing, checkbox contrast, channel controls, settings limits,
  Overview toolbar buttons, and Quick Download layout were refined.
- Linux exposes the Python downloader only; the disabled Bash engine is kept as
  legacy source code.
- Configuration files now follow an explicitly selected `YTD_CONFIG_DIR`, so
  portable and test instances do not inherit another installation's settings.

### Fixed

- Windows console output, logs, archive tables, and subprocess decoding handle
  Cyrillic and emoji safely as UTF-8.
- Successfully downloaded Windows files are no longer removed during failed
  Telegram delivery or an unsuccessful post-processing path.
- Linux/X11 temporary cleanup ignores the `.yth-temp` marker and safely removes
  completed temporary files.
- The Overview preview returns to its placeholder after a manual download and
  no longer flashes the previous channel artwork at startup.
- Clipboard monitoring no longer reopens Quick Download repeatedly for the same
  URL after a download starts.
- Quick Download preserves its position, loads channel artwork more reliably,
  keeps its thumbnail inside the panel, and uses a circular hover highlight.

## [1.0.0] - 2026-07-02

### Added

- First stable release for Linux and Windows.
- Full Overview, channel cards, manual queue, scheduler, archive browser, logs,
  Quick Download, clipboard monitoring, hotkeys, Telegram settings, themes, and
  startup modes.
- Linux `.deb`, source archive, Windows Setup EXE, MSI, portable ZIP, and SHA256
  checksum artifacts.
- Bundled `yt-dlp`, FFmpeg/FFprobe, and Deno in Windows releases.
- First-run responsible-use dialog and third-party component notice.

### Changed

- Python became the shared downloader engine on Linux and Windows.
- Shared runtime helpers moved to `yth_common.py` and were included in every
  package format.
- Quick-download launch uses a single-instance request instead of creating
  duplicate tray processes.

### Fixed

- Telegram errors no longer block or remove locally saved media.
- Downloader exit codes correctly report failed items.
- Temporary cleanup is protected by a marker and path validation.
- Windows/PyInstaller helper scripts can import project runtime modules.

## [0.2.5-beta] - 2026-06-28

### Added

- Quick Download window with clipboard URL detection, metadata preview,
  immediate download, queue action, resolution selection, and Telegram option.
- Native Windows global hotkey, Linux/X11 `pynput` support, and Cinnamon/GNOME
  Wayland system-shortcut installation.

### Changed

- Linux switched to the Python downloader; the Bash engine was disabled.
- Overview and Quick Download layouts became more compact.

### Fixed

- More reliable channel/video previews and saved Quick Download position.
- Better Windows text decoding and interface spacing.

## [0.2.4-beta] - 2026-06-25

### Added

- Windows builds bundle `ffmpeg.exe`, `ffprobe.exe`, and `deno.exe`.
- Automated GitHub release notes and refreshed release assets.

### Fixed

- UTF-8 subprocess decoding for Cyrillic titles and emoji on Windows.
- Correct handling of quoted tool paths and Windows-safe output filenames.
- Failed downloads no longer clean the temporary directory as if processing had
  succeeded.

## [0.2.3-beta] - 2026-06-18

### Changed

- The Overview progress bar keeps showing checked channels while media is being
  downloaded.
- Shorts use a clear lightning icon throughout the interface.

## [0.2.2-beta] - 2026-06-13

### Added

- Responsible-use dialog, settings, experimental Python downloader, Windows
  launcher/build preparation, release packaging, and GitHub Actions.

### Changed

- Compact settings limits, larger event area, channel progress, download stage,
  one-second pauses after checked media sections, and clean idle reports.

### Fixed

- Queue/archive duplicate checks and safe Windows emoji logging.

## [0.2.0-beta.1] - 2026-06-12

### Added

- First public beta with Overview, channel artwork, per-type channel switches,
  manual queue, scheduler, settings, Telegram, themes, logs, and Linux `.deb`.

### Fixed

- Tray opening, log refresh, emoji rendering, and temporary cleanup behavior.

## [0.1.0] - 2026-06-11

- Initial packaged build with tray launcher, channel list, scheduled runs,
  manual queue, logs, and Telegram delivery.
