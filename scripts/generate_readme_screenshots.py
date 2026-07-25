#!/usr/bin/env python3
"""Generate localized README screenshots without touching user data."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time


LANGUAGES = ("en", "ru", "uk", "fr", "es", "hi", "zh", "ar")


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "docs" / "screenshots")
    parser.add_argument("--channels", type=Path, default=root / "channels.txt")
    parser.add_argument("--channel-rules", type=Path, default=root / "channel_rules.json")
    parser.add_argument("--channel-cache", type=Path, default=Path.home() / ".cache" / "YTD")
    parser.add_argument(
        "--preview",
        type=Path,
        default=Path.home() / ".cache" / "YTD" / "previews" / "ytd_preview_3.jpg",
    )
    return parser.parse_args()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_fixture(root: Path, source_root: Path, args: argparse.Namespace) -> tuple[Path, Path]:
    data_dir = root / "data"
    config_dir = root / "config"
    data_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    shutil.copy2(args.channels, data_dir / "channels.txt")
    if args.channel_rules.is_file():
        shutil.copy2(args.channel_rules, config_dir / "channel_rules.json")

    (data_dir / "queue.txt").write_text(
        "https://www.youtube.com/watch?v=tYh-7USx09E\n"
        "https://www.youtube.com/watch?v=AtT9SQVInkc\n",
        encoding="utf-8",
    )
    (data_dir / "yt_archive.txt").write_text(
        "\n".join(f"DemoVideo{index:02d}" for index in range(1, 15)) + "\n",
        encoding="utf-8",
    )
    today = time.strftime("%Y-%m-%d")
    archive_entries = []
    for index, media_type in enumerate(("videos", "videos", "shorts", "streams"), start=1):
        archive_entries.append(
            {
                "video_id": f"DemoToday{index}",
                "youtube_url": f"https://www.youtube.com/watch?v=DemoToday{index}",
                "title": f"Documentation sample {index}",
                "channel_name": "YouTube Harvester",
                "downloaded_at": f"{today} 10:{index:02d}:00",
                "type": media_type,
                "file_path": "",
            }
        )
    (data_dir / "archive_details.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in archive_entries),
        encoding="utf-8",
    )
    now = int(time.time())
    write_json(
        data_dir / "status.json",
        {
            "state": "sleep",
            "channels_total": 19,
            "channels_checked": 19,
            "last_run_completed_at": now - 420,
            "last_run_stopped": False,
            "last_run_new_count": 4,
            "last_run_failed_count": 0,
            "last_run_videos": 2,
            "last_run_shorts": 1,
            "last_run_streams": 1,
            "last_run_queue": 0,
            "last_run_channels_total": 19,
            "last_run_channels_checked": 19,
            "last_download_at": str(now - 420),
        },
    )
    (data_dir / "last_download_at.txt").write_text(str(now - 420) + "\n", encoding="ascii")
    (data_dir / "download.log").write_text(
        "[info] YouTube Harvester 1.1.1\n"
        "[info] Channel scan completed\n"
        "[info] Downloaded 2 videos, 1 Short and 1 stream\n"
        "[info] Queue will be checked again after all channels\n"
        "[info] Temporary files cleaned safely\n",
        encoding="utf-8",
    )
    write_json(
        config_dir / "settings.json",
        {
            "theme": "dark",
            "language": "en",
            "download_dir": "/home/demo/Downloads/YouTubeHarvester",
            "temp_dir": "/home/demo/.cache/YouTubeHarvester/temp",
            "videos_limit": 5,
            "shorts_limit": 5,
            "streams_limit": 5,
            "max_resolution": "1080",
            "log_keep_count": 3,
            "cleanup_temp": True,
            "retry_failed_queue": True,
            "telegram_enabled": False,
            "clipboard_watch_enabled": True,
            "startup_display_mode": "tray",
            "check_paid_content_enabled": True,
            "quick_download_hotkey": "Ctrl+Shift+Alt+Y",
            "quick_download_telegram_notify": False,
            "usage_rules_accepted_version": "2026-06-13",
        },
    )
    write_json(
        config_dir / "schedules.json",
        [
            {"hour": 9, "enabled": True, "last_run_marker": today},
            {"hour": 18, "enabled": True, "last_run_marker": ""},
            {"hour": 23, "enabled": False, "last_run_marker": ""},
        ],
    )
    (config_dir / ".env").write_text(
        "TELEGRAM_ENABLED=0\nBOT_TOKEN=''\nCHANNEL_ID=''\nPROXY_URL=''\n",
        encoding="utf-8",
    )

    os.environ.update(
        {
            "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", "offscreen"),
            "XDG_SESSION_TYPE": "wayland",
            "YTD_APP_DIR": str(source_root),
            "YTD_DATA_DIR": str(data_dir),
            "YTD_CONFIG_DIR": str(config_dir),
            "YTD_CACHE_DIR": str(args.channel_cache),
            "YTD_SETTINGS_FILE": str(config_dir / "settings.json"),
            "YTD_SCHEDULES_FILE": str(config_dir / "schedules.json"),
            "YTD_CHANNEL_RULES_FILE": str(config_dir / "channel_rules.json"),
            "YTD_ENV_FILE": str(config_dir / ".env"),
            "YTD_SKIP_CHANNEL_METADATA": "1",
            "YTD_SKIP_USAGE_RULES": "1",
        }
    )
    return data_dir, config_dir


def set_queue_preview(window, preview_path: Path) -> None:
    title = "Every Ultimate in Unreal Tournament 2004"
    uploader = "ROCKY VIII"
    url = "https://www.youtube.com/watch?v=tYh-7USx09E"
    window.preview_timer.stop()
    window.video_url_input.blockSignals(True)
    window.video_url_input.setText(url)
    window.video_url_input.blockSignals(False)
    window.current_previews["queue"] = {
        "title": title,
        "uploader": uploader,
        "thumbnail_path": str(preview_path) if preview_path.is_file() else "",
        "url": url,
    }
    window.video_title_label.setText(title)
    window.video_uploader_label.setText(window.tr("preview.channel", uploader=uploader))
    window.video_status_label.setText(window.tr("preview.ready_queue"))
    if preview_path.is_file():
        window._set_label_image(window.thumbnail_label, preview_path, "YT")


def save_tab(window, app, tab, path: Path) -> None:
    window.tabs.setCurrentWidget(tab)
    window.show()
    for _index in range(4):
        app.processEvents()
    pixmap = window.grab()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"Could not save screenshot: {path}")


def main() -> int:
    args = parse_args()
    source_root = Path(__file__).resolve().parents[1]
    if not args.channels.is_file():
        raise SystemExit(f"Channel list not found: {args.channels}")
    if not (args.channel_cache / "channels").is_dir():
        raise SystemExit(f"Channel cache not found: {args.channel_cache / 'channels'}")

    with tempfile.TemporaryDirectory(prefix="yth-readme-") as temp_name:
        prepare_fixture(Path(temp_name), source_root, args)
        sys.path.insert(0, str(source_root))
        import tray_launcher as yth

        launcher = yth.TrayLauncher()
        window = yth.MainWindow(launcher)
        launcher.main_window = window
        window.setFixedSize(900, 620)

        for language in LANGUAGES:
            launcher.language = language
            window.language = language
            window.ui_settings["language"] = language
            window.apply_language()
            window.refresh_all()
            set_queue_preview(window, args.preview)
            window.refresh_overview()

            destination = args.output / language
            save_tab(window, launcher.app, window.overview_tab, destination / "overview.png")
            save_tab(window, launcher.app, window.channels_tab, destination / "channels.png")
            save_tab(window, launcher.app, window.queue_tab, destination / "queue.png")
            save_tab(window, launcher.app, window.settings_tab, destination / "settings.png")
            print(f"Generated {language}: {destination}")

        launcher.cleanup_global_hotkey()
        window.close()
        launcher.app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
