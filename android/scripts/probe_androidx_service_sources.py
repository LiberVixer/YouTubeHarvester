"""Check AndroidX generated service sources using retained inputs and SDK tools."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import textwrap
import zipfile

from collect_controlled_sources import validate_file_inventory
from package_controlled_payloads import digest, safe_name


PROTOCOL_SHA256 = "c280b6c0bec0c30b1b6127ed7f53488971efadfb249d7776331b9d63bc78f917"
DETECTION_TEMPLATE = "inspection-gradle-plugin/src/main/kotlin/androidx/inspection/gradle/GenerateProguardDetectionFileTask.kt"


def compare_aidl(generated, published):
    def without_command(data):
        lines = data.splitlines(keepends=True)
        commands = [line for line in lines if line.startswith(b" * Using: ")]
        if len(commands) != 1 or not data.startswith(b"/*\n * This file is auto-generated."):
            raise ValueError("Unexpected AIDL generated header")
        if b"/36.0.0/aidl " not in commands[0] or b"--structured --min_sdk_version 23 " not in commands[0]:
            raise ValueError("Unreviewed AIDL compiler or flags")
        return b"".join(line for line in lines if not line.startswith(b" * Using: "))
    if without_command(generated) != without_command(published):
        raise ValueError("AIDL source differs beyond the compiler command receipt")
    return "exact-except-build-command-receipt"


def render_detection(template, group, artifact):
    helper = '''val strippedArtifact =
        mavenArtifact.removePrefix(mavenGroup.split('.').last()).removePrefix("-").replace('-', '.')
    val group = mavenGroup.removePrefix("androidx.")
    // It's possible for strippedArtifact to be empty, e.g. "compose.ui/ui" has no hyphen
    return "androidx.inspection.$group" +
        if (strippedArtifact.isNotEmpty()) ".$strippedArtifact" else ""
}'''
    if helper not in template:
        raise ValueError("Inspection package generator changed")
    matches = re.findall(r'val text =\s*"""(.*?)"""\s*\.trimIndent\(\)', template, re.DOTALL)
    if len(matches) != 1 or matches[0].count("$packageName") != 1:
        raise ValueError("Unknown inspection source template")
    suffix = artifact.removeprefix(group.split(".")[-1]).removeprefix("-").replace("-", ".")
    package = "androidx.inspection." + group.removeprefix("androidx.") + ("." + suffix if suffix else "")
    return textwrap.dedent(matches[0].strip("\n")).rstrip().replace("$packageName", package).encode()


def compare_public_r(generated, published):
    if generated == published:
        return "exact"
    tail = b"  @android.annotation.DocOnly\n  public static final class styleable {\n  }\n}"
    if published.endswith(b"\n"):
        tail += b"\n"
    marker = b"  /**\n   * @doconly\n   */\n  public static final class styleable {\n"
    if not published.endswith(tail) or generated.count(marker) != 1:
        raise ValueError("Unreviewed generated public R source shape")
    # The published documentation stub omits styleable's @doconly members.
    # This verifies the entire public resource prefix, not a full stub regeneration.
    if generated.split(marker)[0] != published[:-len(tail)]:
        raise ValueError("Public R resource source prefix differs")
    return "public-resource-prefix-exact-documentation-stub-tail"


def extract_files(archive_path, target, predicate):
    retained = []
    with tarfile.open(archive_path, "r|gz") as archive:
        for member in archive:
            name = safe_name(member.name)
            if not member.isfile() or not predicate(name):
                continue
            file = target / name
            file.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, file.open("xb") as sink:
                shutil.copyfileobj(source, sink)
            retained.append({"file": name, "sha256": digest(file)})
    if not retained:
        raise ValueError("Required generator inputs missing")
    return retained


def probe(jvm, trees, builds, published_inputs, output, protoc, aidl, aapt2, framework):
    if output.exists():
        raise ValueError("Use a new service source-probe directory")
    release = json.loads((trees / "ANDROIDX-RELEASE-SOURCES.json").read_text())
    build = json.loads((builds / "ANDROIDX-BUILD-INPUTS.json").read_text())
    published = json.loads((published_inputs / "ANDROIDX-PUBLISHED-INPUTS.json").read_text())
    for folder, report in ((trees, release), (builds, build), (published_inputs, published)):
        validate_file_inventory(folder, report)
    if digest(protoc) != PROTOCOL_SHA256:
        raise ValueError("Unexpected isolated protoc probe tool")
    version = subprocess.check_output([str(protoc), "--version"], text=True).strip()
    if version != "libprotoc 28.2":
        raise ValueError("Wrong protoc version")
    graph = json.loads((jvm / "JVM-SOURCE-INVENTORY.json").read_text())
    output.mkdir(parents=True)
    results = []

    def record(module, source_name, generated, comparison, inputs):
        item = next(a for a in graph["artifacts"] if a["binary"].get("module") == module)
        jar = next(d for d in item["downloads"] if d["file"].endswith("-sources.jar"))
        if digest(jvm / jar["file"]) != jar["sha256"]:
            raise ValueError("Published generated source JAR changed")
        with zipfile.ZipFile(jvm / jar["file"]) as archive:
            expected = archive.read(source_name)
        kind = comparison(generated, expected)
        results.append({"module": module, "sourceJarFile": source_name,
                        "sourceJarSha256": jar["sha256"], "sourceSha256": hashlib.sha256(expected).hexdigest(),
                        "comparison": kind, "preferredInputs": inputs})

    names = {"datastore-preferences-proto", "room-runtime-android", "ui-android",
             "work-runtime", "appcompat", "appcompat-resources"}
    for r in [r for r in release["artifacts"] if r["module"]["name"] in names]:
        module, name = r["module"], r["module"]["name"]
        work = output / name
        work.mkdir()
        if name == "datastore-preferences-proto":
            schema_name = "datastore-preferences-proto/src/main/proto/preferences.proto"
            inputs = extract_files(trees / r["file"], work, lambda n: n == schema_name)
            schema = work / schema_name
            subprocess.run([str(protoc), "-I" + str(schema.parent), "--java_out=lite:" + str(work), str(schema)], check=True)
            target = "androidx/datastore/preferences/PreferencesProto.java"
            record(module, target, (work / target).read_bytes(), require_exact, inputs)
        elif name == "room-runtime-android":
            prefix = "room-runtime/src/androidMain/stableAidl/"
            inputs = extract_files(trees / r["file"], work,
                                   lambda n: n.startswith(prefix) and n.endswith(".aidl"))
            base = work / prefix
            for schema in sorted(base.rglob("*.aidl")):
                command = [str(aidl), "-o" + str(work), "-I" + str(base), "--structured",
                           "--min_sdk_version", "23", str(schema)]
                subprocess.run(command, check=True)
                target = "androidx/room/" + schema.stem + ".java"
                record(module, "androidMain/" + target, (work / target).read_bytes(), compare_aidl, inputs)
        else:
            for source in r["sourceMatches"]["unmatched"]:
                if source.endswith("/ProguardDetection.kt"):
                    tree = builds / r["commit"] / "inspection.tar.gz"
                    inputs = extract_files(tree, work, lambda n: n == DETECTION_TEMPLATE)
                    template = (work / DETECTION_TEMPLATE).read_text()
                    artifact = name.removesuffix("-android")
                    record(module, source, render_detection(template, module["group"], artifact), require_exact, inputs)
                elif source.endswith("/R.java"):
                    prefix = name + "/src/main/res/"
                    inputs = extract_files(trees / r["file"], work, lambda n: n.startswith(prefix))
                    folder = published_inputs / (module["group"] + "-" + name + "-" + module["version"])
                    manifest = folder / "AndroidManifest.xml"
                    inputs.append({"publishedInput": str(manifest.relative_to(published_inputs)), "sha256": digest(manifest)})
                    resources = work / prefix
                    compiled, generated = work / "compiled.zip", work / "generated"
                    generated.mkdir()
                    package = source.removesuffix("/R.java").replace("/", ".")
                    subprocess.run([str(aapt2), "compile", "--dir", str(resources), "-o", str(compiled)], check=True)
                    subprocess.run([str(aapt2), "link", "--static-lib", "--merge-only", "--private-symbols",
                                    package + ".internal", "--java", str(generated), "--manifest", str(manifest),
                                    "-I", str(framework), "-o", str(work / "library.ap_"), str(compiled)], check=True)
                    record(module, source, (generated / source).read_bytes(), compare_public_r, inputs)
                else:
                    raise ValueError("Unknown generated service source")
        print(name + ": retained generator inputs checked", flush=True)
    if len(results) != 8:
        raise ValueError("Expected eight generated AndroidX service sources")
    result = {"schemaVersion": 1, "sourceComparisons": results,
              "toolInputs": [{"file": str(p), "sha256": digest(p)} for p in (protoc, aidl, aapt2, framework)],
              "protocVersion": version, "completeCorrespondingSourcesVerified": False,
              "scope": "Generated service sources; R documentation stubs are not fully regenerated",
              "remaining": ["Review full build/notices coverage; do not infer byte-identical APK rebuildability"]}
    (output / "ANDROIDX-SERVICE-SOURCE-PROBE.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def require_exact(generated, published):
    if generated != published:
        raise ValueError("Generated service source differs")
    return "exact"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("jvm", "trees", "builds", "published-inputs", "output", "protoc", "aidl", "aapt2", "framework"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    probe(args.jvm, args.trees, args.builds, args.published_inputs, args.output,
          args.protoc, args.aidl, args.aapt2, args.framework)
