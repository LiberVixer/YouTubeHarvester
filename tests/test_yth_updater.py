from __future__ import annotations

import hashlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from yth_common import yt_dlp_command
from yth_updater import (
    YtDlpUpdateError,
    install_yt_dlp_release,
    managed_yt_dlp_path,
    release_asset_name,
)


class FakeResponse(io.BytesIO):
    def getcode(self):
        return 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class YtDlpUpdaterTests(unittest.TestCase):
    def test_platform_asset_names(self):
        self.assertEqual(release_asset_name("Windows"), "yt-dlp.exe")
        self.assertEqual(release_asset_name("Linux"), "yt-dlp")

    def test_managed_path_override_is_preferred(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            managed = Path(temp_dir) / "yt-dlp"
            managed.write_text("test", encoding="utf-8")
            environment = {
                "YTD_MANAGED_YT_DLP_PATH": str(managed),
                "YTD_YT_DLP_COMMAND": "",
                "YTD_YT_DLP_COMMAND_JSON": "",
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                self.assertEqual(managed_yt_dlp_path(), managed)
                self.assertEqual(yt_dlp_command(), [str(managed)])

    @unittest.skipIf(os.name == "nt", "the fixture is a POSIX executable")
    def test_verified_download_is_installed_atomically(self):
        binary = b"#!/usr/bin/env python3\nprint('2026.07.04')\n"
        release = {
            "version": "2026.07.04",
            "url": "https://example.invalid/yt-dlp",
            "sha256": hashlib.sha256(binary).hexdigest(),
            "size": len(binary),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "yt-dlp"
            with mock.patch(
                "yth_updater.urllib.request.urlopen", return_value=FakeResponse(binary)
            ):
                result = install_yt_dlp_release(
                    release, target=target, user_agent="test"
                )
            self.assertEqual(result["version"], "2026.07.04")
            self.assertEqual(
                subprocess.check_output([target, "--version"], text=True).strip(),
                "2026.07.04",
            )

    @unittest.skipIf(os.name == "nt", "the fixture is a POSIX executable")
    def test_failed_checksum_keeps_previous_version(self):
        binary = b"#!/usr/bin/env python3\nprint('2026.07.04')\n"
        release = {
            "version": "2026.07.04",
            "url": "https://example.invalid/yt-dlp",
            "sha256": "0" * 64,
            "size": len(binary),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "yt-dlp"
            target.write_bytes(b"previous version")
            with mock.patch(
                "yth_updater.urllib.request.urlopen", return_value=FakeResponse(binary)
            ):
                with self.assertRaises(YtDlpUpdateError):
                    install_yt_dlp_release(release, target=target, user_agent="test")
            self.assertEqual(target.read_bytes(), b"previous version")


if __name__ == "__main__":
    unittest.main()
