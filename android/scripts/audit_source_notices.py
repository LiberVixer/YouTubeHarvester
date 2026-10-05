"""Inventory original component notices inside a verified source preparation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile
import tempfile
import zipfile

from package_controlled_payloads import digest, safe_name
from verify_source_preparation import verify
from collect_jvm_build_inputs import match_source_files
from collect_controlled_sources import validate_file_inventory


NOTICE = re.compile(r"^(copying|copyright|licen[cs]e|notice|unlicense|authors|patents?)([._-].*)?$", re.I)
LATER = re.compile(r"either\s+version\s+2\b.{0,200}?any\s+later\s+version", re.I | re.S)
ENTRY_LIMIT = 16 * 1024**2


def notice_name(name):
    return bool(NOTICE.fullmatch(Path(name).name))


def preserve_notice(output, relative, data):
    target = output / safe_name(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError("Conflicting notice: " + relative)
    else:
        target.write_bytes(data)
    return {"file": str(target.relative_to(output)),
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def archive_entries(path):
    seen = set()
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                name = safe_name(entry.filename)
                if not entry.is_dir():
                    if name in seen:
                        raise ValueError("Duplicate source entry: " + name)
                    seen.add(name)
                    if entry.file_size > ENTRY_LIMIT:
                        if notice_name(name):
                            raise ValueError("Notice exceeds size limit: " + name)
                        continue
                    yield name, archive.read(entry)
    else:
        with tarfile.open(path, "r|*") as archive:
            for entry in archive:
                name = safe_name(entry.name)
                if entry.isfile():
                    if name in seen:
                        raise ValueError("Duplicate source entry: " + name)
                    seen.add(name)
                    if entry.size > ENTRY_LIMIT:
                        if notice_name(name):
                            raise ValueError("Notice exceeds size limit: " + name)
                        continue
                    yield name, archive.extractfile(entry).read()


def inspect_archive(path, component, output):
    records, later = [], []
    for name, data in archive_entries(path):
        if notice_name(name):
            records.append({"upstreamFile": name, **preserve_notice(
                output, "notices/" + component + "/" + path.name + "/" + name, data)})
        if len(later) < 5 and name.endswith((".c", ".h", ".cpp", ".cc", ".txt", ".md", ".rst")):
            text = data[:32768].decode("utf-8", "replace")
            text = re.sub(r"(?m)^\s*(?:\*|//|#)\s?", "", text)
            match = LATER.search(text)
            if match:
                later.append({"file": name, "sha256": hashlib.sha256(data).hexdigest(),
                              "declaration": match.group(0)})
    return {"archiveSha256": digest(path), "notices": records, "gpl2OrLaterHeaderExamples": later}


def audit(source, output, rust_supplement=None):
    if output.exists():
        raise ValueError("Use a new notice-audit directory")
    integrity = verify(source)
    output.mkdir(parents=True)
    findings = []
    with tempfile.TemporaryDirectory(prefix="source-notice-inputs-", dir=output.parent) as temporary:
        stage = Path(temporary)
        with tarfile.open(source) as archive:
            archive.extractall(stage, filter="data")
        coverage = json.loads((stage / "RUNTIME-PACKAGE-SOURCE-COVERAGE.json").read_text())
        packages = next(b["packages"] for b in json.loads((stage / "controlled-source-audit.json").read_text())["builds"]
                        if b["architecture"] == "x86_64")
        native = []
        wanted = sorted({entry["recipe"].split("/")[1] for entry in coverage.values() if "recipe" in entry})
        with tarfile.open(stage / "termux-recipes.tar.gz") as recipes:
            recipe_notices = {m.name: recipes.extractfile(m).read() for m in recipes
                              if m.isfile() and m.size <= ENTRY_LIMIT and
                              (notice_name(m.name) or m.name.startswith("packages/termux-licenses/LICENSES/")
                               or m.name == "packages/libcrypt/crypt3.c")}
        for component in wanted:
            metadata = packages[component]
            records = []
            for original in metadata["originalArchives"]:
                relative = "original-sources/" + safe_name(original["path"])
                path = stage / relative
                if digest(path) != original["sha256"]:
                    raise ValueError("Original native source changed")
                records.append({"sourceFile": relative, **inspect_archive(path, component, output)})
            local = []
            for name, data in recipe_notices.items():
                if name.startswith("packages/" + component + "/"):
                    local.append({"upstreamFile": name, **preserve_notice(
                        output, "notices/" + component + "/" + name, data)})
            if component == "ca-certificates":
                local += preserve_generic_notice(recipe_notices, "MPL-2.0", component, output)
            if component == "libc++":
                records.append({"sourceFile": "ndk/ndk-build-metadata.tar.gz",
                                **inspect_archive(stage / "ndk/ndk-build-metadata.tar.gz", component, output)})
                records.append({"sourceFile": "ndk/llvm-project-97a699bf.tar.gz",
                                **inspect_archive(stage / "ndk/llvm-project-97a699bf.tar.gz", component, output)})
            if not local and not any(r["notices"] for r in records):
                findings.append({"component": component, "issue": "No original notice identified"})
            native.append({"component": component, "version": metadata["version"],
                           "recipeLicenseDeclaration": metadata["licenseDeclared"],
                           "sourceArchives": records, "recipeNotices": local})
            print(component + ": original notice evidence inventoried", flush=True)
        for component, file in (("pycryptodomex", "original-sources/python-pycryptodomex/cache/v3.23.0x.tar.gz"),
                                ("mutagen", "mutagen-1.47.0.tar.gz"), ("quickjs", "quickjs-2026-06-04.tar.xz"),
                                ("wrapper", "youtubedl-android-wrapper-0.18.1.tar.gz")):
            native.append({"component": component, "sourceArchives": [
                {"sourceFile": file, **inspect_archive(stage / file, component, output)}]})
        supplemental = []
        for name in ("yt-dlp.tar.gz", "yt_dlp_ejs-0.8.0.tar.gz", "ejs-4fb477f.tar.gz",
                     "astring-1.9.0.tgz", "astring-96dfb2b.tar.gz", "meriyah-6.1.4.tgz",
                     "meriyah-abbbfe0.tar.gz", "protobuf-28.2.tar.gz"):
            supplemental.append({"sourceFile": "supplemental-sources/" + name,
                                 **inspect_archive(stage / "supplemental-sources" / name,
                                                   "supplemental", output)})
        application_notice = preserve_notice(output, "notices/application/LICENSE", (stage / "LICENSE").read_bytes())
        jvm = json.loads((stage / "jvm-sources/JVM-SOURCE-INVENTORY.json").read_text())
        producers = json.loads((stage / "jvm-build-inputs/JVM-BUILD-INPUTS.json").read_text())
        java_notices = []
        for producer in producers["projects"]:
            component = "jvm-" + producer["module"]["name"] + "-" + producer["commit"][:12]
            java_notices.append({"modules": [p["module"] for p in [producer, *producer.get("relatedArtifacts", [])]],
                                 "sourceFile": "jvm-build-inputs/" + producer["file"],
                                 **inspect_archive(stage / "jvm-build-inputs" / producer["file"], component, output)})
        published = json.loads((stage / "androidx-published-inputs/ANDROIDX-PUBLISHED-INPUTS.json").read_text())
        androidx = json.loads((stage / "androidx-release-sources/ANDROIDX-RELEASE-SOURCES.json").read_text())
        for item in published["records"]:
            module = item["module"]
            component = module["group"] + "-" + module["name"] + "-" + module["version"]
            root = stage / "androidx-published-inputs" / component
            notice_files = []
            for entry in item["retained"]:
                if notice_name(entry["file"]):
                    original = root / entry["file"]
                    notice_files.append(preserve_notice(output, "notices/" + component + "/" + entry["file"],
                                                        original.read_bytes()))
            r = next(r for r in androidx["artifacts"] if r["module"] == module)
            license_file = stage / "androidx-build-inputs" / r["commit"] / "LICENSE.txt"
            if not license_file.is_file():
                findings.append({"component": component, "issue": "Root license missing"})
            else:
                notice_files.append(preserve_notice(output, "notices/" + component + "/ROOT-LICENSE.txt",
                                                    license_file.read_bytes()))
            java_notices.append({"modules": [module], "notices": notice_files})
        source_jars = [{"module": item["binary"].get("module"),
                        "binaryNotices": item["binaryNotices"],
                        "sourceNoticeFiles": item.get("sources", {}).get("noticeFiles", []),
                        "pomLicenses": item.get("declaredLicenses", [])} for item in jvm["artifacts"]]
        rust = json.loads((stage / "rust-sources/RUST-SOURCE-INVENTORY.json").read_text())
        rust_notices = [{"name": r["name"], "version": r["version"], "sourceFile": "rust-sources/" + r["file"],
                         **inspect_archive(stage / "rust-sources" / r["file"], "rust", output)}
                        for r in rust["registryPackages"]]
        supplemental_rust = None
        if rust_supplement is not None:
            supplemental_rust = json.loads((rust_supplement / "RUST-NOTICE-SOURCES.json").read_text())
            validate_file_inventory(rust_supplement, supplemental_rust)
            findings.extend(supplemental_rust["findings"])
        for item in rust_notices:
            if not item["notices"]:
                extra = next((e for e in (supplemental_rust or {}).get("crates", [])
                              if e["name"] == item["name"] and e["version"] == item["version"]
                              and e["crateSha256"] == item["archiveSha256"]), None)
                if extra is None or extra["sourceMatches"]["unmatched"] or not extra["notices"]:
                    findings.append({"component": item["name"], "issue": "Rust crate needs matching original notices"})
                else:
                    item["supplementalNoticeEvidence"] = {
                        "inventory": "rust-notice-sources/RUST-NOTICE-SOURCES.json", "commit": extra["commit"],
                        "sourceMatches": extra["sourceMatches"], "notices": extra["notices"]}
        common = next(a for a in jvm["artifacts"] if a["binary"].get("module", {}).get("name") == "common")
        common_source = next(d for d in common["downloads"] if d["file"].endswith("-sources.jar"))
        common_matches = match_source_files(stage / "jvm-sources" / common_source["file"],
                                            stage / "youtubedl-android-wrapper-0.18.1.tar.gz")
        if common_matches["unmatched"]:
            findings.append({"component": "common:0.18.1", "issue": "Wrapper sources differ"})
        java_notices.append({"modules": [common["binary"]["module"]],
                             "sourceFile": "youtubedl-android-wrapper-0.18.1.tar.gz", "sourceMatches": common_matches})
        covered = {json.dumps(m, sort_keys=True) for entry in java_notices for m in entry["modules"]}
        for artifact in jvm["artifacts"]:
            module = artifact["binary"].get("module")
            if module is not None and json.dumps(module, sort_keys=True) not in covered:
                findings.append({"component": module, "issue": "No JVM producer notice mapping"})
        overrides = [{"module": r["module"], "commit": r["commit"], "versionKey": r["versionKey"],
                      "snapshotVersion": r["treeVersion"], "rebuildVersion": r["module"]["version"]}
                     for r in androidx["artifacts"] if r["treeVersion"] not in (None, r["module"]["version"])]
        result = {"schemaVersion": 1, "sourcePreparation": integrity,
                  "auditScriptSha256": digest(Path(__file__)),
                  "runtimeProducerPackages": len(coverage), "nativeComponents": native,
                  "jvmProducerNotices": java_notices, "mavenArtifacts": source_jars,
                  "rustNotices": rust_notices, "androidxVersionOverrides": overrides,
                  "supplementalNotices": supplemental, "applicationLicense": application_notice,
                  "findings": findings, "completeCorrespondingSourcesVerified": False,
                  "scope": "Original notice locations and rebuild-version inputs; not an automatic legal/source approval"}
    result["files"] = [{"file": str(p.relative_to(output)), "sha256": digest(p), "bytes": p.stat().st_size}
                       for p in sorted(output.rglob("*")) if p.is_file()]
    (output / "SOURCE-NOTICE-AUDIT.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def preserve_generic_notice(notices, name, component, output):
    path = "packages/termux-licenses/LICENSES/" + name + ".txt"
    data = notices[path]
    return [{"upstreamFile": path, **preserve_notice(output, "notices/" + component + "/" + Path(path).name, data),
             "scope": "Declared data-file license text"}]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rust-supplement", type=Path)
    args = parser.parse_args()
    result = audit(args.archive, args.output, args.rust_supplement)
    print(json.dumps({"nativeComponents": len(result["nativeComponents"]), "findings": result["findings"],
                      "noticeFiles": len(result["files"])}), flush=True)
