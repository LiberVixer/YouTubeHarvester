from pathlib import Path
import tempfile
import unittest
import zipfile

from package_controlled_payloads import ABIS, digest
from patch_controlled_runtime import FILES, patch


class ControlledRuntimePatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.original = self.root / "original.aar"
        self.replacements = self.root / "replacements.zip"
        self.output = self.root / "result.aar"

    def prepare(self, extra=False):
        with zipfile.ZipFile(self.original, "w") as archive:
            archive.writestr("classes.jar", b"wrapper unchanged")
            for abi in ABIS.values():
                for name in FILES["library"]:
                    archive.writestr(f"jni/{abi}/{name}", b"old bytes")
            if extra:
                archive.writestr("jni/x86/libunknown.so", b"unknown native payload")
        with zipfile.ZipFile(self.replacements, "w") as archive:
            for abi in ABIS.values():
                for name in FILES["library"]:
                    archive.writestr(f"{abi}/{name}", b"PKnew zip" if name.endswith(".zip.so") else b"\x7fELFnew")

    def test_all_native_payloads_replaced_wrapper_preserved(self):
        self.prepare()
        patch(self.original, self.replacements, self.output, digest(self.replacements), "library")
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.read("classes.jar"), b"wrapper unchanged")
            self.assertTrue(all(archive.read(name) != b"old bytes" for name in archive.namelist() if name.startswith("jni/")))

    def test_checksum_and_inventory_failure_preserve_existing_output(self):
        self.prepare(extra=True)
        self.output.write_bytes(b"previous output")
        for expected in ("0" * 64, digest(self.replacements)):
            with self.assertRaises(ValueError):
                patch(self.original, self.replacements, self.output, expected, "library")
            self.assertEqual(self.output.read_bytes(), b"previous output")
            self.assertFalse(self.output.with_suffix(".aar.part").exists())

    def test_invalid_replacement_rejected(self):
        self.prepare()
        with zipfile.ZipFile(self.replacements, "w") as archive:
            for abi in ABIS.values():
                for name in FILES["library"]:
                    archive.writestr(f"{abi}/{name}", b"not ELF or ZIP")
        with self.assertRaises(ValueError):
            patch(self.original, self.replacements, self.output, digest(self.replacements), "library")
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
