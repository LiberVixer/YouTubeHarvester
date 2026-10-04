# Android dev31 security checkpoint

Scope: the Android dev30 APK findings supplied in `error.txt`. This work does not
change desktop download behavior or publish a GitHub release.

| Finding | Result | Remaining acceptance |
| --- | --- | --- |
| Debug APK distributed | `legacyBeta` is optimized, non-debuggable and excludes debug tooling; internal debug uses a separate package ID | The legacy certificate is retained ONLY for existing testers. Permanent-key migration is not complete |
| Unverified runtime download | Removed runtime self-update; pinned yt-dlp 2026.08.19 in the APK; SHA-256 checked at build and initialization; atomic replacement of old engine | Test a dev30 upgrade on a phone with a previously downloaded engine |
| Network while holding global runtime lock | Initialization has no network calls; APK updater remains separate | Offline diagnostics on real hardware |
| Exported debug screens | Absent in all four legacyBeta APKs; public packager rejects them | Keep final-artifact checks when dependencies change |
| Exported action reads clipboard | Action only requests Overview; clipboard watcher is opt-in; explicit Quick tap is unchanged | Instrumentation test compiled; execution on phone/emulator pending |
| Uppercase HTTPS rejected | Fixed for video and channel URLs; ID case and URL restrictions preserved | JVM regression tests pass |
| APK/source provenance | Public packager validates tag/commit, exact package/version, approved certificate and emits BUILD-INFO | Android sources/tag/release are not published in this task |

## Signing and migration

Do not uninstall dev30. The private dev31 legacyBeta APK has the original package
ID, a higher versionCode and the same certificate, enabling an in-place update.
No claim is made that a debug certificate becomes a secure release identity by
disabling debugging. The packaging tool rejects that certificate for publication.

Before a public release, choose and securely back up a permanent signing key,
approve the Android license, complete the native corresponding-source bundle,
and implement/test migration to a differently signed APK. A new key cannot
silently replace the certificate of an existing installation.

## Engine trust

The upstream release digest was checked before pinning the engine. A digest
from the same upstream release is not an independent publisher signature. The
reviewed pin and engine are then covered by source review and APK signing.
Runtime initialization checks the installed bytes on each process start before
the first engine execution; it does not download replacement executable code.
Copy/verification failure throws and prevents engine initialization.

## Verification boundary

Local JVM and packaging-script tests cover URL restrictions, bundled-file restore,
corruption, interrupted copy, manifest checks and certificate policy. APK checks
also inspect the bundled bytes and 16 KB ZIP alignment. Instrumentation tests
compile, but no device is attached. Live YouTube/VK/Rutube downloads, upgrade data
preservation, background lifecycle and external-intent behavior still need device
acceptance. This is not a claim that the entire application is vulnerability-free.

The report's separate desktop recommendations (release-job token privileges,
independently signed update manifests and Windows Authenticode) remain outside
this Android patch. Authenticode and permanent APK signing require real signing
identities and an approved key-management procedure.
