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
from verify_apk import verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sources", type=Path, required=True,
                        help="Reviewed local archive of corresponding third-party runtime sources")
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
    if not (android / "LICENSE").is_file():
        raise SystemExit("Android release license has not been approved")
    if not args.sources.is_file() or args.sources.stat().st_size == 0:
        raise SystemExit("A reviewed corresponding-source archive is required")
    if subprocess.check_output(["git", "status", "--porcelain", "--", "android"], cwd=repo).strip():
        raise SystemExit("Commit Android changes before packaging a public release")
    sdk = Path(os.environ.get("ANDROID_HOME", os.environ.get("ANDROID_SDK_ROOT", "")))
    tools = sorted((sdk / "build-tools").glob("*/apksigner"))
    if not tools:
        raise SystemExit("Android build tools are missing")
    output = android / "dist"
    output.mkdir(exist_ok=True)
    if any(output.iterdir()):
        raise SystemExit("Use an empty android/dist directory to avoid publishing stale artifacts")
    packaged = []
    verified = []
    for abi in ("arm64-v8a", "armeabi-v7a", "x86", "x86_64"):
        apk = android / f"app/build/outputs/apk/release/app-{abi}-release.apk"
        verified.append(verify(apk, tools[-1].parent, version, version_code, certificate))
        target = output / f"YouTubeHarvester-{version}-{abi}-release.apk"
        shutil.copy2(apk, target)
        packaged.append(target)
    app_source = output / f"YouTubeHarvester-{version}-android-source.tar.gz"
    subprocess.run(["git", "archive", "--format=tar.gz", f"--output={app_source}", "HEAD", "android"], cwd=repo, check=True)
    packaged.append(app_source)
    native_source = output / f"YouTubeHarvester-{version}-runtime-sources.tar.gz"
    # Validate format without extracting untrusted archive paths.
    with tarfile.open(args.sources, "r:gz") as archive:
        if not archive.getmembers():
            raise SystemExit("Runtime source archive is empty")
    shutil.copy2(args.sources, native_source)
    packaged.append(native_source)
    provenance = output / "BUILD-INFO-android.json"
    provenance.write_text(json.dumps({
        "version": version,
        "versionCode": version_code,
        "commit": commit,
        "tag": args.tag,
        "buildTask": "assembleRelease",
        "artifacts": verified,
        "runtime": dict(line.split("=", 1) for line in
                        (android / "runtime.properties").read_text().splitlines() if "=" in line),
    }, indent=2) + "\n", encoding="utf-8")
    packaged.append(provenance)
    checksums = output / "SHA256SUMS-android.txt"
    lines = []
    for path in packaged:
        with path.open("rb") as stream:
            lines.append(f"{hashlib.file_digest(stream, 'sha256').hexdigest()}  {path.name}\n")
    checksums.write_text("".join(lines), encoding="utf-8")
    print(json.dumps({"version": version, "artifacts": [p.name for p in packaged]}))


if __name__ == "__main__":
    main()
