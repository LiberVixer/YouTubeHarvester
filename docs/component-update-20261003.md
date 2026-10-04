# Component Update, 2026-10-03

This is a development update, not a published release or an upgrade of every
installed copy. Existing running applications and user downloads were left alone.

## Desktop

- yt-dlp remains on the reviewed latest stable `2026.08.19`; yt-dlp-ejs `0.8.0`,
  PyQt5 `5.15.11`, pynput `1.8.2`, and Pillow `12.3.0` remain unchanged.
- PyInstaller is now `6.22.3`. Windows and Linux lock files pin their complete
  dependency graphs, including updated charset-normalizer `3.5.2`, idna `3.20`,
  pyinstaller-hooks-contrib `2026.8`, urllib3 `2.8.0`, and websockets `17.2`.
- Linux's Qt wheel is `5.15.19`; Windows's compatible Qt wheel remains `5.15.2`.
- Deno `2.9.7` and FFmpeg `9.0.2` are staged under `tools/<platform>/`.
  Linux FFmpeg is the pinned BtbN GPL build
  `n9.0.2-22-g46d8f462ee-20261001`, not an unmodified upstream tag build.
- `scripts/fetch_desktop_tools.py` pins archive URLs and SHA-256 digests,
  verifies before publishing each tool, and refuses existing target directories.
- The launcher gives explicit environment overrides priority, then selects local
  tools before system PATH. An incomplete FFmpeg/FFprobe pair is not selected.
- `start_tray.sh` prefers the project's isolated `.venv`; `YTD_PYTHON` can
  explicitly select another interpreter. The Debian launcher uses this script.
  Debian still relies on distribution packages unless a separate environment is
  provisioned. It does not download packages or upgrade system Python in postinst.

Verified locally: isolated Python 3.12 environment, `pip check`, 79 desktop tests,
Linux FFmpeg H.264/AAC generation and FFprobe inspection, Linux Deno JS/crypto,
and Qt runtime `5.15.19` initialization through the actual XCB plugin.
The downloaded Windows executables passed the same version and media/JS checks on
Windows over the existing SSH connection. PyInstaller successfully built the
complete Windows application offline after Windows PyPI DNS resolution failed.
Windows tests: 77 pass, 2 POSIX-only updater fixtures skipped. The frozen EXE
passed waited subprocess checks for yt-dlp/helper execution and downloaded a
local MP4, remuxed it to MKV with bundled FFmpeg, and produced valid metadata.
Windows installer generation and interactive GUI acceptance remain pending.

## Android dev34

Pins updated: AGP `9.4.1`, Gradle `9.8.0`, Compose compiler `2.4.20`, KSP `2.3.12`,
Compose BOM `2026.09.00`, Core KTX `1.19.1`, AppCompat `1.8.0`, Room `2.8.5`,
WorkManager `2.12.0`, Coil `3.6.3`, Jackson BOM `2.22.3`, and debug-only Kotlin
serialization BOM `1.11.0`. Existing stable Activity, Lifecycle, and DataStore pins
are retained instead of adopting alpha releases.

QuickJS `2026-06-04` is rebuilt from the pinned official source for all four ABIs,
using API 26 and 16 KB ELF alignment. The patched library retains upstream Java
classes and Python assets. See `android/native/QUICKJS.md` for hashes and recipe.
The local file-AAR dependency explicitly restores its required Maven dependencies.

Verified: four native builds/alignment, 30 Android Python tests, x86_64 QuickJS
smoke on LDPlayer, and upstream language/builtin/bigint/closure/loop test suites.
All debug/test/legacyBeta APKs built successfully. An offline strict-verification
repeat succeeded. JVM tests: 149 pass, no skips. LDPlayer selected device
regression: 36 pass, no skips. Debug lint: 0 errors, 12 unused-resource warnings.
All four non-debuggable legacyBeta APKs passed certificate/manifest/zipalign/native
checks; new QuickJS bytes match the reviewed replacement in all eight debug/beta
APKs. Evidence is under `android/build/qa-dev34/` and `android/build/`.
The installed main beta remains dev33; only the separate debug app was upgraded.
All 304 added/changed dependency artifact hashes were independently checked
against official Maven checksum files: SHA-256 where available, otherwise SHA-1
plus the cached artifact's recomputed SHA-256. Existing hashes were retained.
Gradle Wrapper JAR SHA-256 matches the official Gradle 9.8.0 checksum.
The root Android tester set now contains only the four verified dev34 APKs.
Cleanup removed about 786 MiB of regenerable native intermediates after all builds
and tests finished. Current APKs, diagnostics, maps, SDK, and dependency caches
were retained; app/build is 1.7 GiB and the task-output cache is 1.4 GiB.

Not updated yet: Android Python `3.12.11`, OpenSSL `3.5.2`, and FFmpeg `7.1.1`.
These require compatible custom-prefix Android rebuilds, not desktop binaries or
arbitrary Termux packages. ARM execution, other Android API levels, signing/source
correspondence, and existing public-release gates remain open.

## Upstream References

- [yt-dlp releases](https://github.com/yt-dlp/yt-dlp/releases)
- [Deno 2.9.7](https://github.com/denoland/deno/releases/tag/v2.9.7)
- [FFmpeg download](https://ffmpeg.org/download.html)
- [Windows FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/)
- [AndroidX releases](https://developer.android.com/jetpack/androidx/versions)
- [QuickJS source](https://bellard.org/quickjs/)
