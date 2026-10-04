# Android license

SPDX-License-Identifier: GPL-3.0-only

The owner explicitly approved GPL-3.0-only on 2026-10-03. `android/LICENSE`
contains the complete GPL version 3 text, unchanged from the proposed copy.
This applies to the Android application module only. It does not change the
desktop application's license or the licenses of third-party components.
The third-party corresponding-source bundle remains a separate release gate.

## Runtime source provenance

Inspected youtubedl-android tag `0.18.1`, commit
`d725d5c9a18c3a99a13ee0308bf78275dc310760` (annotated tag object
`864791ae478e5e32194722337286790829c0a689`). The Maven AARs and embedded runtime
are fixed by Gradle verification hashes.

Upstream includes its GPL-3.0 text, Kotlin sources and bundled binaries. Its
BUILD_FFMPEG.md and BUILD_PYTHON.md refer to Termux build recipes without pinning
the revisions used for every bundled binary. These documents alone do not establish
a complete corresponding-source set for the packaged native runtime.

Before public distribution, obtain or reconstruct the matching source versions,
patches, license texts and build scripts for Python, QuickJS, FFmpeg and all bundled
codecs/libraries. Review the resulting archive and record its SHA-256 in the release
environment. The release packager deliberately fails without that archive.
