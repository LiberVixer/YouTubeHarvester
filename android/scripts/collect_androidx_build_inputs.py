"""Preserve missing AndroidX settings plugins and wrappers at the audited commits."""
import argparse
import base64
import json
from pathlib import Path
import tarfile
import time
import urllib.request

from audit_application_sources import COMMITS
from package_controlled_payloads import digest


TREES = {"graphics": ("placeholder", "gradle"),
         "datastore": ("androidx-settings-plugins", "placeholder", "gradle")}
FILES = ("gradlew",)


def download(url, target, encoded=False):
    if target.exists():
        raise ValueError("Refusing to overwrite build input: " + str(target))
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read(64 * 1024**2 + 1)
            if len(data) > 64 * 1024**2:
                raise ValueError("AndroidX build input exceeds size limit")
            if encoded:
                data = base64.b64decode(data, validate=True)
            with target.open("xb") as stream:
                stream.write(data)
            return
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def collect(output):
    if output.exists():
        raise ValueError("Use a new build-input output directory")
    output.mkdir(parents=True)
    records = []
    for family, commit in COMMITS.items():
        folder = output / family
        folder.mkdir()
        for name in TREES[family]:
            url = f"https://android.googlesource.com/platform/frameworks/support/+archive/{commit}/{name}.tar.gz"
            target = folder / (name + ".tar.gz")
            download(url, target)
            with tarfile.open(target) as archive:
                if not any(item.isfile() for item in archive):
                    raise ValueError("Empty AndroidX build-input archive")
            records.append({"commit": commit, "url": url, "file": str(target.relative_to(output)),
                            "sha256": digest(target), "bytes": target.stat().st_size})
        for name in FILES:
            url = f"https://android.googlesource.com/platform/frameworks/support/+/{commit}/{name}?format=TEXT"
            target = folder / name
            download(url, target, encoded=True)
            records.append({"commit": commit, "url": url, "file": str(target.relative_to(output)),
                            "sha256": digest(target), "bytes": target.stat().st_size})
        print(family + ": required settings/wrapper inputs preserved", flush=True)
    report = {"purpose": "Supplement to preserved module/buildSrc trees, not standalone build approval",
              "files": records, "completeCorrespondingSourcesVerified": False}
    (output / "ANDROIDX-BUILD-INPUTS.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    collect(parser.parse_args().output)
