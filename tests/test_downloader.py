import unittest

from scripts.downloader import Downloader


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


if __name__ == "__main__":
    unittest.main()
