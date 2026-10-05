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
they are not by themselves a complete standalone upstream build checkout.
AndroidX module/buildSrc/root inputs are supplemented by the matching settings
plugins, placeholder project, Gradle trees and wrappers. A clean upstream JVM
build-input closure has not yet been certified. The subsequent collection under
`build/source-final-review-20261005/jvm-build-inputs-r2/` closes the missing Jackson
parents and preserves complete Jackson/OkHttp/Coil build trees. In these trees,
use the original Maven wrapper/POM for Jackson and the original Gradle wrapper
for OkHttp/Coil, with the versions/catalogs shipped in each tree. Their generated
version templates reproduce the published source files exactly. Other JVM
producer families still need equivalent build-input review; five successful
producer checks do not certify the whole graph. Do not mark the combined
corresponding-source review complete from this subset.
