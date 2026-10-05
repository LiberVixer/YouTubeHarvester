import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from audit_source_notices import archive_entries, inspect_archive, notice_name, preserve_notice, preserve_generic_notice
from prepare_androidx_version_overrides import patch_versions
from collect_rust_notice_sources import match_rust_sources


class NoticeTests(unittest.TestCase):
    def test_original_notice_and_header_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.tar.gz"
            with tarfile.open(source, "w:gz") as archive:
                for name, data in (("src/COPYING", b"Actual copyright"),
                                   ("src/test.c", b"/*\n * either version 2 of the License, or\n * any later version.\n */")):
                    item = tarfile.TarInfo(name)
                    item.size = len(data)
                    archive.addfile(item, io.BytesIO(data))
            report = inspect_archive(source, "test", root / "out")
            self.assertEqual(len(report["notices"]), 1)
            self.assertEqual(len(report["gpl2OrLaterHeaderExamples"]), 1)
            self.assertEqual((root / "out" / report["notices"][0]["file"]).read_bytes(), b"Actual copyright")

    def test_conflicting_notice_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = preserve_notice(root, "notices/LICENSE", b"first")
            self.assertEqual(first, preserve_notice(root, "notices/LICENSE", b"first"))
            with self.assertRaises(ValueError):
                preserve_notice(root, "notices/LICENSE", b"second")
            self.assertEqual((root / "notices/LICENSE").read_bytes(), b"first")
            with self.assertRaises(ValueError):
                preserve_notice(root, "../escape", b"bad")

    def test_duplicate_escape_and_oversized_notice_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sources.zip"
            for names in (("LICENSE", "./LICENSE"), ("../LICENSE",), ("LICENSE",)):
                with self.subTest(names=names):
                    with zipfile.ZipFile(path, "w") as archive:
                        for name in names:
                            archive.writestr(name, b"original")
                    with patch("audit_source_notices.ENTRY_LIMIT", 4 if len(names) == 1 and names[0] == "LICENSE" else 100):
                        with self.assertRaises(ValueError):
                            list(archive_entries(path))

    def test_generic_data_license_is_not_original_copyright_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            path = "packages/termux-licenses/LICENSES/MPL-2.0.txt"
            report = preserve_generic_notice({path: b"license"}, "MPL-2.0", "ca-certificates", Path(folder))
            self.assertEqual(report[0]["scope"], "Declared data-file license text")
            self.assertTrue(notice_name("META-INF/LICENSE.txt"))
            self.assertFalse(notice_name("notices.py"))


class VersionPatchTests(unittest.TestCase):
    def test_only_selected_version_changes(self):
        text = '[versions]\nFRAGMENT = "1.5.5" # original\nCORE = "1.8.0"\n[libraries]\nmodule = "stable"\n'
        revised = patch_versions(text, {"FRAGMENT": ("1.5.5", "1.5.4")})
        self.assertEqual(revised, text.replace('"1.5.5"', '"1.5.4"'))

    def test_unknown_changed_or_ambiguous_version_fails(self):
        for text in ('[versions]\nCORE = "2.0"\n', '[versions]\nOTHER = "1.0"\n',
                     '[versions]\nCORE = "1.0"\n[other]\nCORE = "1.0"\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                patch_versions(text, {"CORE": ("1.0", "1.1")})


class RustNoticeTests(unittest.TestCase):
    def test_checks_exact_rust_bytes_and_subtree(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder) / name for name in ("crate.tar.gz", "tree.tar.gz")]
            for path, prefix in zip(paths, ("crate-1.0/", "repo-commit/member/")):
                with tarfile.open(path, "w:gz") as archive:
                    for name, data in (("src/lib.rs", b"fn example() {}"), ("build.rs", b"fn main() {}")):
                        item = tarfile.TarInfo(prefix + name)
                        item.size = len(data)
                        archive.addfile(item, io.BytesIO(data))
            self.assertEqual(match_rust_sources(*paths, "member")["matchedRustFiles"], 2)
            self.assertEqual(match_rust_sources(*paths, "wrong")["unmatched"], ["src/lib.rs", "build.rs"])


if __name__ == "__main__":
    unittest.main()
