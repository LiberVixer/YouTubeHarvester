"""Replace only the four QuickJS executables in the upstream library AAR."""
import argparse
import hashlib
from pathlib import Path
import zipfile

from rebuild_quickjs import TARGETS


def patch(original, replacements, output, expected):
    if hashlib.sha256(replacements.read_bytes()).hexdigest() != expected:
        raise ValueError("QuickJS replacement bundle SHA-256 mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".aar.part")
    wanted = {f"jni/{abi}/libqjs.so" for abi in TARGETS}
    replaced = set()
    try:
        with zipfile.ZipFile(original) as aar, zipfile.ZipFile(replacements) as bundle, \
                zipfile.ZipFile(temporary, "w") as target:
            for entry in aar.infolist():
                data = aar.read(entry)
                if entry.filename in wanted:
                    if entry.filename in replaced:
                        raise ValueError("Duplicate upstream QuickJS executable")
                    abi = entry.filename.split('/')[1]
                    data = bundle.read(f"{abi}/libqjs.so")
                    if not data.startswith(b'\x7fELF'):
                        raise ValueError("Replacement is not ELF")
                    replaced.add(entry.filename)
                target.writestr(entry, data)
        if replaced != wanted:
            raise ValueError("Expected one QuickJS executable for each of four ABIs")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("upstream", "replacements", "output"):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    patch(args.upstream, args.replacements, args.output, args.sha256)
