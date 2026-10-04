"""Capture real Compose screens in a separate documentation-only Android UID."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile


PACKAGE = "com.liberivixer.youtubeharvester.screenshots"
LANGUAGES = ("en", "ru", "uk", "be", "fr", "es", "hi", "zh", "ja", "ar")
SCREENS = ("overview", "channels", "queue", "archive", "settings")


def read_images(archive: bytes) -> dict[str, bytes]:
    expected = {f"readme-screenshots/{language}/{screen}.png"
                for language in LANGUAGES for screen in SCREENS}
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        files = {}
        for entry in source:
            if entry.isdir():
                continue
            if not entry.isfile() or entry.name not in expected or entry.name in files:
                raise ValueError(f"Unexpected screenshot archive entry: {entry.name}")
            files[entry.name] = source.extractfile(entry).read()
    if files.keys() != expected:
        raise ValueError(f"Missing screenshots: {expected - files.keys()}")
    return {name.removeprefix("readme-screenshots/"): data for name, data in files.items()}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, default=Path.home() / "Android/Sdk/platform-tools/adb")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=5037)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--output", type=Path, default=root.parent / "docs/screenshots/android")
    parser.add_argument("--channel-cache", type=Path, default=Path.home() / ".cache/YTD/channels")
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--preview-metadata", type=Path, required=True)
    args = parser.parse_args()
    adb = [str(args.adb)]
    if args.host:
        adb += ["-H", args.host, "-P", str(args.port)]
    adb += ["-s", args.serial]

    def run(*command: str, **kwargs) -> subprocess.CompletedProcess:
        return subprocess.run(adb + list(command), check=True, timeout=kwargs.pop("timeout", 120), **kwargs)

    apk_folder = root / "app/build/outputs/apk/screenshots"
    metadata = json.loads((apk_folder / "output-metadata.json").read_text())
    if metadata["applicationId"] != PACKAGE:
        raise ValueError("Refusing to install over a user/tester application")
    element = next(e for e in metadata["elements"]
                   if {"filterType": "ABI", "value": "x86_64"} in e["filters"])
    assets = {
        "igm.jpg": args.channel_cache / "https___www_youtube_com__onlinegamercentral.jpg",
        "prohitec.jpg": args.channel_cache / "https___www_youtube_com__prohitec.jpg",
        "video.jpg": args.preview,
        "video.json": args.preview_metadata,
    }
    for asset in assets.values():
        if not asset.is_file():
            raise FileNotFoundError(asset)
    run("install", "-r", str(apk_folder / element["outputFile"]))
    run("install", "-r", str(root / "app/build/outputs/apk/androidTest/screenshots/app-screenshots-androidTest.apk"))
    for name, path in assets.items():
        command = f"run-as {PACKAGE} sh -c 'mkdir -p files/readme-assets && cat > files/readme-assets/{name}'"
        run("shell", "-T", command, input=path.read_bytes(), capture_output=True)
        result = run("shell", "run-as", PACKAGE, "sha256sum", f"files/readme-assets/{name}", capture_output=True, text=True)
        if result.stdout.split()[0] != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError(f"Device asset checksum mismatch: {name}")
    result = run("shell", "am", "instrument", "-w", "-r", "-e", "class",
                 "com.liberivixer.youtubeharvester.DocumentationScreenshotTest",
                 PACKAGE + ".test/androidx.test.runner.AndroidJUnitRunner",
                 capture_output=True, text=True, timeout=600)
    report = result.stdout + result.stderr
    evidence = root / "build/qa-readme-screenshots-20261004"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "capture.txt").write_text(report)
    if not re.search(r"OK \(1 test\)", report):
        raise RuntimeError(report[-6000:])
    archive = run("exec-out", "run-as", PACKAGE, "tar", "-cf", "-", "-C", "files", "readme-screenshots",
                  capture_output=True).stdout
    images = read_images(archive)
    for relative, data in images.items():
        target = args.output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest = {"package": PACKAGE, "version": element["versionName"],
                "versionCode": element["versionCode"], "theme": "dark", "fixtureData": True,
                "images": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(images.items())}}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "capture.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Captured {len(images)} dark Android screenshots: {args.output}")


if __name__ == "__main__":
    main()
