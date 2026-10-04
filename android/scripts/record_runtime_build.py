"""Record intermediate native rebuild artifacts; never approve a public release."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--architecture", required=True)
    parser.add_argument("--application", type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads((args.folder / "runtime-build-lock.json").read_text())
    if args.architecture not in lock["architectures"].values():
        raise ValueError("Unknown build architecture")
    files = [path for path in sorted(args.folder.rglob("*")) if path.is_file()]
    entries = [{"file": path.relative_to(args.folder).as_posix(),
                "bytes": path.stat().st_size, "sha256": digest(path)} for path in files]
    report = {
        "applicationCommit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=args.application, text=True).strip(),
        "architecture": args.architecture,
        "buildExitCode": int((args.folder / "build-exit-code.txt").read_text()),
        "lock": lock, "files": entries,
        "publicReleaseReady": False,
        "completeCorrespondingSourcesVerified": False,
        "remaining": ["Review full dependency source set", "Build Python extension modules",
                      "Package launchers and payloads", "Integrate verified replacements",
                      "Check exact replacement candidate on device"],
    }
    (args.folder / "BUILD-INFO-runtime.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"architecture": args.architecture, "buildExitCode": report["buildExitCode"],
                      "files": len(entries), "publicReleaseReady": False}))


if __name__ == "__main__":
    main()
