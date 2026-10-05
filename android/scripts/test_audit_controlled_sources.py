import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from audit_controlled_sources import DONE, inspect_worktrees, read_metadata, safe_parts


class ControlledSourceAuditTest(unittest.TestCase):
    def archive(self, path, entries):
        with tarfile.open(path, "w:gz") as archive:
            for name, data in entries:
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))

    def test_only_unique_finished_packages_count(self):
        log = "termux - building ffmpeg for arch arm...\ntermux - build of 'python' done\n"
        log += "termux - build of 'python' done\ntermux - build of 'ffmpeg' done\n"
        self.assertEqual({"python", "ffmpeg"}, set(DONE.findall(log)))

    def test_unsafe_paths_rejected(self):
        for name in ("/absolute/file", "./python/src/../../../../file"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_parts(name)
        self.assertEqual(("python", "src", "LICENSE"), safe_parts("./python/src/LICENSE"))

    def test_license_and_original_archive_evidence(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "worktrees.tar.gz"
            source = b"upstream archive"
            self.archive(path, [("./python/src/LICENSE", b"license"),
                                ("./python/src/Modules/module.c", b"code"),
                                ("./python/cache/python.tar.xz", source),
                                ("./python/build/object.o", b"object")])
            metadata = {"python": {"licenseFilesDeclared": "LICENSE", "urls": ["https://example.org/python.tar.xz"],
                                   "hashes": [hashlib.sha256(source).hexdigest()]}}
            evidence = inspect_worktrees(path, metadata)["python"]
            self.assertEqual(2, evidence["sourceFiles"])
            self.assertEqual(1, len(evidence["licenseEvidence"]))
            self.assertTrue(evidence["originalArchives"][0]["recipeHashMatches"])
            metadata["python"]["hashes"] = ["0" * 64]
            evidence = inspect_worktrees(path, metadata)["python"]
            self.assertFalse(evidence["originalArchives"][0]["recipeHashMatches"])

    def test_no_source_or_license_is_not_assumed_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "worktrees.tar.gz"
            self.archive(path, [("./other/src/main.c", b"unrelated")])
            evidence = inspect_worktrees(path, {"python": {"licenseFilesDeclared": "", "urls": [], "hashes": []}})
            self.assertEqual({"sourceFiles": 0, "licenseEvidence": [], "originalArchives": []}, evidence["python"])

    def test_bash_metadata_preserves_license_and_multiple_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            recipe = repo / "packages/demo/build.sh"
            recipe.parent.mkdir(parents=True)
            recipe.write_text('TERMUX_PKG_VERSION=1.2\nTERMUX_PKG_LICENSE="BSD 2-Clause, Public Domain"\n'
                              'TERMUX_PKG_LICENSE_FILE="LICENSE.rst"\nTERMUX_PKG_SRCURL=("https://a/$TERMUX_ARCH" "https://b/")\n'
                              'TERMUX_PKG_SHA256=(first second)\n')
            data = read_metadata(repo, "demo", "arm", {"prefix": "/runtime/usr", "apiLevel": 26})
            self.assertEqual("BSD 2-Clause, Public Domain", data["licenseDeclared"])
            self.assertEqual(["https://a/arm", "https://b/"], data["urls"])
            self.assertEqual(["first", "second"], data["hashes"])
