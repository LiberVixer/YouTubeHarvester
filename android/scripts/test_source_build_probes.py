import base64
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from collect_androidx_build_inputs import collect, collect_release_inputs, download
from probe_androidx_native_sources import extract_native
from probe_protobuf_sources import extract_sources


class BuildInputTests(unittest.TestCase):
    def test_release_build_inputs_resume_checks_inventory_and_cached_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "sources"
            sources.mkdir()
            (sources / "ANDROIDX-RELEASE-SOURCES.json").write_text(json.dumps({
                "files": [], "artifacts": [{"commit": "a" * 40}]}))
            entries = {"entries": [{"name": "buildSrc", "type": "tree"},
                                   {"name": "inspection", "type": "tree"},
                                   {"name": "lint-checks", "type": "tree"},
                                   {"name": "root-helper.groovy", "type": "blob"},
                                   {"name": "settings.gradle", "type": "blob"},
                                   {"name": "LICENSE.txt", "type": "blob"}]}

            def save(url, target, encoded=False):
                if encoded:
                    target.write_bytes(b"root script")
                else:
                    with tarfile.open(target, "w:gz") as archive:
                        member = tarfile.TarInfo("build.gradle")
                        member.size = 6
                        archive.addfile(member, io.BytesIO(b"source"))

            output = root / "out"
            with patch("collect_androidx_release_sources.gitiles_json", return_value=entries), \
                    patch("collect_androidx_build_inputs.download", side_effect=save):
                first = collect_release_inputs(output, sources)
            self.assertEqual(len(first["files"]), 7)
            self.assertIn("lint-checks", first["snapshots"][0]["retainedRootEntries"])
            self.assertIn("root-helper.groovy", first["snapshots"][0]["retainedRootEntries"])
            self.assertFalse(first["completeCorrespondingSourcesVerified"])
            with patch("collect_androidx_release_sources.gitiles_json") as network, \
                    patch("collect_androidx_build_inputs.download") as download:
                second = collect_release_inputs(output, sources, resume=True)
            network.assert_not_called()
            download.assert_not_called()
            self.assertEqual(first, second)
            (output / ("a" * 40) / "settings.gradle").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                collect_release_inputs(output, sources, resume=True)

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
