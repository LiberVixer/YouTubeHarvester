import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.downloader import Downloader, YoutubeAccessBlocked


class YoutubePlayerClientCommandTests(unittest.TestCase):
    def test_adds_fallback_client_before_url(self) -> None:
        command = ["yt-dlp", "-f", "399+140", "https://youtu.be/example"]

        updated = Downloader.command_with_youtube_player_client(command, "web_embedded")

        self.assertEqual(
            updated,
            [
                "yt-dlp",
                "-f",
                "399+140",
                "--extractor-args",
                "youtube:player_client=web_embedded",
                "https://youtu.be/example",
            ],
        )
        self.assertEqual(command, ["yt-dlp", "-f", "399+140", "https://youtu.be/example"])

    def test_preserves_existing_youtube_settings_and_audio_client(self) -> None:
        command = [
            "yt-dlp",
            "--extractor-args",
            "youtube:skip=hls;player_client=android_vr",
            "https://youtu.be/example",
        ]

        updated = Downloader.command_with_youtube_player_client(command, "web_embedded")

        self.assertEqual(
            updated[2],
            "youtube:skip=hls;player_client=web_embedded,android_vr",
        )

    def test_does_not_add_fallback_client_twice(self) -> None:
        command = [
            "yt-dlp",
            "--extractor-args",
            "youtube:player_client=web_embedded,android_vr",
            "https://youtu.be/example",
        ]

        updated = Downloader.command_with_youtube_player_client(command, "web_embedded")

        self.assertEqual(updated, command)


class DownloadCommandTests(unittest.TestCase):
    def test_prefers_resumable_https_formats_over_hls(self) -> None:
        downloader = Downloader.__new__(Downloader)
        downloader.max_resolution = "1080"

        selector = downloader.build_format_selector("1080")

        self.assertTrue(
            selector.startswith(
                "bestvideo[ext=mp4][protocol=https][height<=1080]+"
                "bestaudio[ext=m4a][protocol=https]/"
            )
        )
        self.assertIn("bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/", selector)

    def test_network_retry_limits_are_bounded_and_configurable(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "YTD_SOCKET_TIMEOUT": "12",
                "YTD_DOWNLOAD_RETRIES": "4",
                "YTD_FRAGMENT_RETRIES": "2",
            },
        ):
            downloader = Downloader()

        command = downloader.yt_dlp_base_command("test.%(ext)s")

        self.assertEqual(command[command.index("--socket-timeout") + 1], "12")
        self.assertEqual(command[command.index("--retries") + 1], "4")
        self.assertEqual(command[command.index("--fragment-retries") + 1], "2")
        self.assertIn("--abort-on-unavailable-fragments", command)

    def test_access_block_stops_run_and_preserves_unprocessed_queue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = {
                "YTD_APP_DIR": str(root),
                "YTD_DATA_DIR": str(root),
                "YTD_CONFIG_DIR": str(root),
                "YTD_TEMP_DIR": str(root / "temp"),
                "YTD_FINAL_DIR": str(root / "final"),
                "YTD_TELEGRAM_ENABLED": "0",
                "YTD_SYSTEM_NOTIFICATIONS_ENABLED": "0",
            }
            with patch.dict("os.environ", environment, clear=True):
                downloader = Downloader()

            urls = ["https://youtu.be/aaaaaaaaaaa", "https://youtu.be/bbbbbbbbbbb"]
            downloader.run_yt_dlp_with_subtitle_fallback = lambda *_args, **_kwargs: [
                "ERROR: Sign in to confirm you’re not a bot"
            ]

            with self.assertRaises(YoutubeAccessBlocked):
                downloader.process_queue_urls(urls, retry_failed=True)

            self.assertEqual(downloader.read_nonempty_lines(downloader.queue_file), urls)
            self.assertEqual(downloader.failed_count, 1)

    def test_stop_interrupts_active_child_and_allows_next_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict("os.environ", {
                "YTD_APP_DIR": str(root),
                "YTD_DATA_DIR": str(root),
                "YTD_CONFIG_DIR": str(root),
                "YTD_TEMP_DIR": str(root / "temp"),
                "YTD_FINAL_DIR": str(root / "final"),
            }, clear=True):
                downloader = Downloader()
            downloader.prepare()
            command = [sys.executable, "-u", "-c", "import time; print('ready', flush=True); time.sleep(30)"]
            timer = threading.Timer(0.5, lambda: downloader.stop_file.write_text("stop\n"))
            timer.start()
            started = time.monotonic()
            children = []
            original_popen = subprocess.Popen

            def start_child(*args, **kwargs):
                child = original_popen(*args, **kwargs)
                children.append(child)
                return child

            try:
                with patch("scripts.downloader.subprocess.Popen", side_effect=start_child):
                    with self.assertRaises(KeyboardInterrupt):
                        downloader.run_yt_dlp(command, "queue", report_failure=False)
                self.assertIsNotNone(children[0].poll())
            finally:
                timer.join(timeout=2)
            self.assertLess(time.monotonic() - started, 5)

            downloader.prepare()
            self.assertTrue(downloader.stop_file.exists())
            downloader.stop_file.unlink()
            lines = downloader.run_yt_dlp(
                [sys.executable, "-u", "-c", "print('next run works')"], "queue", report_failure=False
            )
            self.assertIn("next run works", lines)

    def test_interrupted_queue_retains_links_without_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict("os.environ", {
                "YTD_APP_DIR": str(root),
                "YTD_DATA_DIR": str(root),
                "YTD_CONFIG_DIR": str(root),
                "YTD_TEMP_DIR": str(root / "temp"),
                "YTD_FINAL_DIR": str(root / "final"),
            }, clear=True):
                downloader = Downloader()
            downloader.prepare()
            urls = ["https://youtu.be/aaaaaaaaaaa", "https://youtu.be/bbbbbbbbbbb"]
            downloader.save_queue(urls)

            def interrupt(*_args, **_kwargs):
                self.assertEqual(downloader.read_nonempty_lines(downloader.queue_file), urls)
                raise KeyboardInterrupt

            downloader.run_yt_dlp_with_subtitle_fallback = Mock(side_effect=interrupt)

            with self.assertRaises(KeyboardInterrupt):
                downloader.process_queue()

            self.assertEqual(downloader.read_nonempty_lines(downloader.queue_file), urls)

    def test_queue_keeps_file_when_final_publish_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict("os.environ", {
                "YTD_APP_DIR": str(root),
                "YTD_DATA_DIR": str(root),
                "YTD_CONFIG_DIR": str(root),
                "YTD_TEMP_DIR": str(root / "temp"),
                "YTD_FINAL_DIR": str(root / "final"),
            }, clear=True):
                downloader = Downloader()
            downloader.prepare()
            url = "https://youtu.be/aaaaaaaaaaa"
            downloader.save_queue([url])
            video = downloader.temp_dir / "Example - Author [Youtube] [aaaaaaaaaaa] [queue] [480p].mp4"
            video.write_bytes(b"test media")
            downloader.run_yt_dlp_with_subtitle_fallback = Mock(return_value=[f"[download] Destination: {video}"])

            with patch("scripts.downloader.shutil.move", side_effect=OSError("destination unavailable")), patch(
                "scripts.downloader.time.sleep"
            ):
                downloader.process_queue()

            self.assertEqual(downloader.read_nonempty_lines(downloader.queue_file), [url])
            self.assertTrue(video.exists())
            self.assertEqual(downloader.downloaded_counts["queue"], 0)
            self.assertEqual(downloader.archive_details_file.read_text(), "")


if __name__ == "__main__":
    unittest.main()
