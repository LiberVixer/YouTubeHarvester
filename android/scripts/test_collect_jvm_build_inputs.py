import io
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

from collect_jvm_build_inputs import match_source_files, parent_coordinate


class JvmBuildInputTests(unittest.TestCase):
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
