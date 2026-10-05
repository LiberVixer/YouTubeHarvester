"""Run the retained upstream icon generator and compare published Kotlin sources."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import zipfile

from collect_controlled_sources import validate_file_inventory
from package_controlled_payloads import digest, safe_name


def compare_icon_source(generated, published):
    pattern = rb"\A(/\*\n \* Copyright )\d{4}( The Android Open Source Project\n)"
    current, historical = re.match(pattern, generated), re.match(pattern, published)
    if not current or not historical:
        raise ValueError("Unexpected icon copyright generator output")
    if generated == published:
        return "exact"
    # KotlinPoetUtils.kt emits the current build year; all other bytes must match.
    normalized = re.sub(pattern, lambda m: historical.group(0), generated, count=1)
    if normalized != published:
        raise ValueError("Generated icon differs beyond the build-year stamp")
    return "copyright-build-year-only"


def probe(jvm, trees, output, java, compiler_classpath, generator_classpath):
    if output.exists():
        raise ValueError("Use a new icon source-probe directory")
    report = json.loads((trees / "ANDROIDX-RELEASE-SOURCES.json").read_text())
    validate_file_inventory(trees, report)
    records = [r for r in report["artifacts"] if r["module"]["name"] in {
        "material-icons-core-android", "material-icons-extended-android"}]
    if len(records) != 2 or len({r["file"] for r in records}) != 1:
        raise ValueError("Both icon artifacts must share one retained generator tree")
    output.mkdir(parents=True)
    prefix = "material/icons/generator/"
    with tarfile.open(trees / records[0]["file"], "r|gz") as archive:
        for member in archive:
            name = safe_name(member.name)
            if not name.startswith(prefix) or not member.isfile():
                continue
            target = output / "generator" / name.removeprefix(prefix)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("xb") as sink:
                shutil.copyfileobj(source, sink)
    utils = output / "generator/src/main/kotlin/androidx/compose/material/icons/generator/KotlinPoetUtils.kt"
    if 'SimpleDateFormat("yyyy").format(Date())' not in utils.read_text():
        raise ValueError("Reviewed upstream build-year generator is missing")
    runner = Path(__file__).parent / "probes/MaterialIconsProbe.kt"
    sources = [p for p in sorted((output / "generator/src/main").rglob("*.kt"))
               if "tasks" not in p.parts and p.name != "IconTestingManifestGenerator.kt"]
    tool_inputs = [{"file": str(p), "sha256": digest(p)} for p in [
        *map(Path, compiler_classpath.split(":")), *map(Path, generator_classpath.split(":")), runner]]
    with (output / "compile.log").open("w") as log:
        subprocess.run([str(java), "-cp", compiler_classpath, "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
                        "-no-stdlib", "-no-reflect", "-classpath", generator_classpath, "-d",
                        str(output / "generator.jar"), *map(str, sources), str(runner)],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    with (output / "generate.log").open("w") as log:
        subprocess.run([str(java), "-Xmx2g", "-cp", str(output / "generator.jar") + ":" + generator_classpath,
                        "MaterialIconsProbeKt", str(output / "generator"), str(output / "generated")],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    graph = json.loads((jvm / "JVM-SOURCE-INVENTORY.json").read_text())
    comparisons = []
    for record in records:
        item = next(a for a in graph["artifacts"] if a["binary"].get("module") == record["module"])
        source = next(d for d in item["downloads"] if d["file"].endswith("-sources.jar"))
        if digest(jvm / source["file"]) != source["sha256"]:
            raise ValueError("Published icon sources changed")
        component = "core" if "icons-core" in record["module"]["name"] else "extended"
        with zipfile.ZipFile(jvm / source["file"]) as jar:
            for name in record["sourceMatches"]["unmatched"]:
                relative = safe_name(name.removeprefix("commonMain/"))
                generated = (output / "generated" / component / relative).read_bytes()
                published = jar.read(name)
                kind = compare_icon_source(generated, published)
                comparisons.append({"module": record["module"], "sourceJarFile": name,
                                    "comparison": kind, "sha256": hashlib.sha256(published).hexdigest()})
    result = {"schemaVersion": 1, "upstreamCommit": records[0]["commit"],
              "generatorArchiveSha256": digest(trees / records[0]["file"]),
              "generatorInputs": len(list((output / "generator/raw-icons").rglob("*.xml"))),
              "toolInputs": tool_inputs, "sourceComparisons": comparisons,
              "verifiedGeneratedSources": len(comparisons), "completeCorrespondingSourcesVerified": False,
              "scope": "Unmodified upstream icon generator; published copyright build year checked separately"}
    (output / "MATERIAL-ICON-SOURCE-PROBE.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"generatedSourcesVerified": len(comparisons), "generatorInputs": result["generatorInputs"]}), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("jvm", "trees", "output", "java"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("compiler-classpath", "generator-classpath"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    probe(args.jvm, args.trees, args.output, args.java, args.compiler_classpath, args.generator_classpath)
