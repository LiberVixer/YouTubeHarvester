import unittest

from verify_jvm_generated_sources import render_template


class GeneratedSourceTests(unittest.TestCase):
    def test_jackson_template_substitutions(self):
        source, values = render_template("com/fasterxml/jackson/core/json/PackageVersion.java",
            {"name": "jackson-core", "group": "com.fasterxml.jackson.core", "version": "2.22.3"},
            b"package @package@; @projectversion@ @projectgroupid@ @projectartifactid@")
        self.assertEqual(source,
            b"package com.fasterxml.jackson.core.json; 2.22.3 com.fasterxml.jackson.core jackson-core")
        self.assertEqual(len(values), 4)

    def test_okhttp_version_template(self):
        source, _ = render_template("okhttp3/OkHttp.kt",
            {"name": "okhttp", "version": "4.12.0"}, b'const val VERSION = "$projectVersion"')
        self.assertEqual(source, b'const val VERSION = "4.12.0"')

    def test_unknown_source_is_not_assumed_generated(self):
        with self.assertRaises(ValueError):
            render_template("okhttp3/Changed.kt", {"name": "okhttp", "version": "4.12.0"}, b"code")

    def test_missing_or_duplicate_tokens_rejected(self):
        for template in (b"no variable", b"$projectVersion $projectVersion"):
            with self.assertRaises(ValueError):
                render_template("okhttp3/OkHttp.kt", {"name": "okhttp", "version": "4.12.0"}, template)


if __name__ == "__main__":
    unittest.main()
