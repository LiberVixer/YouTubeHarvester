"""Preserve official Maven sources and notices for the resolved release graph.

Downloaded source hashes record provenance, not an independent reproducible-build
or legal attestation. Missing sources and native code coverage fail closed.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from package_controlled_payloads import digest


GOOGLE = "https://dl.google.com/dl/android/maven2/"
CENTRAL = "https://repo.maven.apache.org/maven2/"


def repository(module):
    return GOOGLE if module["group"].startswith("androidx.") else CENTRAL


def artifact_url(module, suffix):
    for key in ("group", "name", "version"):
        if not re.fullmatch(r"[A-Za-z0-9_.+-]+", module[key]):
            raise ValueError("Invalid Maven coordinate")
    path = module["group"].replace(".", "/")
    return (repository(module) + f"{path}/{module['name']}/{module['version']}/"
            f"{module['name']}-{module['version']}{suffix}")


def fetch(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=45) as response:
                if not response.url.startswith((GOOGLE, CENTRAL)):
                    raise ValueError("Download redirected outside official repositories")
                data = response.read(64 * 1024**2 + 1)
                if len(data) > 64 * 1024**2:
                    raise ValueError("Source artifact too large")
                return data
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if attempt == 2:
                raise
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(attempt + 1)


def zip_evidence(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        broken = archive.testzip()
        if broken:
            raise ValueError("Invalid source ZIP: " + broken)
        names = archive.namelist()
        return {"sourceFiles": [name for name in names if name.endswith(
                    (".kt", ".java", ".cpp", ".cc", ".c", ".h", ".hpp", ".proto"))],
                "noticeFiles": [name for name in names if re.search(
                    r"(^|/)(LICENSE|NOTICE|COPYING|COPYRIGHT)([./_-]|$)", name, re.I)],
                "nativeSources": [name for name in names if name.endswith(
                    (".cpp", ".cc", ".c", ".h", ".hpp"))]}


def licenses_from_pom(data):
    root = ET.fromstring(data)
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    return [{"name": item.findtext("m:name", "", ns), "url": item.findtext("m:url", "", ns)}
            for item in root.findall("m:licenses/m:license", ns)]


def collect(graph_path, output):
    if output.exists():
        raise ValueError("Source output already exists; preserve previous evidence")
    graph = json.loads(graph_path.read_text())
    output.mkdir(parents=True)
    records, missing = [], []
    for artifact in unique_artifacts(graph["artifacts"]):
        binary = Path(artifact["file"])
        if digest(binary) != artifact["sha256"]:
            raise ValueError("Resolved binary changed: " + str(binary))
        record = {"binary": artifact, "downloads": []}
        with zipfile.ZipFile(binary) as archive:
            record["nativeLibraries"] = [name for name in archive.namelist()
                                         if name.startswith("jni/") and name.endswith(".so")]
            notices = [name for name in archive.namelist() if re.search(
                r"(^|/)(LICENSE|NOTICE|COPYING|COPYRIGHT)([./_-]|$)", name, re.I)]
            record["binaryNotices"] = [{"name": name, "text": archive.read(name).decode("utf-8", "replace")}
                                        for name in notices]
        module = artifact.get("module")
        if not module:
            record["sourceCoverage"] = "Controlled wrapper/runtime sources audited separately"
            records.append(record)
            continue
        coordinate = ":".join(module[key] for key in ("group", "name", "version"))
        directory = output / module["group"] / module["name"] / module["version"]
        directory.mkdir(parents=True, exist_ok=True)
        for suffix in ("-sources.jar", ".pom"):
            url = artifact_url(module, suffix)
            data = fetch(url)
            if data is None:
                missing.append({"module": coordinate, "url": url})
                continue
            path = directory / url.rsplit("/", 1)[1]
            path.write_bytes(data)
            record["downloads"].append({"url": url, "file": str(path.relative_to(output)),
                                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
            if suffix == "-sources.jar":
                record["sources"] = zip_evidence(data)
            else:
                record["declaredLicenses"] = licenses_from_pom(data)
        records.append(record)
        print(f"{len(records)}/{len(graph['artifacts'])} {coordinate}: "
              f"sources={'sources' in record}, native={len(record['nativeLibraries'])}", flush=True)
    report = {"configuration": graph["configuration"], "graphSha256": digest(graph_path),
              "artifacts": records, "missing": missing,
              "completeCorrespondingSourcesVerified": False,
              "remaining": ["Review native AndroidX producer sources and notices",
                            "Review exact signed APK coverage and final source archive"]}
    (output / "JVM-SOURCE-INVENTORY.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"artifacts": len(records), "missing": len(missing), "output": str(output)}), flush=True)


def unique_artifacts(artifacts):
    result = {}
    for artifact in artifacts:
        key = (str(artifact.get("module")), artifact["name"])
        if key in result and result[key]["sha256"] != artifact["sha256"]:
            raise ValueError("Conflicting runtime artifacts: " + artifact["name"])
        result[key] = artifact
    return list(result.values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    collect(args.graph, args.output)
