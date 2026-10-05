# Android 1.2.1 Release Candidate

## Current Controlled Candidate: R2, 2026-10-05

The initial controlled candidate below was superseded after a real LDPlayer
download exposed a Media NDK library-name collision. R2 excludes Termux's shim
and uses Android's platform library, with imported symbols checked against
API 26 for all four ABIs. All four R2 APKs are signed with the permanent
certificate; independent manifest, signature, hash and ZIP/native alignment
checks passed, including 432 nested 64-bit ELF files.

Exact signed x86_64 R2 acceptance passed on LDPlayer API 34: YouTube download,
FFmpeg postprocessing, publication to Downloads and archive persistence after
force-stop/relaunch. See [evidence](legal/RUNTIME-ACCEPTANCE-CONTROLLED-20261005.md).
Old candidates remain preserved. The new signed set is under
`android/build/release-candidate-controlled-20261005-r2/`.

| ABI | Signed R2 APK SHA-256 |
| --- | --- |
| arm64-v8a | `daa78e484fa2c32f850d988094782e325544524fe6dce12377b6d8afc1a758ef` |
| armeabi-v7a | `6a184ab1cb59d82aa404bb547280513a7d72132eeffd102cab082ee90dac2faf` |
| x86 | `43361145aa4f1b9bc5ffecb9eb8ed646a7f24c511a41fff520ede796fcf839f9` |
| x86_64 | `807ec7b2da0298c7169f68ee18b58f39d1ce23aaba602f439d2dbc557cd752ec` |

The source preparation snapshot is not yet an approved complete corresponding
source set. Application/JVM source and notice coverage review remains required;
no R2 APK has been published and the release remains a draft.

## Controlled Runtime Candidate: 2026-10-05

Four replacement APKs were signed with the same permanent certificate listed
below, after replacing all six native payload entries per ABI from the pinned
controlled runtime bundle. Version remains `1.2.1`, code `120100`.
Independent certificate, packaged manifest, ZIP alignment and native ELF
alignment checks passed. All four recorded APK hashes were independently
rechecked; 434 nested 64-bit ELF files passed alignment checks.

Local directory: `android/build/release-candidate-controlled-20261005-retry/`.

| ABI | Signed APK SHA-256 |
| --- | --- |
| arm64-v8a | `696ff66919050143536d6baed8c63661b8525d51d265323a396f5cfefff5ef84` |
| armeabi-v7a | `669a6afa2b68a65a64b79f1e92f33bb239db24c04ff6326843756e8f597b54b1` |
| x86 | `ceeb2138fd8d775aa1232c3718d504d8ae17080dafc7125730af0966066ba195` |
| x86_64 | `6767adc98188ff1bac1db29aa31e01476d43f43b6f8927f53494982dd3537213` |

The first signing attempt could unlock the key but could not run APK signing:
the GUI terminal had neither `JAVA_HOME` nor Java on `PATH`. It produced no APKs.
Retry with the explicit JDK succeeded. The helper now checks Java before password
entry, with regression coverage. Neither attempt changed the key or password.

Acceptance of these exact replacement APKs is pending: the Windows SSH tunnel
works, but LDPlayer was stopped and ADB had no device. The earlier acceptance
below applies only to the preserved October 4 candidates. The prepared native
source archive is not yet an approved complete corresponding-source set;
application/JVM source and notice coverage review is still required.
No replacement candidate has been published.

## Historical Candidate: 2026-10-04

Prepared on 2026-10-04. Version code: `120100`. No beta version suffix.

All four APKs have been signed with the owner-approved permanent certificate:
`25bec4a973717a990f023b7dc07b2588629883c268d71ed820956c0f8bca23ca`.
The signing helper checked package/version, non-debuggable policy, exported
components, signing identity and ZIP/native alignment before recording hashes.
Independent rechecks passed for all four hashes and 518 nested 64-bit ELF files.
32-bit ELF page alignment is not counted as a 16 KB device check.

The owner confirmed the key backup is completed. Its independent storage was
not inspected by the agent.

## Exact APK Acceptance

With explicit owner authorization, all seven former Harvester app/test variants
were uninstalled from LDPlayer. This removed their app data and settings.
Other apps, the VPN and shared media files were not removed.

The exact signed x86_64 APK was installed on LDPlayer Android 14/API 34:

- Fresh launch showed `1.2.1`, zero channels, zero queued entries and an empty
  archive.
- A real YouTube download completed: `jNQXAC9IVRw`, 240p, archive title
  `Me at the zoo`.
- Force-stop and relaunch preserved the archive entry.

This is limited acceptance, not a completed full device matrix, migration,
TalkBack, 16 KB system or ARM-device acceptance. The owner requested no further
test expansion while preparing publication. CI/API 26/35 checks are deferred
by the owner's decision, not recorded as passed.

## Publication Blocker

The complete corresponding-source set for the embedded native runtime is not
available. The application source archive and the partial known-source archive
must not be represented as that set. See
[source preparation](legal/SOURCE-PREPARATION-20261004.md).

Stage only a draft release until matching sources are available or the runtime
is rebuilt from controlled sources. Do not disable the public packager's gate.

## Local Artifacts

Signed APKs, checksums and verification data:
`android/build/release-candidate-20261004/` (ignored by Git).
Signing password and private key are not included.
