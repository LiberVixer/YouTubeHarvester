import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fetch_controlled_payloads import fetch


class PayloadFetchTests(unittest.TestCase):
    def prepare(self, root, data):
        (root / "native").mkdir()
        (root / "native/controlled-payloads.properties").write_text(
            "bundle=build/runtime.zip\nsha256=" + hashlib.sha256(data).hexdigest() +
            "\nrepository=owner/repo\nrelease=android-v1.2.1\nasset=runtime.zip\n")

    @patch("fetch_controlled_payloads.subprocess.run")
    def test_existing_payload_is_verified_without_download(self, run):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare(root, b"verified")
            (root / "build").mkdir()
            (root / "build/runtime.zip").write_bytes(b"verified")
            fetch(root, "gh")
            run.assert_not_called()
            (root / "build/runtime.zip").write_bytes(b"user modification")
            with self.assertRaises(ValueError):
                fetch(root, "gh")
            self.assertEqual((root / "build/runtime.zip").read_bytes(), b"user modification")

    def test_download_commits_only_verified_bytes(self):
        for incoming, allowed in ((b"verified", True), (b"tampered", False)):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.prepare(root, b"verified")

                def download(command, check):
                    destination = Path(command[command.index("--dir") + 1])
                    (destination / "runtime.zip").write_bytes(incoming)

                with patch("fetch_controlled_payloads.subprocess.run", side_effect=download):
                    if allowed:
                        fetch(root, "gh")
                        self.assertEqual((root / "build/runtime.zip").read_bytes(), b"verified")
                    else:
                        with self.assertRaises(ValueError):
                            fetch(root, "gh")
                        self.assertFalse((root / "build/runtime.zip").exists())


if __name__ == "__main__":
    unittest.main()
