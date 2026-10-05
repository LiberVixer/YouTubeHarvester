import io
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from collect_jvm_build_inputs import collect, match_source_files, parent_coordinate, select_artifact, source_inputs


class JvmBuildInputTests(unittest.TestCase):
    def test_compose_producer_is_selected_by_group_not_first_name(self):
        wrong = {"binary": {"module": {"name": "ui-android", "group": "androidx.compose.ui"}}}
        correct = {"binary": {"module": {"name": "ui-android", "group": "org.jetbrains.compose.ui"}}}
        self.assertIs(select_artifact({"artifacts": [wrong, correct]}, "ui-android"), correct)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            select_artifact({"artifacts": [correct, correct]}, "ui-android")

    def test_resume_does_not_redownload_and_rechecks_source_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jvm, output, _ = self.make_reuse(root)
            resolution = [{"ref": "refs/tags/v1.0", "object": {"type": "commit", "sha": "1" * 40}}]
            tree_name = "example-" + "1" * 12 + ".tar.gz"
            (output / "example.tar.gz").rename(output / tree_name)
            previous = json.loads((output / "JVM-BUILD-INPUTS.json").read_text())
            previous["files"][0]["file"] = tree_name
            previous["projects"][0]["file"] = tree_name
            (output / "JVM-BUILD-INPUTS.json").write_text(json.dumps(previous))
            with patch("collect_jvm_build_inputs.PROJECTS", {"example": ("example/repo", "v1.0", "1.0")}), \
                    patch("collect_jvm_build_inputs.resolve_tag", return_value=("1" * 40, resolution)), \
                    patch("collect_jvm_build_inputs.download") as download:
                report = collect(jvm, output, Path("gh"), resume=True)
            download.assert_not_called()
            self.assertEqual(report["projects"][0]["sourceMatches"]["exactSourceMatches"], 1)
            self.assertNotIn("JVM-BUILD-INPUTS.json", [x["file"] for x in report["files"]])

    def make_reuse(self, root):
        jvm, reuse = root / "jvm", root / "reuse"
        jvm.mkdir()
        reuse.mkdir()
        module = {"group": "example", "name": "example", "version": "1.0"}
        source = jvm / "example-sources.jar"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("example/Test.kt", b"source")
        pom = jvm / "example.pom"
        pom.write_bytes(b'<project xmlns="http://maven.apache.org/POM/4.0.0"/>')
        downloads = [{"file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                     for p in (source, pom)]
        item = {"binary": {"module": module}, "downloads": downloads}
        (jvm / "JVM-SOURCE-INVENTORY.json").write_text(json.dumps({"artifacts": [item]}))
        tree = reuse / "example.tar.gz"
        with tarfile.open(tree, "w:gz") as archive:
            member = tarfile.TarInfo("repo/src/Test.kt")
            member.size = 6
            archive.addfile(member, io.BytesIO(b"source"))
        digest = hashlib.sha256(tree.read_bytes()).hexdigest()
        project = {"module": module, "repo": "example/repo", "tag": "v1.0", "commit": "1" * 40,
                   "url": "https://codeload.github.com/example/repo/tar.gz/" + "1" * 40,
                   "file": tree.name, "sha256": digest}
        report = {"projects": [project], "mavenParents": [],
                  "files": [{"file": tree.name, "sha256": digest, "bytes": tree.stat().st_size}]}
        (reuse / "JVM-BUILD-INPUTS.json").write_text(json.dumps(report))
        return jvm, reuse, item

    def test_reuse_checks_inputs_without_redownloading_or_approving(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jvm, reuse, _ = self.make_reuse(root)
            with patch("collect_jvm_build_inputs.PROJECTS", {"example": ("example/repo", "v1.0", "1.0")}), \
                    patch("collect_jvm_build_inputs.resolve_tag") as resolve, \
                    patch("collect_jvm_build_inputs.download") as download:
                report = collect(jvm, root / "out", Path("gh"), reuse)
            resolve.assert_not_called()
            download.assert_not_called()
            self.assertEqual(report["projects"][0]["sourceMatches"]["exactSourceMatches"], 1)
            self.assertIs(report["completeCorrespondingSourcesVerified"], False)

    def test_reuse_pin_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jvm, reuse, _ = self.make_reuse(root)
            with patch("collect_jvm_build_inputs.PROJECTS", {"example": ("other/repo", "v1.0", "1.0")}):
                with self.assertRaisesRegex(ValueError, "pin differs"):
                    collect(jvm, root / "out", Path("gh"), reuse)
            self.assertFalse((root / "out/JVM-BUILD-INPUTS.json").exists())

    def test_resume_rejects_a_moved_producing_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jvm, output, _ = self.make_reuse(root)
            with patch("collect_jvm_build_inputs.PROJECTS", {"example": ("example/repo", "v1.0", "1.0")}), \
                    patch("collect_jvm_build_inputs.resolve_tag", return_value=("2" * 40, [])):
                with self.assertRaisesRegex(ValueError, "tag changed"):
                    collect(jvm, output, Path("gh"), resume=True)

    def test_reuse_tree_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jvm, reuse, _ = self.make_reuse(root)
            (reuse / "example.tar.gz").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                collect(jvm, root / "out", Path("gh"), reuse)

    def test_maven_input_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jvm, _, item = self.make_reuse(root)
            (jvm / "example.pom").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "Maven input changed"):
                source_inputs(jvm, item)

    def test_maven_parent_coordinate_and_absence(self):
        pom = b'<project xmlns="http://maven.apache.org/POM/4.0.0"><parent><groupId>com.fasterxml.jackson</groupId><artifactId>jackson-base</artifactId><version>2.22.3</version></parent></project>'
        self.assertEqual(parent_coordinate(pom), ("com.fasterxml.jackson", "jackson-base", "2.22.3"))
        self.assertIsNone(parent_coordinate(b'<project xmlns="http://maven.apache.org/POM/4.0.0"/>'))

    def test_parent_variables_and_unsafe_coordinates_rejected(self):
        for version in ("\u0024{revision}", "../2.22.3"):
            pom = ('<project xmlns="http://maven.apache.org/POM/4.0.0"><parent><groupId>com.fasterxml.jackson</groupId><artifactId>jackson-base</artifactId><version>' + version + '</version></parent></project>').encode()
            with self.assertRaises(ValueError):
                parent_coordinate(pom)

    def test_exact_source_match_does_not_hide_generated_or_changed_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, tree = root / "sources.jar", root / "tree.tar.gz"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("commonMain/example/Test.kt", b"source")
                archive.writestr("example/Version.java", b"generated")
            with tarfile.open(tree, "w:gz") as archive:
                for name, data in (("repo/src/main/example/Test.kt", b"source"),
                                   ("repo/src/main/example/Version.java", b"template")):
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))
            report = match_source_files(source, tree)
            self.assertEqual(report["exactSourceMatches"], 1)
            self.assertEqual(report["unmatched"], ["example/Version.java"])


if __name__ == "__main__":
    unittest.main()
