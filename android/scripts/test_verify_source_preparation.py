import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from verify_source_preparation import verify


class SourceArchiveTests(unittest.TestCase):
    def make_archive(self, root, data=b"source", extra=False, missing=False, link=None, duplicate=False):
        path = root / "source.tar.gz"
        entries = [{"file": "src/Example.java", "bytes": 6,
                    "sha256": hashlib.sha256(b"source").hexdigest()}]
        if link is not None:
            entries.append({**entries[0], "file": "src/link"})
        with tarfile.open(path, "w:gz") as archive:
            files = [("SOURCE-INVENTORY.json", json.dumps({"files": entries}).encode())]
            if not missing:
                files.append(("src/Example.java", data))
            if extra:
                files.append(("untracked", b"extra"))
            if duplicate:
                files.append(("src/Example.java", data))
            for name, value in files:
                member = tarfile.TarInfo(name)
                member.size = len(value)
                archive.addfile(member, io.BytesIO(value))
            if link is not None:
                member = tarfile.TarInfo("src/link")
                member.type = tarfile.SYMTYPE
                member.linkname = link
                archive.addfile(member)
        return path

    def test_checks_source_bytes_without_approving_source_closure(self):
        with tempfile.TemporaryDirectory() as folder:
            report = verify(self.make_archive(Path(folder)))
            self.assertEqual(report["verifiedFiles"], 1)
            self.assertIs(report["completeCorrespondingSourcesVerified"], False)

    def test_changed_missing_extra_and_duplicate_rejected(self):
        for kwargs in ({"data": b"change"}, {"missing": True}, {"extra": True}, {"duplicate": True}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError):
                    verify(self.make_archive(Path(folder), **kwargs))

    def test_internal_link_verified_external_and_cyclic_links_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(verify(self.make_archive(Path(folder), link="Example.java"))["verifiedFiles"], 2)
        for link in ("../../escape", "/etc/passwd", "link", "missing"):
            with self.subTest(link=link), tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError):
                    verify(self.make_archive(Path(folder), link=link))


if __name__ == "__main__":
    unittest.main()
