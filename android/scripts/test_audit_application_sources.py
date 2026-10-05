from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from audit_application_sources import check_source_snapshot, match_native_library


class ApplicationSourceTests(unittest.TestCase):
    def test_source_match_and_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            jar = Path(directory) / "sources.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("androidMain/example/Test.kt", b"source")
            snapshot = {"project/src/androidMain/kotlin/example/Test.kt": b"source"}
            self.assertEqual(check_source_snapshot(jar, snapshot), 1)
            with self.assertRaises(ValueError):
                check_source_snapshot(jar, {"project/example/Test.kt": b"changed"})
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("META-INF/MANIFEST.MF", "metadata")
            with self.assertRaises(ValueError):
                check_source_snapshot(jar, {})

    def test_unmodified_native_library(self):
        self.assertEqual(match_native_library(b"ELF", b"ELF", Path("unused")), "unchanged")

    def test_strip_result_must_match(self):
        def strip(args, **kwargs):
            Path(args[args.index("-o") + 1]).write_bytes(b"stripped")
        with patch("audit_application_sources.subprocess.run", side_effect=strip) as run:
            self.assertEqual(match_native_library(b"original", b"stripped", Path("llvm-strip")),
                             "llvm-strip --strip-unneeded")
            with self.assertRaises(ValueError):
                match_native_library(b"original", b"unrelated", Path("llvm-strip"))
            self.assertTrue(run.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
