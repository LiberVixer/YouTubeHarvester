"""Fail-closed checks against the packaged manifest and signing certificate."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
from elf_alignment import verify_native

PACKAGE = "com.liberivixer.youtubeharvester"
MIGRATION_PACKAGE = PACKAGE + ".migrationqa"
PROTECTED_COMPONENTS = {
    "androidx.work.impl.background.systemjob.SystemJobService": "android.permission.BIND_JOB_SERVICE",
    "androidx.work.impl.diagnostics.DiagnosticsReceiver": "android.permission.DUMP",
    "androidx.profileinstaller.ProfileInstallReceiver": "android.permission.DUMP",
}


def parse_tree(output):
    """Decode aapt2's XML tree into elements; never use a source manifest as evidence."""
    stack = []
    root = None
    for line in output.splitlines():
        indent = len(line) - len(line.lstrip())
        text = line.strip()
        if text.startswith("E: "):
            node = ET.Element(text[3:].split()[0])
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if stack:
                stack[-1][1].append(node)
            else:
                if root is not None:
                    raise ValueError("Multiple manifest roots")
                root = node
            stack.append((indent, node))
        elif text.startswith("A: "):
            if not stack:
                raise ValueError("Attribute outside element")
            key, value = text[3:].split("=", 1)
            key = key.split("(", 1)[0].rsplit(":", 1)[-1]
            if value.startswith('"'):
                value = json.JSONDecoder().raw_decode(value)[0]
            stack[-1][1].set(key, value)
    if root is None or root.tag != "manifest":
        raise ValueError("No packaged manifest")
    return root


def check_manifest(root, version, version_code, migration_qa=False):
    if (root.get("package"), root.get("versionName"), root.get("versionCode")) != (
        MIGRATION_PACKAGE if migration_qa else PACKAGE, version, str(version_code)
    ):
        raise ValueError("APK package/version differs from the release source")
    app = root.find("application")
    if app is None or app.get("debuggable", "false") != "false":
        raise ValueError("Debuggable APK must not be distributed")
    if app.get("testOnly", "false") != "false" or app.get("allowBackup") != "false":
        raise ValueError("Unexpected testOnly/allowBackup policy")
    public = []
    for node in app:
        if node.tag not in {"activity", "activity-alias", "service", "receiver", "provider"}:
            continue
        name = node.get("name", "")
        if name in {"androidx.compose.ui.tooling.PreviewActivity", "androidx.activity.ComponentActivity"}:
            raise ValueError(f"Debug tooling component: {name}")
        if node.get("exported") == "false":
            continue
        if node.get("exported") != "true":
            raise ValueError(f"Explicit exported policy required: {name}")
        public.append(name)
        if node.tag == "activity" and name == f"{PACKAGE}.MainActivity":
            continue
        if name not in PROTECTED_COMPONENTS or node.get("permission") != PROTECTED_COMPONENTS[name]:
            raise ValueError(f"Unexpected exported component: {name}")
    if f"{PACKAGE}.MainActivity" not in public:
        raise ValueError("Launcher/share entry point missing")
    return public


def check_certificate(output, expected, allow_legacy=False):
    fingerprints = re.findall(r"^Signer #\d+ certificate SHA-256 digest: ([a-fA-F0-9]{64})$", output, re.M)
    if fingerprints != [expected.lower()]:
        raise ValueError("APK signing certificate mismatch")
    if not allow_legacy and re.search(r"certificate DN:.*CN=Android Debug", output, re.I):
        raise ValueError("Debug signing certificate is forbidden for public releases")


def verify(apk, build_tools, version, version_code, certificate, allow_legacy=False, migration_qa=False):
    if migration_qa and allow_legacy:
        raise ValueError("Migration target requires permanent signing identity")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", certificate):
        raise ValueError("An independently configured certificate SHA-256 is required")
    manifest = subprocess.check_output([
        str(build_tools / "aapt2"), "dump", "xmltree", "--file", "AndroidManifest.xml", str(apk)
    ], text=True)
    public = check_manifest(parse_tree(manifest), version, version_code, migration_qa)
    signature = subprocess.check_output([
        str(build_tools / "apksigner"), "verify", "--verbose", "--print-certs", str(apk)
    ], text=True)
    check_certificate(signature, certificate.lower(), allow_legacy)
    subprocess.run([str(build_tools / "zipalign"), "-c", "-P", "16", "4", str(apk)], check=True)
    native_count = verify_native(apk)
    return {"apk": apk.name, "certificateSha256": certificate.lower(), "exported": public, "nativeElfCount": native_count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("apk", type=Path)
    parser.add_argument("--build-tools", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--version-code", type=int, required=True)
    parser.add_argument("--certificate", required=True)
    parser.add_argument("--allow-legacy-certificate", action="store_true",
                        help="Private beta migration build only; never for publication")
    parser.add_argument("--migration-qa", action="store_true",
                        help="Isolated .migrationqa package only; not a public release")
    args = parser.parse_args()
    print(json.dumps(verify(args.apk, args.build_tools, args.version, args.version_code,
                            args.certificate, args.allow_legacy_certificate, args.migration_qa), indent=2))
