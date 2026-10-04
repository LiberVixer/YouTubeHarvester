import io
import tarfile
import unittest

from capture_readme_screenshots import LANGUAGES, SCREENS, read_images


class ScreenshotArchiveTest(unittest.TestCase):
    def archive(self, extra=None, omit=None):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as target:
            for language in LANGUAGES:
                for screen in SCREENS:
                    name = f'readme-screenshots/{language}/{screen}.png'
                    if name == omit:
                        continue
                    payload = b'demonstration screenshot'
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    target.addfile(info, io.BytesIO(payload))
            if extra:
                target.addfile(extra)
        return buffer.getvalue()

    def test_accepts_exactly_five_screens_in_ten_languages(self):
        result = read_images(self.archive())
        self.assertEqual(50, len(result))
        self.assertIn('ar/settings.png', result)

    def test_refuses_incomplete_capture(self):
        with self.assertRaises(ValueError):
            read_images(self.archive(omit='readme-screenshots/ru/channels.png'))

    def test_refuses_traversal_and_duplicate_files(self):
        for name in ('../../outside.png', 'readme-screenshots/en/overview.png'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                read_images(self.archive(extra=tarfile.TarInfo(name)))

    def test_refuses_symlinks(self):
        link = tarfile.TarInfo('readme-screenshots/en/other.png')
        link.type = tarfile.SYMTYPE
        link.linkname = '/etc/passwd'
        with self.assertRaises(ValueError):
            read_images(self.archive(extra=link))


if __name__ == '__main__':
    unittest.main()
