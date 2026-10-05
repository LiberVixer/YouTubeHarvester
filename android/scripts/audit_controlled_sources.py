"""Audit source evidence in controlled artifacts without approving publication."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile


DONE = re.compile(r"termux - build of '([^']+)' done")
LICENSE = re.compile(r"^(copying|copyright|licen[cs]e|notice|unlicense)([._-].*)?$", re.I)
RECIPE_QUERY = r'''
set -e
source "$1"
printf '%s\0' "${TERMUX_PKG_VERSION-}" "${TERMUX_PKG_LICENSE-}" "${TERMUX_PKG_LICENSE_FILE-}"
printf '%s\0' "${#TERMUX_PKG_SRCURL[@]}" "${TERMUX_PKG_SRCURL[@]}"
printf '%s\0' "${#TERMUX_PKG_SHA256[@]}" "${TERMUX_PKG_SHA256[@]}"
'''


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_parts(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Unsafe source archive path: " + name)
    return path.parts


def read_metadata(repo, package, arch, lock):
    recipe = repo / "packages" / package / "build.sh"
    if not recipe.is_file():
        raise ValueError("Missing producing recipe: " + package)
    env = {**os.environ, "TERMUX_ARCH": arch, "TERMUX_PREFIX": lock["prefix"],
           "TERMUX_PKG_API_LEVEL": str(lock["apiLevel"]), "TERMUX_ON_DEVICE_BUILD": "false",
           "TERMUX_SCRIPTDIR": str(repo), "TERMUX_PKG_BUILDER_DIR": str(recipe.parent),
           "TERMUX_PKG_NAME": package, "TERMUX_PKG_SRCURL": "", "TERMUX_PKG_SHA256": ""}
    fields = subprocess.check_output(["bash", "-c", RECIPE_QUERY, "audit", str(recipe)],
                                     env=env, timeout=30).decode().split("\0")[:-1]
    count = int(fields[3])
    urls = fields[4:4 + count]
    hash_count = int(fields[4 + count])
    hashes = fields[5 + count:5 + count + hash_count]
    return {"version": fields[0], "licenseDeclared": fields[1],
            "licenseFilesDeclared": fields[2], "urls": urls, "hashes": hashes}


def inspect_worktrees(path, metadata):
    result = {name: {"sourceFiles": 0, "licenseEvidence": [], "originalArchives": []}
              for name in metadata}
    expected = {}
    for name, recipe in metadata.items():
        for url, digest in zip(recipe["urls"], recipe["hashes"]):
            if url and re.fullmatch(r"[a-f0-9]{64}", digest):
                expected[(name, url.rsplit("/", 1)[-1])] = digest
    with tarfile.open(path, "r|gz") as archive:
        for member in archive:
            parts = safe_parts(member.name)
            if len(parts) < 3 or parts[0] not in result or not member.isfile():
                continue
            name, kind = parts[:2]
            record = result[name]
            if kind == "src":
                record["sourceFiles"] += 1
                declared = metadata[name]["licenseFilesDeclared"].split()
                relative = "/".join(parts[2:])
                if (LICENSE.fullmatch(parts[-1]) or relative in declared) and member.size <= 8 * 1024**2:
                    stream = archive.extractfile(member)
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    record["licenseEvidence"].append({"path": member.name, "bytes": member.size, "sha256": digest})
            elif kind == "cache" and (name, parts[-1]) in expected:
                stream = archive.extractfile(member)
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
                record["originalArchives"].append({"path": member.name, "sha256": digest,
                                                    "recipeHashMatches": digest == expected[(name, parts[-1])]})
    return result


def audit(folder, recipe_root, lock, evidence_hashes):
    build = json.loads((folder / "BUILD-INFO-runtime.json").read_text())
    arch = build["architecture"]
    if build["buildExitCode"] != 0 or build["lock"] != lock:
        raise ValueError("Build failed or runtime lock differs: " + str(folder))
    # Check the archived evidence before parsing or using the producing recipes.
    files = {entry["file"]: entry["sha256"] for entry in build["files"]}
    for name in ("build.log", "termux-recipes.tar.gz", "termux-runtime.patch", "runtime-source-worktrees.tar.gz"):
        if sha256(folder / name) != files.get(name):
            raise ValueError("Evidence checksum mismatch: " + name)
    for name in ("termux-recipes.tar.gz", "termux-runtime.patch"):
        if files[name] != evidence_hashes[name]:
            raise ValueError("Producing recipes differ between architectures: " + name)
    packages = sorted(set(DONE.findall((folder / "build.log").read_text())))
    metadata = {name: read_metadata(recipe_root, name, arch, lock) for name in packages}
    evidence = inspect_worktrees(folder / "runtime-source-worktrees.tar.gz", metadata)
    missing_sources, missing_licenses, mismatches = [], [], []
    for name, record in evidence.items():
        record.update(metadata[name])
        record["genericLicenseEvidence"] = []
        for license_name in metadata[name]["licenseDeclared"].split(","):
            generic = recipe_root / "packages/termux-licenses/LICENSES" / (license_name.strip() + ".txt")
            if generic.is_file():
                record["genericLicenseEvidence"].append({"path": generic.relative_to(recipe_root).as_posix(),
                                                         "sha256": sha256(generic)})
        record["recipeOnly"] = not any(metadata[name]["urls"])
        if not record["sourceFiles"] and not record["recipeOnly"]:
            missing_sources.append(name)
        if not record["licenseEvidence"] and not record["genericLicenseEvidence"]:
            missing_licenses.append(name)
        if any(not source["recipeHashMatches"] for source in record["originalArchives"]):
            mismatches.append(name)
    return {"architecture": arch, "applicationCommit": build["applicationCommit"],
            "completedPackages": len(packages), "packages": evidence,
            "missingSourceWorktrees": missing_sources, "withoutLicenseFileEvidence": missing_licenses,
            "sourceArchiveHashMismatches": mismatches,
            "prebuiltNdkComponentsRequiringSourceReview": ["libc++"],
            "completeCorrespondingSourcesVerified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = []
    with tempfile.TemporaryDirectory(prefix="yth-source-recipes-") as directory:
        repo = Path(directory)
        first = args.folders[0]
        info = json.loads((first / "BUILD-INFO-runtime.json").read_text())
        expected = next(e["sha256"] for e in info["files"] if e["file"] == "termux-recipes.tar.gz")
        if sha256(first / "termux-recipes.tar.gz") != expected:
            raise ValueError("Recipe archive checksum mismatch")
        patch_hash = next(e["sha256"] for e in info["files"] if e["file"] == "termux-runtime.patch")
        if sha256(first / "termux-runtime.patch") != patch_hash:
            raise ValueError("Recipe patch checksum mismatch")
        with tarfile.open(first / "termux-recipes.tar.gz", "r:gz") as archive:
            archive.extractall(repo, filter="data")
        subprocess.run(["git", "-C", str(repo), "apply", "--recount", "--unidiff-zero",
                        str((first / "termux-runtime.patch").resolve())], check=True)
        evidence_hashes = {"termux-recipes.tar.gz": expected, "termux-runtime.patch": patch_hash}
        for folder in args.folders:
            report = audit(folder, repo, info["lock"], evidence_hashes)
            reports.append(report)
            print(json.dumps({key: value for key, value in report.items() if key != "packages"}), flush=True)
    document = {"scope": "Controlled Python/FFmpeg build source evidence, not an APK publication attestation",
                "builds": reports, "publicReleaseReady": False,
                "remaining": ["Review license evidence and recipe-only/NDK components",
                              "Build and source Python site-packages (Cryptodome and mutagen)",
                              "Replace all native launchers and payloads with controlled builds",
                              "Verify final APK native dependency closure and source manifest",
                              "Accept exact replacement APK on device"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2) + "\n")


if __name__ == "__main__":
    main()
