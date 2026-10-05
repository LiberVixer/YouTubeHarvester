"""Check supplemental source evidence against exact signed Android candidates."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

from package_controlled_payloads import digest


COMMITS = {
    "graphics": "8a05a22af450d589ef911d772a001a49dcb05b71",
    "datastore": "03aea68c431abd3fa436e9f8fa9b9cda12f18334",
}
PINS = {
    "yt-dlp.tar.gz": "072aad4f2a7604e92155f61a275a4752dc64046c8f6d90df3710525d94cd37c1",
    "yt_dlp_ejs-0.8.0.tar.gz": "d5fa1639f63b5c4af8d932495f60689d5370f1a095782c944f7f62a303eb104e",
    "yt_dlp_ejs-0.8.0-py3-none-any.whl": "79300e5fca7f937a1eeede11f0456862c1b41107ce1d726871e0207424f4bdb4",
    "ejs-4fb477f.tar.gz": "47830f927650be514ec13c90b0e15fffbc8c462675d01c4a201632fae7ebdcfc",
    "androidx-graphics-path-8a05a22.tar.gz": "d29f614893503d15cb27f91db77e14ffad281220239ccec02a7f7880297e3536",
    "androidx-datastore-03aea68.tar.gz": "f4081775573797e8d4f06d731f3e06f14ee6965c90bdab04f06077dc6478e22b",
    "androidx-graphics-buildSrc-8a05a22.tar.gz": "349c77b239a308eda6041f1a543da37bcbce84f1e4ad219d0d383d716468f504",
    "androidx-datastore-buildSrc-03aea68.tar.gz": "70b955e1bb3bb3ed0c93d13e4d6de31638439669350121e17b7d3788b8e9d588",
}


def read_tar(path):
    with tarfile.open(path) as archive:
        return {item.name: archive.extractfile(item).read() for item in archive if item.isfile()}


def check_source_snapshot(source_jar, snapshot):
    with zipfile.ZipFile(source_jar) as archive:
        names = [name for name in archive.namelist() if name.endswith((".kt", ".java"))]
        if not names:
            raise ValueError("Selected AndroidX source artifact contains no source code")
        for name in names:
            suffix = name.split("/", 1)[1] if name.startswith(
                ("androidMain/", "jvmAndroidMain/", "commonMain/")) else name
            if not any(value == archive.read(name) for path, value in snapshot.items()
                       if path.endswith("/" + suffix)):
                raise ValueError("Release source differs from selected AndroidX commit: " + name)
        return len(names)


def preserve_build_metadata(output):
    records = []
    for family, commit in COMMITS.items():
        directory = output / ("androidx-" + family + "-build-inputs")
        directory.mkdir(exist_ok=True)
        for name in ("LICENSE.txt", "libraryversions.toml", "gradle/libs.versions.toml",
                     "settings.gradle", "build.gradle", "gradle.properties"):
            target = directory / name
            url = f"https://android.googlesource.com/platform/frameworks/support/+/{commit}/{name}?format=TEXT"
            if not target.exists():
                with urllib.request.urlopen(url, timeout=45) as response:
                    data = base64.b64decode(response.read(), validate=True)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            records.append({"url": url, "file": str(target.relative_to(output)), "sha256": digest(target)})
    return records


def verify_ejs_dependencies(output):
    source = read_tar(output / "ejs-4fb477f.tar.gz")
    lock = json.loads(next(value for name, value in source.items() if name.endswith("/package-lock.json")))
    records = []
    for name in ("astring", "meriyah"):
        dependency = lock["packages"]["node_modules/" + name]
        path = output / f"{name}-{dependency['version']}.tgz"
        algorithm, expected = dependency["integrity"].split("-", 1)
        if algorithm != "sha512" or hashlib.sha512(path.read_bytes()).digest() != base64.b64decode(expected):
            raise ValueError("EJS dependency integrity mismatch: " + name)
        records.append({"name": name, "version": dependency["version"], "url": dependency["resolved"],
                        "integrity": dependency["integrity"], "file": path.name, "sha256": digest(path)})
    return records


def match_native_library(original, packaged, strip_tool):
    if original == packaged:
        return "unchanged"
    with tempfile.TemporaryDirectory(prefix="yth-source-strip-") as directory:
        source, target = Path(directory) / "original.so", Path(directory) / "stripped.so"
        source.write_bytes(original)
        subprocess.run([str(strip_tool), "--strip-unneeded", "-o", str(target), str(source)],
                       check=True, capture_output=True)
        if target.read_bytes() != packaged:
            raise ValueError("Native library differs after the pinned NDK strip operation")
    return "llvm-strip --strip-unneeded"


def audit(android, jvm, additional, candidates, payload, ndk):
    report_path = additional / "APPLICATION-SOURCE-AUDIT.json"
    if report_path.exists():
        raise ValueError("Audit already exists; preserve previous result")
    for name, expected in PINS.items():
        if digest(additional / name) != expected:
            raise ValueError("Supplemental source checksum mismatch: " + name)
    metadata = preserve_build_metadata(additional)
    npm = verify_ejs_dependencies(additional)
    graph = json.loads((jvm / "JVM-SOURCE-INVENTORY.json").read_text())
    if graph["missing"]:
        raise ValueError("Maven source artifacts missing")
    for item in graph["artifacts"]:
        for download in item["downloads"]:
            if digest(jvm / download["file"]) != download["sha256"]:
                raise ValueError("Maven source archive changed")
    source_matches = {}
    for artifact, archive in (("graphics-path", "androidx-graphics-path-8a05a22.tar.gz"),
                              ("datastore-core-android", "androidx-datastore-03aea68.tar.gz")):
        item = next(x for x in graph["artifacts"] if x["binary"].get("module", {}).get("name") == artifact)
        source = next(x for x in item["downloads"] if x["file"].endswith("-sources.jar"))
        source_matches[artifact] = check_source_snapshot(jvm / source["file"], read_tar(additional / archive))
    with zipfile.ZipFile(android / "app/src/main/res/raw/ytdlp") as engine:
        source = {name.removeprefix("yt-dlp/"): value for name, value in read_tar(additional / "yt-dlp.tar.gz").items()}
        names = [n for n in engine.namelist() if n.startswith("yt_dlp/") and n.endswith(".py")]
        if any(source.get(name) != engine.read(name) for name in names):
            raise ValueError("Bundled yt-dlp source mismatch")
        with zipfile.ZipFile(additional / "yt_dlp_ejs-0.8.0-py3-none-any.whl") as wheel:
            ejs_names = [n for n in engine.namelist() if n.startswith("yt_dlp_ejs/")]
            if any(wheel.read(name) != engine.read(name) for name in ejs_names):
                raise ValueError("Bundled EJS distribution mismatch")
    protobuf_item = next(x for x in graph["artifacts"] if x["binary"].get("module", {}).get("name") ==
                         "datastore-preferences-external-protobuf")
    with zipfile.ZipFile(protobuf_item["binary"]["file"]) as relocated, zipfile.ZipFile(
            additional / "protobuf-javalite-4.28.2.jar") as original:
        original_names = {name.replace("com/google/protobuf/", "androidx/datastore/preferences/protobuf/")
                          for name in original.namelist() if name.endswith(".class")}
        relocated_names = {name for name in relocated.namelist() if name.endswith(".class")}
        if original_names != relocated_names:
            raise ValueError("Protobuf relocated class inventory mismatch")
    manifest = json.loads((candidates / "verified.json").read_text())
    native = []
    strip_tool = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip"
    with zipfile.ZipFile(payload) as bundle:
        for item in manifest["artifacts"]:
            apk = candidates / item["apk"]
            if digest(apk) != item["sha256"]:
                raise ValueError("Signed candidate changed")
            with zipfile.ZipFile(apk) as archive:
                abi = item["abi"]
                payload_names = [name for name in bundle.namelist() if name.startswith(abi + "/")]
                if len(payload_names) != 6:
                    raise ValueError("Expected six controlled payload entries per ABI")
                for name in bundle.namelist():
                    if name.startswith(abi + "/"):
                        target = "lib/" + name
                        if archive.read(target) != bundle.read(name):
                            raise ValueError("APK runtime payload mismatch: " + target)
                for dependency in graph["artifacts"]:
                    for name in dependency["nativeLibraries"]:
                        if "module" not in dependency["binary"] or not name.startswith("jni/" + abi + "/"):
                            continue
                        with zipfile.ZipFile(dependency["binary"]["file"]) as producer:
                            target = "lib/" + name.removeprefix("jni/")
                            data = archive.read(target)
                            transformation = match_native_library(producer.read(name), data, strip_tool)
                        native.append({"abi": abi, "file": target, "module": dependency["binary"]["module"],
                                       "transformation": transformation,
                                       "sha256": hashlib.sha256(data).hexdigest()})
    files = [{"file": str(p.relative_to(additional)), "sha256": digest(p), "bytes": p.stat().st_size}
             for p in sorted(additional.rglob("*")) if p.is_file()]
    report = {"signedApks": manifest["artifacts"], "androidxNativeLibraries": native,
              "androidxReleaseSourceMatches": source_matches, "ytDlpPythonSourceMatches": len(names),
              "ejsDistributionFileMatches": len(ejs_names), "ejsDependencies": npm,
              "protobuf": {"version": "4.28.2", "relocatedClassInventory": len(relocated_names),
                           "bytecodeReproducibilityVerified": False},
              "buildMetadata": metadata, "files": files, "stripToolSha256": digest(strip_tool),
              "completeCorrespondingSourcesVerified": False,
              "remaining": ["Final combined source/notices/rebuild coverage review",
                            "No full device acceptance beyond LDPlayer x86_64 has been claimed"]}
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"nativeAndroidXMatches": len(native), "androidxSourceMatches": source_matches,
                      "ytDlpSourceMatches": len(names), "ejsMatches": len(ejs_names),
                      "protobufClasses": len(relocated_names), "report": str(report_path)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("android", "jvm", "additional", "candidates", "payload", "ndk"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    audit(args.android, args.jvm, args.additional, args.candidates, args.payload, args.ndk)
