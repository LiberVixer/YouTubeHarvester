import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sign_release_candidate import validate_inputs


class ReleaseCandidateSigningTest(unittest.TestCase):
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
