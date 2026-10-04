"""Inspect ELF LOAD segments, including runtime libraries inside nested ZIPs."""
import io
import struct
import zipfile
import argparse
import json
from pathlib import Path


def elf_alignments(data):
    if not data.startswith(b"\x7fELF"):
        return None
    endian = "<" if data[5] == 1 else ">"
    if data[4] == 2:
        offset = struct.unpack_from(endian + "Q", data, 32)[0]
        entry_size, count = struct.unpack_from(endian + "HH", data, 54)
        layout = endian + "IIQQQQQQ"
    elif data[4] == 1:
        offset = struct.unpack_from(endian + "I", data, 28)[0]
        entry_size, count = struct.unpack_from(endian + "HH", data, 42)
        layout = endian + "IIIIIIII"
    else:
        raise ValueError("Unsupported ELF class")
    return [struct.unpack_from(layout, data, offset + n * entry_size)[-1]
            for n in range(count) if struct.unpack_from(endian + "I", data, offset + n * entry_size)[0] == 1]


def inspect_native(data, name, depth=0):
    alignment = elf_alignments(data)
    if alignment is not None:
        if not alignment or any(a < 16384 for a in alignment):
            raise ValueError(f"ELF is not 16 KB aligned: {name} {alignment}")
        return 1
    if data.startswith(b"PK"):
        if depth >= 3:
            raise ValueError(f"Nested runtime depth exceeds limit: {name}")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return sum(inspect_native(archive.read(item), name + "!" + item.filename, depth + 1)
                       for item in archive.infolist() if not item.is_dir())
    return 0


def verify_native(apk):
    with zipfile.ZipFile(apk) as archive:
        return sum(inspect_native(archive.read(item), item.filename)
                   for item in archive.infolist()
                   if item.filename.startswith(("lib/arm64-v8a/", "lib/x86_64/")) and not item.is_dir())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("apks", nargs="+", type=Path)
    args = parser.parse_args()
    for apk in args.apks:
        print(json.dumps({"apk": apk.name, "checked64BitElfCount": verify_native(apk)}))
