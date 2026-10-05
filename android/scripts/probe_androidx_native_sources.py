"""Compile preserved AndroidX native sources for four ABIs; never replace APK libraries."""
import argparse
import json
from pathlib import Path
import subprocess
import tarfile

from audit_application_sources import PINS
from package_controlled_payloads import digest, safe_name


TARGETS = {"arm64-v8a": "aarch64-linux-android", "armeabi-v7a": "armv7a-linux-androideabi",
           "x86": "i686-linux-android", "x86_64": "x86_64-linux-android"}


def extract_native(archive_path, output):
    with tarfile.open(archive_path) as archive:
        for member in archive:
            if not member.isfile() or "/cpp/" not in member.name:
                continue
            path = output / safe_name(member.name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(archive.extractfile(member).read())


def probe(additional, ndk, output):
    if output.exists():
        raise ValueError("Use a new probe output directory")
    inputs = {name: additional / name for name in (
        "androidx-graphics-path-8a05a22.tar.gz", "androidx-datastore-03aea68.tar.gz")}
    for name, path in inputs.items():
        if digest(path) != PINS[name]:
            raise ValueError("AndroidX source archive changed: " + name)
    output.mkdir(parents=True)
    graphics, datastore = output / "graphics", output / "datastore"
    extract_native(inputs["androidx-graphics-path-8a05a22.tar.gz"], graphics)
    extract_native(inputs["androidx-datastore-03aea68.tar.gz"], datastore)
    toolchain = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
    records = []
    for abi, target in TARGETS.items():
        compiler = toolchain / (target + "26-clang++")
        common = [str(compiler), "-shared", "-fPIC", "-O2", "-std=c++17", "-static-libstdc++",
                  "-Wl,-z,max-page-size=16384", "-Wl,--no-undefined"]
        if abi == "armeabi-v7a":
            common.append("-march=armv7-a")
        g = graphics / "src/main/cpp"
        d = datastore / "datastore-core/src/androidMain/cpp"
        builds = {
            "libandroidx.graphics.path.so": [str(g / name) for name in (
                "Conic.cpp", "PathIterator.cpp", "pathway.cpp")] +
                ["-Wl,--version-script=" + str(g / "libandroidx.graphics.path.map")],
            "libdatastore_shared_counter.so": [str(d / "shared/shared_counter.cc"),
                str(d / "jni/androidx_datastore_core_SharedCounter.cc"), "-Wall", "-Werror"],
        }
        directory = output / abi
        directory.mkdir()
        for name, sources in builds.items():
            library = directory / name
            command = common + sources + ["-o", str(library)]
            result = subprocess.run(command, capture_output=True, text=True)
            (directory / (name + ".log")).write_text(result.stdout + result.stderr)
            result.check_returncode()
            records.append({"abi": abi, "file": str(library.relative_to(output)),
                            "sha256": digest(library), "bytes": library.stat().st_size,
                            "command": command})
            print(abi + ": source compile passed: " + name, flush=True)
    report = {"purpose": "Preferred-source compilation feasibility, not reproduction of Maven ELF bytes",
              "apkLibrariesReplaced": False, "binaryReproducibilityVerified": False,
              "sources": {name: digest(path) for name, path in inputs.items()},
              "compilerSha256": digest(toolchain / "clang"), "libraries": records}
    (output / "ANDROIDX-NATIVE-SOURCE-PROBE.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("additional", "ndk", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    probe(args.additional.resolve(), args.ndk.resolve(), args.output.resolve())
