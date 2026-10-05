"""Retain immutable AndroidX release trees and report exact published source coverage."""
import argparse
import base64
import json
from pathlib import Path
import re
import time
import tomllib
import urllib.request
from urllib.error import HTTPError

from collect_controlled_sources import validate_file_inventory
from collect_jvm_build_inputs import download, match_source_files, source_tree_index
from package_controlled_payloads import digest


ROOT = "https://android.googlesource.com/platform/frameworks/support/"
FAMILIES = {
    "activity": ("activity", "activity", "ACTIVITY"),
    "annotation": ("annotation", "annotation", "ANNOTATION"),
    "appcompat": ("appcompat", "appcompat", "APPCOMPAT"),
    "arch.core": ("arch-core", "arch/core", "ARCH_CORE"),
    "autofill": ("autofill", "autofill", "AUTOFILL"),
    "collection": ("collection", "collection", "COLLECTION"),
    "compose.animation": ("compose", "compose/animation", "COMPOSE"),
    "compose.foundation": ("compose", "compose/foundation", "COMPOSE"),
    "compose.material": ("compose", "compose/material", "COMPOSE"),
    "compose.material3": ("compose-material3", "compose/material3", "COMPOSE_MATERIAL3"),
    "compose.runtime": ("compose", "compose/runtime", "COMPOSE_RUNTIME"),
    "compose.ui": ("compose", "compose/ui", "COMPOSE"),
    "concurrent": ("concurrent", "concurrent", "CONCURRENT"),
    "core": ("core", "core", "CORE"),
    "cursoradapter": ("main", "cursoradapter", "CURSORADAPTER"),
    "customview": ("customview", "customview", "CUSTOMVIEW"),
    "datastore": ("datastore", "datastore", "DATASTORE"),
    "drawerlayout": ("drawerlayout", "drawerlayout", "DRAWERLAYOUT"),
    "emoji2": ("emoji2", "emoji2", "EMOJI2"),
    "exifinterface": ("exifinterface", "exifinterface", "EXIFINTERFACE"),
    "fragment": ("fragment", "fragment", "FRAGMENT"),
    "graphics": ("graphics", "graphics", "GRAPHICS_PATH"),
    "interpolator": ("main", "interpolator", "INTERPOLATOR"),
    "lifecycle": ("lifecycle", "lifecycle", "LIFECYCLE"),
    "loader": ("loader", "loader", "LOADER"),
    "navigationevent": ("navigationevent", "navigationevent", "NAVIGATIONEVENT"),
    "profileinstaller": ("profileinstaller", "profileinstaller", "PROFILEINSTALLER"),
    "resourceinspection": ("resourceinspection", "resourceinspection", "RESOURCEINSPECTION"),
    "room": ("room", "room", "ROOM"),
    "savedstate": ("savedstate", "savedstate", "SAVEDSTATE"),
    "sqlite": ("sqlite", "sqlite", "SQLITE"),
    "startup": ("startup", "startup", "STARTUP"),
    "tracing": ("tracing", "tracing", "TRACING"),
    "vectordrawable": ("main", "vectordrawable", "VECTORDRAWABLE"),
    "versionedparcelable": ("main", "versionedparcelable", "VERSIONED_PARCELABLE"),
    "viewpager": ("main", "viewpager", "VIEWPAGER"),
    "window": ("window", "window", "WINDOW"),
    "work": ("work", "work", "WORK"),
}
FIXED = {"datastore": "03aea68c431abd3fa436e9f8fa9b9cda12f18334",
         "graphics": "8a05a22af450d589ef911d772a001a49dcb05b71"}
VERSION_COMMITS = {
    ("activity", "1.13.0"): "706d9b26589a836d9f01400a8c33c288be043fcd",
    ("annotation", "1.10.0"): "ef97474ecef4ec4c50eb995b569ee670ce50d4d5",
    ("annotation", "1.5.0"): "f6a144dc5cb17b4ffaa76b6feba7fc6e940de984",
    ("autofill", "1.0.0"): "0afd9552e241b2b0eb29298239cdfec10d314b51",
    ("collection", "1.5.0"): "cbdae62495aa2202c57c5baef4fa9ea5b35ea6ae",
    ("emoji2", "1.4.0"): "630d6fc74a5df2961dde2ef6cc0aab4989145b96",
    ("window", "1.5.0"): "a1f9af8f027354c304b677047519d90e99e6ab4a",
    ("sqlite", "2.6.2"): "1ec5220f6b5a4289e45bbd5556d2770ac1319049",
    ("compose.material", "1.7.8"): "e51a011fca975678b1de50f9c5714b958c8c4b0b",
    ("compose.material3", "1.4.0"): "481494000a889d22766acae98cc0975c4842c445",
    ("fragment", "1.5.4"): "79713716bccad6256bd5f11c767318f51cc85c67",
    ("savedstate", "1.4.0"): "8e7998752c4c90da920dc21f0a553ae32b5c9000",
    ("startup", "1.1.1"): "84791e325d3d815537b80c27e19cbb7e65cf96d3",
    ("tracing", "1.2.0"): "60117810ce9ae9cf99ebc9f355f221e5bec062a2",
    ("versionedparcelable", "1.1.1"): "346bc41692f9bbfcc5b2ac1e0394ee747da9dea3",
    ("navigationevent", "1.0.0"): "cd68042ced872596399364b454064000859a2929",
    ("concurrent", "1.1.0"): "64ffb2122739cbaa0e86f19cdae8e0537bb98cf6",
    ("customview", "1.0.0"): "96237d5a9aabb984d35a07fb2d17f4f01cb905c7",
    ("drawerlayout", "1.0.0"): "96237d5a9aabb984d35a07fb2d17f4f01cb905c7",
    ("loader", "1.0.0"): "96237d5a9aabb984d35a07fb2d17f4f01cb905c7",
    ("cursoradapter", "1.0.0"): "96237d5a9aabb984d35a07fb2d17f4f01cb905c7",
    ("interpolator", "1.0.0"): "96237d5a9aabb984d35a07fb2d17f4f01cb905c7",
    ("viewpager", "1.0.0"): "96237d5a9aabb984d35a07fb2d17f4f01cb905c7",
    ("vectordrawable", "1.1.0"): "24356fbe0255dc4df0e45c676d72eab2a5c19f5f",
}
MODULE_COMMITS = {
    ("androidx.customview", "customview-poolingcontainer", "1.0.0"):
        "0a9065ee52d81df8e7773741d211d41f04a0136b",
}


def gitiles_json(url):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read(8 * 1024**2 + 1)
            break
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 4:
                raise
            retry_after = error.headers.get("Retry-After", "")
            delay = min(int(retry_after), 120) if retry_after.isdigit() else 15 * (attempt + 1)
            time.sleep(max(delay, 1))
    if len(data) > 8 * 1024**2 or not data.startswith(b")]}'"):
        raise ValueError("Invalid Gitiles JSON response")
    return json.loads(data[4:])


def source_variants(item):
    module = item["binary"]["module"]
    family = module["group"].removeprefix("androidx.")
    branch, tree, version_key = FAMILIES[family]
    if module["name"] == "annotation-experimental":
        branch, version_key = "annotation-annotation-experimental", "ANNOTATION_EXPERIMENTAL"
    if module["name"] == "customview-poolingcontainer":
        branch, version_key = "customview-customview-poolingcontainer", "CUSTOMVIEW_POOLINGCONTAINER"
    if module["name"] == "core-viewtree":
        version_key = "CORE_VIEWTREE"
    if family == "vectordrawable" and module["version"] == "1.1.0":
        tree = "graphics/drawable"
    return family, "androidx-" + branch + "-release", tree, version_key


def version_metadata(commit, directory):
    """Read version metadata when that historical tree actually shipped it.

    Early AndroidX release snapshots predate libraryversions.toml.  A missing
    file is recorded in the receipt and leaves treeVersion unset; it must not
    turn an otherwise valid immutable source snapshot into a network failure.
    """
    versions_url = ROOT + f"+/{commit}/libraryversions.toml?format=TEXT"
    versions_file = directory / "libraryversions.toml"
    metadata = {"url": versions_url, "status": "present"}
    if not versions_file.exists():
        try:
            with urllib.request.urlopen(versions_url, timeout=60) as response:
                encoded = response.read(2 * 1024**2 + 1)
            if len(encoded) > 2 * 1024**2:
                raise ValueError("AndroidX version metadata exceeds size limit")
            decoded = base64.b64decode(encoded, validate=True)
            tomllib.loads(decoded.decode())
            versions_file.write_bytes(decoded)
        except HTTPError as error:
            if error.code != 404:
                raise
            metadata.update({"status": "not-present", "httpStatus": 404})
            return {}, metadata
    return tomllib.loads(versions_file.read_text()).get("versions", {}), metadata


def collect(jvm, output, families=None, resume=False):
    if output.exists() and not resume:
        raise ValueError("Use a new AndroidX source directory")
    old = None
    if (output / "ANDROIDX-RELEASE-SOURCES.json").is_file():
        old = json.loads((output / "ANDROIDX-RELEASE-SOURCES.json").read_text())
        validate_file_inventory(output, old)
    output.mkdir(parents=True, exist_ok=resume)
    graph = json.loads((jvm / "JVM-SOURCE-INVENTORY.json").read_text())
    previous = {tuple(r["module"][k] for k in ("group", "name", "version")): r["commit"]
                for r in old["artifacts"]} if old else {}
    heads = gitiles_json(ROOT + "+refs/heads?format=JSON")
    selected = [a for a in graph["artifacts"] if a["binary"].get("module", {}).get("group", "").startswith("androidx.")
                and (families is None or a["binary"]["module"]["group"].removeprefix("androidx.") in families)]
    snapshots, records = {}, []
    for item in selected:
        family, branch, tree, version_key = source_variants(item)
        identity = tuple(item["binary"]["module"][k] for k in ("group", "name", "version"))
        version_commit = MODULE_COMMITS.get(identity) or VERSION_COMMITS.get((family, identity[2]))
        commit = version_commit or FIXED.get(family) or previous.get(identity) or heads.get(branch, {}).get("value")
        if commit is None:
            raise ValueError("No official release ref for " + family + ": " + branch)
        if not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise ValueError("Invalid AndroidX source commit")
        key = (tree, commit)
        if key not in snapshots:
            directory = output / (tree.replace("/", "-") + "-" + commit[:12])
            directory.mkdir(exist_ok=True)
            archive_path = directory / "module-tree.tar.gz"
            archive_url = ROOT + f"+archive/{commit}/{tree}.tar.gz"
            if not archive_path.exists():
                download(archive_url, archive_path, limit=256 * 1024**2)
            index = source_tree_index(archive_path)
            versions, version_metadata_record = version_metadata(commit, directory)
            receipt = {"discoveryRef": branch, "resolvedCommit": commit,
                       "moduleTree": tree, "archiveUrl": archive_url,
                       "versionsUrl": version_metadata_record["url"],
                       "fixedPreviouslyAuditedCommit": family in FIXED,
                       "versionCommitSelected": version_commit is not None,
                       "versionMetadata": version_metadata_record}
            receipt_path = directory / "GITILES-RECEIPT.json"
            if receipt_path.exists():
                saved = json.loads(receipt_path.read_text())
                for field in ("resolvedCommit", "moduleTree", "archiveUrl"):
                    if saved[field] != receipt[field]:
                        raise ValueError("AndroidX source receipt identity changed")
            else:
                receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
            snapshots[key] = (archive_path, index, versions)
        archive_path, index, versions = snapshots[key]
        source = next(d for d in item["downloads"] if d["file"].endswith("-sources.jar"))
        if digest(jvm / source["file"]) != source["sha256"]:
            raise ValueError("Published AndroidX source JAR changed")
        matching = match_source_files(jvm / source["file"], archive_path, index)
        module = item["binary"]["module"]
        record = {"module": module, "commit": commit, "tree": tree,
                  "file": str(archive_path.relative_to(output)), "sourceSha256": source["sha256"],
                  "versionKey": version_key, "treeVersion": versions.get(version_key),
                  "sourceMatches": matching}
        records.append(record)
        print(f"{module['name']}:{module['version']}: {matching['exactSourceMatches']} exact sources, "
              f"{len(matching['unmatched'])} unresolved; tree version={versions.get(version_key)}", flush=True)
    files = [{"file": str(p.relative_to(output)), "sha256": digest(p), "bytes": p.stat().st_size}
             for p in sorted(output.rglob("*")) if p.is_file() and p.name != "ANDROIDX-RELEASE-SOURCES.json"
             and not p.name.endswith(".part")]
    unresolved = [{"module": r["module"], "unmatched": r["sourceMatches"]["unmatched"],
                   "treeVersion": r["treeVersion"]} for r in records if r["sourceMatches"]["unmatched"]]
    report = {"artifacts": records, "files": files, "unresolved": unresolved,
              "completeCorrespondingSourcesVerified": False,
              "scope": "Immutable upstream module trees; branch discovery is not a producing-commit attestation",
              "remaining": ["Resolve different/generated sources and review resources, generators and build closure"]}
    (output / "ANDROIDX-RELEASE-SOURCES.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("jvm", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--family", action="append", choices=FAMILIES)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    collect(args.jvm, args.output, args.family, args.resume)
