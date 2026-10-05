import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from collect_controlled_sources import collect_worktrees


class SourceCollectionTests(unittest.TestCase):
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
