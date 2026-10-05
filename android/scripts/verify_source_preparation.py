"""Check every inventoried source archive member without extracting or approving it."""
import argparse
import hashlib
import json
from pathlib import Path
import posixpath
import tarfile

from package_controlled_payloads import digest, safe_name


def verify(archive_path):
    actual, links, seen = {}, {}, set()
    inventory = None
    with tarfile.open(archive_path, "r|gz") as archive:
        for member in archive:
            name = safe_name(member.name)
            if name in seen:
                raise ValueError("Duplicate source archive member: " + name)
            seen.add(name)
            if member.isdir():
                continue
            if member.issym() or member.islnk():
                target = (posixpath.join(posixpath.dirname(name), member.linkname)
                          if member.issym() else member.linkname)
                if member.linkname.startswith("/"):
                    raise ValueError("Absolute source link")
                links[name] = safe_name(posixpath.normpath(target))
                continue
            if not member.isfile():
                raise ValueError("Unsupported source archive member: " + name)
            with archive.extractfile(member) as stream:
                if name == "SOURCE-INVENTORY.json":
                    if member.size > 16 * 1024**2:
                        raise ValueError("Source inventory exceeds size limit")
                    inventory = json.loads(stream.read())
                else:
                    sha = hashlib.file_digest(stream, "sha256").hexdigest()
                    actual[name] = {"sha256": sha, "bytes": member.size}
    if inventory is None or not inventory.get("files"):
        raise ValueError("Nonempty source inventory is required")
    for name in links:
        target, followed = name, set()
        while target in links:
            if target in followed:
                raise ValueError("Cyclic source link")
            followed.add(target)
            target = links[target]
        if target not in actual:
            raise ValueError("Source link target missing: " + name)
        actual[name] = actual[target]
    expected = {}
    for item in inventory["files"]:
        name = safe_name(item["file"])
        if name in expected:
            raise ValueError("Duplicate source inventory record")
        expected[name] = {"sha256": item["sha256"], "bytes": item["bytes"]}
    if actual != expected:
        missing = sorted(expected.keys() - actual.keys())
        extra = sorted(actual.keys() - expected.keys())
        changed = sorted(n for n in expected.keys() & actual.keys() if expected[n] != actual[n])
        raise ValueError(f"Source archive mismatch: missing={missing}, extra={extra}, changed={changed}")
    return {"archive": str(archive_path), "sha256": digest(archive_path),
            "bytes": archive_path.stat().st_size, "verifiedFiles": len(expected),
            "completeCorrespondingSourcesVerified": False,
            "scope": "Archive inventory integrity only; not source/build-input/license approval"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Preserve previous verification reports")
    report = verify(args.archive)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)
