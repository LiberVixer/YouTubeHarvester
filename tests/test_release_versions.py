import ast
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.2.1"


class ReleaseVersionTests(unittest.TestCase):
    def test_desktop_and_android_versions_match(self):
        module = ast.parse((ROOT / "tray_launcher.py").read_text(encoding="utf-8"))
        versions = [
            ast.literal_eval(node.value)
            for node in module.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "APP_VERSION"
                    for target in node.targets)
        ]
        self.assertEqual(versions, [VERSION])
        android = ROOT / "android/app/build.gradle.kts"
        if android.exists():
            text = android.read_text(encoding="utf-8")
            self.assertEqual(re.search(r'versionName = "([^"]+)"', text).group(1), VERSION)
            self.assertEqual(int(re.search(r"versionCode = (\d+)", text).group(1)), 120100)

    def test_installer_defaults_match(self):
        expected = {
            "packaging/build_deb.sh": 'VERSION="${1:-1.2.1}"',
            "packaging/build_release.sh": 'RELEASE_VERSION="${2:-1.2.1}"',
            "packaging/windows/build_release.ps1": '[string]$Version = "1.2.1"',
            "packaging/windows/YouTubeHarvester.iss": '#define AppVersion "1.2.1"',
            "BUILD_WINDOWS_OFFLINE.cmd": "YouTubeHarvester_1.2.1_windows*",
        }
        for filename, token in expected.items():
            with self.subTest(filename=filename):
                self.assertIn(token, (ROOT / filename).read_text(encoding="utf-8"))
        script = (ROOT / "packaging/windows/build_release.ps1").read_text(encoding="utf-8")
        self.assertIn('[string]$MsiVersion = "1.2.1"', script)
        self.assertIn('DEB_VERSION="${1:-1.2.1}"',
                      (ROOT / "packaging/build_release.sh").read_text(encoding="utf-8"))
        resource = (ROOT / "packaging/windows/version_info.txt").read_text(encoding="utf-8")
        for token in ("filevers=(1, 2, 1, 0)", "prodvers=(1, 2, 1, 0)",
                      "StringStruct('FileVersion', '1.2.1')",
                      "StringStruct('ProductVersion', '1.2.1')", "flags=0x0"):
            self.assertIn(token, resource)
        self.assertIn('"--version-file", (Join-Path $ScriptDir "version_info.txt")',
                      (ROOT / "packaging/windows/build_windows.ps1").read_text(encoding="utf-8"))

    def test_publication_defaults_are_stable(self):
        script = (ROOT / "packaging/publish_github_release.sh").read_text(encoding="utf-8")
        self.assertIn('TAG="${YTH_RELEASE_TAG:-v1.2.1}"', script)
        self.assertIn('PRERELEASE="${YTH_RELEASE_PRERELEASE:-false}"', script)
        workflow = ROOT / ".github/workflows/release.yml"
        if workflow.exists():
            text = workflow.read_text(encoding="utf-8")
            for key in ("APP_VERSION", "DEB_VERSION", "MSI_VERSION"):
                self.assertIn(f"  {key}: {VERSION}\n", text)
            self.assertNotIn("prerelease: true", text)
            self.assertEqual(text.count("prerelease: false"), 2)


if __name__ == "__main__":
    unittest.main()
