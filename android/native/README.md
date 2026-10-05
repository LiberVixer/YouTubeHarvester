# Controlled Runtime Payloads

The Gradle build retains the upstream 0.18.1 wrapper classes but replaces every
native entry of the library and FFmpeg AARs. No upstream Python/FFmpeg payload
is retained. `controlled-artifacts.json` pins the producing build inventories;
`controlled-payloads.properties` pins the resulting replacement bundle.

With the downloaded and verified core/extension artifacts retained in their
recorded `android/build` locations, run from the repository root:

```sh
python3 android/scripts/package_controlled_payloads.py --android android \
  --inputs android/native/controlled-artifacts.json \
  --ndk /path/to/android-sdk/ndk/28.2.13676358 \
  --output android/build/controlled-payloads-20261005-r2/runtime-replacements.zip
```

The output directory must not already contain the target ZIP. Payload assembly
checks package hashes, ELF architecture, non-system dependency closure and
64-bit 16 KB alignment. It includes Cryptodome 3.23.0 and Mutagen 1.47.0 and
records each packaged file's producing package and hash in the adjacent JSON.
All payload symlinks are relative and remain inside `usr/`.

Use Android's platform `libmediandk.so`, not Termux's same-named compatibility
shim. Bundling the shim shadows the system library and breaks the system native
dependency graph. Assembly checks every imported shim symbol against the pinned
NDK's API 26 platform stub for each ABI before excluding it from the payload.
This does not substitute for API 26 device acceptance.

For a fresh checkout with GitHub access, restore the pinned prepared bundle:

```sh
python3 android/scripts/fetch_controlled_payloads.py --android android
```

Until publication it is a draft-release asset and requires authenticated read
access. CI uses its read-only GitHub token. A missing asset or mismatched hash
stops the build; no old runtime fallback is used. Existing local bundle files
are checked and never silently replaced.

Downloading the recorded artifacts and unpacking their
`runtime-packages.tar.gz` reuses compiled intermediates; it is NOT a source
rebuild. For actual compilation, use the pinned Termux recipes and
`scripts/build_controlled_runtime.sh`, then rebuild the launchers/QuickJS and
review the new package inventories before assembling. See
[source rebuild procedures](../legal/SOURCE-REBUILD.md). Rebuilt bytes must not
be silently accepted under the old artifact hashes. Existing accepted signed
APKs can be packaged without rebuilding or resigning them.

## Previous WebP Repair

Earlier candidates changed the upstream `ffmpeg:0.18.1` AAR only for five WebP libraries per ABI.
`scripts/patch_ffmpeg.py` replaces those ELF payloads during the Gradle build;
the upstream AAR remains covered by Gradle dependency verification.

- Source: official libwebp 1.6.0, included as `libwebp-1.6.0.tar.gz`.
- Source URL: https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-1.6.0.tar.gz
- Source SHA-256: `e4ab7009bf0629fd11982d4c2aa83964cf244cffba7347ecd39019a9e38c4564`.
- Android NDK: `28.2.13676358`, minimum API 26, Release, shared libraries.
- Linker: `-Wl,-z,max-page-size=16384`.
- Bundle SHA-256: `cc5adfc8ac62b4213f044c931f55d4275a4c3f69e24240a19ef8a93c7a477162`.

Rebuild with `python3 scripts/rebuild_webp.py --ndk /path/to/ndk/28.2.13676358`.
Review outputs and update the pinned bundle hash when rebuilding. The source is
unmodified. The bundle includes upstream COPYING, PATENTS and AUTHORS; include
the source archive and rebuild script in the corresponding release sources.
This does not replace source obligations for the rest of FFmpeg and its codecs.
