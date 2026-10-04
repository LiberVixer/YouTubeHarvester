import argparse
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.generate_readme_screenshots import prepare_fixture


class ReadmeFixtureTest(unittest.TestCase):
    def test_capture_isolates_cache_and_uses_current_version_and_channel_count(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ):
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            (source / 'tray_launcher.py').write_text('APP_VERSION = "1.2.1"\n')
            channels = root / 'channels.txt'
            channels.write_text('# comment\nhttps://www.youtube.com/@first\n\nhttps://www.youtube.com/@second\n')
            cache = root / 'original-cache'
            (cache / 'channels').mkdir(parents=True)
            (cache / 'channels/sample.json').write_text('{"name":"sample"}')
            args = argparse.Namespace(channels=channels, channel_rules=root / 'absent.json', channel_cache=cache)
            data, config = prepare_fixture(root / 'fixture', source, args)
            status = json.loads((data / 'status.json').read_text())
            self.assertEqual(2, status['channels_total'])
            self.assertEqual(2, status['last_run_channels_checked'])
            self.assertIn('YouTube Harvester 1.2.1', (data / 'download.log').read_text())
            self.assertNotIn('Beta', (data / 'download.log').read_text())
            self.assertEqual('dark', json.loads((config / 'settings.json').read_text())['theme'])
            captured_cache = Path(os.environ['YTD_CACHE_DIR'])
            self.assertNotEqual(cache, captured_cache)
            self.assertEqual((cache / 'channels/sample.json').read_bytes(),
                             (captured_cache / 'channels/sample.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
