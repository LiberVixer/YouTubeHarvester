"""Rebuild the pinned QuickJS executable for all supported Android ABIs."""
import argparse
import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import urllib.request
import zipfile

VERSION = "2026-06-04"
SHA256 = "b376e839b322978313d929fd20663b11ba58b75df5a46c126dd19ea2fa70ad2a"
URL = f"https://bellard.org/quickjs/quickjs-{VERSION}.tar.xz"
TARGETS = {
    "arm64-v8a": "aarch64-linux-android26",
    "armeabi-v7a": "armv7a-linux-androideabi26",
    "x86": "i686-linux-android26",
    "x86_64": "x86_64-linux-android26",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndk", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    native = root / "native"
    native.mkdir(exist_ok=True)
    archive_path = native / f"quickjs-{VERSION}.tar.xz"
    if not archive_path.exists():
        with urllib.request.urlopen(URL, timeout=60) as response:
            data = response.read(10 * 1024 * 1024 + 1)
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise ValueError("Upstream QuickJS source SHA-256 mismatch")
        archive_path.write_bytes(data)
    data = archive_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("Local QuickJS source SHA-256 mismatch")
    tools = args.ndk.resolve() / "toolchains/llvm/prebuilt/linux-x86_64/bin"
    work = root / "build/native-quickjs"
    work.mkdir(parents=True, exist_ok=True)
    output = native / f"quickjs-{VERSION}-16k.zip"
    temporary = output.with_suffix(".zip.part")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for abi, target in TARGETS.items():
                build = work / abi
                build.mkdir(exist_ok=True)
                with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                    archive.extractall(build, filter="data")
                source = build / f"quickjs-{VERSION}"
                command = ["make", "-j2", "qjs", "CONFIG_CLANG=y", "CROSS_PREFIX=android-",
                    f"CC={tools}/{target}-clang", f"AR={tools}/llvm-ar", "HOST_CC=gcc",
                    "LDFLAGS=-pie -Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384",
                    "LIBS=-lm -ldl"]
                with (work / f"{abi}.log").open("w") as log:
                    subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT, check=True)
                    subprocess.run([str(tools / "llvm-strip"), str(source / "qjs")],
                                   stdout=log, stderr=subprocess.STDOUT, check=True)
                entry = zipfile.ZipInfo(f"{abi}/libqjs.so", (2026, 6, 4, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100755 << 16
                bundle.writestr(entry, (source / "qjs").read_bytes())
                if abi == "arm64-v8a":
                    bundle.writestr("licenses/LICENSE", (source / "LICENSE").read_bytes())
                print(f"Built {abi}", flush=True)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(output, hashlib.sha256(output.read_bytes()).hexdigest(), flush=True)


if __name__ == "__main__":
    main()
