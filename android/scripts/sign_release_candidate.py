"""Interactively sign and verify all four release candidates without publishing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from sign_migration_qa import manifest, sign_one, unlock_keystore
from verify_apk import check_manifest, verify

ABIS = ("arm64-v8a", "armeabi-v7a", "x86", "x86_64")


def validate_inputs(args):
    if not sys.stdin.isatty():
        raise ValueError("Use a local interactive terminal, not chat or redirected input")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", args.certificate):
        raise ValueError("An independently approved certificate is required")
    if os.path.lexists(args.output_dir):
        raise ValueError("Refusing to overwrite an existing output directory")
    if not args.keystore.is_file() or args.keystore.is_symlink() or args.keystore.stat().st_mode & 0o077:
        raise ValueError("Keystore must be a private regular file")
    sources = [args.apk_dir / f"app-{abi}-release-unsigned.apk" for abi in ABIS]
    if not all(path.is_file() for path in sources) or not args.keytool.is_file():
        raise ValueError("Required unsigned release APKs or keytool are missing")
    for source in sources:
        check_manifest(manifest(source, args.build_tools), args.version, args.version_code)
    return sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("apk-dir", "build-tools", "keytool", "keystore", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--alias", default="yth-android")
    parser.add_argument("--certificate", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--version-code", type=int, required=True)
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    password = None
    try:
        sources = validate_inputs(args)
        password = unlock_keystore(args.keytool, args.keystore, args.alias, args.certificate.lower())
        args.output_dir.mkdir(mode=0o700)
        with tempfile.TemporaryDirectory(prefix="sign-", dir=args.output_dir) as temporary:
            staged = []
            reports = []
            for abi, source in zip(ABIS, sources):
                target = Path(temporary) / f"YouTubeHarvester-{args.version}-{abi}-release.apk"
                sign_one(source, target, args.build_tools, args.keystore, args.alias, password)
                report = verify(target, args.build_tools, args.version, args.version_code, args.certificate.lower())
                report.update(abi=abi, sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                              sourceSha256=hashlib.sha256(source.read_bytes()).hexdigest())
                reports.append(report)
                staged.append(target)
            password = None
            for source in staged:
                target = args.output_dir / source.name
                with target.open("xb") as output, source.open("rb") as stream:
                    os.chmod(target, 0o600)
                    shutil.copyfileobj(stream, output)
            report = {"version": args.version, "versionCode": args.version_code,
                      "certificateSha256": args.certificate.lower(), "published": False,
                      "deviceAcceptanceComplete": False, "artifacts": reports}
            with (args.output_dir / "verified.json").open("x") as output:
                json.dump(report, output, indent=2)
                output.write("\n")
            with (args.output_dir / "SHA256SUMS-android.txt").open("x") as output:
                output.writelines(f"{item['sha256']}  {item['apk']}\n" for item in reports)
        print("Four release candidates signed and verified. Nothing was published.")
        result = 0
    except (ValueError, OSError, subprocess.SubprocessError):
        print("Signing not completed. No key or password changes were made.")
        result = 1
    finally:
        password = None
    if args.wait:
        input("Press Enter to close this window. ")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
