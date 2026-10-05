"""Preserve missing AndroidX settings plugins and wrappers at the audited commits."""
import argparse
import base64
import json
from pathlib import Path
import tarfile
import time
import urllib.request

from audit_application_sources import COMMITS
from collect_controlled_sources import validate_file_inventory
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


def collect_release_inputs(output, release_sources, resume=False):
    from collect_androidx_release_sources import ROOT, gitiles_json
    if output.exists() and not resume:
        raise ValueError("Use a new build-input output directory")
    source_report = json.loads((release_sources / "ANDROIDX-RELEASE-SOURCES.json").read_text())
    validate_file_inventory(release_sources, source_report)
    report_path = output / "ANDROIDX-BUILD-INPUTS.json"
    if report_path.exists():
        validate_file_inventory(output, json.loads(report_path.read_text()))
    output.mkdir(parents=True, exist_ok=resume)
    commits = sorted({r["commit"] for r in source_report["artifacts"]})
    records, snapshots = [], []
    build_trees = {"buildSrc", "gradle", "androidx-settings-plugins", "placeholder", "inspection", "lint-checks"}
    for commit in commits:
        folder = output / commit
        folder.mkdir(exist_ok=True)
        root_url = ROOT + f"+/{commit}/?format=JSON"
        receipt_path = folder / "ROOT-RECEIPT.json"
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if receipt["commit"] != commit or receipt["url"] != root_url:
                raise ValueError("AndroidX root receipt identity changed")
            root = receipt["root"]
        else:
            root = gitiles_json(root_url)
            receipt_path.write_text(json.dumps({"commit": commit, "url": root_url,
                                                "root": root}, indent=2) + "\n")
        records.append({"commit": commit, "url": root_url,
                        "file": str(receipt_path.relative_to(output)),
                        "sha256": digest(receipt_path), "bytes": receipt_path.stat().st_size})
        retained = []
        for entry in root["entries"]:
            name, kind = entry["name"], entry["type"]
            tree = kind == "tree" and name in build_trees
            blob = kind == "blob" and (name.endswith((".gradle", ".gradle.kts", ".properties", ".toml", ".groovy")) or
                                       name in {"LICENSE.txt", "NOTICE", "NOTICE.txt", "README.md", "gradlew", "gradlew.bat"})
            if not tree and not blob:
                continue
            filename = name + ".tar.gz" if tree else name
            target = folder / filename
            url = (ROOT + f"+archive/{commit}/{name}.tar.gz" if tree else
                   ROOT + f"+/{commit}/{name}?format=TEXT")
            if not target.exists():
                download(url, target, encoded=blob)
            if tree:
                with tarfile.open(target) as archive:
                    if not any(m.isfile() for m in archive):
                        raise ValueError("Empty AndroidX build tree")
            retained.append(name)
            records.append({"commit": commit, "url": url, "file": str(target.relative_to(output)),
                            "sha256": digest(target), "bytes": target.stat().st_size})
        if "buildSrc" not in retained or not any(n.startswith("settings.gradle") for n in retained):
            raise ValueError("AndroidX root build inputs incomplete: " + commit)
        snapshots.append({"commit": commit, "retainedRootEntries": retained,
                          "upstreamRoot": root})
        print(commit[:12] + ": root build scripts, tooling and notices preserved", flush=True)
    report = {"purpose": "Pinned module producer root scripts, buildSrc, settings tooling and notices",
              "snapshots": snapshots, "files": records, "completeCorrespondingSourcesVerified": False}
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-sources", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.release_sources:
        collect_release_inputs(args.output, args.release_sources, args.resume)
    else:
        if args.resume:
            parser.error("--resume requires --release-sources")
        collect(args.output)
