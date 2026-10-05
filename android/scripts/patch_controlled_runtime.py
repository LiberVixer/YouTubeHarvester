"""Atomically replace every upstream native runtime entry, retaining wrapper code."""
import argparse
from pathlib import Path
import zipfile

from package_controlled_payloads import ABIS, digest


FILES = {"library": ("libpython.so", "libpython.zip.so", "libqjs.so"),
         "ffmpeg": ("libffmpeg.so", "libffmpeg.zip.so", "libffprobe.so")}


def patch(original, replacements, output, expected, component):
    if digest(replacements) != expected:
        raise ValueError("Controlled replacement bundle checksum mismatch")
    wanted = {f"jni/{abi}/{name}" for abi in ABIS.values() for name in FILES[component]}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".aar.part")
    try:
        with zipfile.ZipFile(original) as upstream, zipfile.ZipFile(replacements) as bundle, \
                zipfile.ZipFile(temporary, "w") as target:
            if len(upstream.namelist()) != len(set(upstream.namelist())):
                raise ValueError("Duplicate upstream AAR entry")
            if len(bundle.namelist()) != len(set(bundle.namelist())):
                raise ValueError("Duplicate replacement entry")
            actual = {item.filename for item in upstream.infolist()
                      if item.filename.startswith("jni/") and not item.is_dir()}
            if actual != wanted:
                raise ValueError("Unexpected upstream native inventory")
            for item in upstream.infolist():
                data = bundle.read(item.filename.removeprefix("jni/")) if item.filename in wanted else upstream.read(item)
                if item.filename in wanted:
                    magic = b"PK" if item.filename.endswith(".zip.so") else b"\x7fELF"
                    if not data.startswith(magic):
                        raise ValueError("Invalid replacement type: " + item.filename)
                target.writestr(item, data)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("upstream", "replacements", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--component", choices=FILES, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    patch(args.upstream, args.replacements, args.output, args.sha256, args.component)
