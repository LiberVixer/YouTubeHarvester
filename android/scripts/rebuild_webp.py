"""Rebuild the five FFmpeg WebP dependencies from pinned upstream sources."""
import argparse
import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import urllib.request
import zipfile

VERSION = "1.6.0"
SHA256 = "e4ab7009bf0629fd11982d4c2aa83964cf244cffba7347ecd39019a9e38c4564"
URL = f"https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-{VERSION}.tar.gz"
LIBRARIES = ("libwebp.so", "libwebpdecoder.so", "libwebpdemux.so", "libwebpmux.so", "libsharpyuv.so")
ABIS = ("arm64-v8a", "armeabi-v7a", "x86", "x86_64")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ndk", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    native = root / "native"
    native.mkdir(exist_ok=True)
    source_archive = native / f"libwebp-{VERSION}.tar.gz"
    if not source_archive.exists():
        with urllib.request.urlopen(URL, timeout=60) as response:
            payload = response.read(10 * 1024 * 1024 + 1)
        if hashlib.sha256(payload).hexdigest() != SHA256:
            raise SystemExit("Upstream WebP source SHA-256 mismatch")
        source_archive.write_bytes(payload)
    payload = source_archive.read_bytes()
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise SystemExit("Local WebP source SHA-256 mismatch")
    work = root / "build" / "native-webp"
    work.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        archive.extractall(work, filter="data")
    source = work / f"libwebp-{VERSION}"
    output = native / f"webp-{VERSION}-16k.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for abi in ABIS:
            build = work / abi
            command = ["cmake", "-S", str(source), "-B", str(build),
                       f"-DCMAKE_TOOLCHAIN_FILE={args.ndk.resolve()}/build/cmake/android.toolchain.cmake",
                       f"-DANDROID_ABI={abi}", "-DANDROID_PLATFORM=android-26", "-DCMAKE_BUILD_TYPE=Release",
                       "-DBUILD_SHARED_LIBS=ON", "-DCMAKE_SKIP_RPATH=ON",
                       "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384",
                       "-DWEBP_BUILD_ANIM_UTILS=OFF", "-DWEBP_BUILD_CWEBP=OFF", "-DWEBP_BUILD_DWEBP=OFF",
                       "-DWEBP_BUILD_GIF2WEBP=OFF", "-DWEBP_BUILD_IMG2WEBP=OFF", "-DWEBP_BUILD_VWEBP=OFF",
                       "-DWEBP_BUILD_WEBPINFO=OFF", "-DWEBP_BUILD_WEBPMUX=OFF", "-DWEBP_BUILD_EXTRAS=OFF"]
            with (work / f"{abi}.log").open("w") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
                subprocess.run(["cmake", "--build", str(build), "--parallel", "2"], stdout=log, stderr=subprocess.STDOUT, check=True)
            for name in LIBRARIES:
                data = (build / name).read_bytes()
                entry = zipfile.ZipInfo(f"{abi}/{name}", (2025, 7, 9, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(entry, data)
            print(f"Built {abi}", flush=True)
        for name in ("COPYING", "PATENTS", "AUTHORS"):
            bundle.writestr(f"licenses/{name}", (source / name).read_bytes())
    print(output, hashlib.sha256(output.read_bytes()).hexdigest(), flush=True)


if __name__ == "__main__":
    main()
