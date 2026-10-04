import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / ".github/scripts/install_android_sdk.sh"


class InstallAndroidSdkTests(unittest.TestCase):
    def run_installer(self, root, version=None, variable="ANDROID_HOME", exit_code=0):
        environment = os.environ.copy()
        environment.pop("ANDROID_HOME", None)
        environment.pop("ANDROID_SDK_ROOT", None)
        environment[variable] = str(root)
        environment["GITHUB_PATH"] = str(root / "github-path")
        if version:
            manager = root / "cmdline-tools" / version / "bin/sdkmanager"
            manager.parent.mkdir(parents=True)
            manager.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@"\nexit {exit_code}\n')
            manager.chmod(0o755)
        return subprocess.run(
            ["bash", str(SCRIPT), "platforms;android-37.0", "build-tools;36.0.0"],
            env=environment, capture_output=True, text=True,
        )

    def test_latest_tools_and_arguments(self):
        with tempfile.TemporaryDirectory(prefix="sdk with spaces ") as directory:
            root = Path(directory)
            result = self.run_installer(root, "latest")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["platforms;android-37.0", "build-tools;36.0.0"])
            self.assertEqual((root / "github-path").read_text().strip(), str(root / "cmdline-tools/latest/bin"))

    def test_numbered_tools_and_sdk_root_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_installer(root, "12.0", "ANDROID_SDK_ROOT")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "github-path").read_text().strip(), str(root / "cmdline-tools/12.0/bin"))

    def test_missing_tools_fail_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_installer(Path(directory))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("command-line tools were not found", result.stderr)

    def test_sdkmanager_failure_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_installer(Path(directory), "latest", exit_code=7)
            self.assertEqual(result.returncode, 7)


if __name__ == "__main__":
    unittest.main()
