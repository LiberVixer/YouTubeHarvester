# Changelog

<p align="center">
  <a href="CHANGELOG.md">🇺🇸 🇬🇧 English</a> ·
  <a href="CHANGELOG.ru.md">🇷🇺 Русский</a> ·
  <a href="CHANGELOG.uk.md">🇺🇦 Українська</a> ·
  <a href="CHANGELOG.fr.md">🇫🇷 Français</a> ·
  <a href="CHANGELOG.es.md">🇪🇸 Español</a> ·
  <a href="CHANGELOG.hi.md">🇮🇳 हिन्दी</a> ·
  <a href="CHANGELOG.zh.md">🇨🇳 中文</a> ·
  <a href="CHANGELOG.ar.md">🇸🇦 العربية</a>
</p>

All notable changes to **YouTube Harvester** are documented here.

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
