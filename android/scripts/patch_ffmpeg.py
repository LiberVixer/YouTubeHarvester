"""Replace WebP ELF payloads in the upstream AAR, preserving all other entries."""
import argparse
import hashlib
import io
from pathlib import Path
import zipfile


def patch(original, replacements, output, expected):
    if hashlib.sha256(replacements.read_bytes()).hexdigest() != expected:
        raise ValueError("WebP replacement bundle SHA-256 mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    replaced = 0
    with zipfile.ZipFile(original) as aar, zipfile.ZipFile(replacements) as bundle, zipfile.ZipFile(output, "w") as target:
        for item in aar.infolist():
            data = aar.read(item)
            if item.filename.endswith("/libffmpeg.zip.so"):
                abi = item.filename.split("/")[-2]
                buffer = io.BytesIO()
                with zipfile.ZipFile(io.BytesIO(data)) as runtime, zipfile.ZipFile(buffer, "w") as updated:
                    for entry in runtime.infolist():
                        replacement = f"{abi}/{Path(entry.filename).name}"
                        content = runtime.read(entry)
                        if entry.filename.startswith("usr/lib/") and replacement in bundle.namelist():
                            content = bundle.read(replacement)
                            replaced += 1
                        updated.writestr(entry, content)
                data = buffer.getvalue()
            target.writestr(item, data)
    if replaced != 20:
        output.unlink(missing_ok=True)
        raise ValueError(f"Expected 20 runtime replacements, got {replaced}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--replacements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    patch(args.upstream, args.replacements, args.output, args.sha256)
