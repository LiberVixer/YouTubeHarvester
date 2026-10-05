"""Create replacement payloads with package provenance; never approve publication."""
import argparse
import configparser
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import subprocess
import tarfile
import tempfile
import zipfile

from elf_alignment import inspect_native
from runtime_inventory import elf_dependencies


ABIS = {"aarch64": "arm64-v8a", "arm": "armeabi-v7a", "i686": "x86", "x86_64": "x86_64"}
MACHINES = {"aarch64": 183, "arm": 40, "i686": 3, "x86_64": 62}
SYSTEM = {"libc.so", "libm.so", "libdl.so", "liblog.so", "libandroid.so", "libmediandk.so"}
NDK_TRIPLES = {"aarch64": "aarch64-linux-android", "arm": "arm-linux-androideabi",
               "i686": "i686-linux-android", "x86_64": "x86_64-linux-android"}
PREFIX = "data/data/com.liberivixer.youtubeharvester/"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass(frozen=True)
class Entry:
    data: bytes
    package: str
    link: bool = False


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Unsafe archive path: " + name)
    return path.as_posix()


def link_target(name, entry):
    target = entry.data.decode("utf-8")
    if target.startswith("/"):
        raise ValueError("Absolute runtime symlink: " + name)
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
    if not resolved.startswith("usr/"):
        raise ValueError("Runtime symlink escapes prefix: " + name)
    return resolved


def resolve(entries, name, visited=None):
    visited = set() if visited is None else visited
    if name in visited:
        raise ValueError("Cyclic runtime symlink: " + name)
    if name not in entries:
        raise ValueError("Missing runtime file: " + name)
    visited.add(name)
    entry = entries[name]
    return resolve(entries, link_target(name, entry), visited) if entry.link else entry


def merge(entries, name, entry):
    if name in entries and entries[name] != entry:
        if entries[name].data != entry.data or entries[name].link != entry.link:
            raise ValueError("Conflicting runtime files: " + name)
    else:
        entries[name] = entry


def load_build(folder, expected, arch, lock):
    manifest = folder / "BUILD-INFO-runtime.json"
    if digest(manifest) != expected:
        raise ValueError("Unpinned build manifest: " + str(folder))
    info = json.loads(manifest.read_text())
    if info["architecture"] != arch or info["buildExitCode"] != 0 or info["lock"] != lock:
        raise ValueError("Build identity mismatch: " + str(folder))
    packages = {}
    for entry in info["files"]:
        if not entry["file"].startswith("packages/"):
            continue
        name = safe_name(entry["file"])
        path = folder / name
        if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError("Package checksum mismatch: " + name)
        packages[path.name.split("_", 1)[0]] = path
    return packages


def read_package(path, wanted=lambda name: True):
    entries = {}
    with subprocess.Popen(["dpkg-deb", "--fsys-tarfile", str(path)], stdout=subprocess.PIPE) as process:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                name = safe_name(member.name)
                if not name.startswith(PREFIX) or member.isdir():
                    continue
                name = name[len(PREFIX):]
                if not name.startswith("usr/") or not wanted(name):
                    continue
                if member.issym():
                    entry = Entry(member.linkname.encode(), path.name, True)
                    link_target(name, entry)
                elif member.isfile():
                    entry = Entry(archive.extractfile(member).read(), path.name)
                else:
                    raise ValueError("Unsupported runtime tar entry: " + name)
                merge(entries, name, entry)
        # tarfile stops at the end marker; drain producer padding before wait().
        process.stdout.read()
        if process.wait() != 0:
            raise ValueError("Failed to read package: " + str(path))
    return entries


def is_library(name):
    return bool(re.fullmatch(r"usr/lib/[^/]+\.so(?:\..+)?", name))


def dynamic_symbols(data):
    with tempfile.NamedTemporaryFile() as binary:
        binary.write(data)
        binary.flush()
        output = subprocess.check_output(["readelf", "--dyn-syms", "--wide", binary.name], text=True)
    defined, undefined = set(), set()
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 8 or fields[4] not in {"GLOBAL", "WEAK"}:
            continue
        name = fields[7].split("@", 1)[0]
        (undefined if fields[6] == "UND" else defined).add(name)
    return defined, undefined


def validate_media_api(payload, shim, stub):
    provided, _ = dynamic_symbols(shim.data)
    available, _ = dynamic_symbols(stub)
    used = set()
    for entry in payload.values():
        if not entry.link and entry.data.startswith(b"\x7fELF"):
            _, undefined = dynamic_symbols(entry.data)
            used.update(undefined & provided)
    missing = used - available
    if not used or missing:
        raise ValueError("Media NDK API coverage failed: " + ", ".join(sorted(missing)))
    return sorted(used)


def closure(pool, roots, arch):
    chosen = dict(roots)
    queue = list(roots)
    checked = set()
    while queue:
        name = queue.pop()
        if name in checked:
            continue
        checked.add(name)
        entry = chosen[name]
        if entry.link:
            resolve(pool, name)
            target = link_target(name, entry)
            if target not in chosen:
                chosen[target] = pool[target]
                queue.append(target)
            continue
        if not entry.data.startswith(b"\x7fELF"):
            continue
        if entry.data[5] != 1 or int.from_bytes(entry.data[18:20], "little") != MACHINES[arch]:
            raise ValueError("Wrong ELF architecture: " + name)
        if arch in ("aarch64", "x86_64"):
            inspect_native(entry.data, name)
        for needed in elf_dependencies(entry.data):
            if needed in SYSTEM:
                continue
            target = "usr/lib/" + needed
            if target not in pool:
                raise ValueError("Unresolved ELF dependency: " + name + " -> " + needed)
            if target not in chosen:
                chosen[target] = pool[target]
                queue.append(target)
    return chosen


def make_zip(entries):
    stream = io.BytesIO()
    directories = set()
    for name in entries:
        directories.update(str(p) + "/" for p in PurePosixPath(name).parents if str(p) != ".")
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(directories):
            item = zipfile.ZipInfo(name)
            item.create_system = 3
            item.external_attr = (stat.S_IFDIR | 0o755) << 16
            archive.writestr(item, b"")
        for name, entry in sorted(entries.items()):
            item = zipfile.ZipInfo(name)
            item.create_system = 3
            item.compress_type = zipfile.ZIP_DEFLATED
            mode = stat.S_IFLNK | 0o777 if entry.link else stat.S_IFREG | 0o644
            item.external_attr = mode << 16
            archive.writestr(item, entry.data)
    return stream.getvalue()


def mutagen_entries(source, expected):
    if digest(source) != expected:
        raise ValueError("Mutagen source checksum mismatch")
    result = {}
    with tarfile.open(source) as archive:
        for member in archive:
            parts = PurePosixPath(safe_name(member.name)).parts
            if not member.isfile() or len(parts) < 2:
                continue
            if parts[1] == "mutagen":
                name = "usr/lib/python3.12/site-packages/" + "/".join(parts[1:])
            elif parts[1] in ("PKG-INFO", "COPYING"):
                name = "usr/lib/python3.12/site-packages/mutagen-1.47.0.dist-info/" + (
                    "METADATA" if parts[1] == "PKG-INFO" else "COPYING")
            else:
                continue
            result[name] = Entry(archive.extractfile(member).read(), source.name)
    if "usr/lib/python3.12/site-packages/mutagen/__init__.py" not in result:
        raise ValueError("Mutagen source module missing")
    return result


def provenance(entries):
    return [{"file": name, "package": entry.package, "symlink": entry.link,
             "sha256": hashlib.sha256(entry.data).hexdigest()} for name, entry in sorted(entries.items())]


def build(android, inputs, output, ndk):
    if output.exists():
        raise ValueError("Replacement output already exists")
    lock = json.loads((android / "native/runtime-build-lock.json").read_text())
    properties = configparser.ConfigParser(interpolation=None)
    properties.read_string("[ndk]\n" + (ndk / "source.properties").read_text())
    if properties["ndk"].get("Pkg.Revision") != lock["ndkVersion"]:
        raise ValueError("NDK version differs from the controlled build lock")
    extension_lock = json.loads((android / "native/python-extensions-lock.json").read_text())
    pins = json.loads(inputs.read_text())
    if set(pins["architectures"]) != set(ABIS):
        raise ValueError("Require all four ABIs")
    quickjs = android / "native/quickjs-2026-06-04-16k.zip"
    if digest(quickjs) != "1d12127c7fdbaafa64fe01ad1b1380179c777d9e6c4abe8b8b912e88074a10df":
        raise ValueError("QuickJS bundle checksum mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".zip.part")
    reports = []
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as bundle, \
                zipfile.ZipFile(quickjs) as qjs:
            for arch, abi in ABIS.items():
                pin = pins["architectures"][arch]
                core = load_build(android / pin["core"], pin["coreInfoSha256"], arch, lock)
                extensions = load_build(android / pin["extensions"], pin["extensionsInfoSha256"], arch, lock)
                pool = {}
                for package in core.values():
                    for name, entry in read_package(package, is_library).items():
                        if is_library(name):
                            merge(pool, name, entry)
                python = read_package(core["python"], lambda name: name.startswith("usr/lib/python3.12/")
                                      or name == "usr/bin/python3.12")
                python_roots = {name: entry for name, entry in python.items()
                                if name.startswith("usr/lib/python3.12/") and not name.endswith((".a", ".o", ".pc"))}
                python_roots["usr/bin/python3.12"] = python["usr/bin/python3.12"]
                certs = read_package(core["ca-certificates"], lambda name: name == "usr/etc/tls/cert.pem")
                python_roots["usr/etc/tls/cert.pem"] = certs["usr/etc/tls/cert.pem"]
                crypto = read_package(extensions["python-pycryptodomex"],
                                      lambda name: name.startswith("usr/lib/python3.12/site-packages/"))
                for name, entry in crypto.items():
                    if name.startswith("usr/lib/python3.12/site-packages/"):
                        merge(python_roots, name, entry)
                for name, entry in mutagen_entries(android / "native/mutagen-1.47.0.tar.gz",
                                                  extension_lock["mutagenSourceSha256"]).items():
                    merge(python_roots, name, entry)
                python_payload = closure({**pool, **python_roots}, python_roots, arch)
                ffmpeg = read_package(core["ffmpeg"], lambda name: name in ("usr/bin/ffmpeg", "usr/bin/ffprobe"))
                ffmpeg_roots = {name: ffmpeg[name] for name in ("usr/bin/ffmpeg", "usr/bin/ffprobe")}
                ffmpeg_payload = closure({**pool, **ffmpeg_roots}, ffmpeg_roots, arch)
                stub = ndk / "toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib" / NDK_TRIPLES[arch] / str(lock["apiLevel"]) / "libmediandk.so"
                media_symbols = validate_media_api(ffmpeg_payload, pool["usr/lib/libmediandk.so"], stub.read_bytes())
                launchers = {"libpython.so": python_payload.pop("usr/bin/python3.12"),
                             "libffmpeg.so": ffmpeg_payload.pop("usr/bin/ffmpeg"),
                             "libffprobe.so": ffmpeg_payload.pop("usr/bin/ffprobe")}
                for name, entry in launchers.items():
                    bundle.writestr(abi + "/" + name, entry.data)
                bundle.writestr(abi + "/libpython.zip.so", make_zip(python_payload))
                bundle.writestr(abi + "/libffmpeg.zip.so", make_zip(ffmpeg_payload))
                bundle.writestr(abi + "/libqjs.so", qjs.read(abi + "/libqjs.so"))
                reports.append({"architecture": arch, "abi": abi, "input": pin,
                                "python": provenance(python_payload), "ffmpeg": provenance(ffmpeg_payload),
                                "launchers": provenance(launchers),
                                "platformMediaNdk": {"apiLevel": lock["apiLevel"],
                                                     "stubSha256": digest(stub), "imports": media_symbols}})
                print(json.dumps({"architecture": arch, "pythonFiles": len(python_payload),
                                  "ffmpegFiles": len(ffmpeg_payload)}), flush=True)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    report = {"bundleSha256": digest(output), "architectures": reports,
              "completeCorrespondingSourcesVerified": False, "publicReleaseReady": False}
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ndk", type=Path, required=True)
    args = parser.parse_args()
    build(args.android, args.inputs, args.output, args.ndk)
