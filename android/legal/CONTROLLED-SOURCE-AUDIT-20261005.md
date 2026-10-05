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

Local detailed report: `android/build/controlled-source-audit-20261005.json`.
It deliberately records `completeCorrespondingSourcesVerified=false`.

## Remaining Before Publication

- `ca-certificates` downloads a PEM data file without an unpacked source tree.
  Its producing recipe and SHA256 are preserved. Verify the final PEM against
  that hash and retain the declared MPL-2.0 notice; absence of a source worktree
  is not treated as evidence of missing C source code.
- `libc++` copies `libc++_shared.so` from the pinned NDK instead of compiling it.
  Preserve matching NDK/LLVM source and notices, or rebuild this library from
  corresponding source. Its preserved ELF is not source code. The recipe's
  generic NCSA text alone is not a complete notice/provenance review.
- Some compatibility/generated packages have their source in the recipe tree
  or custom source-fetch hooks. Include those recipes and local C/header files,
  not only cached upstream archives.
- Existing APKs contain `Cryptodome 3.23.0` and `mutagen 1.47.0`; the initial
  core targets did not include them. A separate source-built extension target
  is now pinned in `native/python-extensions-lock.json`. Its artifact must be
  checked before replacing the old runtime; do not reuse old extension ELFs.
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
