# Controlled Source Rebuild Procedures

These procedures distinguish compilation from reuse of the recorded binary
artifacts. They do not certify a byte-for-byte reproducible build or approval of
the combined source set. The publisher's private signing key is not a build
input: a third party can build and sign a modified APK with their own key.

## Python, FFmpeg and Cryptodome

The preserved native source set contains original source archives, two custom
source trees, the producing Termux recipe archive and override patch, Dockerfile,
runtime/extension locks, and producing build scripts/manifests. The current
repository scripts also contain preflight checks for every ABI and for formerly
broken dependency downloads. Cargo's producing lock and all its registry crates
are included separately, together with the pinned Rust sources.

Use Linux, Git, Python 3.12, jq, Docker and the pinned NDK r28c. The Docker base
image is pinned by digest in `native/runtime-build-lock.json`. The producing
Termux commit is `7c74f85f3b36991d07d4cfb0d1be458c1b4f0896`.
The current build driver requires a clean Git checkout of that commit, not just
an unpacked recipe tree. Its archived recipes are preserved for comparison;
the driver does not claim to operate entirely offline from the source archive.

From the Harvester repository root, use a separate clean Termux checkout for
each invocation, because the driver applies the recorded patch to that checkout:

```sh
bash android/scripts/build_controlled_runtime.sh aarch64 /path/to/clean-termux /path/to/harvester /path/to/new-core-output runtime
bash android/scripts/build_controlled_runtime.sh aarch64 /path/to/another-clean-termux /path/to/harvester /path/to/new-extension-output extensions
```

Repeat with `arm`, `i686` and `x86_64`. This source-builds the dependency graph;
it does not select Termux's prebuilt-dependency option. Source downloads remain
validated against the recipes. For preserved upstream archives, their cache
paths are recorded under `original-sources/`. Do not confuse the smaller
extension graph with a full FFmpeg rebuild.

Review the resulting `BUILD-INFO-runtime.json`, source logs and packages. Pin
the NEW inventories in a separate working tree, rather than changing or deleting
the accepted artifacts. `scripts/package_controlled_payloads.py` assembles these
newly reviewed packages and records the file/package map. Old inventory hashes
will intentionally reject newly rebuilt packages until this review is done.
QuickJS and launcher compilation is recorded in that assembler and
`scripts/rebuild_quickjs.py`; the NDK/LLVM source/notice evidence is under `ndk/`.

## Supplemental Native AndroidX Sources

The retained graphics-path and DataStore module trees contain all sources needed
by the isolated native compilation probe. From the repository root:

```sh
python3 android/scripts/probe_androidx_native_sources.py --additional /path/to/supplemental-sources --ndk /path/to/ndk/28.2.13676358 --output /path/to/new-androidx-probe
```

This compiles both libraries for all four ABIs at API 26 and records the commands,
compiler hash and output hashes. It uses the original C++ sources and export map,
but not the producing Kotlin/Native toolchain for DataStore. Its outputs are
feasibility evidence, NOT byte-identical replacements for the Maven AARs, and
are never copied into the accepted APKs.

## Protobuf

`scripts/probe_protobuf_sources.py` compiles all 159 preserved protobuf-javalite
4.28.2 Java sources, without loading the upstream binary on the compiler
classpath. JDK 17 with Java 8 source/target settings produces the expected
523-class inventory. The upstream archive additionally retains generators and
build recipes. This probe does not reproduce the upstream compiler's class bytes.

`scripts/verify_protobuf_relocation.py` uses ASM 9.9 core, commons and util JARs
and JDK 17 to apply the producing AndroidX package relocation to the original
binary. All 523 remapped class bytes match the repackaged DataStore dependency.
That is stronger than comparing class names, but not reproduction of ZIP
metadata or a source-to-binary reproducibility claim.

## Application and JVM Libraries

The accepted app source snapshot is included as `application-sources.tar.gz`.
Use its committed Gradle wrapper and normal dependency verification. To rebuild
against the accepted binary runtime, restore the pinned payload before running
Gradle. To use newly compiled runtime bytes, first review and update their pins;
never bypass the mismatch check.

The 130 Maven source JARs/POMs retain editable library sources and notices, but
they are not by themselves standalone upstream build checkouts. The expanded
`jvm-build-inputs-r3` inventory retains 19 producer trees covering 38 artifacts
and ten recursive parent POMs. Use each original wrapper/build/catalog and its
recorded producing commit. The generated-version/redirect checks and their
limitations are described in `FINAL-SOURCE-REVIEW-20261005.md`.

The AndroidX release-source inventory maps all 91 artifacts to 41 selected
module trees at 32 immutable official commits. Corresponding root/buildSrc,
settings tooling, wrappers, catalogs, inspection generators and root licenses
are retained separately in `androidx-build-inputs-r3`; restore the module tree
to its recorded `tree` path at that same root commit. Published AAR resources,
manifests, symbols, assets and notices supplement the preferred module sources.
Source matches, not a nearby version bump or moving branch name, identify the
selected inputs. This does not certify a whole upstream Gradle rebuild or
byte-identical Maven artifacts.

`scripts/probe_material_icon_sources.py` compiles and runs the original retained
icon generator with a thin runner. Its `--compiler-classpath` accepts Kotlin's
compiler/runtime dependencies, and `--generator-classpath` accepts the original
generator dependencies from its pinned version catalog. The probe checks every
generated icon; only the generator's initial date-derived copyright year may
differ. Provide new output directories so existing evidence is preserved.

`scripts/probe_androidx_service_sources.py` accepts the JVM/module/root/published
inventories, protoc 4.28.2's Linux tool, SDK 36.0.0 AIDL/aapt2 and an Android
framework JAR. It regenerates PreferencesProto and Room RPC sources and checks
the inspector template and public R sources. AppCompat documentation-stub tails
are checked explicitly, not claimed as fully regenerated. Neither probe produces
replacement APKs or a completed corresponding-source approval.

## Explicit AndroidX Publication Versions

Six source-identical artifact snapshots have a different root version-table
entry. Do not silently build their RC/next version or change the saved trees.
`scripts/prepare_androidx_version_overrides.py` validates the module/root
inventories and creates five version-only patches in a new output directory:

```sh
python3 scripts/prepare_androidx_version_overrides.py --sources /path/to/androidx-release-sources --builds /path/to/androidx-build-inputs --output /path/to/new-version-overrides
```

The corrections are annotation-experimental 1.5.0, core-viewtree 1.0.0,
customview-poolingcontainer 1.0.0, Fragment 1.5.4, and tracing/tracing-ktx 1.2.0.
`ANDROIDX-VERSION-OVERRIDES.json` identifies each immutable root commit,
original/revised table hashes and affected Maven coordinate. After restoring
that commit's root and selected module tree into a NEW rebuild directory, run
`git apply --check /path/to/COMMIT-versions.patch` and then `git apply` there.
The script parses TOML before and after each change and rejects unexpected
versions, ambiguous assignments or changes to unrelated settings. These patches
are explicit rebuild inputs, not proof that these snapshots produced the
published binary or a byte-reproducibility claim.

## Original Notices

`scripts/audit_source_notices.py --archive PREPARATION --output NEW-AUDIT`
first verifies every source-preparation inventory entry, then retains original
component notices, source declarations and their hashes. A generic recipe
license name does not substitute for original copyright/notice text.
In particular, libcrypt's generic BSD template contains placeholders; its
actual FreeBSD copyright and conditions are retained from `crypt3.c` as well.

Eight pinned Rust distributions omit separate license files. Collect their
matching repository notices with `scripts/collect_rust_notice_sources.py --rust
/path/to/rust-sources --output NEW-RUST-NOTICES`, then pass that directory as
`--rust-supplement` to the notice audit. All Rust code files must match at the
recorded subtree, not just the package name/version. simd_helpers' retained
notice snapshot is the later LICENSE-addition commit with identical Rust code;
its original Cargo VCS commit remains in the unmodified crate. The Windows
import-library crates are Cargo-lock inputs, not Android runtime libraries.

Supply the completed inventories to the preparation collector as
`--notice-audit`, `--version-overrides` and `--rust-notices`. It checks their
file hashes before inclusion. All these reports remain preparation evidence:
an empty automated finding list does not itself approve the final exact-APK
source/build/notices review or publication.

AndroidX settings can force `:lint-checks` into a prefix-filtered build. The
expanded root inventory also retains that tree at each selected commit where
present, plus root Groovy scripts. Restore these alongside buildSrc, inspection
and settings tooling; filtering to a library prefix does not remove this input.
Public repository access uses the upstream settings' `ALLOW_PUBLIC_REPOS`
switch where supported. The source bundle does not claim to contain Google's
private prebuilts or to support a completely offline upstream AndroidX build.
