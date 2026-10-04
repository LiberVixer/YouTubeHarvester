import hashlib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from scripts.fetch_desktop_tools import fetch, sha256_file, unpack

try:
    from tray_launcher import TrayLauncher
except ImportError:
    TrayLauncher = None


class DesktopToolsTest(unittest.TestCase):
    def test_sha256_empty_and_multiple_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'archive'
            for content in (b'', b'archive bytes' * 100000):
                with self.subTest(size=len(content)):
                    path.write_bytes(content)
                    self.assertEqual(sha256_file(path), hashlib.sha256(content).hexdigest())

    def test_extracts_only_selected_names_without_archive_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'tools.zip'
            output = root / 'out'
            output.mkdir()
            with zipfile.ZipFile(archive, 'w') as source:
                source.writestr('../../ffmpeg.exe', b'QA exe')
                source.writestr('../../unwanted', b'ignored')
            unpack(archive, output, ('ffmpeg.exe',))
            self.assertEqual(b'QA exe', (output / 'ffmpeg.exe').read_bytes())
            self.assertFalse((root / 'unwanted').exists())

    def test_duplicate_or_missing_executable_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'tools.zip'
            with zipfile.ZipFile(archive, 'w') as source:
                source.writestr('a/deno.exe', b'a')
                source.writestr('b/deno.exe', b'b')
            with self.assertRaises(ValueError):
                unpack(archive, root, ('deno.exe',))
            with self.assertRaises(ValueError):
                unpack(archive, root, ('absent',))

    def test_cached_hash_mismatch_cannot_publish_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = hashlib.sha256(b'expected').hexdigest()
            cache = root / 'cache'
            cache.mkdir()
            (cache / (digest + '.zip')).write_bytes(b'wrong')
            with patch('scripts.fetch_desktop_tools.TOOLS', {'windows': {'deno': ('https://example.org/a.zip', digest, ('deno.exe',))}}):
                with self.assertRaises(ValueError):
                    fetch('windows', root / 'output', cache)
            self.assertFalse((root / 'output/deno').exists())


@unittest.skipIf(TrayLauncher is None, 'PyQt5 desktop dependencies unavailable')
class DesktopToolDetectionTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.launcher = SimpleNamespace(app_dir=self.root, is_windows=False)
        self.env = patch.dict('os.environ', {'YTD_FFMPEG_DIR': '', 'YTD_DENO_PATH': ''})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.which = patch('tray_launcher.shutil.which', return_value=None)
        self.which.start()
        self.addCleanup(self.which.stop)

    def stage(self, folder, windows=False):
        ffmpeg = folder / 'ffmpeg'
        deno = folder / 'deno'
        ffmpeg.mkdir(parents=True)
        deno.mkdir(parents=True)
        suffix = '.exe' if windows else ''
        for name in ('ffmpeg', 'ffprobe'):
            (ffmpeg / (name + suffix)).touch()
        deno_path = deno / ('deno' + suffix)
        deno_path.touch()
        return ffmpeg, deno_path

    def test_managed_tools_selected_on_both_platforms(self):
        for platform in ('linux', 'windows'):
            with self.subTest(platform=platform):
                windows = platform == 'windows'
                self.launcher.is_windows = windows
                expected = self.stage(self.root / 'tools' / platform, windows)
                self.assertEqual(expected[0], TrayLauncher.detect_ffmpeg_dir(self.launcher))
                self.assertEqual(expected[1], TrayLauncher.detect_deno_path(self.launcher))

    def test_explicit_configuration_has_priority(self):
        self.stage(self.root / 'tools/linux')
        expected = self.stage(self.root / 'custom')
        with patch.dict('os.environ', {'YTD_FFMPEG_DIR': str(expected[0]), 'YTD_DENO_PATH': str(expected[1])}):
            self.assertEqual(expected[0], TrayLauncher.detect_ffmpeg_dir(self.launcher))
            self.assertEqual(expected[1], TrayLauncher.detect_deno_path(self.launcher))

    def test_incomplete_local_ffmpeg_pair_falls_back_to_path(self):
        local = self.root / 'tools/linux/ffmpeg'
        local.mkdir(parents=True)
        (local / 'ffmpeg').touch()
        expected = self.stage(self.root / 'system')
        paths = {'ffmpeg': expected[0] / 'ffmpeg', 'ffprobe': expected[0] / 'ffprobe', 'deno': expected[1]}
        with patch('tray_launcher.shutil.which', side_effect=lambda name: str(paths[name])):
            self.assertEqual(expected[0], TrayLauncher.detect_ffmpeg_dir(self.launcher))
            self.assertEqual(expected[1], TrayLauncher.detect_deno_path(self.launcher))
