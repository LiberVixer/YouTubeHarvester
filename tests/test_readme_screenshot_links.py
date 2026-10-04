import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import struct
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "docs/screenshots"
LANGUAGES = ("en", "ru", "uk", "be", "fr", "es", "hi", "zh", "ja", "ar")
DESKTOP_VIEWS = ("overview", "channels", "queue", "settings")
ANDROID_VIEWS = (*DESKTOP_VIEWS, "archive")


class ImageSources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = set()

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            source = dict(attrs).get("src")
            if source:
                self.sources.add(source)


class ReadmeScreenshotTests(unittest.TestCase):
    def test_manifest_covers_complete_verified_png_set(self):
        manifest = json.loads((SCREENSHOTS / "manifest.json").read_text())
        expected = {f"{lang}/{view}.png" for lang in LANGUAGES for view in DESKTOP_VIEWS}
        expected.update(f"android/{lang}/{view}.png" for lang in LANGUAGES for view in ANDROID_VIEWS)
        self.assertEqual(expected, set(manifest["images"]))
        self.assertEqual("dark", manifest["theme"])
        self.assertTrue(manifest["demoData"])
        for name, metadata in manifest["images"].items():
            with self.subTest(image=name):
                content = (SCREENSHOTS / name).read_bytes()
                self.assertEqual(b"\x89PNG\r\n\x1a\n", content[:8])
                self.assertEqual(b"IHDR", content[12:16])
                dimensions = struct.unpack(">II", content[16:24])
                self.assertEqual((metadata["width"], metadata["height"]), dimensions)
                self.assertEqual(metadata["sha256"], hashlib.sha256(content).hexdigest())

    def test_android_capture_matches_catalog(self):
        capture = json.loads((SCREENSHOTS / "android/capture.json").read_text())
        manifest = json.loads((SCREENSHOTS / "manifest.json").read_text())
        self.assertEqual("com.liberivixer.youtubeharvester.screenshots", capture["package"])
        self.assertEqual(manifest["version"], capture["version"])
        self.assertEqual("dark", capture["theme"])
        self.assertTrue(capture["fixtureData"])
        expected = {name.removeprefix("android/"): metadata["sha256"]
                    for name, metadata in manifest["images"].items() if name.startswith("android/")}
        self.assertEqual(expected, capture["images"])

    def test_all_readme_galleries_use_matching_language_and_existing_images(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                filename = "README.md" if language == "en" else f"README.{language}.md"
                text = (ROOT / filename).read_text(encoding="utf-8")
                parser = ImageSources()
                parser.feed(text)
                sources = parser.sources | set(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text))
                actual = {source for source in sources if source.startswith("docs/screenshots/")}
                expected = {f"docs/screenshots/{language}/{view}.png" for view in DESKTOP_VIEWS}
                expected.update(f"docs/screenshots/android/{language}/{view}.png" for view in ANDROID_VIEWS)
                self.assertEqual(expected, actual)
                for source in actual:
                    self.assertTrue((ROOT / source).is_file(), source)


if __name__ == "__main__":
    unittest.main()
