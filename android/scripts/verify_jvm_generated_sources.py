"""Verify the three release-generated source files in the retained JVM build trees."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import zipfile

from collect_controlled_sources import validate_file_inventory
from collect_jvm_build_inputs import match_source_files
from package_controlled_payloads import digest


def render_template(name, module, template):
    if module["name"] in {"jackson-core", "jackson-databind"} and name.endswith("/PackageVersion.java"):
        substitutions = {"@package@": name.rsplit("/", 1)[0].replace("/", "."),
                         "@projectversion@": module["version"], "@projectgroupid@": module["group"],
                         "@projectartifactid@": module["name"]}
    elif module["name"] == "okhttp" and name == "okhttp3/OkHttp.kt":
        substitutions = {"$projectVersion": module["version"]}
    else:
        raise ValueError("Unknown generated source; do not assume it is a version template")
    text = template.decode()
    for token, value in substitutions.items():
        if text.count(token) != 1:
            raise ValueError("Unexpected generating template token")
        text = text.replace(token, value)
    return text.encode(), substitutions


def verify(jvm, build_inputs, output):
    if output.exists():
        raise ValueError("Preserve previous review results")
    report = json.loads((build_inputs / "JVM-BUILD-INPUTS.json").read_text())
    validate_file_inventory(build_inputs, report)
    graph = json.loads((jvm / "JVM-SOURCE-INVENTORY.json").read_text())
    records = []
    for project in report["projects"]:
        item = next(x for x in graph["artifacts"] if x["binary"].get("module") == project["module"])
        source = next(x for x in item["downloads"] if x["file"].endswith("-sources.jar"))
        if digest(jvm / source["file"]) != source["sha256"]:
            raise ValueError("Preserved Maven source JAR changed")
        matching = match_source_files(jvm / source["file"], build_inputs / project["file"])
        if matching != project["sourceMatches"]:
            raise ValueError("Previously recorded upstream source matches changed")
        with zipfile.ZipFile(jvm / source["file"]) as jar, tarfile.open(
                build_inputs / project["file"]) as tree:
            for name in project["sourceMatches"]["unmatched"]:
                suffix = name + ".in" if name.endswith("/PackageVersion.java") else "java-templates/" + name
                templates = [entry for entry in tree if entry.isfile() and entry.name.endswith("/" + suffix)]
                if len(templates) != 1:
                    raise ValueError("Generating source template missing or ambiguous")
                template = templates[0]
                rendered, substitutions = render_template(name, project["module"], tree.extractfile(template).read())
                if rendered != jar.read(name):
                    raise ValueError("Generated Maven source differs from producing template: " + name)
                records.append({"module": project["module"], "sourceJarFile": name,
                                "templateFile": template.name, "substitutions": substitutions,
                                "sha256": hashlib.sha256(rendered).hexdigest()})
    result = {"projects": len(report["projects"]), "generatedSourceMatches": records,
              "exactSourceFiles": sum(x["sourceMatches"]["exactSourceMatches"] for x in report["projects"]),
              "completeCorrespondingSourcesVerified": False,
              "scope": "Five preserved producer trees; not the entire JVM producer graph"}
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"projects": result["projects"], "exactSourceFiles": result["exactSourceFiles"],
                      "generatedSourceFiles": len(records)}))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("jvm", "build-inputs", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    verify(args.jvm, args.build_inputs, args.output)
