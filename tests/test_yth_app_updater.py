from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from yth_app_updater import (
    AppUpdateError,
    download_app_release,
    installation_kind,
    latest_app_release,
    version_key,
)


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes, status: int = 200):
        super().__init__(payload)
        self.status = status

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class AppUpdaterTests(unittest.TestCase):
    def test_version_key_orders_stable_and_prerelease_versions(self):
        self.assertEqual(version_key("v1.2.0"), (1, 2, 0, 3, 0))
        self.assertEqual(version_key("1.2.0-beta"), (1, 2, 0, 1, 0))
        self.assertEqual(version_key("1.2.0-beta.2"), (1, 2, 0, 1, 2))
        self.assertGreater(version_key("1.2.0-beta"), version_key("1.1.3"))
        self.assertGreater(version_key("1.2.0"), version_key("1.2.0-beta"))
        self.assertEqual(version_key("1.2"), ())

    def test_installation_kind_distinguishes_packages(self):
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}):
            self.assertEqual(
                installation_kind(
                    system="Windows",
                    frozen=True,
                    executable_path=r"C:\Users\Test\AppData\Local\Programs\YouTube Harvester\YouTubeHarvester.exe",
                ),
                "windows_setup",
            )
        with mock.patch.dict(os.environ, {"PROGRAMFILES": r"C:\Program Files"}):
            self.assertEqual(
                installation_kind(
                    system="Windows",
                    frozen=True,
                    executable_path=r"C:\Program Files\YouTube Harvester\YouTubeHarvester.exe",
                ),
                "windows_msi",
            )
            self.assertEqual(
                installation_kind(system="Windows", frozen=True, executable_path=r"D:\Portable\YouTubeHarvester.exe"),
                "windows_portable",
            )
        self.assertEqual(
            installation_kind(system="Windows", frozen=False, executable_path=r"C:\Source\YouTubeHarvester\python.exe"),
            "source",
        )
        self.assertEqual(installation_kind(system="Linux", app_dir="/opt/yt-harvester"), "linux_deb")
        self.assertEqual(installation_kind(system="Linux", app_dir="/home/test/YTD"), "source")

    def test_latest_release_selects_asset_and_checksum(self):
        version = "1.1.3"
        asset_name = f"YouTubeHarvester_{version}_windows_setup.exe"
        binary = b"verified setup"
        digest = hashlib.sha256(binary).hexdigest()
        metadata = {
            "tag_name": f"v{version}",
            "draft": False,
            "prerelease": False,
            "html_url": f"https://github.com/LiberVixer/YouTubeHarvester/releases/tag/v{version}",
            "published_at": "2026-08-20T00:00:00Z",
            "assets": [
                {
                    "name": asset_name,
                    "size": len(binary),
                    "digest": f"sha256:{digest}",
                    "browser_download_url": (
                        f"https://github.com/LiberVixer/YouTubeHarvester/releases/download/v{version}/{asset_name}"
                    ),
                },
                {
                    "name": "SHA256SUMS-windows.txt",
                    "browser_download_url": (
                        f"https://github.com/LiberVixer/YouTubeHarvester/releases/download/v{version}/"
                        "SHA256SUMS-windows.txt"
                    ),
                },
            ],
        }
        checksum = f"{digest}  {asset_name}\n".encode()
        responses = [FakeResponse(json.dumps(metadata).encode()), FakeResponse(checksum)]
        with mock.patch("yth_app_updater.urllib.request.urlopen", side_effect=responses):
            release = latest_app_release(
                current_version="1.1.2",
                user_agent="test",
                kind="windows_setup",
            )
        self.assertTrue(release["update_available"])
        self.assertEqual(release["sha256"], digest)
        self.assertEqual(release["action"], "installer")

    def test_download_is_verified_before_atomic_install(self):
        binary = b"release package"
        digest = hashlib.sha256(binary).hexdigest()
        release = {
            "asset_name": "YouTubeHarvester_1.1.3_linux_all.deb",
            "url": (
                "https://github.com/LiberVixer/YouTubeHarvester/releases/download/v1.1.3/"
                "YouTubeHarvester_1.1.3_linux_all.deb"
            ),
            "sha256": digest,
            "size": len(binary),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch(
                "yth_app_updater.urllib.request.urlopen",
                return_value=FakeResponse(binary),
            ):
                result = download_app_release(
                    release,
                    target_dir=Path(temp_dir),
                    user_agent="test",
                )
            target = Path(result["path"])
            self.assertEqual(target.read_bytes(), binary)
            self.assertFalse((target.parent / f".{target.name}.part").exists())

    def test_bad_checksum_is_not_published(self):
        binary = b"tampered package"
        release = {
            "asset_name": "YouTubeHarvester_1.1.3_source.tar.gz",
            "url": (
                "https://github.com/LiberVixer/YouTubeHarvester/releases/download/v1.1.3/"
                "YouTubeHarvester_1.1.3_source.tar.gz"
            ),
            "sha256": "0" * 64,
            "size": len(binary),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / release["asset_name"]
            with mock.patch(
                "yth_app_updater.urllib.request.urlopen",
                return_value=FakeResponse(binary),
            ):
                with self.assertRaises(AppUpdateError):
                    download_app_release(
                        release,
                        target_dir=Path(temp_dir),
                        user_agent="test",
                    )
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
