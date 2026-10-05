"""Collect pinned native source evidence without approving the public release."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import tarfile
import tempfile

from package_controlled_payloads import digest, read_package, safe_name


NDK_ARCHIVES = {
    "llvm-project-97a699bf.tar.gz": "4a1754e2205ba9a18c8ab62a6352280df872dfcf44a4c51d6ef0e0b848c6a998",
    "llvm_android-e727bfb.tar.gz": "4247557fe143da44ab6562bf9299a419822444fdfb38dd8315c055f6db51dc61",
    "ndk-build-metadata.tar.gz": "40435d84c53d40979e31b956a7c2784318cc80d0dca92c316a5b9b232cae9f3a",
}
WRAPPER_SHA256 = "0c2430b6e0568f619fe744eb37230c86182b00660ecac907328325bbbdced70a"


def collect_worktrees(archive_path, metadata, destination, extra_trees):
    wanted = {item["path"]: item["sha256"] for package in metadata.values()
              for item in package["originalArchives"]}
    found = set()
    with tarfile.open(archive_path, "r|gz") as archive:
        for member in archive:
            name = safe_name(member.name)
            parts = PurePosixPath(name).parts
            extra = len(parts) > 2 and parts[0] in extra_trees and parts[1] == "src"
            if member.name not in wanted and not extra:
                continue
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if extra and member.issym():
                linked = posixpath.normpath(posixpath.join(posixpath.dirname(name), member.linkname))
                if member.linkname.startswith("/") or not linked.startswith("/".join(parts[:2]) + "/"):
                    raise ValueError("Source symlink escapes tree: " + member.name)
                target.symlink_to(member.linkname)
                continue
            if not member.isfile():
                if not member.isdir():
                    raise ValueError("Unsupported source worktree entry: " + member.name)
                continue
            with archive.extractfile(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            if member.name in wanted:
                if digest(target) != wanted[member.name]:
                    raise ValueError("Original source checksum mismatch: " + member.name)
                found.add(member.name)
    if found != set(wanted):
        raise ValueError("Missing original sources: " + str(set(wanted) - found))
    return len(found)


def collect(android, audit_path, ndk, wrapper, payload, output):
    if output.exists():
        raise ValueError("Source output already exists")
    audit = json.loads(audit_path.read_text())
    core_evidence = next(build for build in audit["builds"] if build["architecture"] == "x86_64")
    pins = json.loads((android / "native/controlled-artifacts.json").read_text())
    core = android / pins["architectures"]["x86_64"]["core"]
    extension = android / pins["architectures"]["x86_64"]["extensions"]
    if digest(core / "BUILD-INFO-runtime.json") != pins["architectures"]["x86_64"]["coreInfoSha256"]:
        raise ValueError("Core manifest mismatch")
    if digest(extension / "BUILD-INFO-runtime.json") != pins["architectures"]["x86_64"]["extensionsInfoSha256"]:
        raise ValueError("Extension manifest mismatch")
    for folder in (core, extension):
        info = json.loads((folder / "BUILD-INFO-runtime.json").read_text())
        expected = next(item["sha256"] for item in info["files"] if item["file"] == "runtime-source-worktrees.tar.gz")
        if digest(folder / "runtime-source-worktrees.tar.gz") != expected:
            raise ValueError("Source evidence checksum mismatch")
    for name, expected in NDK_ARCHIVES.items():
        if digest(ndk / name) != expected:
            raise ValueError("NDK source checksum mismatch: " + name)
    if digest(wrapper) != WRAPPER_SHA256:
        raise ValueError("Wrapper source checksum mismatch")
    extension_lock = json.loads((android / "native/python-extensions-lock.json").read_text())
    extension_metadata = {"python-pycryptodomex": {"originalArchives": []}}
    # The extension recipe downloads this exact original archive, not a binary wheel.
    extension_metadata["python-pycryptodomex"]["originalArchives"].append({
        "path": "./python-pycryptodomex/cache/v3.23.0x.tar.gz",
        "sha256": extension_lock["pycryptodomexSourceSha256"],
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yth-corresponding-sources-", dir=output.parent) as directory:
        stage = Path(directory)
        source_count = collect_worktrees(core / "runtime-source-worktrees.tar.gz", core_evidence["packages"],
                                         stage / "original-sources", {"libandroid-selinux", "pulseaudio"})
        source_count += collect_worktrees(extension / "runtime-source-worktrees.tar.gz", extension_metadata,
                                          stage / "original-sources", set())
        for filename in ("termux-recipes.tar.gz", "termux-runtime.patch", "RuntimeBuilder.Dockerfile",
                         "runtime-build-lock.json", "build_controlled_runtime.sh", "record_runtime_build.py"):
            info = json.loads((core / "BUILD-INFO-runtime.json").read_text())
            expected = next(item["sha256"] for item in info["files"] if item["file"] == filename)
            if digest(core / filename) != expected:
                raise ValueError("Producing build input changed: " + filename)
            shutil.copy2(core / filename, stage / filename)
        for arch, pin in pins["architectures"].items():
            evidence_dir = stage / "build-evidence" / arch
            evidence_dir.mkdir(parents=True)
            for component in ("core", "extensions"):
                source = android / pin[component]
                expected = pin[component + "InfoSha256"]
                if digest(source / "BUILD-INFO-runtime.json") != expected:
                    raise ValueError("Build inventory changed: " + arch)
                shutil.copy2(source / "BUILD-INFO-runtime.json", evidence_dir / (component + "-BUILD-INFO.json"))
            shutil.copy2(android / pin["extensions"] / "build_controlled_runtime.sh",
                         evidence_dir / "extension-build_controlled_runtime.sh")
        for name in NDK_ARCHIVES:
            (stage / "ndk").mkdir(exist_ok=True)
            shutil.copy2(ndk / name, stage / "ndk" / name)
        for filename in ("VERIFIED-NDK-SOURCES.json", "VERIFIED-LIBCXX-BUILD-IDS.json"):
            shutil.copy2(ndk / filename, stage / "ndk" / filename)
        for filename in ("quickjs-2026-06-04.tar.xz", "libwebp-1.6.0.tar.gz", "mutagen-1.47.0.tar.gz",
                         "python-extensions-lock.json", "controlled-artifacts.json", "controlled-payloads.properties"):
            shutil.copy2(android / "native" / filename, stage / filename)
        shutil.copy2(wrapper, stage / "youtubedl-android-wrapper-0.18.1.tar.gz")
        shutil.copy2(audit_path, stage / "controlled-source-audit.json")
        shutil.copy2(payload, stage / "runtime-payload-package-mapping.json")
        shutil.copytree(android / "scripts", stage / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(android / "legal", stage / "legal")
        for filename in ("LICENSE", "NOTICE", "RELEASING.md"):
            shutil.copy2(android / filename, stage / filename)
        cert_package = next((core / "packages").glob("ca-certificates_*_all.deb"))
        cert = read_package(cert_package, lambda name: name == "usr/etc/tls/cert.pem")["usr/etc/tls/cert.pem"]
        if hashlib.sha256(cert.data).hexdigest() != "64dfd5b1026700e0a0a324964749da9adc69ae5e51e899bf16ff47d6fd0e9a5e":
            raise ValueError("Certificate data checksum mismatch")
        (stage / "cacert-2025-08-12.pem").write_bytes(cert.data)
        files = [{"file": str(p.relative_to(stage)), "sha256": digest(p), "bytes": p.stat().st_size}
                 for p in sorted(stage.rglob("*")) if p.is_file()]
        report = {"scope": "Native runtime source preparation; not a complete application source attestation",
                  "originalArchives": source_count, "files": files, "publicReleaseReady": False,
                  "completeCorrespondingSourcesVerified": False,
                  "remaining": ["Review exact APK-to-package/source coverage and notices",
                                "Review application/JVM dependency source coverage",
                                "Sign and accept exact replacement APKs on device"]}
        (stage / "SOURCE-INVENTORY.json").write_text(json.dumps(report, indent=2) + "\n")
        temporary = output.with_suffix(".tar.gz.part")
        try:
            with tarfile.open(temporary, "w:gz") as archive:
                for path in sorted(stage.iterdir()):
                    archive.add(path, arcname=path.name)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
    print(json.dumps({"archive": str(output), "sha256": digest(output), "originalArchives": source_count,
                      "files": len(files), "publicReleaseReady": False}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("android", "audit", "ndk", "wrapper", "payload", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    collect(args.android, args.audit, args.ndk, args.wrapper, args.payload, args.output)
