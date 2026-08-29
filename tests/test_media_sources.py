import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.downloader import Downloader, MEDIA_FILE_RE
from scripts.migrate_archive_details import entry_from_file
from yth_common import (
    archive_entry_media_id,
    archive_entry_source,
    archive_entry_source_url,
    extract_media_id,
    looks_like_supported_media_url,
    media_key,
    normalize_media_source,
)


class MediaUrlTests(unittest.TestCase):
    def test_recognizes_supported_single_video_urls(self) -> None:
        urls = {
            "https://www.youtube.com/watch?v=05h8f6kX6g8": ("youtube", "05h8f6kX6g8"),
            "https://rutube.ru/video/3eac3b4561676c17df9132a9a1e62e3e/": (
                "rutube",
                "3eac3b4561676c17df9132a9a1e62e3e",
            ),
            "https://vk.com/video-77521_162222515": ("vk", "-77521_162222515"),
            "https://vk.com/clip-77521_162222515": ("vk", "-77521_162222515"),
            "https://vk.com/video?z=video-77521_162222515%2Fclub77521": (
                "vk",
                "-77521_162222515",
            ),
        }
        for url, (source, media_id) in urls.items():
            with self.subTest(url=url):
                self.assertTrue(looks_like_supported_media_url(url))
                self.assertEqual(normalize_media_source("", url), source)
                self.assertEqual(extract_media_id(url), media_id)

    def test_rejects_channels_and_unrelated_pages(self) -> None:
        for url in (
            "https://www.youtube.com/@example/videos",
            "https://rutube.ru/channel/12345/videos/",
            "https://vk.com/video/@example",
            "https://example.com/video-77521_162222515",
        ):
            with self.subTest(url=url):
                self.assertFalse(looks_like_supported_media_url(url))

    def test_media_key_keeps_services_separate(self) -> None:
        overlapping_id = "12345_67890"
        self.assertNotEqual(
            media_key("youtube", overlapping_id),
            media_key("vk", overlapping_id),
        )


class ArchiveCompatibilityTests(unittest.TestCase):
    def test_old_detailed_entry_is_treated_as_youtube(self) -> None:
        entry = {"video_id": "05h8f6kX6g8", "youtube_url": "https://youtu.be/05h8f6kX6g8"}
        self.assertEqual(archive_entry_source(entry), "youtube")
        self.assertEqual(archive_entry_media_id(entry), "05h8f6kX6g8")
        self.assertEqual(
            archive_entry_source_url(entry),
            "https://youtu.be/05h8f6kX6g8",
        )

    def test_service_archive_lookup_uses_source_and_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = Downloader.__new__(Downloader)
            downloader.archive_file = Path(temp_dir) / "yt_archive.txt"
            downloader.archive_details_file = Path(temp_dir) / "archive_details.jsonl"
            downloader.archive_file.write_text("youtube 12345_67890\n", encoding="utf-8")

            self.assertTrue(downloader.archive_has_video("youtube", "12345_67890"))
            self.assertFalse(downloader.archive_has_video("vk", "12345_67890"))

    def test_legacy_variant_remains_youtube_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media_file = root / "legacy.mp4"
            media_file.write_bytes(b"video")
            details_file = root / "archive_details.jsonl"
            details_file.write_text(
                json.dumps({
                    "video_id": "12345_67890",
                    "youtube_url": "https://www.youtube.com/watch?v=12345_67890",
                    "file_path": str(media_file),
                    "requested_resolution": "720",
                    "audio_tracks": [],
                    "subtitle_selections": [],
                }) + "\n",
                encoding="utf-8",
            )
            downloader = Downloader.__new__(Downloader)
            downloader.archive_details_file = details_file
            downloader.max_resolution = "720"
            downloader.audio_tracks = []
            downloader.subtitle_selections = []

            self.assertTrue(downloader.archive_details_has_variant("youtube", "12345_67890"))
            self.assertFalse(downloader.archive_details_has_variant("vk", "12345_67890"))

    def test_new_and_legacy_download_names_are_recognized(self) -> None:
        samples = {
            "Title - Channel [Youtube] [05h8f6kX6g8] [queue] [1080p].mp4": (
                "Youtube",
                "05h8f6kX6g8",
            ),
            "Title - Channel [Rutube] [3eac3b4561676c17df9132a9a1e62e3e] [queue] [720p].mp4": (
                "Rutube",
                "3eac3b4561676c17df9132a9a1e62e3e",
            ),
            "Title - Channel [VK] [-77521_162222515] [queue] [720p].mp4": (
                "VK",
                "-77521_162222515",
            ),
            "Title - Channel [05h8f6kX6g8] [videos] [1080p].mp4": (
                None,
                "05h8f6kX6g8",
            ),
        }
        for filename, (source, media_id) in samples.items():
            with self.subTest(filename=filename):
                match = MEDIA_FILE_RE.match(filename)
                self.assertIsNotNone(match)
                self.assertEqual(match.group("source"), source)
                self.assertEqual(match.group("video_id"), media_id)

    def test_source_marker_is_removed_from_final_filename(self) -> None:
        temporary_name = "Title - Channel [VK] [-77521_162222515] [queue] [720p].mp4"
        self.assertEqual(
            Downloader.final_basename_without_source(temporary_name),
            "Title - Channel [-77521_162222515] [queue] [720p].mp4",
        )

    def test_vk_file_is_moved_and_archived_with_its_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            temporary_dir = root / "temp"
            final_dir = root / "downloads"
            temporary_dir.mkdir()
            source_file = temporary_dir / "Title - Channel [VK] [-77521_162222515] [queue] [720p].mp4"
            source_file.write_bytes(b"video")

            downloader = Downloader.__new__(Downloader)
            downloader.temp_dir = temporary_dir
            downloader.final_dir = final_dir
            downloader.archive_file = root / "yt_archive.txt"
            downloader.archive_details_file = root / "archive_details.jsonl"
            downloader.last_download_file = root / "last_download.txt"
            downloader.max_resolution = "720"
            downloader.audio_tracks = []
            downloader.audio_format_id = ""
            downloader.audio_language = ""
            downloader.audio_track_name = ""
            downloader.subtitle_selections = []
            downloader.subtitle_selection = "none"
            downloader.telegram_enabled = False
            downloader.system_notifications_enabled = False
            downloader.new_count = 0
            downloader.failed_count = 0
            downloader.downloaded_counts = {"videos": 0, "shorts": 0, "streams": 0, "queue": 0}
            downloader.log = lambda _message: None
            downloader.write_status = lambda: None
            downloader.set_type_status = lambda _type_name, _status: None
            downloader.reset_progress = lambda: None
            downloader.find_status_thumbnail = lambda _path: ""
            downloader.check_stop = lambda: None

            lines = [f"[download] Destination: {source_file}"]
            with patch("scripts.downloader.time.sleep", return_value=None):
                processed = downloader.process_type_lines(
                    lines,
                    "https://vk.com/video-77521_162222515",
                    "Очередь",
                    "queue",
                )

            self.assertEqual(processed, 1)
            self.assertFalse(source_file.exists())
            final_file = final_dir / "Title - Channel [-77521_162222515] [queue] [720p].mp4"
            self.assertTrue(final_file.exists())
            self.assertEqual(downloader.archive_file.read_text(encoding="utf-8"), "vk -77521_162222515\n")
            entry = json.loads(downloader.archive_details_file.read_text(encoding="utf-8"))
            self.assertEqual(entry["source"], "vk")
            self.assertEqual(entry["media_id"], "-77521_162222515")
            self.assertEqual(entry["source_url"], "https://vk.com/video-77521_162222515")
            self.assertEqual(entry["youtube_url"], "")
            self.assertEqual(Path(entry["file_path"]), final_file)

    def test_migration_uses_service_archive_for_hidden_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Title - Channel [-77521_162222515] [queue] [720p].mp4"
            path.write_bytes(b"video")
            entry = entry_from_file(path, {"-77521_162222515": {"vk"}})
            self.assertIsNotNone(entry)
            self.assertEqual(entry["source"], "vk")

    def test_migration_does_not_guess_ambiguous_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Title - Channel [12345_67890] [queue] [720p].mp4"
            path.write_bytes(b"video")
            entry = entry_from_file(path, {"12345_67890": {"youtube", "vk"}})
            self.assertIsNone(entry)


if __name__ == "__main__":
    unittest.main()
