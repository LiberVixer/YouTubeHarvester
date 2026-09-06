import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from i18n_locales import LOCALE_CHANNEL_SOURCE_TRANSLATIONS
from scripts.check_channel_sections import check_paid_content, check_section
from scripts.downloader import Downloader
from scripts.mark_channel_archived import append_archive, collect_ids, read_archive
from yth_common import (
    channel_section_url,
    channel_sections,
    channel_supports_paid_check,
    normalize_channel_url,
    rutube_channel_metadata,
)


RUTUBE = "https://rutube.ru/channel/23704195"
YOUTUBE = "https://www.youtube.com/@example"
VIDEO_ID = "d4f6c71ef692390960e4a3953fdc5be2"


class ChannelUrlTests(unittest.TestCase):
    def test_normalizes_roots_tabs_and_tracking_parameters(self):
        cases = {
            " https://rutube.ru/channel/23704195/videos/?a=1#top ": RUTUBE,
            "http://www.rutube.ru/channel/023704195/shorts/": RUTUBE,
            "https://rutube.ru/u/rutube/videos/": "https://rutube.ru/u/rutube",
            "https://youtube.com/@example/streams?si=abc": YOUTUBE,
            "https://m.youtube.com/@example/shorts": YOUTUBE,
            "https://www.youtube.com/channel/UCexample/videos": "https://www.youtube.com/channel/UCexample",
            "https://youtube.com/user/example/featured": "https://www.youtube.com/user/example",
            "https://youtube.com/c/example/about": "https://www.youtube.com/c/example",
            "https://youtube.com/@%D0%A2%D0%B5%D1%81%D1%82/videos": "https://www.youtube.com/@%D0%A2%D0%B5%D1%81%D1%82",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_channel_url(value), expected)

    def test_rejects_non_channels_and_host_spoofing(self):
        for url in (
            f"https://rutube.ru/video/{VIDEO_ID}/", "https://rutube.ru/plst/1/",
            "https://rutube.ru/channel/1/playlists/", "https://rutube.ru/channel/1/streams/",
            "https://rutube.ru/channel/no/", "https://rutube.ru/u/", "https://rutube.ru/channel/1/unknown",
            "https://youtube.com/watch?v=05h8f6kX6g8", "https://youtube.com/playlist?list=123",
            "https://youtube.com/@example/videos/extra", "https://vk.com/channel/1",
            "https://rutube.ru.evil.test/channel/1", "https://evil.test/@example",
            "https://rutube.ru@evil.test/channel/1", "https://@rutube.ru/channel/1",
            "https://user:pass@rutube.ru/channel/1", "https://rutube.ru:8443/channel/1",
            "https://rutube.ru/channel/\n1", "https://youtube.com/@a%2Fvideos",
            "file://rutube.ru/channel/1", "--exec=bad",
        ):
            with self.subTest(url=url):
                self.assertEqual(normalize_channel_url(url), "")

    def test_capabilities_and_section_urls_are_source_specific(self):
        self.assertEqual(channel_sections(RUTUBE), ("videos", "shorts"))
        self.assertEqual(channel_sections(YOUTUBE), ("videos", "shorts", "streams"))
        self.assertEqual(channel_sections("https://example.com"), ())
        self.assertEqual(channel_section_url(RUTUBE + "/shorts/", "videos"), RUTUBE + "/videos")
        self.assertEqual(channel_section_url(RUTUBE, "streams"), "")
        self.assertTrue(channel_supports_paid_check(YOUTUBE))
        self.assertFalse(channel_supports_paid_check(RUTUBE))


class RutubeMetadataTests(unittest.TestCase):
    def result(self, entries=None, channel_id="23704195"):
        data = {"id": channel_id, "entries": entries or []}
        return subprocess.CompletedProcess([], 0, json.dumps(data), "")

    @patch("yth_common.urllib.request.urlopen")
    @patch("yth_common.subprocess.run")
    def test_resolves_alias_and_reads_channel_avatar_not_video_thumbnail(self, run, urlopen):
        run.return_value = self.result([{"uploader": "RUTUBE", "thumbnail": "https://example.com/video.jpg"}])
        avatar = "https://pic.rtbcdn.ru/user/avatar.jpeg"
        urlopen.return_value = io.BytesIO(json.dumps({"results": [
            {"author": {"id": 23704195, "name": "RUTUBE", "avatar_url": avatar}},
        ]}).encode())
        result = rutube_channel_metadata("https://rutube.ru/u/rutube/shorts/", ["yt-dlp"])
        self.assertEqual(result, {"channel": RUTUBE, "title": "RUTUBE", "thumbnail_url": avatar})
        command = run.call_args.args[0]
        self.assertEqual(command[-1], "https://rutube.ru/u/rutube")
        self.assertIn("--flat-playlist", command)
        self.assertIn("--skip-download", command)
        self.assertEqual(command[command.index("--playlist-items") + 1], "1")

    @patch("yth_common.urllib.request.urlopen", side_effect=OSError("offline"))
    @patch("yth_common.subprocess.run")
    def test_missing_avatar_or_empty_channel_is_not_a_failure(self, run, urlopen):
        run.return_value = self.result()
        result = rutube_channel_metadata(RUTUBE, ["yt-dlp"])
        self.assertEqual(result["channel"], RUTUBE)
        self.assertEqual(result["title"], "Rutube 23704195")
        self.assertEqual(result["thumbnail_url"], "")

    @patch("yth_common.urllib.request.urlopen")
    @patch("yth_common.subprocess.run")
    def test_rejects_untrusted_avatar_host(self, run, urlopen):
        run.return_value = self.result()
        urlopen.return_value = io.BytesIO(json.dumps({"results": [{"author": {
            "id": 23704195, "avatar_url": "https://rtbcdn.ru.evil.test/avatar.png",
        }}]}).encode())
        self.assertEqual(rutube_channel_metadata(RUTUBE, ["yt-dlp"])["thumbnail_url"], "")

    @patch("yth_common.urllib.request.urlopen")
    @patch("yth_common.subprocess.run")
    def test_rejects_failed_or_invalid_playlist_before_author_request(self, run, urlopen):
        for result in (self.result(channel_id="../../etc"), subprocess.CompletedProcess([], 1, "", "offline")):
            run.return_value = result
            with self.assertRaises(ValueError):
                rutube_channel_metadata(RUTUBE, ["yt-dlp"])
        urlopen.assert_not_called()


class ChannelProbeTests(unittest.TestCase):
    @patch("scripts.check_channel_sections.subprocess.run")
    def test_no_network_for_unsupported_streams_and_paid_checks(self, run):
        self.assertEqual(check_section(["yt-dlp"], RUTUBE, "streams", 5)["status"], "unsupported")
        self.assertEqual(check_paid_content(["yt-dlp"], RUTUBE, {}, 5), "unknown")
        run.assert_not_called()

    @patch("scripts.check_channel_sections.subprocess.run")
    def test_supported_section_uses_normalized_url(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, VIDEO_ID, "")
        self.assertEqual(check_section(["yt-dlp"], RUTUBE + "/videos/", "shorts", 5)["status"], "available")
        self.assertEqual(run.call_args.args[0][-1], RUTUBE + "/shorts")

    @patch("scripts.check_channel_sections.subprocess.run")
    def test_youtube_members_only_check_still_stops_at_first_hit(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "Join this channel: members-only")
        self.assertEqual(check_paid_content(["yt-dlp"], YOUTUBE, {}, 5), "has_paid")
        self.assertEqual(run.call_count, 1)


class ChannelArchiveTests(unittest.TestCase):
    def test_append_preserves_archive_without_final_newline(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "archive.txt"
            archive.write_text("youtube 05h8f6kX6g8", encoding="utf-8")
            lines, keys = read_archive(archive)
            append_archive(archive, [VIDEO_ID], lines, keys, "rutube")
            self.assertEqual(archive.read_text(), f"youtube 05h8f6kX6g8\nrutube {VIDEO_ID}\n")

    @patch("scripts.mark_channel_archived.subprocess.run")
    def test_collects_rutube_ids_and_skips_unsupported_sections(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, f"{VIDEO_ID}\n05h8f6kX6g8\n{VIDEO_ID}\n", "")
        self.assertEqual(collect_ids(["yt-dlp"], RUTUBE, "videos", 3), ([VIDEO_ID], ""))
        self.assertEqual(collect_ids(["yt-dlp"], RUTUBE, "streams", 3), ([], ""))
        self.assertEqual(run.call_count, 1)

    @patch("scripts.mark_channel_archived.subprocess.run")
    def test_youtube_id_validation_is_unchanged(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, f"05h8f6kX6g8\n{VIDEO_ID}\n", "")
        self.assertEqual(collect_ids(["yt-dlp"], YOUTUBE, "videos", 3), (["05h8f6kX6g8"], ""))

    def test_archive_keys_include_source_and_preserve_old_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "archive.txt"
            old = f"youtube 05h8f6kX6g8\nyoutube {VIDEO_ID}\n"
            archive.write_text(old, encoding="utf-8-sig")
            lines, keys = read_archive(archive)
            self.assertEqual(append_archive(archive, [VIDEO_ID], lines, keys, "rutube"), 1)
            self.assertEqual(append_archive(archive, [VIDEO_ID], lines, keys, "rutube"), 0)
            self.assertEqual(append_archive(archive, ["05h8f6kX6g8"], lines, keys), 0)
            self.assertEqual(archive.read_text(encoding="utf-8-sig"), old + f"rutube {VIDEO_ID}\n")


class ChannelDownloaderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        environment = {
            "YTD_APP_DIR": str(root), "YTD_DATA_DIR": str(root), "YTD_CONFIG_DIR": str(root),
            "YTD_TEMP_DIR": str(root / "temp"), "YTD_FINAL_DIR": str(root / "final"),
            "YTD_TELEGRAM_ENABLED": "0", "YTD_SYSTEM_NOTIFICATIONS_ENABLED": "0",
            "YTD_VIDEOS_LIMIT": "2", "YTD_SHORTS_LIMIT": "3", "YTD_STREAMS_LIMIT": "4",
        }
        env = patch.dict(os.environ, environment, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.downloader = Downloader()
        self.downloader.log = Mock()
        self.downloader.temp_dir.mkdir()

    @patch("scripts.downloader.Path.home", side_effect=RuntimeError("Could not determine home directory."))
    def test_explicit_download_directories_do_not_require_home(self, home):
        downloader = Downloader()
        self.assertEqual(downloader.temp_dir, self.downloader.temp_dir)
        self.assertEqual(downloader.final_dir, self.downloader.final_dir)
        home.assert_not_called()

    def test_default_download_directories_use_home(self):
        root = Path(self.directory.name)
        with patch.dict(os.environ, {"YTD_TEMP_DIR": "", "YTD_FINAL_DIR": ""}):
            with patch("scripts.downloader.Path.home", return_value=root):
                downloader = Downloader()
        self.assertEqual(downloader.temp_dir, root / "temp" / "YTH")
        self.assertEqual(downloader.final_dir, root / "Downloads" / "YouTubeHarvester")

    @patch("scripts.downloader.time.sleep")
    def test_scanning_obeys_supported_types_limits_and_legacy_rules(self, sleep):
        d = self.downloader
        legacy_youtube = "https://youtube.com/@example"
        d.channels_file.write_text(f"{RUTUBE}\n{legacy_youtube}\n", encoding="utf-8-sig")
        d.channel_rules_file.write_text(json.dumps({legacy_youtube + "/": {"shorts": False}}), encoding="utf-8")
        d.run_yt_dlp = Mock(return_value=[])
        d.process_channels()
        commands = [call.args[0] for call in d.run_yt_dlp.call_args_list]
        self.assertEqual([cmd[-1] for cmd in commands], [
            RUTUBE + "/videos", RUTUBE + "/shorts", YOUTUBE + "/videos", YOUTUBE + "/streams",
        ])
        self.assertEqual([cmd[cmd.index("--playlist-items") + 1] for cmd in commands], ["1-2", "1-3", "1-2", "1-4"])
        self.assertEqual(sleep.call_count, 4)
        self.assertEqual(d.channels_checked, 2)
        self.assertEqual(d.channel_url, legacy_youtube)

    @patch("scripts.downloader.time.sleep")
    def test_no_scan_or_pause_for_disabled_rutube_sections(self, sleep):
        d = self.downloader
        d.channels_file.write_text(RUTUBE + "\n", encoding="utf-8")
        d.channel_rules_file.write_text(json.dumps({RUTUBE: {"videos": False, "shorts": False, "streams": True}}))
        d.run_yt_dlp = Mock(return_value=[])
        d.process_channels()
        d.run_yt_dlp.assert_not_called()
        sleep.assert_not_called()
        self.assertEqual(d.type_status, {"videos": "disabled", "shorts": "disabled", "streams": "disabled"})

    def test_rutube_does_not_get_youtube_paid_status(self):
        d = self.downloader
        d.set_channel_paid_content_status(RUTUBE, "has_paid")
        self.assertFalse(d.channel_rules_file.exists())
        d.set_channel_paid_content_status(YOUTUBE, "has_paid")
        self.assertEqual(json.loads(d.channel_rules_file.read_text())[YOUTUBE]["paid_content_status"], "has_paid")

    @patch("scripts.downloader.time.sleep")
    def test_completed_rutube_short_is_moved_and_archived_with_source_and_channel(self, sleep):
        d = self.downloader
        video = d.temp_dir / f"Clip - RUTUBE [Rutube] [{VIDEO_ID}] [shorts] [720p].mp4"
        video.write_bytes(b"completed-test-video")
        processed = d.process_type_lines([f"[download] Destination: {video}"], RUTUBE, "RUTUBE", "shorts")
        self.assertEqual(processed, 1)
        self.assertFalse(video.exists())
        entry = json.loads(d.archive_details_file.read_text(encoding="utf-8"))
        self.assertEqual(entry["source"], "rutube")
        self.assertEqual(entry["type"], "shorts")
        self.assertEqual(entry["channel_url"], RUTUBE)
        self.assertEqual(entry["source_url"], f"https://rutube.ru/video/{VIDEO_ID}/")
        self.assertTrue(Path(entry["file_path"]).is_file())
        self.assertTrue(d.archive_has_video("rutube", VIDEO_ID))
        self.assertFalse(d.archive_has_video("youtube", VIDEO_ID))


class ChannelTranslationTests(unittest.TestCase):
    def test_new_channel_strings_cover_all_ten_languages(self):
        translations = LOCALE_CHANNEL_SOURCE_TRANSLATIONS
        self.assertEqual(set(translations), {"en", "ru", "uk", "be", "fr", "es", "hi", "zh", "ja", "ar"})
        for language, strings in translations.items():
            with self.subTest(language=language):
                self.assertEqual(strings.keys(), translations["en"].keys())
                self.assertTrue(all(value.strip() for value in strings.values()))


if __name__ == "__main__":
    unittest.main()
