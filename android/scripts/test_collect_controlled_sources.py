import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from collect_controlled_sources import collect_worktrees, runtime_source_coverage, validate_file_inventory


class SourceCollectionTests(unittest.TestCase):
    def test_subpackage_source_mapping_and_unknown_producer(self):
        with tempfile.TemporaryDirectory() as directory:
            recipes = Path(directory) / "recipes.tar.gz"
            with tarfile.open(recipes, "w:gz") as archive:
                item = tarfile.TarInfo("packages/ncurses/ncurses-ui-libs.subpackage.sh")
                item.size = 0
                archive.addfile(item, io.BytesIO())
            metadata = {"ncurses": {"version": "6.5", "originalArchives": [], "licenseDeclared": "MIT",
                                     "licenseEvidence": [], "genericLicenseEvidence": [], "recipeOnly": False}}
            arch = {"python": [{"package": "ncurses-ui-libs_6.5_x86_64.deb"}], "ffmpeg": [], "launchers": []}
            mapping = {"architectures": [arch]}
            result = runtime_source_coverage(mapping, metadata, recipes)
            self.assertEqual(result[arch["python"][0]["package"]]["recipe"], "packages/ncurses")
            arch["python"] = [{"package": "unknown_1.0_x86_64.deb"}]
            with self.assertRaises(ValueError):
                runtime_source_coverage(mapping, metadata, recipes)

    def test_source_inventory_rejects_changed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.jar").write_bytes(b"source")
            report = {"files": [{"file": "source.jar", "bytes": 6,
                                  "sha256": hashlib.sha256(b"source").hexdigest()}]}
            validate_file_inventory(root, report)
            (root / "source.jar").write_bytes(b"tamper")
            with self.assertRaises(ValueError):
                validate_file_inventory(root, report)

    def test_relative_source_link_preserved_escape_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for target, allowed in (("original", True), ("/etc/passwd", False), ("../../escape", False)):
                source = root / "worktrees.tar.gz"
                with tarfile.open(source, "w:gz") as archive:
                    item = tarfile.TarInfo("./custom/src/link")
                    item.type = tarfile.SYMTYPE
                    item.linkname = target
                    archive.addfile(item)
                out = root / str(allowed) / target.replace("/", "_")
                if allowed:
                    collect_worktrees(source, {}, out, {"custom"})
                    self.assertEqual((out / "custom/src/link").readlink().as_posix(), target)
                else:
                    with self.assertRaises(ValueError):
                        collect_worktrees(source, {}, out, {"custom"})

    def test_collects_original_archive_and_custom_source_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "worktrees.tar.gz"
            data = b"original upstream archive"
            with tarfile.open(source, "w:gz") as archive:
                for name, value in (("./foo/cache/foo.tar.gz", data), ("./custom/src/LICENSE", b"license"),
                                    ("./foo/build/compiled.o", b"not source")):
                    item = tarfile.TarInfo(name)
                    item.size = len(value)
                    archive.addfile(item, io.BytesIO(value))
            metadata = {"foo": {"originalArchives": [{"path": "./foo/cache/foo.tar.gz",
                                                       "sha256": hashlib.sha256(data).hexdigest()}]}}
            out = root / "sources"
            self.assertEqual(collect_worktrees(source, metadata, out, {"custom"}), 1)
            self.assertEqual((out / "foo/cache/foo.tar.gz").read_bytes(), data)
            self.assertTrue((out / "custom/src/LICENSE").is_file())
            self.assertFalse((out / "foo/build/compiled.o").exists())

    def test_missing_original_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "worktrees.tar.gz"
            with tarfile.open(source, "w:gz"):
                pass
            metadata = {"foo": {"originalArchives": [{"path": "./foo/cache/missing.tar.gz", "sha256": "0" * 64}]}}
            with self.assertRaises(ValueError):
                collect_worktrees(source, metadata, root / "sources", set())


if __name__ == "__main__":
    unittest.main()
