# R2 Source Review Progress

This review supplements `APPLICATION-SOURCE-COVERAGE-20261005.md`. It is not a
completed corresponding-source approval and does not authorize publication.
No signed APK or production runtime was changed.

## Checks Completed

- The producing Protobuf relocation was verified beyond its class inventory:
  all 523 classes have identical remapped bytes, including instructions and
  metadata. Original artifact SHA256:
  `dcbac0ae7a6ff7a751ca426bc49008f80c7a5d4ecde9d84750ca86dd2f614db3`.
  DataStore artifact SHA256:
  `4f09ba7fca2a073a5c5527a9b637582b93e262c2b6a89977c584d28cea838ebc`.
- All 159 Protobuf Java source files compile independently of the original
  binary. The result contains the same 523-class inventory. This does not
  establish source-to-binary byte reproducibility.
- Both native AndroidX libraries compile from the retained module sources for
  all four ABIs: eight successful compilations using NDK r28c/API 26. These
  isolated probes do not replace the producing Kotlin/Native toolchain or
  establish device acceptance; none of their outputs went into the APKs.
- Seven additional build inputs were retained from the exact graphics/DataStore
  commits: settings plugins where required, placeholder projects, Gradle trees
  and wrapper scripts. graphics-path's older commit has no settings-plugin
  directory; requesting it produced HTTP 400, not a VPN/compiler failure.
- FreeType 2.13.3's original `LICENSE.TXT` explicitly permits GPL version 2 or
  any later version, as well as its alternative FreeType license. The recipe's
  abbreviated `GPL-2.0` declaration must not be interpreted as GPL-2.0-only.
  The original license and component-specific notices remain in its source
  archive; generic Termux license texts do not replace them.

Local evidence under `build/source-final-review-20261005/`:

- `PROTOBUF-RELOCATION.json`
- `protobuf-source-probe/PROTOBUF-SOURCE-PROBE.json`
- `androidx-native-probe/ANDROIDX-NATIVE-SOURCE-PROBE.json`
- `androidx-build-inputs-r2/ANDROIDX-BUILD-INPUTS.json`
- `jvm-build-inputs-r2/JVM-BUILD-INPUTS.json`
- `JVM-GENERATED-SOURCES-recheck.json`

## Additional JVM Producer Checks

The subsequent collection retained complete versioned producer trees for
Jackson annotations 2.22, Jackson core/databind 2.22.3, OkHttp 4.12.0 and Coil
3.6.3. Maven parent POMs were collected recursively, including the formerly
missing Jackson base/BOM/parent metadata. GitHub tags were resolved to commits
before downloading the trees; neither HEAD nor a moving branch was used.

Across the five selected source artifacts, 922 Java/Kotlin files match these
trees byte for byte. Three remaining files are generated release-version files:
Jackson's two `PackageVersion.java` files and OkHttp's `OkHttp.kt`. The preserved
templates reproduce all three exactly using the published artifact coordinate
and package substitutions. The verifier rechecks both source JAR hashes and
upstream-tree matches before accepting these transformations.

The full Coil archive exceeded the collector's initial 128 MiB bound because
of its test/demo media. A 256 MiB bound was used only for that pinned archive;
no partial download was accepted. The successful producer input directory is
about 140 MiB. These are source/build inputs, not a rebuilt production runtime.

The saved preparation archive remains unchanged. New source/build inputs and
review evidence must be included in the final consolidated source bundle.

## Packaging Defect Fixed

The former public packager accepted any nonempty tar.gz as a reviewed source
bundle. It did not require a completed substantive review. The corrected
packager requires an explicit completed report binding the exact source archive,
release commit and four signed APK hashes, with no unresolved source-review
items. False, missing or string-valued approval flags are rejected.

It can reuse the accepted signed candidate directory, verifies all four before
creating output, preserves their bytes, and creates the final directory only
after all copies/checks succeed. Signature or review failures leave no partial
publishable directory. CI also requires the pinned completed report; no report
was created with an unjustified true approval flag.

## Concrete Remaining Source Gate

This section records the gate before the expanded review below. Its listed
non-AndroidX producer omissions are superseded by that review, not still pending.

The current archive's Maven source JAR/POM collection is NOT a certified closure
of the upstream JVM build inputs. In particular:

- The five selected producer trees and their parents are now retained and
  verified, closing the concrete Jackson/OkHttp/Coil omissions above. This must
  not be extrapolated to the whole 130-artifact graph. Other families, including
  Kotlin/kotlinx, JetBrains Compose, Okio and Apache Commons, still require their
  producer build-input closure to be recorded alongside the source JAR/POM evidence.
- The supplemental AndroidX inputs and new review evidence are not yet merged
  into a final approved source archive with a complete notice/build-input report.

See `SOURCE-REBUILD.md` for the confirmed procedures and explicit limitations.
The exact APK/source review remains incomplete until these build-input and
consolidation items are resolved. Existing source preparation and device
acceptance flags remain false; no public release or tag was created.

## Expanded JVM Review

The subsequent `jvm-build-inputs-r3` collection retains 19 versioned producer
trees and ten recursive Maven parent POMs. It covers 38 resolved artifacts,
including all six Coil artifacts, Accompanist, Okio, the four Apache Commons
families, JetBrains annotations, Kotlin 2.4.20 and its 1.8.21 compatibility
artifacts, coroutines, serialization, JSpecify and the JetBrains Compose
Android redirects. Previously verified producer archives were preserved.

- 2774 Java/Kotlin files match upstream sources byte for byte.
- 30 annotation files differ only by CRLF/LF line endings. The verifier checks
  all bytes after only that normalization; it does not ignore changed code.
- 16 generated files match exactly: the three previously reviewed Jackson/
  OkHttp files, Kotlin's current-version source and twelve Compose redirects.
  Kotlin's producing `prepare/build.version/build.gradle.kts` and Compose's
  `ArtifactRedirection.kt` are retained alongside their source trees.
- The `listenablefuture:1.0` source and module POM match Guava v27.0's
  `futures/listenablefuture1`, despite its parent being `26.0-android`.
  The initially collected Guava v26.0 tree has the annotated general-purpose
  interface instead and is retained only as historical investigation evidence.
- Okio's POM points to `lysine-dev/okio`; its exact `parent-3.18.1` tag is used,
  rather than assuming Square's repository produces this resolved artifact.
- Compose's twelve Android source artifacts contain generated empty redirect
  files, not the actual UI implementation. The latter is provided by the
  resolved AndroidX artifacts already retained as source JARs/POMs. The pinned
  `compose-multiplatform-core` tag message identifies the 1.12.0 publication.

`JVM-GENERATED-SOURCES-r3.json` rechecks these source/tree matches independently
of collection. No unknown difference is silently classified as generated.
This closes the listed non-AndroidX JVM producer-family omissions, not an
assertion that every AndroidX producer build has been reproduced or that the
whole 130-artifact notice/build-input review is complete.

The collector now selects JetBrains Compose by Maven group, avoiding its
name collision with AndroidX, and supports explicit `--resume`. Resuming
re-resolves producing tags, checks existing inventories when present, and
recomputes source matches without re-downloading complete trees. Archives are
indexed once per producer, including producers shared by multiple artifacts.

The new combined preparation includes these trees, supplemental AndroidX build
inputs and the source review reports. `verify_source_preparation.py` checks
every inventoried member, rejects changed/missing/extra/duplicate files and
escaping links, and does not convert integrity verification into release approval.
The public packager now includes `LICENSE-android.txt` and `NOTICE-android.txt`
as separate checksummed files beside the APKs and source archive.

Remaining before a completed exact-APK source approval: review the AndroidX
source/build-input and notice coverage together with the consolidated native,
Rust, NDK and application inventories. Device checks outside LDPlayer remain
explicitly deferred, not recorded as passing. No source approval flag has been
changed to true and no accepted signed APK has been rebuilt or modified.

## Consolidated Preparation Verified

Local archive: `build/controlled-payloads-20261005-r2/source-preparation-combined-r3.tar.gz`.
Size: 1,652,533,264 bytes. SHA256:
`83aff4bd8378c1fa230aa4d7548aa98151e7177cf9c9dcf2ed149c784db6d6e4`.
It preserves the 151 original native source archives, application snapshot
`7248c82`, NDK/Rust/JVM sources, new producer/settings inputs and five source
review reports. Older preparation archives remain unchanged.

An independent streaming pass verified all 3822 inventoried files and sizes,
including link handling, against the finished tar.gz. The report is
`build/source-final-review-20261005/SOURCE-PREPARATION-R3-VERIFIED.json`.
This is an integrity check, not a claim of whole-source rebuildability or
permission to publish. Both approval flags remain false.

The final focused regression run passed 65 tests without skips, including the
JDK/ASM relocation fixture. All four accepted R2 signed APK checksums still
match `SHA256SUMS-android.txt`. No full runtime compilation was restarted.

## AndroidX Preferred Sources And Generators

The expanded collection covers all 91 resolved AndroidX artifacts. Its latest
inventory is `androidx-release-sources-r2/ANDROIDX-RELEASE-SOURCES.json`, under
the same local review directory. It retains 41 selected module trees at 32
immutable official Gitiles commits. Earlier investigated snapshots are kept
as historical evidence; only the artifact records identify the selected trees.

3297 published Java/Kotlin files match these trees byte for byte. A tree's
version table is not used as proof of a producing commit: some source-identical
snapshots have an RC or subsequent version in that table. In particular, the
Fragment snapshot matches all 52 published sources, including fixes absent
from an earlier stable-version bump. `customview-poolingcontainer:1.0.0` has
its own module pin, distinct from `customview:1.0.0`.

The original Material icon generator was compiled and run without changing
its generator sources. All 11385 published generated Kotlin files match its
output after accounting ONLY for the initial copyright year, which the
upstream generator derives from the build date. All other bytes are compared.
The module tree includes its 10660 raw XML inputs, generator, build scripts
and declared dependencies. `MATERIAL-ICON-SOURCE-PROBE.json` records the
generator/tool hashes and each comparison; experimental compiler binaries and
generated classes are not included in the source bundle.

`ANDROIDX-SERVICE-SOURCE-PROBE.json` covers the remaining eight generated files:

- DataStore's PreferencesProto matches protoc 4.28.2's Java-lite output exactly.
- Both Room RPC files match SDK 36.0.0 AIDL output except the single header
  line recording the producing command's host paths. All code bytes match;
  structured mode and minimum SDK 23 are checked rather than ignored.
- Both inspector detection files match their preserved Gradle source template.
- WorkManager's public R source is reproduced exactly by aapt2.
- AppCompat's two public R documentation stubs match the complete generated
  public-resource prefix. Their empty `@DocOnly` styleable tails are explicitly
  checked. This is NOT full regeneration of the documentation-stub processing
  or proof of the APK's compiled R classes. The preferred resource XML, public
  declarations, published symbol tables and relevant build inputs are retained.

The SDK 36 aapt2 probe used the available API 37 framework only as a linking
input; it does not claim to reproduce an upstream SDK environment. The report
records the framework and tool hashes. No probe output entered a signed APK.

For all 32 selected commits, `androidx-build-inputs-r3` retains root scripts,
buildSrc, settings plugins/wrappers/catalogs where present, inspection generator
sources and the root license: 396 inventoried files/archives in total.
`androidx-published-inputs-r2` supplements this with 1163 exact published
resource/manifest/metadata/notice files across all 91 artifacts, including bitmap
and asset inputs; compiled classes and native binaries are excluded.

Collection resumes from verified saved inventories and root receipts. HTTP 429
is retried with a bounded pause; authentication errors are not misclassified as
missing historical metadata. New tests cover this behavior, archive/path safety,
source substitutions and allowed generated-file differences.

These inputs and seven focused source-review reports are included in a NEW R4
preparation archive. R3 and the accepted four signed R2 APKs remain unchanged.
The final combined build-input/notice and exact-APK source manifest approval is
still separate. No partial generator or integrity check sets that approval true.

## R4 Preparation Verified

Local archive: `build/controlled-payloads-20261005-r2/source-preparation-combined-r4.tar.gz`.
Size: 1,731,084,146 bytes. SHA256:
`7658ea2a72cf941498b7d9bfbcdeea9426e3dd2439cb0715f242fab2a8b33a25`.
The independent streaming pass verified all 5568 inventoried files, sizes and
links. Its report is `build/source-final-review-20261005/SOURCE-PREPARATION-R4-VERIFIED.json`.
The archive retains the original 151 native source archives and adds the
AndroidX module/root/resource inputs and generator-review reports above.

The final focused run passed 63 source-collection, generator, relocation and
release-gate regression tests without skips. All four accepted R2 APK checksums
were checked again and match. No runtime or APK was rebuilt; no release was
published. Integrity verification remains distinct from final substantive
source/build/notices approval, which is not recorded as complete.

## Original Notice And Version-Input Review

The additional notice inventory identifies 74 native/launcher/wrapper component
records, the 130 Maven artifacts and two local controlled AAR records, all 227
locked Rust distributions, and eight supplemental yt-dlp/EJS/npm/Protobuf source
archives. It preserves 948 original notice files (6,747,291 bytes) separately
from abbreviated recipe declarations. Its initial empty component-location
finding list was not treated as approval: eight Rust crates required additional
notice evidence outside their published crate archives.

The supplemental Rust collector closes those eight original-notice omissions
with six immutable repository snapshots and exact comparisons of all 67 Rust
files. It covers anes, difflib, profiling/profiling-procmacros, simd_helpers,
valuable and both winapi Windows import-library crates. A later simd_helpers
LICENSE-addition commit is explicitly distinguished from the crate's Cargo VCS
commit; its two Rust files are identical. The Windows crates are preserved
Cargo-lock inputs, not claimed as libraries linked into the Android APKs.
Reports: `rust-notice-sources-r3/RUST-NOTICE-SOURCES.json` and the subsequent
`source-notice-audit-r3/SOURCE-NOTICE-AUDIT.json` in the local review directory.

The common wrapper module's two published Kotlin files match the preserved
0.18.1 wrapper sources exactly. Together with the 38 expanded JVM producer
artifacts and 91 AndroidX mappings, this covers all 130 Maven producer mappings.
The two local controlled AARs retain their separately audited wrapper/runtime
source mapping; they are not counted as downloaded Maven sources.

libcrypt's recipe LICENSE is a generic BSD template with placeholder attribution.
The actual FreeBSD 2011 copyright, conditions and disclaimer are also preserved
from its original `crypt3.c`; the generic template is not used as a substitute.
Original source declarations for FFTW, x264, x265, vid.stab, Rubber Band and Xvid
explicitly allow GPL version 2 or later. FreeType's previously reviewed original
license supplies its own later-version permission. These findings distinguish
the short recipe labels from upstream grants; they do not relabel all source
components as the application's GPL-3.0-only license.

Five explicit version-only patches cover six AndroidX artifact snapshots whose
version table differs from the published coordinate. All five patches were
successfully checked and applied to temporary copies, with exact revised TOML
hashes; the saved source trees remain unchanged. See
`androidx-version-overrides-r1/ANDROIDX-VERSION-OVERRIDES.json` and
`SOURCE-REBUILD.md` for the restore/apply procedure and limits.

The focused regression run passed 70 tests without skips. All four accepted R2
signed APK hashes still match, and application/build/runtime inputs are unchanged
from the accepted application snapshot. These notice/version inputs are included
in a new R5 preparation, without overwriting R4 or the accepted APKs. Final
substantive exact-APK source/build/notices approval remains separate; no public
tag or release is created by these collectors.

The final settings-script read-through found a concrete additional build input:
AndroidX includes `:lint-checks` even when PROJECT_PREFIX filters the requested
libraries. The root-input collector now retains that project tree when present,
as well as root Groovy scripts. The expanded collection uses a NEW
`androidx-build-inputs-r4` directory, preserving r3. The unfinished initial R5
packaging was interrupted and its temporary output removed before consolidating
these inputs; no finished preparation archive or accepted binary was replaced.
The regression fixture now requires the lint tree and root Groovy input to
survive collection and cached-root resumption.

## R5 Preparation Verified

Local archive: `build/controlled-payloads-20261005-r2/source-preparation-combined-r5.tar.gz`.
Size: 1,745,961,172 bytes. SHA256:
`c6b90687e95251082a1a261053aa4ba2bfcb302edd2099261c45868877cf907f`.
All 6571 inventoried files, sizes and links passed the independent streaming
verification recorded in `SOURCE-PREPARATION-R5-VERIFIED.json` under the local
review directory. The archive retains the original 151 native source archives,
notice evidence, six supplemental Rust repository snapshots and five explicit
AndroidX version patches. Earlier preparations and the accepted APKs are intact.

The expanded AndroidX root collection has 424 inventoried files/archives over
32 selected commits. lint-checks exists at 28 of these roots; the four historical
roots have no such directory, as recorded in their immutable root receipts.
The notice audit is bound to the R4 preparation it inspected; R5 additionally
preserves that audit and the newly retained lint trees. Neither report is
misrepresented as a byte-identical whole-upstream rebuild or release approval.

The final 70-test run passed without skips after the root-input fix. GitHub's
Android 1.2.1 release remains a draft containing an older INCOMPLETE source asset;
it has not been replaced by a publicly approved release. The completed substantive
review binding the final source bundle and exact APKs, followed by final draft
artifact/metadata replacement, is still required before publication. No true
source-approval flag or public tag was created in this preparation step.

## Final Combined Decision

The combined engineering source/build/notices review for the exact four signed
R2 APKs is recorded in `SOURCE-REVIEW-1.2.1.json`. It binds their SHA256 values
to R5's immutable source hash and the accepted application snapshot, and closes
the source omissions described in the historical sections above. All 11393
initially unmatched AndroidX generated files are accounted for by the retained
icon/service probes, including their explicitly limited comparison modes.

This decision is based on the preferred sources, build/assembly inputs,
component mapping, original notices and transformation evidence together;
the 6571-file integrity check alone is not the approval. In particular,
source-identical snapshot selection is not silently called producing-commit
attestation, and documentation-stub or whole-APK byte reproducibility is not
claimed. Historical preparation reports remain unchanged and false for their
original narrower scope. The completed distribution report additionally binds
this decision to the final packaging commit.

The public packager preserves the R2 APK bytes and distributes original notices
in a separate `THIRD-PARTY-NOTICES-android.zip`, copied byte-for-byte from the
reviewed bundle. Its focused regression run passed 14 tests. Device acceptance
remains limited to LDPlayer x86_64/API 34; deferred device checks are not passing
checks. The report approves source packaging, not public release publication.
