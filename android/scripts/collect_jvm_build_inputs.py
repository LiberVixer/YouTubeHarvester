"""Retain versioned upstream build trees and Maven parents for the R2 JVM source gaps."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from package_controlled_payloads import digest
from collect_controlled_sources import validate_file_inventory


PROJECTS = {
    "jackson-annotations": ("FasterXML/jackson-annotations", "jackson-annotations-2.22", "2.22"),
    "jackson-core": ("FasterXML/jackson-core", "jackson-core-2.22.3", "2.22.3"),
    "jackson-databind": ("FasterXML/jackson-databind", "jackson-databind-2.22.3", "2.22.3"),
    "okhttp": ("square/okhttp", "parent-4.12.0", "4.12.0"),
    "coil-core-android": ("coil-kt/coil", "3.6.3", "3.6.3"),
    "accompanist-drawablepainter": ("google/accompanist", "v0.37.3", "0.37.3"),
    "listenablefuture": ("google/guava", "v27.0", "1.0"),
    "okio-jvm": ("lysine-dev/okio", "parent-3.18.1", "3.18.1"),
    "commons-codec": ("apache/commons-codec", "rel/commons-codec-1.19.0", "1.19.0"),
    "commons-io": ("apache/commons-io", "rel/commons-io-2.22.0", "2.22.0"),
    "commons-compress": ("apache/commons-compress", "rel/commons-compress-1.28.0", "1.28.0"),
    "commons-lang3": ("apache/commons-lang", "rel/commons-lang-3.18.0", "3.18.0"),
    "annotations": ("JetBrains/java-annotations", "23.0.0", "23.0.0"),
    "kotlin-stdlib": ("JetBrains/kotlin", "v2.4.20", "2.4.20"),
    "kotlin-stdlib-jdk7": ("JetBrains/kotlin", "v1.8.21", "1.8.21"),
    "kotlinx-coroutines-core-jvm": ("Kotlin/kotlinx.coroutines", "1.10.2", "1.10.2"),
    "kotlinx-serialization-core-jvm": ("Kotlin/kotlinx.serialization", "v1.7.3", "1.7.3"),
    "jspecify": ("jspecify/jspecify", "v1.0.0", "1.0.0"),
    "ui-android": ("JetBrains/compose-multiplatform-core", "v1.12.0", "1.12.0"),
}
RELATED = {
    "coil-core-android": ("coil-android", "coil-compose-android", "coil-compose-core-android",
                          "coil-network-core-android", "coil-network-okhttp-android"),
    "kotlin-stdlib-jdk7": ("kotlin-stdlib-jdk8",),
    "kotlinx-coroutines-core-jvm": ("kotlinx-coroutines-android",),
    "kotlinx-serialization-core-jvm": ("kotlinx-serialization-json-jvm",),
    "ui-android": ("animation-android", "animation-core-android", "foundation-android",
                   "foundation-layout-android", "runtime-android", "runtime-saveable-android",
                   "ui-geometry-android", "ui-graphics-android", "ui-text-android",
                   "ui-unit-android", "ui-util-android"),
}
NS = {"m": "http://maven.apache.org/POM/4.0.0"}


def select_artifact(graph, name):
    group = "org.jetbrains.compose.ui" if name == "ui-android" else None
    candidates = [x for x in graph["artifacts"] if x["binary"].get("module", {}).get("name") == name
                  and (group is None or x["binary"]["module"]["group"] == group)]
    if len(candidates) != 1:
        raise ValueError("Missing or ambiguous Maven producer coordinate: " + name)
    return candidates[0]


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


def source_tree_index(tree):
    source_hashes = {}
    with tarfile.open(tree, "r|gz") as archive:
        for member in archive:
            if member.isfile() and member.name.endswith((".java", ".kt")):
                data = archive.extractfile(member).read()
                key = (Path(member.name).name, hashlib.sha256(data).hexdigest())
                source_hashes.setdefault(key, []).append(member.name)
    return source_hashes


def match_source_files(source_jar, tree, index=None):
    source_hashes = source_tree_index(tree) if index is None else index
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


def source_inputs(jvm, item):
    inputs = {kind: next(d for d in item["downloads"] if d["file"].endswith(suffix))
              for kind, suffix in (("source", "-sources.jar"), ("pom", ".pom"))}
    for entry in inputs.values():
        if digest(jvm / entry["file"]) != entry["sha256"]:
            raise ValueError("Previously preserved Maven input changed")
    return inputs


def collect(jvm, output, gh, reuse=None, selected=None, resume=False):
    if output.exists() and not resume:
        raise ValueError("Use a new JVM build-input output directory")
    if resume and reuse is not None:
        raise ValueError("Resume and reuse cannot be combined")
    resumed_projects = {}
    if resume and (output / "JVM-BUILD-INPUTS.json").is_file():
        previous = json.loads((output / "JVM-BUILD-INPUTS.json").read_text())
        validate_file_inventory(output, previous)
        resumed_projects = {x["module"]["name"]: x for x in previous["projects"]}
    output.mkdir(parents=True, exist_ok=resume)
    graph = json.loads((jvm / "JVM-SOURCE-INVENTORY.json").read_text())
    parents, projects = {}, []
    reused = {}
    if reuse is not None:
        previous = json.loads((reuse / "JVM-BUILD-INPUTS.json").read_text())
        validate_file_inventory(reuse, previous)
        for entry in previous["files"]:
            target = output / entry["file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(reuse / entry["file"], target)
        parents = {tuple(x["coordinate"]): x for x in previous["mavenParents"]}
        reused = {x["module"]["name"]: x for x in previous["projects"]}

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
        if not (resume and target.is_file()):
            download(url, target)
        parents[coordinate] = {"coordinate": list(coordinate), "url": url,
                               "file": str(target.relative_to(output)), "sha256": digest(target),
                               "bytes": target.stat().st_size}
        preserve_parents(target.read_bytes())

    for name in selected or PROJECTS:
        repo, tag, version = PROJECTS[name]
        item = select_artifact(graph, name)
        if item["binary"]["module"]["version"] != version:
            raise ValueError("Build-tree pin differs from the resolved library version")
        inputs = source_inputs(jvm, item)
        preserve_parents((jvm / inputs["pom"]["file"]).read_bytes())
        if name in reused:
            old = reused[name]
            if (old["module"], old["repo"], old["tag"]) != (item["binary"]["module"], repo, tag):
                raise ValueError("Reused producer pin differs from requested build inputs")
            commit, url, tree = old["commit"], old["url"], output / old["file"]
            if digest(tree) != old["sha256"]:
                raise ValueError("Reused producer tree changed")
        else:
            commit, resolution = resolve_tag(gh, repo, tag)
            prior = resumed_projects.get(name)
            if prior is not None and (prior["repo"], prior["tag"]) == (repo, tag) and prior["commit"] != commit:
                raise ValueError("Previously resolved producing tag changed")
            tag_path = output / (name + "-" + commit[:12] + "-tag.json")
            old_tag = output / (name + "-tag.json")
            if old_tag.exists():
                old_resolution = json.loads(old_tag.read_text())
                if old_resolution[0]["ref"] == resolution[0]["ref"] and old_resolution != resolution:
                    raise ValueError("Previously resolved producing tag changed")
            if tag_path.exists() and json.loads(tag_path.read_text()) != resolution:
                raise ValueError("Previously resolved producing tag changed")
            if not tag_path.exists():
                tag_path.write_text(json.dumps(resolution, indent=2) + "\n")
            url = f"https://codeload.github.com/{repo}/tar.gz/{commit}"
            tree = output / (name + "-" + commit[:12] + ".tar.gz")
            limit = (256 if name in {"coil-core-android", "ui-android"} else 128) * 1024**2
            if resume and tree.is_file():
                if tree.stat().st_size > limit:
                    raise ValueError("Resumed archive exceeds size limit")
            else:
                download(url, tree, limit=limit)
        index = source_tree_index(tree)
        matching = match_source_files(jvm / inputs["source"]["file"], tree, index)
        related = []
        for related_name in RELATED.get(name, ()):
            other = next(x for x in graph["artifacts"] if x["binary"].get("module", {}).get("name") == related_name
                         and x["binary"]["module"]["version"] == version
                         and (name != "ui-android" or
                              x["binary"]["module"]["group"].startswith("org.jetbrains.compose.")))
            other_inputs = source_inputs(jvm, other)
            preserve_parents((jvm / other_inputs["pom"]["file"]).read_bytes())
            related.append({"module": other["binary"]["module"],
                            "sourceSha256": other_inputs["source"]["sha256"],
                            "sourceMatches": match_source_files(jvm / other_inputs["source"]["file"], tree, index)})
        projects.append({"module": item["binary"]["module"], "repo": repo, "tag": tag, "commit": commit,
                         "file": tree.name, "url": url, "sha256": digest(tree),
                         "bytes": tree.stat().st_size, "sourceMatches": matching,
                         "relatedArtifacts": related})
        print(f"{name}: build tree preserved; {matching['exactSourceMatches']} exact source matches, "
              f"{len(matching['unmatched'])} generated/different files need classification", flush=True)
        for other in related:
            match = other["sourceMatches"]
            print(f"  {other['module']['name']}: {match['exactSourceMatches']} exact, "
                  f"{len(match['unmatched'])} need classification", flush=True)
    files = [{"file": str(p.relative_to(output)), "sha256": digest(p), "bytes": p.stat().st_size}
             for p in sorted(output.rglob("*")) if p.is_file() and p.name != "JVM-BUILD-INPUTS.json"
             and not p.name.endswith(".part")]
    report = {"projects": projects, "mavenParents": list(parents.values()), "files": files,
              "completeCorrespondingSourcesVerified": False,
              "remaining": ["Classify unmatched source files and review combined upstream build-input closure"]}
    (output / "JVM-BUILD-INPUTS.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("jvm", "output", "gh"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--reuse", type=Path)
    parser.add_argument("--project", action="append", choices=PROJECTS)
    parser.add_argument("--resume", action="store_true",
                        help="Resume an incomplete collection, re-resolving tags and source matches")
    args = parser.parse_args()
    collect(args.jvm, args.output, args.gh, args.reuse, args.project, args.resume)
