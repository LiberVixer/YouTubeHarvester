"""Restore the pinned payload bundle from GitHub without publishing anything."""
import argparse
import configparser
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from package_controlled_payloads import digest


def fetch(android, gh):
    properties = configparser.ConfigParser(interpolation=None)
    properties.read_string("[payload]\n" + (android / "native/controlled-payloads.properties").read_text())
    config = properties["payload"]
    expected = config["sha256"]
    if not re.fullmatch("[a-f0-9]{64}", expected):
        raise ValueError("Invalid payload hash")
    output = android / config["bundle"]
    if not output.resolve().is_relative_to(android.resolve() / "build"):
        raise ValueError("Payload path must remain in android/build")
    if output.exists():
        if digest(output) != expected:
            raise ValueError("Existing payload checksum mismatch; refusing replacement")
        print("Controlled payload bundle already verified.")
        return
    asset = config["asset"]
    if Path(asset).name != asset or any(c in asset for c in "*?[]"):
        raise ValueError("An exact payload asset name is required")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="payload-download-", dir=output.parent) as directory:
        subprocess.run([gh, "release", "download", config["release"], "--repo", config["repository"],
                        "--pattern", asset, "--dir", directory], check=True)
        source = Path(directory) / asset
        if digest(source) != expected:
            raise ValueError("Downloaded payload checksum mismatch")
        os.link(source, output)
    print("Controlled payload bundle downloaded and verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android", type=Path, required=True)
    parser.add_argument("--gh", default=shutil.which("gh") or "gh")
    args = parser.parse_args()
    fetch(args.android, args.gh)
