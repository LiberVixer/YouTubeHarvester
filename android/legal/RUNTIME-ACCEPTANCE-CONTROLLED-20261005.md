# Controlled Runtime Acceptance: 2026-10-05

Device: LDPlayer, Android 14/API 34, x86_64. Updated the installed application
without clearing data. On-device APK SHA-256 matched the signed candidate:
`6767adc98188ff1bac1db29aa31e01476d43f43b6f8927f53494982dd3537213`.
The previous archive entry survived the update; version displayed `1.2.1`.

## Initial Candidate Failure

The application retrieved metadata and track options for `jNQXAC9IVRw`.
Downloading then failed at postprocessing with `ffmpeg not found`.
The native loader reported:

```text
cannot find "libmediandk.so" from verneed[1] in DT_NEEDED list for "/system/lib64/libhwui.so"
```

The payload included Termux's `libmediandk.so` compatibility shim, which shadowed
Android's same-named platform library and broke the system dependency graph.
An earlier loader diagnostic about `libc++_shared.so` occurred before the old
FFmpeg directory was refreshed; the final extracted payload contains libc++.

An isolated probe of the packaged FFmpeg executable failed identically. The same
probe with the platform Media NDK library preloaded printed FFmpeg `7.1.1` and
exited successfully. This workaround was diagnostic only, not an application fix.
The failure is local native loading, not a VPN or video-extractor error.

## Python Probe

Probed the installed packaged interpreter as UID 10084 through emulator `su`:

- Python `3.12.11`.
- Cryptodome `3.23.0`; AES encrypt/decrypt round trip passed.
- Mutagen `1.47.0`.
- OpenSSL `3.5.2`; the packaged certificate store loaded successfully.

The probe retained the emulator's privileged `su` SELinux domain; it is not
application instrumentation. The successful metadata request exercised the
application's normal runtime and network path.

## Packaging Repair

Treat `libmediandk.so` as a platform dependency, excluding the Termux shim from
the FFmpeg payload. Before assembly, check all imported shim symbols against the
pinned NDK's API 26 platform stub separately for each ABI. Record the stub hash
and imported symbols in the replacement bundle's adjacent JSON. Preserve all
original producing packages and source archives; no compiler output is patched.

Regression checks cover the shim exclusion and rejection of imports unavailable
at the minimum API. All four ABI checks found the same 29 imports, all available
in the respective API 26 stub. This is static compatibility evidence, not API 26
device acceptance. The repaired bundle SHA-256 is
`51763e9219ea1087860a8dc328362e3b126f43af6df9a0b3c1a2a84ac23fa7a7`.
It is pinned as the `controlled-runtime-replacements-20261005-r2.zip` asset in
the existing draft release; its server digest matches. The prior bundle and all
previous signed APKs remain preserved.

Release assembly and vital lint passed in 51 seconds. All six replacement
payload entries per ABI matched the repaired bundle byte-for-byte after APK
packaging. The shim is absent from all four FFmpeg payloads. Packaged manifests
and ZIP alignment passed for every unsigned APK; the two 64-bit APKs passed
215 and 217 native ELF alignment checks. There are 32 passing controlled-runtime
regression tests.

## Exact Repaired APK Acceptance

All four repaired APKs were signed with the permanent owner-approved certificate.
Independent signature, manifest, ZIP/native alignment and hash checks passed.
The x86_64 APK was installed over the previous candidate; its on-device SHA-256
matched `807ec7b2da0298c7169f68ee18b58f39d1ce23aaba602f439d2dbc557cd752ec`.
Local signed set: `android/build/release-candidate-controlled-20261005-r2/`.

Repeating the same normal application download completed successfully:

- Job `78996ba9-3b8f-403d-8bfa-f6c817e812bb`: `COMPLETED`, 100%, no error.
- Published URI: `content://media/external/downloads/1000000267`.
- File: `Me at the zoo [jNQXAC9IVRw] [240p] (4).mp4`, 535441 bytes.
- Packaged FFprobe, run through emulator root for file diagnostics, identified
  AV1 video at 320x240, AAC audio and duration 19.063583 seconds.
- The extracted FFmpeg directory no longer contains the shim; packaged FFmpeg
  starts without `LD_PRELOAD` or any other workaround.
- Force-stop and relaunch preserved the new archive entry dated October 5.

This is limited x86_64/API 34 acceptance, not ARM, old-API, 16 KB device or full
upgrade-migration acceptance. The complete corresponding-source review remains
unfinished. No release has been published.
