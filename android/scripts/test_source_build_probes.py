import base64
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from collect_androidx_build_inputs import collect, download
from probe_androidx_native_sources import extract_native
from probe_protobuf_sources import extract_sources


class BuildInputTests(unittest.TestCase):
    def test_download_refuses_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing"
            path.write_bytes(b"preserve")
            with patch("collect_androidx_build_inputs.urllib.request.urlopen") as request:
                with self.assertRaises(ValueError):
                    download("https://android.googlesource.com/source", path)
            request.assert_not_called()
            self.assertEqual(path.read_bytes(), b"preserve")

    def test_family_specific_build_inputs(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as archive:
            member = tarfile.TarInfo("build.gradle")
            member.size = 6
            archive.addfile(member, io.BytesIO(b"source"))
        def response(url, **kwargs):
            return io.BytesIO(base64.b64encode(b"wrapper") if url.endswith("?format=TEXT") else data.getvalue())
        with tempfile.TemporaryDirectory() as directory, patch(
                "collect_androidx_build_inputs.urllib.request.urlopen", side_effect=response):
            report = collect(Path(directory) / "inputs")
            self.assertEqual(len(report["files"]), 7)
            self.assertFalse(report["completeCorrespondingSourcesVerified"])
            self.assertFalse(any(x["file"] == "graphics/androidx-settings-plugins.tar.gz"
                                 for x in report["files"]))

    def test_java_sources_reject_path_escape_and_empty_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jar = root / "sources.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("../escape.java", b"source")
            with self.assertRaises(ValueError):
                extract_sources(jar, root / "sources")
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("META-INF/MANIFEST.MF", b"metadata")
            with self.assertRaises(ValueError):
                extract_sources(jar, root / "sources")

    def test_native_sources_reject_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.tar.gz"
            with tarfile.open(source, "w:gz") as archive:
                member = tarfile.TarInfo("src/cpp/../../../escape.cc")
                member.size = 6
                archive.addfile(member, io.BytesIO(b"source"))
            with self.assertRaises(ValueError):
                extract_native(source, root / "sources")
            self.assertFalse((root / "escape.cc").exists())


if __name__ == "__main__":
    unittest.main()
