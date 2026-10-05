"""Retain versioned upstream build trees and Maven parents for the R2 JVM source gaps."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from package_controlled_payloads import digest


PROJECTS = {
    "jackson-annotations": ("FasterXML/jackson-annotations", "jackson-annotations-2.22", "2.22"),
    "jackson-core": ("FasterXML/jackson-core", "jackson-core-2.22.3", "2.22.3"),
    "jackson-databind": ("FasterXML/jackson-databind", "jackson-databind-2.22.3", "2.22.3"),
    "okhttp": ("square/okhttp", "parent-4.12.0", "4.12.0"),
    "coil-core-android": ("coil-kt/coil", "3.6.3", "3.6.3"),
}
NS = {"m": "http://maven.apache.org/POM/4.0.0"}


def parent_coordinate(pom):
    parent = ET.fromstring(pom).find("m:parent", NS)
    if parent is None:
        return None
    values = tuple(parent.findtext("m:" + name, namespaces=NS)
                   for name in ("groupId", "artifactId", "version"))
    if any(value is None or re.fullmatch(r"[A-Za-z0-9_.-]+", value) is None for value in values):
        raise ValueError("Unresolved or unsafe Maven parent coordinate")
    return values


def download(url, target, limit=128 * 1024**2):
    if target.exists():
        raise ValueError("Refusing to overwrite upstream build input: " + str(target))
    for attempt in range(3):
        temporary = target.with_suffix(target.suffix + ".part")
        try:
            with urllib.request.urlopen(url, timeout=60) as response, temporary.open("xb") as stream:
                size = 0
                while block := response.read(1024**2):
                    size += len(block)
                    if size > limit:
                        raise ValueError("JVM build-input archive exceeds size limit")
                    stream.write(block)
            temporary.replace(target)
            return
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
        finally:
            temporary.unlink(missing_ok=True)


def resolve_tag(gh, repo, tag):
    reference = json.loads(subprocess.check_output(
        [str(gh), "api", f"repos/{repo}/git/ref/tags/{tag}"], text=True))
    value = reference["object"]
    records = [reference]
    for _ in range(5):
        if value["type"] == "commit":
            if re.fullmatch(r"[0-9a-f]{40}", value["sha"]) is None:
                raise ValueError("Invalid producing commit")
            return value["sha"], records
        if value["type"] != "tag":
            break
        data = json.loads(subprocess.check_output(
            [str(gh), "api", f"repos/{repo}/git/tags/{value['sha']}"], text=True))
        records.append(data)
        value = data["object"]
    raise ValueError("Upstream tag does not resolve to a commit")


def match_source_files(source_jar, tree):
    source_hashes = {}
    with tarfile.open(tree) as archive:
        for member in archive:
            if member.isfile() and member.name.endswith((".java", ".kt")):
                data = archive.extractfile(member).read()
                key = (Path(member.name).name, hashlib.sha256(data).hexdigest())
                source_hashes.setdefault(key, []).append(member.name)
    matches, unmatched = [], []
    with zipfile.ZipFile(source_jar) as archive:
        for name in archive.namelist():
            if not name.endswith((".java", ".kt")):
                continue
            data = archive.read(name)
            key = (Path(name).name, hashlib.sha256(data).hexdigest())
            if key in source_hashes:
                matches.append({"sourceJarFile": name, "upstreamFiles": source_hashes[key]})
            else:
                unmatched.append(name)
    return {"exactSourceMatches": len(matches), "matches": matches, "unmatched": unmatched}


def collect(jvm, output, gh):
    if output.exists():
        raise ValueError("Use a new JVM build-input output directory")
    output.mkdir(parents=True)
    graph = json.loads((jvm / "JVM-SOURCE-INVENTORY.json").read_text())
    parents, projects = {}, []

    def preserve_parents(pom):
        coordinate = parent_coordinate(pom)
        if coordinate is None or coordinate in parents:
            return
        if len(parents) > 24:
            raise ValueError("Unexpectedly deep Maven parent graph")
        group, name, version = coordinate
        relative = "/".join((group.replace(".", "/"), name, version, name + "-" + version + ".pom"))
        url = "https://repo.maven.apache.org/maven2/" + relative
        target = output / "maven-parents" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        download(url, target)
        parents[coordinate] = {"coordinate": list(coordinate), "url": url,
                               "file": str(target.relative_to(output)), "sha256": digest(target),
                               "bytes": target.stat().st_size}
        preserve_parents(target.read_bytes())

    for name, (repo, tag, version) in PROJECTS.items():
        item = next(x for x in graph["artifacts"] if x["binary"].get("module", {}).get("name") == name)
        if item["binary"]["module"]["version"] != version:
            raise ValueError("Build-tree pin differs from the resolved library version")
        inputs = {kind: next(d for d in item["downloads"] if d["file"].endswith(suffix))
                  for kind, suffix in (("source", "-sources.jar"), ("pom", ".pom"))}
        for entry in inputs.values():
            if digest(jvm / entry["file"]) != entry["sha256"]:
                raise ValueError("Previously preserved Maven input changed")
        preserve_parents((jvm / inputs["pom"]["file"]).read_bytes())
        commit, resolution = resolve_tag(gh, repo, tag)
        (output / (name + "-tag.json")).write_text(json.dumps(resolution, indent=2) + "\n")
        url = f"https://codeload.github.com/{repo}/tar.gz/{commit}"
        tree = output / (name + "-" + commit[:12] + ".tar.gz")
        download(url, tree, limit=(256 if name == "coil-core-android" else 128) * 1024**2)
        matching = match_source_files(jvm / inputs["source"]["file"], tree)
        projects.append({"module": item["binary"]["module"], "repo": repo, "tag": tag, "commit": commit,
                         "file": tree.name, "url": url, "sha256": digest(tree),
                         "bytes": tree.stat().st_size, "sourceMatches": matching})
        print(f"{name}: build tree preserved; {matching['exactSourceMatches']} exact source matches, "
              f"{len(matching['unmatched'])} generated/different files need classification", flush=True)
    files = [{"file": str(p.relative_to(output)), "sha256": digest(p), "bytes": p.stat().st_size}
             for p in sorted(output.rglob("*")) if p.is_file()]
    report = {"projects": projects, "mavenParents": list(parents.values()), "files": files,
              "completeCorrespondingSourcesVerified": False,
              "remaining": ["Classify unmatched source files and review combined upstream build-input closure"]}
    (output / "JVM-BUILD-INPUTS.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("jvm", "output", "gh"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    collect(args.jvm, args.output, args.gh)
