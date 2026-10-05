"""Preserve rav1e's actual Cargo locks, registry sources and Rust standard library."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile
import time
import tomllib
import urllib.request

from package_controlled_payloads import digest


RUST_SOURCE_URL = "https://static.rust-lang.org/dist/rustc-1.89.0-src.tar.xz"
RUST_SOURCE_SHA256 = "0b9d55610d8270e06c44f459d1e2b7918a5e673809c592abed9b9c600e33d95a"


def registry_packages(lock):
    packages = []
    for package in tomllib.loads(lock.decode())["package"]:
        source = package.get("source")
        if source is None:
            continue
        if source != "registry+https://github.com/rust-lang/crates.io-index":
            raise ValueError("Unreviewed Cargo source: " + source)
        if not re.fullmatch(r"[A-Za-z0-9_.+-]+", package["name"]) or not re.fullmatch(
                r"[A-Za-z0-9_.+-]+", package["version"]):
            raise ValueError("Invalid crate coordinate")
        if not re.fullmatch(r"[0-9a-f]{64}", package.get("checksum", "")):
            raise ValueError("Cargo crate lacks locked checksum")
        packages.append(package)
    return packages


def download(url, path, expected):
    if not path.exists():
        temporary = path.with_suffix(path.suffix + ".part")
        try:
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(url, timeout=60) as response, temporary.open("xb") as stream:
                        if not response.url.startswith(("https://static.crates.io/", "https://static.rust-lang.org/")):
                            raise ValueError("Unexpected source redirect")
                        while data := response.read(1024 * 1024):
                            stream.write(data)
                    break
                except OSError:
                    temporary.unlink(missing_ok=True)
                    if attempt == 2:
                        raise
                    time.sleep(attempt + 1)
            if digest(temporary) != expected:
                raise ValueError("Locked source checksum mismatch: " + url)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    if digest(path) != expected:
        raise ValueError("Preserved source checksum mismatch: " + str(path))


def collect(android, output, resume=False):
    if output.exists() and not resume:
        raise ValueError("Cargo source output already exists; use --resume for verified partial downloads")
    if (output / "RUST-SOURCE-INVENTORY.json").exists():
        raise ValueError("Completed Cargo source audit already exists")
    output.mkdir(parents=True, exist_ok=resume)
    pins = json.loads((android / "native/controlled-artifacts.json").read_text())
    locks, common = {}, None
    for arch, pin in pins["architectures"].items():
        core = android / pin["core"]
        info = json.loads((core / "BUILD-INFO-runtime.json").read_text())
        if digest(core / "BUILD-INFO-runtime.json") != pin["coreInfoSha256"]:
            raise ValueError("Core build inventory changed")
        source_path = core / "runtime-source-worktrees.tar.gz"
        expected = next(x["sha256"] for x in info["files"] if x["file"] == source_path.name)
        if digest(source_path) != expected:
            raise ValueError("Producing worktree checksum mismatch")
        lock = None
        with tarfile.open(source_path, "r|gz") as archive:
            for member in archive:
                if member.name == "./librav1e/src/Cargo.lock":
                    lock = archive.extractfile(member).read()
                    break
        if lock is None:
            raise ValueError("Producing Cargo lock missing: " + arch)
        if common is not None and lock != common:
            raise ValueError("Cargo locks differ across ABIs")
        common = lock
        path = output / (arch + "-Cargo.lock")
        path.write_bytes(lock)
        locks[arch] = {"file": path.name, "sha256": digest(path)}
        print(arch + ": producing Cargo.lock verified", flush=True)
    packages = registry_packages(common)
    records = []
    for index, package in enumerate(packages, 1):
        name = f"{package['name']}-{package['version']}.crate"
        url = f"https://static.crates.io/crates/{package['name']}/{name}"
        path = output / name
        download(url, path, package["checksum"])
        with tarfile.open(path) as archive:
            notices = [x.name for x in archive if x.isfile() and re.search(
                r"(^|/)(LICENSE|NOTICE|COPYING|COPYRIGHT)([./_-]|$)", x.name, re.I)]
        records.append({"name": package["name"], "version": package["version"], "file": name,
                        "url": url, "sha256": digest(path), "noticeFiles": notices})
        print(f"{index}/{len(packages)} {name}: locked SHA256 verified", flush=True)
    rust = output / "rustc-1.89.0-src.tar.xz"
    download(RUST_SOURCE_URL, rust, RUST_SOURCE_SHA256)
    files = [{"file": p.name, "sha256": digest(p), "bytes": p.stat().st_size}
             for p in sorted(output.iterdir()) if p.is_file()]
    report = {"component": "rav1e Cargo dependencies and Rust 1.89.0 runtime sources",
              "producingCargoLocks": locks, "registryPackages": records, "files": files,
              "rust": {"version": "1.89.0", "url": RUST_SOURCE_URL, "sha256": RUST_SOURCE_SHA256},
              "completeCorrespondingSourcesVerified": False}
    (output / "RUST-SOURCE-INVENTORY.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"matchingAbiLocks": len(locks), "crates": len(records), "output": str(output)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    collect(args.android, args.output, args.resume)
