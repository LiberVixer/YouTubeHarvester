# Android releases

Use JDK 17 and the committed Gradle wrapper. Desktop packages have a separate
workflow and release tags. Android tags are `android-v<versionName>`.

## Signing

Release signing reads environment variables, never tracked passwords:

- `YTH_ANDROID_KEYSTORE`: absolute path to the permanent release keystore.
- `YTH_ANDROID_STORE_PASSWORD`: store password.
- `YTH_ANDROID_KEY_ALIAS`: signing alias.
- `YTH_ANDROID_KEY_PASSWORD`: key password.
- `YTH_ANDROID_CERT_SHA256`: independently approved release certificate fingerprint
  (64 hexadecimal characters, without colons), required by the packager.

Back up the permanent key securely. Losing it prevents updates to installed
releases. Existing development APKs use a debug certificate; switching to a
release certificate requires a separate installation/migration plan.

Only after the owner explicitly chooses a new key, run the interactive helper
with a private path outside the repository:

```sh
JAVA_HOME=/home/redmin/.local/share/yth-android-toolchain/jdk17 python3 scripts/create_release_key.py --keystore /home/redmin/.local/share/yth-android-signing/release.p12
```

It requires a confirmed 12+ character password, refuses existing key/certificate
paths, exports `release.cert.pem` and prints its SHA-256. It does not create a
backup, approve the fingerprint or configure release signing. Store a protected
off-machine backup and its password separately; independently verify the public
certificate before setting `YTH_ANDROID_CERT_SHA256`.

CI uses the `android-release` environment and secrets `ANDROID_KEYSTORE_BASE64`,
`ANDROID_STORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.
No signing key or password belongs in Git or release artifacts.
Configure `ANDROID_CERT_SHA256` in the release environment variables as well.

For interactive local candidate signing, set `JAVA_HOME` to JDK 17 in the
terminal running `scripts/sign_release_candidate.py`; the GUI terminal may not
inherit the build shell's environment. The helper verifies Java availability
before requesting the key password. Use a new output directory for each attempt.

### Existing development installations

From dev31, `debug` uses `com.liberivixer.youtubeharvester.debug`; it deliberately
does not overwrite earlier installations. The private `assembleLegacyBeta` task
uses release optimization, `debuggable=false`, no debug tooling, and the existing
development certificate with the original package ID. This permits an in-place
test update from dev24 and later legacy betas without deleting their Room/DataStore/Keystore data.
It is a temporary compatibility measure, not a trusted public signing identity.
Never publish legacyBeta artifacts or reuse the development key for public releases.

A permanent signing key, secure backup and a tested explicit data export/import
path are still required before moving these users to a differently signed public
APK. Do not tell testers to uninstall or claim key migration is finished.

### Isolated permanent-key migration QA

Build from the Android directory without changing public signing configuration:

```sh
./gradlew -PythTestBuildType=migrationQa assembleMigrationQa assembleMigrationQaAndroidTest lintMigrationQa
```

This produces unsigned, non-debuggable `.migrationqa` app/test APKs. Only this
variant keeps shared APIs for the separately loaded instrumentation APK; it is
not byte-equivalent to the optimized public candidate. Default tests still target
debug. Use `scripts/sign_migration_qa.py --help` for local interactive signing of
these two APKs with the independently approved certificate. The helper refuses
other packages, debuggable APKs and existing output paths, and sends the password
only through child-process stdin. It never configures or publishes a release.
Install only the explicitly verified QA APKs, preserving the main beta.

The opt-in cross-identity test requires two separate phases and a QA packet copied
between their external-files directories. Source is the old-certificate `.debug`
package; target is the permanent-key `.migrationqa` package. The target verifies
its certificate and a different UID before importing. Do not count a skipped
opt-in test as acceptance or copy real credentials into the QA packet.
See [dev33 evidence and limitations](MIGRATION-QA-dev33.ru.md).

### Bundled engine policy

`runtime.properties` pins the official yt-dlp artifact, version and SHA-256.
The app resource `app/src/main/res/raw/ytdlp` overrides the older library resource.
Gradle refuses a mismatched file. Initialization verifies the installed file and
atomically restores the bundled copy if necessary, before any execution. Failed
verification/copy prevents initialization; no network update happens under the lock.
Keep this code in the same app process as all downloads.

The initial upstream review used the official release asset digest. This is not
an independent upstream signature or proof against a compromised upstream release.
After review, the pin and engine are covered by our source review and APK signature.
Future separate runtime updates require an independently signed manifest and rollback
design; downloading hashes alongside executable code is not sufficient.

## Sources and notices

The current build replaces all upstream native payload entries from controlled
Python/FFmpeg and extension builds. See `native/controlled-artifacts.json`,
`native/controlled-payloads.properties`, `native/README.md` and
`legal/CONTROLLED-SOURCE-AUDIT-20261005.md`. Download the recorded artifacts and
assemble the pinned replacement bundle before Gradle runs. The local
`build/controlled-payloads-20261005-r2/runtime-replacements.json` records every
packaged file's producing package and hash. This supersedes the earlier
partial WebP-only replacement, without changing wrapper classes.

`scripts/collect_controlled_sources.py` prepares preserved native source archives,
custom-fetch source trees, NDK sources/notices and the package mapping. Its output
is explicitly NOT approved for public packaging until exact APK source/notice
coverage, application/JVM dependency coverage and device acceptance are reviewed.

For the exact R2 source audit, export the resolved dependency graph without
updating binary verification pins:

```sh
./gradlew -I scripts/export_release_dependencies.gradle :app:exportReleaseSourceDependencies --offline
python3 scripts/collect_jvm_sources.py --graph build/release-source-dependencies.json --output build/jvm-sources-NEW
python3 scripts/collect_rav1e_sources.py --android . --output build/rust-sources-NEW
```

Preserve supplemental AndroidX native trees/build inputs, yt-dlp/EJS sources
and repackaged Protobuf sources before running `audit_application_sources.py`.
See [source coverage evidence](legal/APPLICATION-SOURCE-COVERAGE-20261005.md)
for exact producing versions and limitations. `collect_controlled_sources.py`
accepts `--jvm`, `--additional`, `--application` and `--rust` to combine verified
inventories in a new preparation archive; it never approves publication itself.
The subsequent `--jvm-builds`, `--androidx-builds` and `--review-evidence` inputs
preserve the reviewed producer/settings trees and compilation/relocation reports.
See `scripts/collect_jvm_build_inputs.py`, `scripts/collect_androidx_build_inputs.py`
and [the current review](legal/FINAL-SOURCE-REVIEW-20261005.md). Probe-generated
ELF/class files are not copied into the source bundle or accepted APKs.
`collect_jvm_build_inputs.py --reuse PREVIOUS` checks and copies a completed
producer inventory into a new output directory. For an interrupted collection,
use `--resume` with its existing output directory; producing tags and source
matches are checked again. `--project` selects an explicit producer family.
Run `verify_jvm_generated_sources.py` on the resulting producer inventory,
then `verify_source_preparation.py ARCHIVE --output NEW-REPORT.json` on the
consolidated preparation. Neither check creates a completed release approval.

For the expanded AndroidX preferred-input review, use a new source directory
with `collect_androidx_release_sources.py --jvm JVM-SOURCES --output NEW-DIR`.
Then run `collect_androidx_build_inputs.py --release-sources NEW-DIR --output
NEW-ROOT-INPUTS` and `collect_androidx_published_inputs.py --inventory
JVM-SOURCES/JVM-SOURCE-INVENTORY.json --output NEW-PUBLISHED-INPUTS`.
The first two collectors support `--resume`; completed inventories are rechecked,
root receipts are reused and discovered commits are frozen. Verify the original
icon/service generators as documented in `legal/SOURCE-REBUILD.md`, then supply
`--androidx-sources` and `--androidx-published` to the consolidated collector.
Their source/build/resource reports are preparation evidence, not release approval.

Earlier dev32 candidates replaced five WebP/SharpYUV shared libraries per ABI,
using the pinned source/binary bundle under `native/`. Include the
source archive, licenses and `scripts/rebuild_webp.py` in corresponding sources.
This supplements, rather than replaces, the complete FFmpeg/runtime source bundle.

An approved `android/LICENSE` and `NOTICE` must accompany the release. Keep the
matching upstream native runtime sources, codec sources, license texts and build
scripts in a reviewed tar.gz archive. Set `ANDROID_SOURCE_BUNDLE` to its local
path when packaging. For CI, configure `ANDROID_SOURCE_URL` and
`ANDROID_SOURCE_SHA256` in the release environment; the workflow downloads and
verifies this reviewed archive before packaging. Do not substitute application sources
for the corresponding third-party runtime sources.

Source preparation is not release approval. The packager also requires a separate
`--review` JSON with `schemaVersion=1`, `completeCorrespondingSourcesVerified=true`,
an empty `remaining` list, `releaseCommit`, `sourceArchiveSha256`, and an
`apkSha256` map for all four ABI names. Record this only after the substantive
source, notice and rebuild-input review is complete. A matching hash alone is
not that review. The report must bind the exact signed APKs and release commit;
rebuilding or resigning requires a new exact-artifact review.

CI fetches this report using `ANDROID_SOURCE_REVIEW_URL` and
`ANDROID_SOURCE_REVIEW_SHA256`; absent or mismatched review blocks publication.
For local packaging of accepted signed candidates, pass `--candidate-dir` rather
than selecting unsigned or subsequently rebuilt Gradle outputs. The packager
verifies all four before creating output, copies them without resigning, and
publishes the output directory atomically only after all checks pass. It does not
upload files or publish a GitHub release itself.
The output includes separate `LICENSE-android.txt` and `NOTICE-android.txt`
files covered by `SHA256SUMS-android.txt`; the complete component-specific
license notices remain in the corresponding-source archive.

## Checks

```sh
./gradlew testDebugUnitTest lintRelease assembleDebug assembleRelease assembleDebugAndroidTest
./gradlew connectedDebugAndroidTest
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/elf_alignment.py app/build/outputs/apk/release/*.apk
```

Device tests exercise Room concurrency, publication and rollback through
MediaStore, Keystore authentication and the bundled runtime. CI runs them on
API 26 and 35. Live provider downloads, SAF provider failures, reboot/Doze and
OEM battery restrictions still require the device acceptance checklist in README.

When dependencies change, review their upstream artifacts, then regenerate:

```sh
./gradlew testDebugUnitTest lintRelease assembleDebug assembleRelease assembleDebugAndroidTest --write-verification-metadata sha256
```

Commit the reviewed verification metadata. Ordinary builds enforce verification.
New hashes must not be generated silently in CI.

Commit the Android sources, update versionCode/versionName, build with the signing
environment, then run `python3 scripts/package_release.py --tag android-vVERSION
--sources /path/to/reviewed-runtime-sources.tar.gz --review /path/to/completed-review.json`
from the Android directory. To reuse accepted signed APKs, also pass
`--candidate-dir /path/to/signed-candidates`.
The script refuses unsigned/debuggable APKs, debug certificates, unexpected exported
components, wrong approved fingerprints, mismatched package/version/tags, missing
licensing/source files, or uncommitted Android changes. It emits four ABI APKs,
application sources, runtime sources, BUILD-INFO and SHA256SUMS. Publish only those
reviewed artifacts. Do not derive the approved fingerprint from the candidate APK.

The recursive ELF check includes nested runtime ZIPs on 64-bit ABIs; a zero count
for 32-bit-only APKs means this 16 KB check is not applicable. Device testing on
a 16 KB Android system remains mandatory even when all LOAD alignments pass.

The in-app updater chooses the device ABI from GitHub releases, requires a GitHub
SHA-256 asset digest, verifies package identity, a higher versionCode and the
installed signing certificate, and opens the Android installer. Stable installs
ignore prereleases. The user grants installation permission through Android.
