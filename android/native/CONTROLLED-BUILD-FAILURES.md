# Controlled runtime build: previous failures and prevention

The first ABI, x86_64, completed all 157 main packages in run
[37222732575](https://github.com/LiberVixer/YouTubeHarvester/actions/runs/37222732575).
All 320 recorded file checksums were verified after downloading the artifact.
This proves neither the other three ABI builds nor public-release readiness.

| Failure encountered while preparing the first ABI | Shared correction |
| --- | --- |
| Runtime rootfs patch did not match the pinned recipes | Explicit application data path, no extra `files` directory; check patch application before Docker setup |
| foot archive checksum mismatch and unrelated terminal source downloads | Keep only ncurses and rxvt terminfo sources; verify source arrays remain paired |
| Invalid ncurses array syntax after patching | Check Bash syntax of all nine overridden dependency recipes |
| Builder host tools did not match the pinned recipes | Ubuntu 24.04 builder with Python 3.12 and the snapshot's setup scripts |
| libx11 shared-memory headers/linking | Declare and link `libandroid-shmem` |
| Fossies LZO source URL returned 404 | Verified upstream tar.gz and its pinned SHA256 |
| Graphite, libsoxr and libsrt used compatibility removed in CMake 4 | Policy floor 3.5 for legacy dependencies, passed into every build container; keep OpenMP |
| libunbound SWIG exception placeholder failed | Replace unsupported `$function` with `$action`; keep Python bindings |
| libunbound Android shared-memory linking failed | Declare and link `libandroid-shmem` |
| Debian's live texinfo archive URL returned 404 | Official Debian Snapshot, original checksum unchanged |
| SourceForge giflib source URL returned 404 | Official Debian Snapshot, original checksum unchanged |
| x265 explicitly selected OLD CMP0025/CMP0054, removed in CMake 4 | Select NEW only for these policies; preserve SOVERSION, compiler target, assembly and semaphore guards |
| GitHub artifact upload rejected Debian epoch colons in package filenames | Upload `runtime-packages.tar.gz`, not individual raw package paths |

`scripts/preflight_controlled_runtime.py` runs before the expensive host builder
installation on a temporary, patched copy of the pinned recipe tree. It checks
recipe syntax, URLs, locked checksums and the real x265/libunbound hooks for all
four architectures. It fetches and SHA256-verifies the three previously broken
LZO/texinfo/giflib URLs; the container uses these files from the normal Termux
package source-cache layout instead of downloading them again. The report,
log, checked archives and preflight script are retained with build diagnostics.
Unit tests deliberately reintroduce the old failure conditions.

This is focused regression protection, not a full cross-compilation test.
Architecture-specific compiler errors, failures of other source hosts, and
runtime/APK integration still require the actual remaining builds and checks.
No checksums are disabled, codecs removed, or release gates bypassed.
