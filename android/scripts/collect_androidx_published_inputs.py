"""Preserve non-binary AndroidX AAR inputs beside exact Maven sources."""
import argparse
import json
from pathlib import Path
import re
import shutil
import stat
import tempfile
import zipfile

from package_controlled_payloads import digest, safe_name


KEEP_SUFFIXES = (
    ".xml", ".txt", ".pro", ".json", ".properties", ".proto", ".aidl",
)
KEEP_NAMES = {"AndroidManifest.xml", "R.txt", "public.txt", "proguard.txt"}
DROP_NAMES = {"classes.jar", "lint.jar"}
DROP_PREFIXES = ("libs/", "jni/", "META-INF/versions/")
ENTRY_LIMIT = 32 * 1024**2
TOTAL_LIMIT = 256 * 1024**2


def selected_artifacts(inventory):
    for item in inventory["artifacts"]:
        module = item.get("binary", {}).get("module", {})
        if module.get("group", "").startswith("androidx."):
            yield item


def retain_entry(name):
    base = Path(name).name
    if base in DROP_NAMES or any(name.startswith(prefix) for prefix in DROP_PREFIXES):
        return False
    if name.startswith("META-INF/"):
        return base.upper().startswith(("LICENSE", "NOTICE", "COPYING"))
    if name.startswith(("res/", "assets/")):
        return True
    return base in KEEP_NAMES or name.endswith(KEEP_SUFFIXES)


def collect(inventory_path, output):
    if output.exists():
        raise ValueError("Use a new published-input directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="androidx-published-", dir=output.parent) as directory:
        stage = Path(directory) / "inputs"
        stage.mkdir()
        report = collect_into(inventory_path, stage)
        stage.rename(output)
    return report


def collect_into(inventory_path, output):
    graph = json.loads(inventory_path.read_text())
    records = []
    seen = set()
    for item in selected_artifacts(graph):
        binary = item["binary"]
        module = binary["module"]
        aar = Path(binary["file"])
        key = (module["group"], module["name"], module["version"])
        if key in seen:
            continue
        seen.add(key)
        if not aar.is_file():
            raise FileNotFoundError(aar)
        if aar.stat().st_size != binary["bytes"] or digest(aar) != binary["sha256"]:
            raise ValueError("Pinned AndroidX artifact changed: " + str(aar))
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in (".", "..") for part in key):
            raise ValueError("Unsafe Maven coordinate")
        safe = "-".join((module["group"], module["name"], module["version"]))
        target = output / safe
        target.mkdir(exist_ok=True)
        retained = []
        excluded = []
        names, total = set(), 0
        with zipfile.ZipFile(aar) as archive:
            for info in archive.infolist():
                name = safe_name(info.filename)
                if name in names:
                    raise ValueError("Duplicate published-input entry: " + name)
                names.add(name)
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError("Published-input symlink: " + name)
                if info.is_dir():
                    continue
                if not retain_entry(name):
                    excluded.append(name)
                    continue
                total += info.file_size
                if info.file_size > ENTRY_LIMIT or total > TOTAL_LIMIT:
                    raise ValueError("Published-input size limit exceeded")
                destination = target / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, destination.open("wb") as sink:
                    shutil.copyfileobj(source, sink)
                retained.append({"file": name, "sha256": digest(destination),
                                 "bytes": destination.stat().st_size})
        records.append({"module": module, "aar": str(aar),
                        "aarSha256": digest(aar), "aarBytes": aar.stat().st_size,
                        "retained": retained, "excludedBinaryOrUnsupported": excluded})
    report = {"schemaVersion": 1, "component": "androidx-published-aar-inputs",
              "records": records,
              "scope": "Published AAR resources, manifests, metadata and notices; classes/native binaries excluded"}
    report["files"] = [{"file": str(path.relative_to(output)), "sha256": digest(path),
                        "bytes": path.stat().st_size}
                       for path in sorted(output.rglob("*")) if path.is_file()]
    (output / "ANDROIDX-PUBLISHED-INPUTS.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.inventory, args.output)
    print(f"collected {len(result['records'])} AndroidX AAR inputs")
