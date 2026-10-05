"""Compile the preserved Protobuf Java sources without using its original binary."""
import argparse
import json
from pathlib import Path
import subprocess
import zipfile

from package_controlled_payloads import digest, safe_name


def extract_sources(source_jar, folder):
    sources = []
    with zipfile.ZipFile(source_jar) as archive:
        for name in archive.namelist():
            if not name.endswith(".java"):
                continue
            path = folder / safe_name(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(archive.read(name))
            sources.append(path)
    if not sources:
        raise ValueError("Protobuf source JAR contains no Java sources")
    return sources


def probe(source_jar, reference, java_home, output):
    if output.exists():
        raise ValueError("Use a new Protobuf probe output directory")
    output.mkdir(parents=True)
    sources = extract_sources(source_jar, output / "sources")
    classes = output / "classes"
    classes.mkdir()
    command = [str(java_home / "bin/javac"), "-source", "8", "-target", "8",
               "-g", "-d", str(classes)] + [str(path) for path in sources]
    result = subprocess.run(command, capture_output=True, text=True)
    (output / "javac.log").write_text(result.stdout + result.stderr)
    result.check_returncode()
    compiled = {str(path.relative_to(classes)) for path in classes.rglob("*.class")}
    with zipfile.ZipFile(reference) as archive:
        expected = {name for name in archive.namelist() if name.endswith(".class")}
    if compiled != expected:
        raise ValueError("Compiled Protobuf class inventory differs from the upstream JAR")
    report = {"javaSourceFiles": len(sources), "compiledClasses": len(compiled),
              "sourceJarSha256": digest(source_jar), "referenceJarSha256": digest(reference),
              "compilerVersion": subprocess.check_output([str(java_home / "bin/javac"), "-version"],
                                                         stderr=subprocess.STDOUT, text=True).strip(),
              "compilerSha256": digest(java_home / "bin/javac"),
              "originalBinaryUsedForCompilation": False, "binaryReproducibilityVerified": False,
              "apkLibrariesReplaced": False, "command": command}
    (output / "PROTOBUF-SOURCE-PROBE.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "command"}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sources", "reference", "java-home", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    probe(args.sources.resolve(), args.reference.resolve(), args.java_home.resolve(), args.output.resolve())
