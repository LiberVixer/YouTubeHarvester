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
