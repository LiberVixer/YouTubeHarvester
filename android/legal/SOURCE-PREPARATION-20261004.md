# Corresponding Source Preparation

The owner requested preparation of Android corresponding sources on 2026-10-04.
This is a work-in-progress inventory, not a complete-source attestation.

## Confirmed Sources

- youtubedl-android 0.18.1: tag resolves to commit
  `d725d5c9a18c3a99a13ee0308bf78275dc310760`. Wrapper Kotlin/Java sources,
  Gradle files, license and upstream build instructions were collected in
  `/tmp/yth-upstream-wrapper-source-0.18.1.tar.gz`. Native binary payloads are
  deliberately excluded: they are not corresponding source code.
- QuickJS 2026-06-04 and libwebp 1.6.0: exact upstream source archives,
  pinned hashes and local rebuild scripts already exist under `android/native`
  and `android/scripts`. Include them unchanged in the final source bundle.
- Application sources and the pinned yt-dlp distribution are in the repository.

## Unresolved Native Payloads

The upstream Python and FFmpeg build instructions point to Termux recipes,
but do not pin the revisions used for the bundled binaries. Their example
Python versions also do not match the observed Python 3.12.11 runtime.
Do not use a current Termux checkout or version-matched upstream tarballs as
proof of corresponding sources for these binaries.

The complete bundle still needs matching recipes, patches and source archives
for Python, FFmpeg, OpenSSL and all embedded codec/support dependencies listed
in `RUNTIME-PROVENANCE.ru.md`, including the Python extension modules.
If provenance cannot be reconstructed reliably, rebuild the runtime from
controlled, pinned sources and repeat candidate acceptance.

The release packager's corresponding-source gate remains enabled. The partial
wrapper archive must not be supplied as the full runtime source archive.

## Upstream Investigation Result

Checked upstream Git history and existing provenance issues on 2026-10-04:

- FFmpeg 7.1.1 binary update:
  `f2280ae7d8bc8d59590c8727a89f047983867c10`.
- Python 3.12.11 binary update:
  `ed17169174832cbdd3839f7f5d5b35c9cc72e85f`.
- QuickJS integration/Python payload update:
  `4e2bb8b4dbe15d13f57cf37c72e155b9f359d3fb`.
- Existing upstream issue 363 asks for the same producing recipes and package
  manifests. Its response points to PR 361, but explicitly says that the PR
  does not establish provenance for the existing 0.18.1 runtime.
- Issue 358 is also open; no comments were present when checked.

Do not open a duplicate request or infer producing recipes from dates alone.
The shortest safe publication path needs the missing corresponding sources
from the producer, or replacement binaries rebuilt from controlled source.
An unfinished upstream PR is not a drop-in release dependency.

The known-source preparation archive is explicitly marked incomplete. Signed
APKs may be staged in a draft release, but public publication remains blocked.

References:

- https://github.com/yausername/youtubedl-android/issues/363
- https://github.com/yausername/youtubedl-android/issues/363#issuecomment-5498971934
- https://github.com/yausername/youtubedl-android/issues/358

Primary evidence:

- https://github.com/yausername/youtubedl-android/tree/d725d5c9a18c3a99a13ee0308bf78275dc310760
- https://github.com/yausername/youtubedl-android/blob/d725d5c9a18c3a99a13ee0308bf78275dc310760/BUILD_PYTHON.md
- https://github.com/yausername/youtubedl-android/blob/d725d5c9a18c3a99a13ee0308bf78275dc310760/BUILD_FFMPEG.md
