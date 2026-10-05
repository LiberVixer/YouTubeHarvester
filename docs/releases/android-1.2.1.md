# YouTube Harvester 1.2.1 for Android

Stable, final Android release approved by the maintainer. Version `1.2.1`,
version code `120100`, minimum Android 8/API 26. Four variants: arm64-v8a,
armeabi-v7a, x86 and x86_64. These are the accepted signed R2 APKs, unchanged
and not recompiled or re-signed for publication.

Permanent certificate SHA256:
`25bec4a973717a990f023b7dc07b2588629883c268d71ed820956c0f8bca23ca`.

## Files

- Four `YouTubeHarvester-1.2.1-<ABI>-release.apk` installers.
- `YouTubeHarvester-1.2.1-android-source.tar.gz`: application and packaging sources.
- `YouTubeHarvester-1.2.1-runtime-sources.tar.gz`: complete reviewed R5 source/build-input bundle, including native runtime, Python modules, JVM/AndroidX inputs, generators, NDK/LLVM and original notices.
- `SOURCE-REVIEW-android.json`: exact APK/source bindings and review scope.
- `THIRD-PARTY-NOTICES-android.zip`: 957 unchanged original notice files.
- `LICENSE-android.txt`, `NOTICE-android.txt`, `BUILD-INFO-android.json`, `SHA256SUMS-android.txt`.
- `controlled-runtime-replacements-20261005-r2.zip`: pinned rebuilding payload, not an installer.

The application is GPL-3.0-only; upstream components retain their own licenses.
The exact signed x86_64 APK passed LDPlayer Android 14/API 34 download,
FFmpeg merge/publication and archive-persistence acceptance. All four APKs
passed signature, manifest, ZIP alignment and applicable native-alignment checks.
The maintainer confirmed working builds and approved publication; attached
reports retain the actual automated test scope and deferred checks rather than
claiming that every Android device was tested.

Choose the APK matching your device ABI. An old tester signed with a different
certificate cannot be overwritten by these APKs; preserve/export data before
any uninstall.

Linux DEB/source, Windows EXE/MSI/portable and these four APKs are also available
from the [main 1.2.1 release](https://github.com/LiberVixer/YouTubeHarvester/releases/tag/v1.2.1).
