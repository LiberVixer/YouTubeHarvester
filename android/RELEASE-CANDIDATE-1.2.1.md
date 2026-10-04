# Android 1.2.1 Release Candidate

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
