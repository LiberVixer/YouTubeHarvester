import io
import unittest
import zipfile

from collect_jvm_sources import artifact_url, licenses_from_pom, unique_artifacts, zip_evidence


class JvmSourceTests(unittest.TestCase):
    def test_identical_variants_deduplicated_conflicts_rejected(self):
        artifact = {"module": {"group": "g", "name": "a", "version": "1"},
                    "name": "a.jar", "sha256": "a"}
        self.assertEqual(unique_artifacts([artifact, dict(artifact)]), [artifact])
        with self.assertRaises(ValueError):
            unique_artifacts([artifact, dict(artifact, sha256="b")])

    def test_repository_and_coordinate_validation(self):
        module = {"group": "androidx.graphics", "name": "graphics-path", "version": "1.0.1"}
        self.assertEqual(artifact_url(module, "-sources.jar"),
                         "https://dl.google.com/dl/android/maven2/androidx/graphics/graphics-path/1.0.1/"
                         "graphics-path-1.0.1-sources.jar")
        module["name"] = "../../bad"
        with self.assertRaises(ValueError):
            artifact_url(module, ".pom")

    def test_native_source_not_confused_with_kotlin_source(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("android/Path.kt", "class Path")
            archive.writestr("native/path.cpp", "source")
            archive.writestr("META-INF/LICENSE.txt", "notice")
        evidence = zip_evidence(data.getvalue())
        self.assertEqual(evidence["nativeSources"], ["native/path.cpp"])
        self.assertEqual(evidence["noticeFiles"], ["META-INF/LICENSE.txt"])

    def test_pom_licenses(self):
        data = b'<project xmlns="http://maven.apache.org/POM/4.0.0"><licenses><license><name>Apache-2.0</name><url>https://www.apache.org/licenses/LICENSE-2.0.txt</url></license></licenses></project>'
        self.assertEqual(licenses_from_pom(data)[0]["name"], "Apache-2.0")
        self.assertEqual(licenses_from_pom(b'<project/>'), [])


if __name__ == "__main__":
    unittest.main()
