# R2 Application Source Coverage

This extends the [controlled runtime audit](CONTROLLED-SOURCE-AUDIT-20261005.md).
It records source evidence for the exact signed R2 candidates, not approval to
publish or a claim of reproducible compilation of every upstream component.
No application code, runtime payload or signed APK was changed by this audit.

## Resolved Dependencies

`scripts/export_release_dependencies.gradle` exports Gradle's actual
`releaseRuntimeClasspath` artifacts under normal offline dependency verification.
After deduplicating two identical resolution variants, the graph contains
132 unique artifacts: 130 Maven dependencies and two locally patched wrapper
AARs. BOMs and unselected multiplatform metadata are not counted as binaries.

`scripts/collect_jvm_sources.py` preserved all 130 official version-matched
source JARs and POMs, plus embedded binary notices. No source URL returned 404.
The collector does not change `gradle/verification-metadata.xml` or silently
approve new binary hashes. Downloaded source hashes are provenance records,
not independently verified upstream signatures.

Local inventory: `build/jvm-sources-20261005-r3/JVM-SOURCE-INVENTORY.json`.

## AndroidX Native Code

The Maven source JARs do not contain the two AndroidX native libraries' C++
sources. Official release-note commit ranges identify these snapshots:

- [graphics-path 1.0.1](https://developer.android.com/jetpack/androidx/releases/graphics#graphics-path-1.0.1):
  `8a05a22af450d589ef911d772a001a49dcb05b71`.
- [DataStore 1.2.1](https://developer.android.com/jetpack/androidx/releases/datastore#1.2.1):
  `03aea68c431abd3fa436e9f8fa9b9cda12f18334`.

Both module source trees, native build recipes, `buildSrc`, root build settings,
version catalogs and Apache license text are preserved. All four graphics-path
and 41 datastore-core Kotlin files in the official source JARs match these
snapshots byte for byte.

All eight packaged AndroidX native libraries across the four signed APKs match
their resolved AAR producers. Where Gradle removed debug symbols, the pinned
NDK's `llvm-strip --strip-unneeded` reproduces the APK bytes exactly. The audit
records the strip tool hash and transformation. This is not a source-to-ELF
reproducible-build claim.

All six controlled runtime entries per ABI were also compared byte for byte
against the pinned R2 replacement bundle during this audit.

## Bundled yt-dlp and EJS

All 1043 bundled `yt_dlp/*.py` files match the official 2026.08.19 source
distribution; its archive SHA256 is
`072aad4f2a7604e92155f61a275a4752dc64046c8f6d90df3710525d94cd37c1`.

All six bundled `yt_dlp_ejs` files, including both minified JavaScript solvers,
match the official PyPI 0.8.0 wheel. The corresponding source distribution,
Git snapshot `4fb477f4af56880cfd324c48bd4294a2d2294e50`, TypeScript, build
scripts and dependency locks are preserved. astring 1.9.0 and meriyah 6.1.4
package archives match the EJS lock's SHA512 integrity values. Matching npm
`gitHead` source snapshots are retained for their preferred editable sources.
Their licenses are Unlicense, MIT and ISC; see the updated `NOTICE`.

## Repackaged Protobuf

DataStore's `datastore-preferences-external-protobuf:1.2.1` source JAR is empty,
although the binary has 523 classes. The producing AndroidX version catalog
and relocation recipe select protobuf-javalite 4.28.2. Its original source
JAR and complete upstream v28.2 archive, with BSD-3-Clause notices, are retained.
All 523 relocated class names match that upstream artifact's class inventory.
The [subsequent source review](FINAL-SOURCE-REVIEW-20261005.md) verified exact
bytes for all 523 remapped classes and independently compiled all 159 Java
sources. Reproduction of JAR metadata or the upstream source-to-binary build
is not asserted.
Other empty compatibility source JARs were inspected and contain no classes in
their corresponding binary JARs, including nested `classes.jar` files.

Local supplemental inventory:
`build/additional-sources-20261005-r2/APPLICATION-SOURCE-AUDIT.json`.

## Rust Dependencies

The original native preparation archive omitted Cargo's external registry cache.
The producing rav1e Cargo.lock was extracted from each of the four verified core
source-worktree archives. All four locks are identical and select 227 registry
packages. `scripts/collect_rav1e_sources.py` downloads their original `.crate`
archives and verifies every checksum against the producing lock, retaining
notices inside those archives. This is a conservative superset of dependencies
across targets, tools and tests, not a claim that 227 crates are linked into APKs.

The producing build log reports Rust 1.89.0. Its complete source archive includes
standard-library and runtime sources; the pinned Termux recipe specifies SHA256
`0b9d55610d8270e06c44f459d1e2b7918a5e673809c592abed9b9c600e33d95a`.
No core runtime or successful ABI was rebuilt to collect these sources.

## Scope and Remaining Gate

Combined preparation archive:
`build/controlled-payloads-20261005-r2/source-preparation-combined-r2.tar.gz`.
Size: 1,185,933,580 bytes. SHA256:
`67e62fa51d0163ac3520b57b07e992515c270978967811efb92cbb657d922099`.
A separate streaming read independently verified all 3724 file inventory
records, including preserved source symlink targets. The archive contains
151 original native source archives, all 130 Maven source JARs/POMs, all 227
locked Cargo crates and the recipe-pinned Rust source archive. The producing
core/extension recipe archives, override patches, Dockerfiles and runtime locks
are identical; their separate producing build scripts/inventories are retained.

The final combined check is not just another hash check: it must record
preferred-source and required-notice coverage for the packaged components,
including the relocated Protobuf build, and the instructions/inputs needed to
rebuild them. This preparation output has not been configured as the public
packager's approved bundle and has not been published.

The collector includes the application snapshot at `7248c82`, matching the
accepted R2 candidate's code, and maps 286 ABI-specific producing package
filenames (including shared data/source inputs) to preserved recipes and source
evidence. Recipe-only compatibility sources and ncurses subpackages are covered.
QuickJS and NDK source evidence remain included separately.

The combined source preparation output deliberately retains
`completeCorrespondingSourcesVerified=false` until the final combined
source, notice and rebuild-input review is recorded. Limited LDPlayer x86_64
acceptance does not establish ARM, API 26/35 or 16 KB device acceptance.
Nothing in this audit approves a public release or changes deferred tests to
passed tests.

The subsequent review closed the Protobuf relocation and native AndroidX source
compilation checks and retained missing settings/wrapper inputs. It identified
specific remaining JVM build-input gaps rather than approving the bundle from
hashes alone. See [review results](FINAL-SOURCE-REVIEW-20261005.md) and
[rebuild procedures](SOURCE-REBUILD.md).
