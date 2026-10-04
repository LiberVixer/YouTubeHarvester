# Android Port Checkpoint

Status: resumed at the user's request on 2026-09-06. Desktop changes are preserved;
Android development remains isolated from Linux/Windows code and packaging.

## Current Development Build

- Storage policy: keep only the latest verified tester APK set in this directory
  (currently 1.2.1, all four ABIs). Older build references below are historical;
  their local APK copies are not retained. See `AGENTS.md` for build/cache upkeep.
- Version: `1.2.1`, version code `120100`.
- Tester APKs: `app/build/outputs/apk/legacyBeta/app-<ABI>-legacyBeta.apk`.
- Available ABIs: `arm64-v8a`, `armeabi-v7a`, `x86`, `x86_64`.
- Physical-phone default: `arm64-v8a`.
- These are private, non-debuggable migration APKs with the old development
  certificate, not a published Android release. Internal debug builds now have
  a separate `.debug` application ID; do not give those to existing testers.
- Android source files are prepared for Git together with Android CI and
  dependency verification. Keep the unrelated desktop changes intact.

## 1.2.1 Version Acceptance (2026-10-03)

All four ABI tester APKs build and pass packaged manifest, certificate, ZIP and
64-bit native alignment checks with version `1.2.1` / code `120100`. The visible
beta badge is replaced by the application version. All 149 JVM, 31 Python and
36 selected LDPlayer tests pass; debug lint has zero errors and 12 warnings.
The separate debug package is updated in place; the main dev33 installation is
untouched. Reports and screenshot: `build/qa-1.2.1/`; the strict offline Gradle
build log is `build/qa-1.2.1-build.txt`.

The root APK set is replaced only after verifying all four builds and copied
checksums. Public signing, corresponding native sources, migration acceptance,
and additional-device checks remain open. This version change does not publish
an Android release or turn private tester signatures into public signatures.

## dev34 Component Acceptance (2026-10-03, Historical)

Updated compatible stable Android dependencies and build tooling, including the
Gradle 9.8.0 Wrapper JAR verified against Gradle's official checksum. QuickJS
2026-06-04 is built from pinned sources for four ABIs; all eight debug/legacyBeta
APKs contain the expected native bytes. Python/OpenSSL/FFmpeg payloads are unchanged.

149 JVM and 30 Python tests pass without skips; 36 selected LDPlayer debug device
tests pass without skips, including bundled-runtime initialization. All debug,
test, and legacyBeta APKs build; strict offline verification succeeds. Debug lint:
0 errors / 12 unused-resource warnings. All 304 new Maven artifact hashes match
official SHA-256 checksums, or official SHA-1 plus independently rehashed cached
SHA-256 where SHA-256 sidecars are unavailable. No verification rules were bypassed.

All four optimized tester copies were verified before pruning the previous dev33
local set. Reports/checksums: `build/qa-dev34/`. Main beta remains dev33; the debug
package alone was upgraded. This is not optimized dev33-to-dev34 migration or
permanent-key public-candidate acceptance. Existing release gates remain open.
Native intermediates cleanup recovered about 786 MiB; app/build is 1.7 GiB and
the preserved shared task-output cache is 1.4 GiB. SDK, dependency caches, current
APKs, reports, mapping files, source archives, and signing material were preserved.
See [all-platform update details](../docs/component-update-20261003.md).

## dev33 Transfer Acceptance (2026-10-03)

Built and verified all four optimized legacyBeta APKs. Installed main beta
dev32 was independently verified against the old certificate, backed up locally,
then updated in place to dev33. No uninstall or data clear was performed.
SQLite schema 10 -> 11 passed integrity_check; hashes of all existing table rows
and the settings bytes remain identical after upgrade and negative import tests.
The baseline contained one archived file and one completed job, no channels,
queue, marks or schedules, so this is not a populated upgrade test of those tables.

Actual optimized Settings/SAF export matches the installed database after
independent AES-GCM decryption and includes the archived file's relink identity.
Wrong-password and nonempty-target imports were rejected. Found and fixed an
invisible result message: success/failure now appears beside the transfer controls
with a polite live region. Both optimized UI outcomes were observed.

149 JVM and 21 Python tests pass; legacyBeta lint has 0 errors / 24 warnings.
Debug device regression: OK (36 tests), including real SAF relinking and the
new result-message test. Same opt-in/API exclusions as the prior 35-test run.
Evidence: build/qa-dev33/. Tester copies and checksums were verified before the
previous local dev32 tester set was pruned. Build storage: 1.9 GiB; shared Gradle
task-output cache: 970 MiB. No build-cache or toolchain cleanup was needed.

Permanent-key/cross-UID follow-up: actual main beta export was imported through
Settings/SAF into a separate non-debuggable `.migrationqa` installation signed
with the approved permanent certificate, without QA app API keep rules. Rows
match safe import normalization; the journal cleared. A newly selected SAF
folder restored the archived file and its name/size/SHA-256 matched the export.
The initial instrumentation runner crashed because application R8 removed
`androidx.tracing.Trace`; QA-only shared API keep rules fixed the runner. The
rebuilt signed QA target passes all six DataTransferTest cases, including
cross-UID old-ciphertext rejection/new-Keystore re-encryption, rollback and journal
recovery. These fixture tests do not replace exact public-candidate acceptance.
27 Python tests pass; main beta rows and settings bytes are still unchanged.
Evidence and limitations: [MIGRATION-QA-dev33.ru.md](MIGRATION-QA-dev33.ru.md).
After all verification completed, regenerable merged/stripped native intermediates
were removed (about 1.14 GiB); app/build is now 1.6 GiB. APKs, mappings and reports
were preserved. Shared Gradle task-output cache is 1.2 GiB and was not pruned.

Historical beta older than dev32, ARM/API26/35+, 16 KB device, TalkBack, complete
runtime sources and advisory review remain open, as does final candidate migration.
See [RELEASE-FIXES-dev33.ru.md](RELEASE-FIXES-dev33.ru.md).

## dev32 Audit Fixes (2026-09-13)

2026-10-03 follow-up: LDPlayer API 34/x86_64 runs the updated debug package;
24 instrumented tests and 134 JVM tests pass. Conditional old-API/SAF paths
remain unexercised. Real debug direct/queue downloads and an optimized
legacyBeta download completed through the user-enabled VPN; both downloaded
MP4s fully decode. The report test now uses an isolated DataStore, preserving
the application's settings. Nine missing dependency metadata checksums were
verified against Maven Central and pinned without disabling verification.
All four legacyBeta APKs were rebuilt, verified and copied to `android/`.
Current arm64 SHA-256 after final Overview validation: `23f4969ff05b8cc6af039edb586f49ba6df4c93b2902c03c5e0bb14f8fb425e8`;
x86_64: `8a2f802c62ae13b1c3fb5f9f1ac68b80d041500fa5f945b4b3afe6b1807f9d39`.
Historical checksums below refer to earlier dev32 builds. Detailed acceptance
results and remaining scenarios are in `TEST-PLAN.ru.md`.

Additional harvest acceptance on 2026-10-03: the canonical Blender channel
discovered and downloaded one 480p video, which fully decoded. A manual URL
added during channel processing was downloaded in the same cycle. Rechecking
skipped the archived video without changing its URI. Cancellation during an
actual transfer removed partial files, and restarting completed without manual
cleanup or duplicate archive variants. Debug settings were restored to 1080p
and five videos; temporary channels and queue items were removed. No network
errors occurred in this run.

SAF follow-up on the same date: actual video publication in QA folder A and
UI selection of B retained both grants and old archive readability. A new
device test cancels copying after the first 64 KiB and verifies partial-file
removal and successful republishing. It exposed repeated SAF deletion throwing
on an already absent document; cleanup now suppresses provider exceptions only
when absence is confirmed. All 26 instrumented tests pass with explicit QA
trees; the opt-in permission-revocation scenario also passes separately.
JVM tests and all four legacyBeta builds pass; verified copies were refreshed.
Debug was updated in place, but installed legacyBeta was not changed. Default
output was restored; folder A remains granted because an archive item uses it.

Accessibility follow-up: fixed clipped Overview actions at fontScale 2.0 by
allowing button height to grow and stacking actions above fontScale 1.3.
Focused full-label tests pass in English and Arabic/RTL at 200%; archive and
settings RTL screens were inspected. All 27 instrumented tests pass at restored
100%/en (conditional SAF/old-API paths remain outside this particular run).
JVM tests and four verified legacyBeta APK builds pass; tester copies were
refreshed. Debug is updated, installed legacyBeta is unchanged. TalkBack is not
installed in LDPlayer and remains untested. Historical APK upgrade remains
pending an old APK; no old build was found locally and Android has no Git history.

Boot recovery follow-up: direct jobs previously depended on opening the app
after reboot. A BOOT_COMPLETED receiver now restarts pending downloads on
API 26-34, leaving paused and terminal jobs alone. API 35+ uses a notification
with a foreground-service Resume action because dataSync services cannot start
from BOOT_COMPLETED on these systems at the current target SDK. Notifications
must be enabled to expose that action; opening the app remains the fallback.
The policy has three new JVM tests, and pending-job filtering and notification
configuration have two new instrumented tests. All 137 JVM, 14 Python and
29 instrumented tests pass (conditional SAF/old-API paths excluded from this run).
Real API 34 reboot during a direct transfer with a 31744-byte partial file
automatically restarted and completed the same job without opening an Activity.
Its final AV1 854x480/AAC MP4 fully decoded; archive has no duplicate and staging
is empty. Debug settings were restored to 1080p/5 and Download/YTH. All four
legacyBeta APKs were verified and tester copies refreshed; installed legacyBeta
is unchanged. LegacyBeta Lint passes with zero errors and 24 warnings, all
about dependency versions or unused resources; none concern the boot receiver.
Real API 35+ boot/Resume acceptance is still outstanding.

Extended live acceptance on 2026-10-03: five cancellation/restart rounds,
two unavailable sources with immediate HTTP 204/200 connectivity checks,
six-item queue/dedup, 500 unselected QA rows with scrolling, and direct download
overlapping manual harvest plus a controlled scheduled worker all pass.
The continuous 30-download run completed in 433 seconds with no retries,
no staging files between batches and no progressive PSS growth in this bounded
run. It is not a multi-day soak. Reboot with two queued and one paused job
completed the queued jobs without an Activity launch; paused bytes and SHA-256
were unchanged, and Resume completed the same paused job. All eight current
archive variants fully decode (138658839 bytes total). Invalid Overview URLs
now show the localized rejection at the field; Queue already shows the error
in its preview, and both screens have focused regression tests. Early failures
of the new live test were timing assertions, not demonstrated service bugs;
the speculative service change was reverted. Production download code was
not changed by this extended stress pass. Final UI regression passes all 27
applicable tests, including both invalid-link tests. SAF opt-ins and the API <=28
sharing test are excluded, not counted as passed. UI-test timing/visibility and
duplicate-message selectors were corrected after initial failed attempts.
All 137 JVM tests pass with no failures/skips, 14 Python tests pass, and lint
reports zero errors/24 warnings. Four legacyBeta APKs were checked for signature,
manifest, ZIP/ELF alignment and copied byte-for-byte to the tester set. Debug was
updated in place; the main installed beta was not changed. No unfinished jobs
remain. Build output is 1.9 GiB, task-output cache 699 MiB; no cleanup was needed.
The user selected public release only after all mandatory gates; see
`RELEASE-READINESS.ru.md`. No publication, tag or certificate change was made.

Initial release preparation before explicit approval: signing helper now refuses existing certificate files and
dangling key symlinks, creates a private new directory under umask 077, exports
the public certificate and prints SHA-256. Four safety tests pass. Actual key
creation was denied by approval review pending an explicit new-key choice.
Separate new-key and Android GPL-3.0-only questions are pending; no license was
adopted or key created. Runtime inventory records packaged paths, SHA-256 and
ELF NEEDED for four ABIs, without claiming source correspondence. Actual x86_64
banners show Python 3.12.11, FFmpeg 7.1.1, QuickJS 2025-04-26, OpenSSL 3.5.2 and
Cryptodome 3.23.0. NOTICE includes the last two components. Source and security
audit work is listed in `legal/RUNTIME-PROVENANCE.ru.md`. All 21 Python script
tests pass. App/APKs unchanged; beta export/import remains unimplemented.

Owner approval received on 2026-10-03: new permanent key and GPL-3.0-only for the
Android module were explicitly authorized. `android/LICENSE` exactly matches
the proposed GPLv3 text; scope is recorded in legal/README and NOTICE, with
desktop and third-party licenses unchanged. The owner entered the password only
in the local terminal; the new PKCS12 key has alias yth-android and RSA 4096.
Private key mode is 0600 in a 0700 directory outside Git. OpenSSL confirmed the
public certificate self-signature and SHA-256:
`25bec4a973717a990f023b7dc07b2588629883c268d71ed820956c0f8bca23ca`.
Only the public certificate was added under `signing/`. The owner-selected
`/media/sf_Data/Android-signing` now contains no-clobber copies of release.p12
and release.cert.pem, with both file SHA-256 hashes verified against originals.
This is a VirtualBox host shared folder exposing mode 0777, not a verified
independent external drive. Host access restrictions and an independent offline
backup remain unconfirmed; no password was copied and R01 is not complete. No public
candidate was signed/published and no beta data was removed. Source runtime,
beta migration and device matrix remain outstanding.

Data-transfer implementation checkpoint (2026-10-03): Settings now offers a
password-encrypted .ythbackup export/import via system document pickers. The
format uses AES-256-GCM and PBKDF2-HMAC-SHA256 (600000 iterations), strict
bounded JSON, and read-back verification of exports. Channels, queue, archive,
hidden marks, schedules, jobs and settings/Telegram credentials are portable;
videos/staging and SAF grants are not. Imports refuse nonempty databases,
pause unfinished jobs, disable schedules, discard old publication ownership,
and re-encrypt credentials under the destination Keystore. Schema 11 adds an
encrypted pending-settings journal for crash recovery and archive relink hints.
Relinking requires an explicitly selected folder and matching name/size/SHA-256;
old MediaStore IDs are not trusted. Unreadable available files/credentials block
complete export. The password dialog is scrollable and screenshot-protected.
All 149 JVM and 21 Python tests pass; debug lint has zero errors/24 warnings.
Initial isolated LDPlayer migration tests passed (5 including schema migration)
and the real SAF relink/tampering test passed separately. Final combined device
regression passed: OK (35 tests), including two password-dialog UI tests and
unreadable archive/credential rejection. Live, old-API and separate old SAF
opt-in tests were excluded, not counted as passes. Evidence is recorded in
build/qa-dev32/transfer-regression-20261003.txt. Debug was updated in place;
the existing main beta was neither updated nor uninstalled. Build output is
1.9 GiB and the shared task-output cache is 801 MiB; no cleanup was needed.
See DATA-TRANSFER.ru.md for remaining gates. No public release or optimized
beta-exporter was produced, and the main beta remains untouched.

Implemented A01/A08 shared durable harvest, A02 retained SAF grants, A03 rebuilt
WebP runtime libraries, A04 legacy archive content sharing, A05/A06 explicit
track mapping, A09 secret recovery, A10 settings draft protection, and A11
verified output metadata. A07 was a false positive: the existing SQL CASE
already protects members-only status; an instrumented regression was added.
Schedule clock changes and unsupported Telegram proxy options are handled too.

The implementation/acceptance record is [RELEASE-FIXES-dev32.ru.md](RELEASE-FIXES-dev32.ru.md).
Do not publish as final until the device matrix and R01/R02 are closed. The device
matrix is incomplete; only LDPlayer API 34/x86_64 is currently exercised.
Keep desktop changes and the existing tester signature.

Historical dev32 validation (2026-09-13): 126 JVM tests, 12 Python tests (including real media
mux and locale parity), release Lint with zero errors/13 warnings/one hint,
four legacyBeta APKs and four unsigned release APKs. Instrumentation compiles
but has not run. All tester APKs pass manifest/certificate/ABI/ZIP checks and
contain the exact bundled engine/plugin bytes. Recursive checks cover 258
ARM64 and 260 x86_64 ELF files. The FFmpeg archive size changed on all four ABIs,
so the upstream size-based runtime cache will recognize this replacement.
Installable copies: `YouTubeHarvester-1.2.0-beta-android-dev32-<ABI>.apk`.
Checksums and verification records are under `build/`; the arm64-v8a checksum
is `c0e8cfd1f4a466aa53a8ff09af2868628eb107a8f7b3c5d5fb984887570465f4`.
No commit/push/tag/public release, permanent key or license adoption was made.

## Pre-release Audit (2026-09-12, Historical)

The read-only audit is recorded in [AUDIT-PRE-RELEASE-dev31.ru.md](AUDIT-PRE-RELEASE-dev31.ru.md).
The original report listed eleven findings (A07 was subsequently retracted):
manual-cycle lifetime, SAF grant retention, nested FFmpeg ELF 16 KB alignment,
legacy file URI sharing, subtitle mode selection, combined-video audio selection,
members-only status overwrite, scheduled-cycle UI/control, secret decryption failure
handling, settings draft replacement, and actual archive resolution.
The dev32 implementation and current status are recorded above.
Application and desktop source code were not changed by the audit.

All four legacyBeta APKs passed the existing manifest/signature/ZIP verifier again.
However, recursive inspection found five 4 KB-aligned libraries inside each
64-bit FFmpeg runtime archive; outer ZIP alignment does not prove runtime
compatibility. Unit-test reports contain 117 passing tests; six verifier tests
were freshly rerun. The validation build succeeded with incremental caching.
A later forced Gradle rerun was denied by the workspace approval service because
its credit limit was exhausted. Device acceptance and public signing/source/license
requirements remain open; see the audit for reproducible evidence and limitations.

## dev31 Security Checkpoint (2026-09-12)

The supplied dev30 audit is addressed by the Android changes documented in
[SECURITY-dev31.md](SECURITY-dev31.md). The runtime is now APK-only, pinned to
yt-dlp 2026.08.19 and checked/restored before initialization; no network updater
runs under its lock. External Quick intents only request Overview. The explicit
Quick button and opt-in clipboard watching keep their existing behavior.

Verification: 117 JVM tests and six release-verifier tests passed. The full
Gradle run (`testDebugUnitTest assembleLegacyBeta assembleRelease
assembleDebugAndroidTest lintRelease`) succeeded. Release lint has zero errors
and ten warnings (unused resources, state boxing, and a Gradle update advisory).
Instrumented tests compile, including the external-intent regression, but no
phone or emulator is attached, so they have not run. Bundled yt-dlp also reports
2026.08.19 when executed locally with host Python; this is not an Android download test.

All four legacyBeta APKs passed manifest, certificate and 16 KB ZIP alignment
checks. Their embedded engine bytes match the pinned SHA-256. Their signing
fingerprint matches dev30, enabling an in-place update without uninstalling.
Installable copies are `YouTubeHarvester-1.2.0-beta-android-dev31-<ABI>.apk`.
Release APKs also compile and pass manifest checks, but remain unsigned and must
not be distributed. No commit, push, public release, permanent signing key or
license adoption was performed. Desktop code/workflows were not changed.

Before public release: approve the license and permanent key, complete the native
source bundle, implement/test migration to a differently signed APK, execute
device acceptance, then publish the reviewed source/tag and signed release.
The public packager now enforces the approved certificate and records provenance.

## Implemented

The full milestone history is in [README.md](README.md). The port is isolated
from the desktop Python/PyQt application and its Linux/Windows packaging.

- Five Compose screens: Overview, Channels, Queue, Archive, Settings.
- Room-backed queue, archive, download jobs, YouTube/Rutube channels, and schedules;
  DataStore settings; recovery of interrupted download jobs.
- Individual YouTube, VK, and Rutube downloads through embedded yt-dlp,
  FFmpeg/ffprobe, and QuickJS, with audio-track and subtitle selection.
- Foreground download progress/cancellation and MediaStore `Download/YTH` or
  persisted SAF-folder publication. The system picker requires a subfolder,
  not the shared-storage root or the entire Download directory.
- YouTube and Rutube channel discovery, Rutube show collections, per-section
  limits, optional YouTube members-only checks, and WorkManager schedules.
- dev22: "Mark latest..." for enabled channel sections, stored separately from
  the visible archive. Marked items are skipped by automatic discovery, while
  explicit manual links remain downloadable. Marking only commits after all
  enabled sections succeed and never proceeds while downloads are pending.
- dev23: real Overview statistics, persisted queue reordering and safe deletion,
  real VK metadata, archive thumbnails with a non-destructive Room 8-to-9
  migration, accurate diagnostics states, and hardened metadata/download process
  cancellation and failure handling. Download completion updates the job,
  archive, and originating queue item atomically. Settings can also update the
  embedded yt-dlp runtime directly and immediately show the installed version.
- Share intent, quick-download home shortcut, and foreground-only clipboard
  watching; operational archive file actions and filters.
- Telegram notices, thumbnail-cache clearing, component/release links, and ten
  interface languages: en, ru, uk, be, fr, es, hi, zh-CN, ja, ar.
- dev18: private UTF-8 logs with retention, size limits, token redaction,
  viewing, refresh, clear confirmation, and sharing.
- dev19: asynchronous diagnostics with refresh and combined report/log sharing.
  Checks initialize the runtime without updating it, report the installed
  yt-dlp version, and inspect bundled FFmpeg/QuickJS, network capabilities,
  notifications, destination access, storage space, and battery optimization.

Diagnostics are not a complete end-to-end download test: native-library
presence/initialization does not verify an FFmpeg CLI invocation, Android's
validated network flag does not prove YouTube connectivity, and a readable SAF
document plus persisted permission does not prove that an actual write succeeds.

## Verification State

The user requested deferring physical-device verification until all features are
configured. Continue implementation and automated checks without blocking on
phone feedback. Keep the device checklist for the final acceptance pass.

dev23 verification on 2026-09-06: all 76 unit tests passed with no failures or
skips. Android Lint completed with zero errors. Its remaining advisories report
Gradle 9.7.1 and Coil 3.6.2; Gradle 9.6.0 remains the documented default for
AGP 9.4.0. All four debug APKs were rebuilt, copied
into this directory, and verified with APK Signature Scheme v2. `aapt2` confirms
version code `120023`, version name `1.2.0-beta-android-dev23`, target SDK 37,
and exactly one expected ABI per package. Copied APK hashes match their Gradle
outputs: `c1873057…` (arm64-v8a), `2281a767…` (armeabi-v7a), `4241290d…`
(x86), and `050bfd08…` (x86_64). Resource-key parity remains complete across all
ten locales except the intentionally untranslated application name.

dev22 verification on 2026-09-06: 69 unit tests passed, no failures or skips.
Tests cover Rutube URL/source handling, failed and cancelled marking, supported
sections, metadata fallbacks, and the exact non-destructive Room 7-to-8 migration.
A separate in-memory SQLite check confirmed preserved existing rows, independent
source/ID keys, deduplication, and no changes to the visible archive from marks.
Lint completed with zero errors and one existing Gradle-update advisory. All four
debug APKs were rebuilt and copied into this directory, with version code 120022
and matching SHA-256 hashes between the build outputs and copied files.
`apksigner verify` succeeded for all four copied APKs; `aapt2 dump badging`
confirmed version code/name and the expected native ABI in each package.

Read-only live checks on the host used yt-dlp 2026.07.04 with the Android request
options, without loading local downloader configuration or downloading videos.
The Rutube show `/metainfo/tv/405933` returned its three latest episodes in the
expected order, and `/channel/23704195/videos` returned valid Rutube entries.
Public metadata returned the show's own poster/name and the channel's avatar.
These checks do not replace an end-to-end test of the embedded Android runtime.
New strings are present in all ten locales; brand-name fallback and locale-specific
plural forms are intentional.

dev21 connects the formerly inactive top-bar theme/menu buttons and channel
filter button, adds translated filter labels and filter unit tests.
Verification on 2026-09-06: 46 unit tests passed with no failures or skips;
lint has zero errors and one existing toolchain-update advisory. All four APKs
were rebuilt after the RTL icon adjustment and copied into this directory.

dev20 fixes scheduled-check successor duplication on retries/cancellation and
local-time calculation after a daylight-saving gap. Three clock-change tests
were added. Verification on 2026-09-06: 42 unit tests passed, no failures or skips;
lint completed with zero errors and one toolchain-update advisory. All four debug
APKs were built and copied into this directory with version code 120020.

Last saved local reports (2026-09-02): 39 Android unit tests passed with no
failures or errors. The preceding development run also completed lint and built
all four APK variants. No new build or test run was needed for this documentation
checkpoint.

Device-specific verification remains open; do not describe all platforms,
languages, schedules, or runtime paths as physically tested. Earlier user
feedback confirmed several phone workflows, but not every dev19 diagnostic.

## Resume Here

dev30 changes only the Overview Quick action: clipboard extraction now goes
directly to downloadQuickLink with the configured resolution, bypassing the
options sheet. The control waits for settings to load. Invalid text does not
start a job; share intents and launcher shortcut behavior are unchanged.

Local dev30 verification: 108 JVM tests passed with no failures, errors or
skips. All four debug APKs compiled and pass signature verification and 16 KB
ZIP-alignment checks. The final Lint report contains zero errors and six
existing advisories. Version code is 120030; the certificate matches dev29.
Installable copies are `YouTubeHarvester-1.2.0-beta-android-dev30-<ABI>.apk`.
arm64 SHA-256: `b7ae794d626b7e9ec6f6d9c373a13da000a795ba0fc93825cc455f330e69ef9c`;
the copy matches the Gradle output. Clipboard-to-download behavior has not
been exercised on a physical phone in this development step.

dev29 rearranges actions: Quick is between Add to queue and Download below the
URL; Downloads opens the destination folder from the bottom bar between Archive
and Settings without changing tabs; Clear temporary files is a full-width
Overview button with the Material broom icon. Cleanup behavior is unchanged.
Check bottom-bar labels and the three URL actions on a narrow phone.

Local dev29 verification: 108 JVM tests passed with no failures, errors or
skips. Debug and instrumentation APKs compiled; Lint reports zero errors and
six advisories (Gradle version and unused legacy resources). All ten locale
resource-key sets match. Four ABI APKs pass signature and 16 KB ZIP-alignment
checks; the signing certificate matches dev28. Installable copies are
`YouTubeHarvester-1.2.0-beta-android-dev29-<ABI>.apk`, version code 120029.
arm64 SHA-256: `3fe8fabc12170db80b65c0ab6afe3db616cec046ceaedb254aa5ae54273b3fc0`.
The copied APK matches the Gradle output. No physical-device or screenshot
verification was performed for the rearranged controls.

dev28 implements the approved Overview channel-identity layout. Avatar/name
and the circular action button are above the check heading/count/time row.
OverviewChannel selects only the actively checked channel; idle and queue-only
phases use the same overview-logo.png bytes as desktop. Fresh scanner metadata
is forwarded to the UI before discoveries are downloaded. Check avatar loading,
rapid channel changes, failure fallback and idle state on a physical device.

Local dev28 verification on 2026-09-07: 108 JVM tests passed with zero failures,
errors or skips. Debug APKs and the instrumentation APK compiled. The final
Android Lint report has zero errors and five existing advisories (Gradle version
and unused legacy labels). All four ABI packages pass signature verification
and 16 KB ZIP-alignment checks; the certificate matches dev27. Version code is
120028. Installable copies are
`YouTubeHarvester-1.2.0-beta-android-dev28-<ABI>.apk` in this directory.
The arm64 copy matches the Gradle output, SHA-256
`904f2f7b6a60704a707a861df47cd28b30344ae096c92612bb3cd39e578de1a9`.
No phone is attached: instrumentation execution and native visual acceptance
remain unverified. All ten locales contain the new channel-checking label.

dev27 implements the Overview lower-panel reference. CheckReport is saved in
DataStore by the harvest runner (manual and scheduled), independently of preview
messages. Section progress includes inspected counts, per-section states and
actual error totals. DailyDownloads uses completed jobs plus legacy archive
fallback deduplicated by publication URI. No desktop code was changed.
Check the new report after a successful, failed, stopped and scheduled cycle,
then restart; compare daily totals for videos/shorts/streams and test narrow
screen wrapping. Unit tests cannot confirm native Compose rendering on a phone.

Local dev27 verification on 2026-09-07: 101 JVM tests passed with zero failures,
errors or skips. Debug and instrumentation APK compilation and Android Lint
completed successfully. Lint reports zero errors and five advisories (Gradle
version and four unused legacy labels). All ten locales have matching resource
keys and matching format placeholders for the new Overview labels. All four
ABI APKs pass signature and 16 KB ZIP-alignment checks. Version code is 120027;
the signing certificate is unchanged from dev26. Installable development copies
are `YouTubeHarvester-1.2.0-beta-android-dev27-<ABI>.apk` in this directory.
arm64 SHA-256: `c98316c53bd6c4d7d28c70e5c7aafe38dea9ea41f156b9954ebcee386f8492c3`;
the copied APK matches the Gradle output. ADB has no attached device and no
emulator is installed: the new DataStore instrumentation test and visual/device
acceptance have not run. Existing dev26 data has no saved check report; run one
harvest cycle in dev27 to populate it. Section counts refer to the most recently
inspected channel, not all channels combined.

dev26 changes the Overview layout and separates direct URL downloads from the
round full-cycle button. HarvestCycleRunner performs queue-before, channel
downloads (awaiting each result), and queue-after; scheduled checks use the same
runner. ChannelCheckRunner now delivers discoveries through an optional suspend
callback, never by inserting into the visible queue. Channels-tab validation and
mark-only checks do not download. Legacy channel queue records are converted to
paused internal jobs during repository initialization so links are preserved.
Test on a phone: a queue-only cycle with no channels, a link added during channel
scanning, immediate Download while another job runs, stop/pause/resume, and
Overview layout in Russian plus a long-text locale. No physical result implied.

Local dev26 verification on 2026-09-07: all 93 JVM tests passed, with no
failures, errors or skips. Debug compilation, all four ABI APKs, the device-test
APK, and Android Lint completed successfully. Lint reports zero errors and four
warnings (the Gradle-update advisory and three unused legacy strings). Resource
keys are complete across all ten locales. APK signatures and ZIP alignment with
16 KB pages pass for all four packages; the signing certificate matches dev25.
Installable copies are `YouTubeHarvester-1.2.0-beta-android-dev26-<ABI>.apk` in
this directory, with version code `120026`. The arm64 copy matches its Gradle
output (SHA-256 `d45799381069120dcc9bdfe993ddd93dcd3fe5ba80459b7ea1da31e829fc213c`).
Instrumentation tests were compiled, not executed; phone layout, background
service restrictions, and real download acceptance remain unverified.

dev25 implements the ROG Phone 7 / Android 15 beta-report follow-up: persistent
failed-job cards, bounded network retry, pause/resume with staging retention,
per-item queue downloads, and destination-aware folder navigation. New strings
cover all ten locales. Room schema 10 adds a durable automatic-retry counter.
Check the dev25 section in README before resuming work. Physical acceptance
must cover airplane mode, pause during startup/download, resumed multi-track
downloads, notification actions, alternate SAF folders, and upgrade from dev24.
Do not claim those phone scenarios passed based on compilation or JVM tests.

Local dev25 verification on 2026-09-07: 87 JVM tests passed, zero failures,
errors or skips. Device integration and schema migration tests compile but
have not run on hardware; ADB reports no attached devices. Debug APKs for
arm64-v8a, armeabi-v7a, x86 and x86_64 pass signature verification and ZIP
alignment checks with 16 KB pages. Installable development copies are named
`YouTubeHarvester-1.2.0-beta-android-dev25-<ABI>.apk` in this directory.
The debug signing certificate matches dev24. Release lint reports zero errors;
its two warnings concern a newer Gradle version and an unused old stop label.

dev24 verification checkpoint (2026-09-06): 82 JVM tests passed with zero
failures, errors or skips. Release lint reports zero errors and one Gradle
update advisory. The device-test APK compiles; instrumentation tests have not
been executed on a phone or emulator. All four debug APKs pass ZIP alignment
checks with 16 KB pages. The arm64 debug signing certificate matches dev23,
so the development update does not require uninstalling the previous build.
Installable copies are named `YouTubeHarvester-1.2.0-beta-android-dev24-<ABI>.apk`
in this directory. These are development builds, not signed public releases.
Public packaging additionally requires a reviewed, complete corresponding-source
archive for the bundled native runtime; upstream source links alone are not
treated as that archive.

dev24 implements the Android audit fixes except finding 10 (paid-content logic).
See README dev24 and RELEASING.md for queue/publication recovery, Keystore,
system locales, the signed GitHub APK updater, dependency verification and CI.
Permanent release signing and the Android project license require the owner's
pending decisions; do not silently adopt a license or publish a debug certificate.
Device tests are implemented but require an emulator or attached test phone.
Keep Android changes isolated from the uncommitted desktop Rutube fixes.
Do not commit, push, or publish either worktree without a new user request.
Continue from the remaining acceptance and hardening checklist, not from a new
Android scaffold. The following device checks remain deferred at the user's
request until feature completion:

1. Install the latest dev build on the physical arm64 phone and verify diagnostics refresh and
   report sharing, plus log viewing, clearing, retention, and sharing.
2. Verify channel discovery, paid-content status, cancellation, and scheduled
   checks across process restart, device reboot, and battery-saving modes.
3. Verify shared links, the launcher shortcut, and archive open/share actions
   using both MediaStore and a user-selected SAF folder.
4. Verify multiple audio tracks and embedded subtitles on representative
   YouTube, VK, and Rutube videos; preserve any failing job/log for diagnosis.
5. Check all ten locales on a physical phone, especially Arabic RTL and long
   French text; verify network-image failure fallbacks and real channel artwork.
6. Add a Rutube numeric channel, the same channel via its `/u/` alias, and a
   `/metainfo/tv/` show. Verify deduplication, artwork, supported sections, and
   queue/archive source labels.
7. Mark recent items, restart the app, and run manual/scheduled checks. Confirm
   marks stay invisible in the archive and are not downloaded automatically.
   Repeat with a failed request/cancellation and confirm no partial marks.
   An explicitly submitted link is intentionally still downloadable.
8. Fix confirmed issues, rerun unit tests/lint, and build the next development
   APKs. Keep desktop behavior and packaging unchanged.

## Local Build

Run from `/home/redmin/YTD/android`:

```bash
JAVA_HOME=/home/redmin/.local/share/yth-android-toolchain/jdk17 ANDROID_HOME=/home/redmin/Android/Sdk ./gradlew testDebugUnitTest lintDebug assembleDebug --no-daemon
```

Toolchain: JDK 17, Gradle 9.6.0, AGP 9.4.0, compile/target SDK 37, minimum SDK 26.
Outputs are under `app/build/outputs/apk/debug/`; architecture-specific copies
for completed development checkpoints are kept in this directory.
