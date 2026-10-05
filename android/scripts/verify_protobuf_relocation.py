"""Verify the AndroidX Protobuf relocation without invoking its entire Gradle build."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(original, relocated, java_home, asm_jars):
    families = [re.fullmatch(r"(asm|asm-commons|asm-util)-[0-9.]+\.jar", p.name) for p in asm_jars]
    if len(asm_jars) != 3 or any(match is None for match in families) or {
            match.group(1) for match in families} != {"asm", "asm-commons", "asm-util"}:
        raise ValueError("Supply asm, asm-commons and asm-util JARs")
    helper = Path(__file__).with_name("VerifyProtobufRelocation.java")
    classpath = ":".join(str(p.resolve()) for p in asm_jars)
    with tempfile.TemporaryDirectory(prefix="yth-protobuf-relocation-") as directory:
        subprocess.run([str(java_home / "bin/javac"), "-cp", classpath, "-d", directory, str(helper)],
                       check=True, capture_output=True, text=True)
        result = subprocess.run([str(java_home / "bin/java"), "-cp", directory + ":" + classpath,
                                 "VerifyProtobufRelocation", str(original), str(relocated)],
                                check=True, capture_output=True, text=True)
    report = json.loads(result.stdout)
    report.update({"originalSha256": digest(original), "relocatedSha256": digest(relocated),
                   "verifierSha256": digest(helper),
                   "tools": [{"file": p.name, "sha256": digest(p)} for p in asm_jars]})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("original", "relocated", "java-home", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--asm", type=Path, nargs=3, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Preserve existing verification reports; use a new output path")
    report = verify(args.original, args.relocated, args.java_home, args.asm)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report))
