# FFmpeg WebP runtime repair

The upstream `ffmpeg:0.18.1` AAR is unchanged except for five WebP libraries per ABI.
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
