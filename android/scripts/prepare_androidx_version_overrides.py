"""Prepare explicit version-only rebuild patches for source-identical snapshots."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import tomllib

from collect_controlled_sources import validate_file_inventory


def patch_versions(original, replacements):
    parsed = tomllib.loads(original)
    revised = original
    for key, (expected, replacement) in sorted(replacements.items()):
        if parsed["versions"].get(key) != expected:
            raise ValueError("Unexpected original version: " + key)
        if not re.fullmatch(r"[A-Z0-9_]+", key) or not re.fullmatch(r"[0-9A-Za-z.-]+", replacement):
            raise ValueError("Invalid version key/value")
        pattern = re.compile(r'(?m)^(' + re.escape(key) + r'\s*=\s*)"' + re.escape(expected) + r'"(?=\s*(?:#.*)?$)')
        revised, count = pattern.subn(lambda match: match[1] + '"' + replacement + '"', revised)
        if count != 1:
            raise ValueError("Ambiguous version assignment: " + key)
    result = tomllib.loads(revised)
    wanted = {**parsed["versions"], **{key: value[1] for key, value in replacements.items()}}
    if result != {**parsed, "versions": wanted}:
        raise ValueError("Version patch changed unrelated inputs")
    return revised


def prepare(sources, builds, output):
    if output.exists():
        raise ValueError("Preserve existing rebuild patches")
    release = json.loads((sources / "ANDROIDX-RELEASE-SOURCES.json").read_text())
    build = json.loads((builds / "ANDROIDX-BUILD-INPUTS.json").read_text())
    validate_file_inventory(sources, release)
    validate_file_inventory(builds, build)
    selected = [r for r in release["artifacts"] if r["treeVersion"] not in (None, r["module"]["version"])]
    replacements = {}
    for item in selected:
        values = replacements.setdefault(item["commit"], {})
        value = (item["treeVersion"], item["module"]["version"])
        if item["versionKey"] in values and values[item["versionKey"]] != value:
            raise ValueError("Conflicting artifact versions")
        values[item["versionKey"]] = value
    patches = []
    for commit, values in sorted(replacements.items()):
        original = (builds / commit / "libraryversions.toml").read_text()
        revised = patch_versions(original, values)
        diff = "".join(difflib.unified_diff(original.splitlines(keepends=True), revised.splitlines(keepends=True),
                                         fromfile="a/libraryversions.toml", tofile="b/libraryversions.toml"))
        patches.append((commit + "-versions.patch", diff.encode(), {
            "commit": commit, "originalSha256": hashlib.sha256(original.encode()).hexdigest(),
            "revisedSha256": hashlib.sha256(revised.encode()).hexdigest(),
            "versionKeys": {key: {"snapshotVersion": v[0], "rebuildVersion": v[1]} for key, v in values.items()}}))
    output.mkdir(parents=True)
    records = []
    for filename, data, metadata in patches:
        (output / filename).write_bytes(data)
        records.append({**metadata, "file": filename, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    result = {"schemaVersion": 1, "artifacts": [{"module": r["module"], "commit": r["commit"],
                                                 "versionKey": r["versionKey"]} for r in selected],
              "files": records, "completeCorrespondingSourcesVerified": False,
              "scope": "Explicit version-only rebuild inputs, not producing-commit or binary reproducibility proof"}
    (output / "ANDROIDX-VERSION-OVERRIDES.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--builds", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = prepare(args.sources, args.builds, args.output)
    print(json.dumps({"artifacts": len(report["artifacts"]), "patches": len(report["files"])}))
