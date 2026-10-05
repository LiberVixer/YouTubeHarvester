import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sign_release_candidate import validate_inputs, validate_java


class ReleaseCandidateSigningTest(unittest.TestCase):
    def test_rejects_missing_java(self):
        with patch.dict("os.environ", {}, clear=True), patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "Java is unavailable"):
                validate_java()

    def test_java_home_takes_precedence_over_path(self):
        with patch.dict("os.environ", {"JAVA_HOME": "/approved/jdk"}, clear=True), \
                patch("os.access", return_value=True), patch("subprocess.run") as run:
            validate_java()
            run.assert_called_once_with(["/approved/jdk/bin/java", "-version"],
                                        check=True, capture_output=True)

    def test_rejects_broken_java_home_even_if_path_has_java(self):
        with patch.dict("os.environ", {"JAVA_HOME": "/missing/jdk"}, clear=True), \
                patch("os.access", return_value=False), patch("shutil.which", return_value="/bin/java"):
            with self.assertRaisesRegex(ValueError, "Java is unavailable"):
                validate_java()

    def arguments(self, root):
        key = root / "key.p12"
        key.write_bytes(b"not a real key")
        key.chmod(0o600)
        tool = root / "keytool"
        tool.touch()
        return SimpleNamespace(certificate="0" * 64, output_dir=root / "output", keystore=key,
                               apk_dir=root, keytool=tool, build_tools=root,
                               version="1.2.1", version_code=120100)

    def test_rejects_noninteractive_input_before_reading_keys(self):
        with patch("sys.stdin.isatty", return_value=False):
            with self.assertRaisesRegex(ValueError, "interactive terminal"):
                validate_inputs(SimpleNamespace())

    def test_rejects_existing_and_dangling_output_paths(self):
        with tempfile.TemporaryDirectory() as directory, patch("sys.stdin.isatty", return_value=True):
            args = self.arguments(Path(directory))
            args.output_dir.mkdir()
            with self.assertRaisesRegex(ValueError, "overwrite"):
                validate_inputs(args)
            args.output_dir.rmdir()
            args.output_dir.symlink_to(Path(directory) / "absent")
            with self.assertRaisesRegex(ValueError, "overwrite"):
                validate_inputs(args)

    def test_rejects_public_key_permissions(self):
        with tempfile.TemporaryDirectory() as directory, patch("sys.stdin.isatty", return_value=True):
            args = self.arguments(Path(directory))
            args.keystore.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "private regular"):
                validate_inputs(args)

    def test_requires_all_four_unsigned_release_apks(self):
        with tempfile.TemporaryDirectory() as directory, patch("sys.stdin.isatty", return_value=True):
            args = self.arguments(Path(directory))
            (args.apk_dir / "app-x86_64-release-unsigned.apk").touch()
            with self.assertRaisesRegex(ValueError, "Required unsigned"):
                validate_inputs(args)


if __name__ == "__main__":
    unittest.main()
