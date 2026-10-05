# Controlled runtime source audit

All four controlled core runtime builds completed 157 main packages. Downloaded
artifacts passed their complete file checksum inventories: 320 entries for
x86_64, 326 for each other ABI. Existing signed APKs still use the earlier
upstream runtime and are not attested by these new source archives.

| ABI | Run | Application commit |
| --- | --- | --- |
| x86_64 | 37222732575 | 63f2d671f1a0abb8dc4ba99151d3cf83a2a7aa0b |
| armeabi-v7a | 37253992814 | bc42cd59e8b81f6a0e8729621e0a98b79e46784d |
| x86 | 37253997563 | bc42cd59e8b81f6a0e8729621e0a98b79e46784d |
| arm64-v8a | 37253987803 | bc42cd59e8b81f6a0e8729621e0a98b79e46784d |

## Evidence Checked

`scripts/audit_controlled_sources.py` verifies producing recipe/source archive
hashes, applies the archived override patch to the pinned recipe tree, reads
each finished package's version/license/source declarations, and inventories
the preserved source worktrees without extracting them. It checks identical
recipe archives, override patches and runtime locks across ABIs.

Each core artifact contains matching cached upstream archives for 150 source
URLs and 482 source-tree license/notice candidates. There were no mismatched
source archive hashes. Generic license texts for packages without dedicated
license files are present in the pinned recipes' `termux-licenses/LICENSES`.
These are evidence counts, not an assertion that every individual source file
or notice has undergone legal review.

The final `usr/etc/tls/cert.pem` extracted from each core ABI's
`ca-certificates` package matches the producing recipe's SHA256:
`64dfd5b1026700e0a0a324964749da9adc69ae5e51e899bf16ff47d6fd0e9a5e`.
This checks certificate data integrity, not the final APK source bundle.

Local detailed report: `android/build/controlled-source-audit-20261005.json`.
It deliberately records `completeCorrespondingSourcesVerified=false`.

## Python Extension Builds

Run `37265901720`, application commit
`8f468ecc3cb80355407e1ab7abce0646831e8c79`, completed successfully for all
four ABIs. Every final log records 43 unique completed packages, ending with
`python-pycryptodomex`. Downloaded artifacts are retained under
`android/build/controlled-extensions-37265901720/ARCH` with per-ABI
`VERIFIED-extensions.json` reports.

| Architecture | Completed packages | Verified SHA256 entries | Cryptodome native modules |
| --- | --- | --- | --- |
| aarch64 | 43 | 105 | 40 |
| arm | 43 | 105 | 40 |
| i686 | 43 | 105 | 42 |
| x86_64 | 43 | 105 | 42 |

For each artifact, every inventory entry including the unpacked raw packages
matches its hash and size. Architecture, application commit, exit code zero,
runtime lock, extension lock and `BUILD-COMPONENT.json` were checked.
The `python-pycryptodomex` package is version 3.23.0 and all its native modules
have the expected ELF machine type. All 82 native modules across the two
64-bit ABIs pass the existing 16 KB LOAD-segment alignment check.

Each source worktree archive retains the original Cryptodome source tarball
with SHA256 matching the pinned extension lock, 1420 source files and both
`LICENSE.rst` notices. The retained Mutagen source archive also matches its
pinned hash. These checks establish preserved source evidence, not final APK
runtime acceptance or a complete corresponding-source attestation.

Final logs have no GitHub fatal-error annotations. Python's test-file
`compileall` diagnostic (`ValueError: field 'value' is required for Constant`)
occurs once per ABI and does not stop these builds. Debian's package reader
warns about Termux's `x86_64` architecture spelling; the package contents were
read successfully and their ELF architecture was checked independently.

## Remaining Before Publication

- `ca-certificates` downloads a PEM data file without an unpacked source tree.
  Its producing recipe and SHA256 are preserved, and the packaged PEM hash was
  checked for all four ABIs. Retain the declared MPL-2.0 notice in the final
  source bundle; absence of a source worktree
  is not treated as evidence of missing C source code.
- `libc++` copies `libc++_shared.so` from the pinned NDK instead of compiling it.
  Matching LLVM/builder archives, 51 applied patches and NDK notices have now
  been preserved; see [NDK evidence](NDK-SOURCE-EVIDENCE-20261005.md). Include
  them in the reviewed final source bundle. Its preserved ELF is not source
  code. The recipe's
  generic NCSA text alone is not a complete notice/provenance review.
- Some compatibility/generated packages have their source in the recipe tree
  or custom source-fetch hooks. Include those recipes and local C/header files,
  not only cached upstream archives.
- Existing APKs contain `Cryptodome 3.23.0` and `mutagen 1.47.0`; the initial
  core targets did not include them. The separate source-built Cryptodome
  artifacts pinned in `native/python-extensions-lock.json` are now verified
  for all four ABIs. Integrate these replacements rather than old extension
  ELFs; exact APK imports and download acceptance remain unverified.
- Mutagen's source distribution is retained as `native/mutagen-1.47.0.tar.gz`,
  SHA256 `719fadef0a978c31b4cf3c956261b3c58b6948b32023078a2117b1de09f0fc99`.
  It contains its GPL-2.0-or-later COPYING file and package metadata. The version
  matches the previously bundled module, and no native compilation is needed.
- Replace Python/FFmpeg/FFprobe executables and every packaged runtime library,
  then verify ELF dependency closure and package-to-source mapping of the exact
  APKs. Keep QuickJS's already controlled sources and all wrapper sources.
- Assemble and independently check the final corresponding-source bundle,
  notices, rebuild instructions and exact signed APK acceptance. The public
  packaging gate remains enabled; nothing has been published.

## Replacement APK Preparation

All six native entries per ABI (Python executable/payload, FFmpeg executable/
payload, FFprobe and QuickJS) have been replaced. The replacement bundle SHA256
is `cb247989fdeeb7a553da97796d42da0a579e8d089b211fa82097c3d3e4d03833`.
The adjacent JSON preserves the producing package and file hash for each payload
entry. Non-system ELF dependency closure was checked for all four ABIs before
packaging. Dynamic plugin loading still needs device acceptance; static NEEDED
closure alone is not a full runtime test.

`assembleRelease` and its vital lint checks passed. All four resulting unsigned
1.2.1 / 120100 APKs passed packaged manifest and ZIP alignment checks. Every
replacement native entry is byte-identical to the pinned bundle after Gradle
packaging. The two 64-bit APKs passed 216 and 218 ELF alignment checks respectively.
Signing and acceptance of these new exact artifacts remain pending. Old signed
candidates under `build/release-candidate-20261004` were preserved.

The source preparation archive under `build/controlled-payloads-20261005`
retains 151 checked original upstream archives, the two custom-fetch Git source
trees, recipe/override archives, all producing build inventories, NDK sources
and notices, wrapper sources and the payload package mapping. Its 3189-entry
file inventory was independently checked after packaging. It remains marked
incomplete pending exact source/notice coverage review and application/JVM
dependency source coverage; it is not configured as the reviewed public bundle.
