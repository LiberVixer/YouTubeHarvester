"""Verify signed Android artifacts and package exact committed application sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from verify_apk import verify


ABIS = ("arm64-v8a", "armeabi-v7a", "x86", "x86_64")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_apk_abi(apk, abi):
    with zipfile.ZipFile(apk) as archive:
        packaged = {name.split("/")[1] for name in archive.namelist()
                    if name.startswith("lib/") and len(name.split("/")) == 3 and name.endswith(".so")}
    if packaged != {abi}:
        raise ValueError("APK native ABI differs from its release filename")


def check_source_review(sources, review_path, commit, apks):
    review = json.loads(review_path.read_text())
    if (type(review.get("schemaVersion")) is not int or review.get("schemaVersion") != 1 or
            review.get("completeCorrespondingSourcesVerified") is not True or
            review.get("remaining") != []):
        raise ValueError("Corresponding-source review is incomplete")
    if review.get("releaseCommit") != commit:
        raise ValueError("Source review belongs to a different release commit")
    if review.get("sourceArchiveSha256") != digest(sources):
        raise ValueError("Reviewed source archive changed")
    actual = {abi: digest(apk) for abi, apk in apks.items()}
    if set(actual) != set(ABIS) or review.get("apkSha256") != actual:
        raise ValueError("Source review does not cover these exact four signed APKs")
    # Read format without extracting paths supplied by the source archive.
    with tarfile.open(sources, "r|gz") as archive:
        if not any(member.isfile() for member in archive):
            raise ValueError("Runtime source archive is empty")
    return review


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sources", type=Path, required=True,
                        help="Reviewed local archive of corresponding third-party runtime sources")
    parser.add_argument("--review", type=Path, required=True,
                        help="Completed review binding the source archive, release commit and APK hashes")
    parser.add_argument("--candidate-dir", type=Path,
                        help="Preserve and package already signed candidates instead of Gradle outputs")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    android = Path(__file__).resolve().parents[1]
    repo = android.parent
    gradle = (android / "app/build.gradle.kts").read_text()
    version = re.search(r'versionName = "([^"]+)"', gradle).group(1)
    version_code = int(re.search(r'versionCode = (\d+)', gradle).group(1))
    certificate = os.environ.get("YTH_ANDROID_CERT_SHA256", "").lower()
    if not re.fullmatch(r"[a-f0-9]{64}", certificate):
        raise SystemExit("Set the approved YTH_ANDROID_CERT_SHA256 before packaging")
    if args.tag != f"android-v{version}":
        raise SystemExit("Tag must match the Android versionName")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    tagged_commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", f"refs/tags/{args.tag}^{{commit}}"], cwd=repo, text=True,
    ).strip()
    if tagged_commit != commit:
        raise SystemExit("Release tag must point to the source commit being packaged")
    for name in ("LICENSE", "NOTICE"):
        if not (android / name).is_file() or (android / name).stat().st_size == 0:
            raise SystemExit("Android release license/notice is missing: " + name)
    if not args.sources.is_file() or args.sources.stat().st_size == 0:
        raise SystemExit("A reviewed corresponding-source archive is required")
    if subprocess.check_output(["git", "status", "--porcelain", "--", "android"], cwd=repo).strip():
        raise SystemExit("Commit Android changes before packaging a public release")
    apks = {abi: (args.candidate_dir / f"YouTubeHarvester-{version}-{abi}-release.apk"
                  if args.candidate_dir else
                  android / f"app/build/outputs/apk/release/app-{abi}-release.apk") for abi in ABIS}
    review = check_source_review(args.sources, args.review, commit, apks)
    sdk = Path(os.environ.get("ANDROID_HOME", os.environ.get("ANDROID_SDK_ROOT", "")))
    tools = sorted((sdk / "build-tools").glob("*/apksigner"))
    if not tools:
        raise SystemExit("Android build tools are missing")
    output = args.output or android / "dist"
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise SystemExit("Use a new or empty output directory to avoid publishing stale artifacts")
    verified = []
    for abi, apk in apks.items():
        result = verify(apk, tools[-1].parent, version, version_code, certificate)
        check_apk_abi(apk, abi)
        result.update({"abi": abi, "sha256": review["apkSha256"][abi]})
        verified.append(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yth-release-", dir=output.parent) as directory:
        stage = Path(directory)
        packaged = []
        for abi, apk in apks.items():
            target = stage / f"YouTubeHarvester-{version}-{abi}-release.apk"
            shutil.copy2(apk, target)
            if digest(target) != review["apkSha256"][abi]:
                raise ValueError("Signed candidate changed during packaging")
            packaged.append(target)
        app_source = stage / f"YouTubeHarvester-{version}-android-source.tar.gz"
        subprocess.run(["git", "archive", "--format=tar.gz", f"--output={app_source}", "HEAD", "android"],
                       cwd=repo, check=True)
        packaged.append(app_source)
        native_source = stage / f"YouTubeHarvester-{version}-runtime-sources.tar.gz"
        shutil.copy2(args.sources, native_source)
        if digest(native_source) != review["sourceArchiveSha256"]:
            raise ValueError("Source archive changed during packaging")
        packaged.append(native_source)
        source_review = stage / "SOURCE-REVIEW-android.json"
        source_review.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        packaged.append(source_review)
        for source_name, target_name in (("LICENSE", "LICENSE-android.txt"), ("NOTICE", "NOTICE-android.txt")):
            target = stage / target_name
            shutil.copy2(android / source_name, target)
            packaged.append(target)
        provenance = stage / "BUILD-INFO-android.json"
        provenance.write_text(json.dumps({
            "version": version, "versionCode": version_code, "commit": commit, "tag": args.tag,
            "buildTask": "assembleRelease", "reusedSignedCandidates": args.candidate_dir is not None,
            "artifacts": verified, "sourceReviewSha256": digest(source_review),
            "runtime": dict(line.split("=", 1) for line in
                            (android / "runtime.properties").read_text().splitlines() if "=" in line),
        }, indent=2) + "\n", encoding="utf-8")
        packaged.append(provenance)
        checksums = stage / "SHA256SUMS-android.txt"
        checksums.write_text("".join(f"{digest(path)}  {path.name}\n" for path in packaged), encoding="utf-8")
        stage.replace(output)
    print(json.dumps({"version": version, "artifacts": [p.name for p in packaged]}))


if __name__ == "__main__":
    main()
