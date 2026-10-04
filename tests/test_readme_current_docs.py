from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("en", "ru", "uk", "be", "fr", "es", "hi", "zh", "ja", "ar")


class LocalReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"href", "src"} and value:
                self.references.add(value)


class CurrentReadmeTests(unittest.TestCase):
    def readmes(self):
        for language in LANGUAGES:
            name = "README.md" if language == "en" else f"README.{language}.md"
            yield language, (ROOT / name).read_text(encoding="utf-8")

    def test_all_languages_document_current_platforms_and_release_limits(self):
        required = (
            "versionCode 120100", "API 26", "-debug", "GPL-3.0-only",
            "arm64-v8a", "armeabi-v7a", "x86_64", "x86", ".ythbackup",
            "VK", "Rutube", "WorkManager", "MediaStore/SAF", "TalkBack",
            "SHA-256", "2026-10-04", "2026.08.19", "9.0.2", "2.9.7",
            "android/RELEASE-READINESS.ru.md", "android/DATA-TRANSFER.ru.md",
            "android/legal/README.md", "docs/screenshots/README.md",
            "YouTubeHarvester_1.2.1_linux_all.deb",
            "YouTubeHarvester_1.2.1_windows_x64.msi",
            "YouTubeHarvester-1.2.1-<ABI>.apk", "cp -n .env.example .env",
        )
        for language, text in self.readmes():
            with self.subTest(language=language):
                self.assertEqual("# YouTube Harvester 1.2.1", text.splitlines()[0])
                self.assertNotIn("UPD", text)
                self.assertNotIn("1.1.3", text)
                self.assertEqual(19, len(re.findall(r"^## ", text, re.MULTILINE)))
                for token in required:
                    self.assertIn(token, text)
                android_section = text.split("\n## Android\n", 1)[1].split("\n## ", 1)[0]
                self.assertIn("VK", android_section)
                self.assertIn("2026-09-14", android_section)
                if language == "ar":
                    self.assertIn('dir="rtl"', text)

    def test_all_local_links_and_images_resolve(self):
        for language, text in self.readmes():
            parser = LocalReferences()
            parser.feed(text)
            references = parser.references | set(re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text))
            for reference in references:
                url = urlsplit(reference)
                if url.scheme or url.netloc or not url.path:
                    continue
                with self.subTest(language=language, reference=reference):
                    self.assertTrue((ROOT / unquote(url.path)).is_file())


if __name__ == "__main__":
    unittest.main()
