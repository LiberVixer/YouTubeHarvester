#!/usr/bin/env python3
"""Python downloader engine for YouTube Harvester.

It writes the public runtime contract used by the GUI: status.json, queue.txt,
yt_archive.txt, archive_details.jsonl and the same YTD_* environment variables.
"""

from __future__ import annotations

import datetime as _dt
import contextlib
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from yth_common import (  # noqa: E402
    SingleInstanceLock,
    archive_entry_file_exists,
    archive_entry_matches_variant,
    extract_video_id,
    fix_mojibake,
    media_resolution_from_path,
    positive_int,
    read_env_file,
    safe_print,
    truthy,
    utf8_subprocess_env,
    yt_dlp_command,
)


TYPE_LABELS = {
    "videos": ("🎬", "Видео"),
    "shorts": ("⚡", "Shorts"),
    "streams": ("🔴", "Трансляция"),
    "queue": ("📥", "Очередь"),
}

ISO_639_2_CODES = {
    "ar": "ara", "bg": "bul", "ca": "cat", "cs": "ces", "da": "dan", "de": "deu",
    "el": "ell", "en": "eng", "es": "spa", "et": "est", "fa": "fas", "fi": "fin",
    "fr": "fra", "he": "heb", "hi": "hin", "hr": "hrv", "hu": "hun", "id": "ind",
    "it": "ita", "ja": "jpn", "ko": "kor", "lt": "lit", "lv": "lav", "nl": "nld",
    "no": "nor", "pl": "pol", "pt": "por", "ro": "ron", "ru": "rus", "sk": "slk",
    "sl": "slv", "sr": "srp", "sv": "swe", "th": "tha", "tr": "tur", "uk": "ukr",
    "vi": "vie", "zh": "zho",
}

MEDIA_FILE_RE = re.compile(
    r"^(?P<base>.*) \[(?P<video_id>[A-Za-z0-9_-]{11})\] "
    r"\[(?P<type>videos|shorts|streams|queue)\] \[[^]]+\]\.mp4$"
)

MISSING_PAGE_RE = re.compile(
    r"does not have.*tab|No entries|No items|No video|No shorts|No streams|does not exist|not found|HTTP Error 404",
    re.IGNORECASE,
)

MEMBERS_ONLY_RE = re.compile(
    r"members-only|join this channel|get access to members-only|exclusive perks|channel members",
    re.IGNORECASE,
)
PAID_CONTENT_STATUS_KEY = "paid_content_status"
PAID_CONTENT_HAS = "has_paid"
MIN_FREE_SPACE_MB = 1024
PLAYLIST_ITEM_RE = re.compile(r"^\[download\] Downloading item \d+ of \d+")
SUBTITLE_DOWNLOAD_ERROR_RE = re.compile(
    r"Unable to download video subtitles for ['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)


def short_channel_name(channel: str) -> str:
    text = channel.rstrip("/")
    if "/@" in text:
        return text.rsplit("/@", 1)[-1]
    return text.rsplit("/", 1)[-1]


def iso_639_2_code(language: str) -> str:
    base = str(language or "").strip().lower().split("-", 1)[0]
    if len(base) == 3:
        return base
    return ISO_639_2_CODES.get(base, "und")


class Downloader:
    def __init__(self) -> None:
        self.base_dir = Path(os.environ.get("YTD_APP_DIR", Path(__file__).resolve().parents[1]))
        self.data_dir = Path(os.environ.get("YTD_DATA_DIR", self.base_dir))
        self.config_dir = Path(os.environ.get("YTD_CONFIG_DIR", self.data_dir))
        self.channels_file = Path(os.environ.get("YTD_CHANNELS_FILE", self.data_dir / "channels.txt"))
        self.queue_file = Path(os.environ.get("YTD_QUEUE_FILE", self.data_dir / "queue.txt"))
        self.single_queue_url = os.environ.get("YTD_SINGLE_QUEUE_URL", "").strip()
        self.archive_file = Path(os.environ.get("YTD_ARCHIVE_FILE", self.data_dir / "yt_archive.txt"))
        self.archive_details_file = Path(os.environ.get("YTD_ARCHIVE_DETAILS_FILE", self.data_dir / "archive_details.jsonl"))
        self.env_file = Path(os.environ.get("YTD_ENV_FILE", self.config_dir / ".env"))
        self.status_file = Path(os.environ.get("YTD_STATUS_FILE", self.data_dir / "status.json"))
        self.stop_file = Path(os.environ.get("YTD_STOP_FILE", self.data_dir / "stop_requested"))
        self.last_download_file = Path(os.environ.get("YTD_LAST_DOWNLOAD_FILE", self.data_dir / "last_download_at.txt"))
        self.channel_rules_file = Path(os.environ.get("YTD_CHANNEL_RULES_FILE", self.config_dir / "channel_rules.json"))
        self.temp_dir = Path(os.environ.get("YTD_TEMP_DIR", Path.home() / "temp" / "YTH"))
        self.final_dir = Path(os.environ.get("YTD_FINAL_DIR", Path.home() / "Downloads" / "YouTubeHarvester"))
        self.ffmpeg_dir = self.detect_ffmpeg_dir()
        self.deno_path = self.detect_deno_path()
        self.log_file = Path(os.environ.get("YTD_LOG_FILE", self.data_dir / "download.log"))
        self.temp_marker_file = self.temp_dir / ".yth-temp"

        env_values = read_env_file(self.env_file)
        merged = dict(env_values)
        merged.update({key: value for key, value in os.environ.items() if key.startswith("YTD_")})
        self.bot_token = os.environ.get("BOT_TOKEN") or env_values.get("BOT_TOKEN", "")
        self.channel_id = os.environ.get("CHANNEL_ID") or env_values.get("CHANNEL_ID", "")
        self.proxy_url = os.environ.get("PROXY_URL") or env_values.get("PROXY_URL", "")

        self.telegram_enabled = truthy(os.environ.get("YTD_TELEGRAM_ENABLED", env_values.get("TELEGRAM_ENABLED", "1")))
        self.videos_limit = positive_int(os.environ.get("YTD_VIDEOS_LIMIT", env_values.get("VIDEOS_LIMIT")), 5)
        self.shorts_limit = positive_int(os.environ.get("YTD_SHORTS_LIMIT", env_values.get("SHORTS_LIMIT")), 5)
        self.streams_limit = positive_int(os.environ.get("YTD_STREAMS_LIMIT", env_values.get("STREAMS_LIMIT")), 5)
        self.log_keep_count = positive_int(os.environ.get("YTD_LOG_KEEP_COUNT", env_values.get("LOG_KEEP_COUNT")), 3)
        self.cleanup_temp = truthy(os.environ.get("YTD_CLEANUP_TEMP", env_values.get("CLEANUP_TEMP", "1")))
        self.retry_failed_queue = truthy(os.environ.get("YTD_RETRY_FAILED_QUEUE", env_values.get("RETRY_FAILED_QUEUE", "1")))
        self.max_resolution = os.environ.get("YTD_MAX_RESOLUTION", env_values.get("MAX_RESOLUTION", "1080")).strip()
        self.audio_tracks: list[dict] = []
        try:
            configured_audio_tracks = json.loads(os.environ.get("YTD_AUDIO_TRACKS_JSON", "[]"))
        except json.JSONDecodeError:
            configured_audio_tracks = []
        if isinstance(configured_audio_tracks, list):
            for track in configured_audio_tracks:
                if not isinstance(track, dict):
                    continue
                format_id = str(track.get("format_id") or "").strip()
                if not re.fullmatch(r"[A-Za-z0-9._-]+", format_id):
                    continue
                format_kind = str(track.get("format_kind") or "audio").strip().lower()
                player_client = str(track.get("player_client") or "").strip()
                self.audio_tracks.append({
                    "format_id": format_id,
                    "format_kind": format_kind if format_kind in {"audio", "combined"} else "audio",
                    "language": str(track.get("language") or "").strip(),
                    "name": fix_mojibake(str(track.get("name") or "").strip()),
                    "player_client": player_client if re.fullmatch(r"[A-Za-z0-9_-]+", player_client) else "",
                })
        if not self.audio_tracks:
            audio_format_id = os.environ.get("YTD_AUDIO_FORMAT_ID", "").strip()
            if re.fullmatch(r"[A-Za-z0-9._-]+", audio_format_id):
                audio_format_kind = os.environ.get("YTD_AUDIO_FORMAT_KIND", "audio").strip().lower()
                audio_player_client = os.environ.get("YTD_YOUTUBE_AUDIO_PLAYER_CLIENT", "").strip()
                self.audio_tracks.append({
                    "format_id": audio_format_id,
                    "format_kind": audio_format_kind if audio_format_kind in {"audio", "combined"} else "audio",
                    "language": os.environ.get("YTD_AUDIO_LANGUAGE", "").strip(),
                    "name": fix_mojibake(os.environ.get("YTD_AUDIO_TRACK_NAME", "").strip()),
                    "player_client": audio_player_client if re.fullmatch(r"[A-Za-z0-9_-]+", audio_player_client) else "",
                })
        self.audio_format_id = str(self.audio_tracks[0].get("format_id") or "") if self.audio_tracks else ""
        self.audio_format_kind = str(self.audio_tracks[0].get("format_kind") or "audio") if self.audio_tracks else "audio"
        self.audio_language = str(self.audio_tracks[0].get("language") or "") if self.audio_tracks else ""
        self.audio_track_name = str(self.audio_tracks[0].get("name") or "") if self.audio_tracks else ""
        self.audio_player_client = next((str(track.get("player_client") or "") for track in self.audio_tracks if track.get("player_client")), "")

        try:
            configured_subtitles = json.loads(os.environ.get("YTD_SUBTITLE_SELECTIONS_JSON", "[]"))
        except json.JSONDecodeError:
            configured_subtitles = []
        self.subtitle_selections = sorted({
            str(value or "").strip()
            for value in configured_subtitles
            if isinstance(value, str) and str(value or "").strip().lower() not in {"", "none"}
        }, key=str.casefold) if isinstance(configured_subtitles, list) else []
        if not self.subtitle_selections:
            legacy_subtitle = os.environ.get("YTD_SUBTITLE_SELECTION", "").strip()
            if legacy_subtitle.lower() not in {"", "none"}:
                self.subtitle_selections = [legacy_subtitle]
        self.subtitle_selection = self.subtitle_selections[0] if self.subtitle_selections else "none"
        self.format_selector = self.build_format_selector(self.max_resolution, self.audio_tracks)

        self.state = "sleep"
        self.channel_url = ""
        self.channel_name = ""
        self.current_type = ""
        self.type_status = {"videos": "idle", "shorts": "idle", "streams": "idle"}
        self.video_title = ""
        self.video_thumbnail = ""
        self.download_percent = ""
        self.download_speed = ""
        self.download_eta = ""
        self.download_size = ""
        self.download_stage = ""
        self.progress_bucket = ""
        self.channels_total = 0
        self.channels_checked = 0
        self.new_count = 0
        self.failed_count = 0
        self.downloaded_counts = {"videos": 0, "shorts": 0, "streams": 0, "queue": 0}
        self.last_yt_dlp_return_code = 0
        self.run_completed_at = 0
        self.archived_log = self.data_dir / f"download_{_dt.datetime.now():%Y-%m-%d_%H-%M}.log"

    def build_format_selector(self, value: str, audio_tracks: list[dict] | None = None) -> str:
        audio_tracks = audio_tracks or []
        if audio_tracks:
            combined_ids = [str(track.get("format_id") or "") for track in audio_tracks if track.get("format_kind") == "combined"]
            audio_ids = [str(track.get("format_id") or "") for track in audio_tracks if track.get("format_kind") != "combined"]
            if combined_ids:
                return "+".join([combined_ids[0], *audio_ids])
            audio_suffix = "+".join(audio_ids)
            if value in {"480", "720", "1080", "1440", "2160"}:
                return (
                    f"bestvideo[ext=mp4][height<={value}]+{audio_suffix}/"
                    f"bestvideo[height<={value}]+{audio_suffix}"
                )
            self.max_resolution = "best" if value.lower() == "best" else "1080"
            if self.max_resolution == "best":
                return f"bestvideo[ext=mp4]+{audio_suffix}/bestvideo+{audio_suffix}"
            return (
                f"bestvideo[ext=mp4][height<=1080]+{audio_suffix}/"
                f"bestvideo[height<=1080]+{audio_suffix}"
            )
        if value in {"480", "720", "1080", "1440", "2160"}:
            return (
                f"bestvideo[ext=mp4][height<={value}]+bestaudio[ext=m4a]/"
                f"best[ext=mp4][height<={value}]/best[height<={value}]"
            )
        self.max_resolution = "best" if value.lower() == "best" else "1080"
        if self.max_resolution == "best":
            return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        return "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best[height<=1080]"

    def ordered_audio_tracks(self) -> list[dict]:
        combined = [track for track in self.audio_tracks if track.get("format_kind") == "combined"]
        separate = [track for track in self.audio_tracks if track.get("format_kind") != "combined"]
        return [*combined[:1], *separate]

    def audio_metadata_postprocessor_args(self) -> str:
        arguments: list[str] = []
        for index, track in enumerate(self.ordered_audio_tracks()):
            arguments.extend([f"-metadata:s:a:{index}", f"language={iso_639_2_code(track.get('language'))}"])
        return f"Merger+ffmpeg_o:{' '.join(arguments)}" if arguments else ""

    def detect_ffmpeg_dir(self) -> Path | None:
        configured = os.environ.get("YTD_FFMPEG_DIR", "").strip()
        candidates: list[Path] = []
        if configured:
            candidates.append(Path(configured))
        candidates.extend([
            self.base_dir / "ffmpeg",
            self.base_dir / "ffmpeg" / "bin",
            self.base_dir / "bin",
            self.base_dir / "tools" / "windows" / "ffmpeg" / "bin",
            self.base_dir / "tools" / "windows" / "ffmpeg",
        ])
        ffmpeg_path = shutil.which("ffmpeg")
        ffprobe_path = shutil.which("ffprobe")
        if ffmpeg_path and ffprobe_path and Path(ffmpeg_path).parent == Path(ffprobe_path).parent:
            candidates.append(Path(ffmpeg_path).parent)

        ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        ffprobe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
        for candidate in candidates:
            if (candidate / ffmpeg_name).exists() and (candidate / ffprobe_name).exists():
                return candidate
        return None

    def detect_deno_path(self) -> Path | None:
        configured = os.environ.get("YTD_DENO_PATH", "").strip()
        candidates: list[Path] = []
        if configured:
            candidates.append(Path(configured))
        deno_name = "deno.exe" if os.name == "nt" else "deno"
        candidates.extend([
            self.base_dir / "deno" / deno_name,
            self.base_dir / "deno" / "bin" / deno_name,
            self.base_dir / "bin" / deno_name,
            self.base_dir / "tools" / "windows" / "deno" / deno_name,
            self.base_dir / "tools" / "windows" / "deno" / "bin" / deno_name,
        ])
        deno_path = shutil.which("deno")
        if deno_path:
            candidates.append(Path(deno_path))

        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def js_runtime_arg(self) -> str:
        if self.deno_path:
            return f"deno:{self.deno_path}"
        return "deno"

    def prepare(self) -> None:
        for path in (self.data_dir, self.config_dir, self.temp_dir, self.final_dir):
            path.mkdir(parents=True, exist_ok=True)
        for path in (self.channels_file, self.archive_file, self.archive_details_file, self.log_file, self.queue_file):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        self.ensure_temp_marker()
        with contextlib.suppress(OSError):
            self.stop_file.unlink(missing_ok=True)

    def human_size(self, size: int) -> str:
        value = float(max(0, int(size or 0)))
        for unit in ("Б", "КиБ", "МиБ", "ГиБ", "ТиБ"):
            if value < 1024 or unit == "ТиБ":
                return f"{value:.1f} {unit}" if unit != "Б" else f"{int(value)} {unit}"
            value /= 1024
        return f"{value:.1f} ТиБ"

    def minimum_free_space_bytes(self) -> int:
        try:
            mb = int(os.environ.get("YTD_MIN_FREE_SPACE_MB", MIN_FREE_SPACE_MB))
        except (TypeError, ValueError):
            mb = MIN_FREE_SPACE_MB
        return max(128, mb) * 1024 * 1024

    def validate_free_space(self) -> bool:
        required = self.minimum_free_space_bytes()
        ok = True
        for label, path in (("временной папке", self.temp_dir), ("папке загрузок", self.final_dir)):
            try:
                usage = shutil.disk_usage(path)
            except OSError as exc:
                self.log(f"❌ Не удалось проверить место в {label}: {exc}")
                ok = False
                continue
            if usage.free < required:
                self.log(
                    f"❌ Мало места в {label}: свободно {self.human_size(usage.free)}, "
                    f"нужно хотя бы {self.human_size(required)}"
                )
                ok = False
        return ok

    def ensure_temp_marker(self) -> None:
        try:
            if self.temp_marker_file.exists():
                return
            has_files = any(self.temp_dir.iterdir())
            if not has_files or self.is_dedicated_temp_dir():
                self.temp_marker_file.write_text("YouTube Harvester temp directory\n", encoding="utf-8")
        except OSError:
            pass

    def log(self, message: str) -> None:
        message = fix_mojibake(str(message))
        safe_print(message)
        try:
            with self.log_file.open("a", encoding="utf-8") as log:
                log.write(message + "\n")
        except OSError:
            pass

    def reset_progress(self) -> None:
        self.download_percent = ""
        self.download_speed = ""
        self.download_eta = ""
        self.download_size = ""
        self.download_stage = ""
        self.progress_bucket = ""

    def write_status(self) -> None:
        last_download = ""
        try:
            if self.last_download_file.exists():
                last_download = self.last_download_file.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            pass
        payload = {
            "state": self.state,
            "channel_url": self.channel_url,
            "channel_name": self.channel_name,
            "current_type": self.current_type,
            "videos_status": self.type_status["videos"],
            "shorts_status": self.type_status["shorts"],
            "streams_status": self.type_status["streams"],
            "video_title": self.video_title,
            "video_thumbnail": self.video_thumbnail,
            "download_percent": self.download_percent,
            "download_speed": self.download_speed,
            "download_eta": self.download_eta,
            "download_size": self.download_size,
            "download_stage": self.download_stage,
            "channels_total": self.channels_total,
            "channels_checked": self.channels_checked,
            "last_run_completed_at": self.run_completed_at,
            "last_run_stopped": self.state == "stopped",
            "last_run_new_count": sum(self.downloaded_counts.values()),
            "last_run_failed_count": self.failed_count,
            "last_run_videos": self.downloaded_counts["videos"],
            "last_run_shorts": self.downloaded_counts["shorts"],
            "last_run_streams": self.downloaded_counts["streams"],
            "last_run_queue": self.downloaded_counts["queue"],
            "last_run_channels_total": self.channels_total,
            "last_run_channels_checked": self.channels_checked,
            "last_download_at": last_download,
            "stop_requested": self.stop_file.exists(),
            "updated_at": int(time.time()),
        }
        tmp = self.status_file.with_suffix(self.status_file.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(self.status_file)
        except OSError:
            pass

    def set_type_status(self, type_name: str, status: str) -> None:
        if type_name in self.type_status:
            self.type_status[type_name] = status

    def check_stop(self) -> None:
        if self.stop_file.exists():
            self.log("⏹ Запрошена мягкая остановка")
            self.state = "stopping"
            self.write_status()
            raise KeyboardInterrupt

    def type_limit(self, type_name: str) -> int:
        return {"videos": self.videos_limit, "shorts": self.shorts_limit, "streams": self.streams_limit}.get(type_name, 5)

    def read_nonempty_lines(self, path: Path) -> list[str]:
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
        except OSError:
            return []
        return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]

    def save_queue(self, urls: list[str]) -> None:
        self.queue_file.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")

    def load_channel_rules(self) -> dict:
        try:
            data = json.loads(self.channel_rules_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_channel_rules_data(self, rules_data: dict) -> None:
        try:
            self.channel_rules_file.parent.mkdir(parents=True, exist_ok=True)
            self.channel_rules_file.write_text(
                json.dumps(rules_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def normalize_channel_key(self, channel: str) -> str:
        return str(channel or "").strip().rstrip("/")

    def looks_like_channel_url(self, url: str) -> bool:
        text = self.normalize_channel_key(url)
        return (
            text.startswith(("https://www.youtube.com/", "https://youtube.com/"))
            and ("/@" in text or "/channel/" in text or "/c/" in text or "/user/" in text)
        )

    def set_channel_paid_content_status(self, channel: str, status: str) -> None:
        channel_key = self.normalize_channel_key(channel)
        if not self.looks_like_channel_url(channel_key):
            return
        rules_data = self.load_channel_rules()
        stored_key = next((key for key in rules_data if self.normalize_channel_key(key) == channel_key), channel_key)
        rules = rules_data.get(stored_key)
        if not isinstance(rules, dict):
            rules = {}
        if rules.get(PAID_CONTENT_STATUS_KEY) == status:
            return
        rules[PAID_CONTENT_STATUS_KEY] = status
        rules_data[stored_key] = rules
        self.save_channel_rules_data(rules_data)

    def channel_type_enabled(self, channel: str, type_name: str) -> bool:
        rules_data = self.load_channel_rules()
        channel_key = channel.rstrip("/")
        rules = rules_data.get(channel_key)
        if rules is None:
            for key, value in rules_data.items():
                if str(key).rstrip("/") == channel_key:
                    rules = value
                    break
        if not isinstance(rules, dict):
            return True
        value = rules.get(type_name, True)
        if value is False:
            return False
        return not (isinstance(value, str) and value.strip().lower() in {"0", "false", "no", "off"})

    def archive_has_video(self, video_id: str) -> bool:
        if not video_id:
            return False
        try:
            if self.archive_file.exists() and video_id in self.archive_file.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            pass
        return self.archive_details_has_video(video_id)

    def archive_detail_entries(self, video_id: str = "") -> list[dict]:
        entries: list[dict] = []
        try:
            lines = self.archive_details_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return entries
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            if video_id and str(entry.get("video_id") or "").strip() != video_id:
                continue
            entries.append(entry)
        return entries

    def archive_details_has_video(self, video_id: str) -> bool:
        if not video_id:
            return False
        return bool(self.archive_detail_entries(video_id))

    def archive_details_has_variant(self, video_id: str) -> bool:
        return any(
            archive_entry_file_exists(entry)
            and archive_entry_matches_variant(
                entry,
                resolution=self.max_resolution,
                audio_format_ids=[str(track.get("format_id") or "") for track in self.audio_tracks],
                audio_languages=[str(track.get("language") or "") for track in self.audio_tracks],
                subtitle_selections=self.subtitle_selections,
            )
            for entry in self.archive_detail_entries(video_id)
        )

    def ensure_video_in_archive(self, video_id: str) -> None:
        if not video_id or video_id == "unknown":
            return
        try:
            lines = self.archive_file.read_text(encoding="utf-8", errors="ignore").splitlines() if self.archive_file.exists() else []
            if any(video_id in line.split() for line in lines):
                return
            self.archive_file.parent.mkdir(parents=True, exist_ok=True)
            with self.archive_file.open("a", encoding="utf-8") as archive:
                archive.write(f"youtube {video_id}\n")
        except OSError:
            pass

    def remove_video_from_archive(self, video_id: str) -> None:
        if not video_id or not self.archive_file.exists():
            return
        if self.archive_details_has_video(video_id):
            self.log(f"   ↩️ ID оставлен в архиве: сохранены другие варианты {video_id}")
            return
        try:
            lines = self.archive_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            kept = [line for line in lines if video_id not in line.split()]
            self.archive_file.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
            self.log(f"   ↩️ Убран из архива для повтора: {video_id}")
        except OSError:
            pass

    def append_archive_details(self, video_id: str, url: str, title: str, channel: str, channel_url: str, type_name: str, file_path: Path) -> None:
        if video_id != "unknown":
            existing_lines: list[str] = []
            kept_lines: list[str] = []
            has_existing_variant = False
            try:
                existing_lines = self.archive_details_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                pass
            for raw_line in existing_lines:
                try:
                    existing = json.loads(raw_line)
                except json.JSONDecodeError:
                    kept_lines.append(raw_line)
                    continue
                matches = (
                    isinstance(existing, dict)
                    and str(existing.get("video_id") or "").strip() == video_id
                    and archive_entry_matches_variant(
                        existing,
                        resolution=self.max_resolution,
                        audio_format_ids=[str(track.get("format_id") or "") for track in self.audio_tracks],
                        audio_languages=[str(track.get("language") or "") for track in self.audio_tracks],
                        subtitle_selections=self.subtitle_selections,
                    )
                )
                if matches and archive_entry_file_exists(existing):
                    has_existing_variant = True
                    kept_lines.append(raw_line)
                elif not matches:
                    kept_lines.append(raw_line)
            if has_existing_variant:
                self.log(f"   🗃 Такой вариант уже есть в архиве: {video_id}")
                return
            if kept_lines != existing_lines:
                try:
                    self.archive_details_file.write_text(
                        "\n".join(kept_lines) + ("\n" if kept_lines else ""),
                        encoding="utf-8",
                    )
                except OSError:
                    pass
        entry = {
            "video_id": video_id,
            "youtube_url": url,
            "title": fix_mojibake(title),
            "channel_name": fix_mojibake(channel),
            "channel_url": channel_url,
            "downloaded_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "downloaded_at_ts": int(time.time()),
            "type": type_name,
            "file_path": str(file_path),
            "filename": fix_mojibake(file_path.name),
            "resolution": media_resolution_from_path(file_path),
            "requested_resolution": self.max_resolution,
            "audio_format_id": self.audio_format_id,
            "audio_language": self.audio_language or "auto",
            "audio_track_name": fix_mojibake(self.audio_track_name),
            "subtitle_selection": self.subtitle_selection or "none",
            "audio_tracks": self.audio_tracks,
            "subtitle_selections": self.subtitle_selections,
        }
        try:
            with self.archive_details_file.open("a", encoding="utf-8") as details:
                details.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            pass

    def send_telegram_message(self, message: str) -> bool:
        if not self.bot_token or not self.channel_id:
            self.log("   ❌ Telegram credentials are missing")
            return False
        if self.proxy_url:
            return self.send_telegram_message_with_curl(message)

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = urllib.parse.urlencode(
            {
                "chat_id": self.channel_id,
                "parse_mode": "HTML",
                "text": message,
            }
        ).encode("utf-8")
        request = urllib.request.Request(url, data=payload, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            self.log(f"   ❌ Telegram API error: {exc}")
            return False
        if '"ok":true' in body.replace(" ", ""):
            return True
        self.log(f"   ❌ Telegram API error: {body.strip()}")
        return False

    def send_telegram_message_with_curl(self, message: str) -> bool:
        if not shutil.which("curl"):
            self.log("   ❌ Telegram proxy mode needs curl, but curl was not found")
            return False
        command = [
            "curl",
            "-sS",
            "-X",
            "POST",
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            "-d",
            f"chat_id={self.channel_id}",
            "-d",
            "parse_mode=HTML",
            "--data-urlencode",
            f"text={message}",
        ]
        if self.proxy_url:
            command[1:1] = ["--socks5-hostname", self.proxy_url]
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=utf8_subprocess_env(),
                timeout=60,
                check=False,
            )
        except Exception as exc:
            self.log(f"   ❌ Telegram API error: {exc}")
            return False
        if result.returncode == 0 and '"ok":true' in (result.stdout or "").replace(" ", ""):
            return True
        self.log(f"   ❌ Telegram API error: {(result.stdout or '').strip()}")
        return False

    def status_base_without_ext(self, path: Path) -> Path:
        text = str(path)
        if text.endswith(".part"):
            text = text[:-5]
        text = re.sub(r"\.f[0-9]+(\.[^.]+)$", r"\1", text)
        return Path(re.sub(r"\.[^.]+$", "", text))

    def status_title_from_path(self, path: Path) -> str:
        basename = path.name.removesuffix(".part")
        basename = re.sub(r"\.f[0-9]+(\.[^.]+)$", r"\1", basename)
        title = re.sub(r" \[[A-Za-z0-9_-]{11}\] \[(videos|shorts|streams|queue)\] \[[^]]+\]\.[^.]+$", "", basename)
        if " - " in title:
            title = title.rsplit(" - ", 1)[0]
        return title[:180]

    def find_status_thumbnail(self, video_path: str | Path) -> str:
        base = self.status_base_without_ext(Path(video_path))
        for ext in ("jpg", "jpeg", "png", "webp"):
            candidate = base.with_suffix(f".{ext}")
            if candidate.exists():
                return str(candidate)
        images: list[Path] = []
        for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            images.extend(self.temp_dir.glob(pattern))
        files = [image for image in images if image.is_file()]
        if not files:
            return ""
        return str(max(files, key=lambda item: item.stat().st_mtime))

    def update_status_from_line(self, line: str, type_name: str) -> None:
        is_thumbnail_destination = bool(
            "Destination: " in line
            and re.search(r"\.(?:jpe?g|png|webp)(?:$|[\"'])", line, re.IGNORECASE)
        )
        if "Merging formats into" in line:
            self.download_stage = "merge"
        elif re.search(r"\[(?:EmbedThumbnail|Metadata|ModifyChapters|FFmpeg|VideoConvertor)\]", line):
            self.download_stage = "postprocess"
        elif "Destination: " in line and not is_thumbnail_destination:
            self.download_stage = "audio" if self.download_stage == "video" else "video"

        thumbnail_match = re.search(
            r"[Ww]riting video thumbnail [0-9]+ to: (.*)$|[Cc]onverting thumbnail \"?([^\"]+)\"? to |[Dd]estination: (.*\.(jpg|jpeg|png|webp))",
            line,
        )
        if thumbnail_match:
            thumb = next((group for group in thumbnail_match.groups()[:3] if group), "")
            if thumb:
                jpg = str(Path(thumb).with_suffix(".jpg"))
                self.video_thumbnail = jpg if Path(jpg).exists() else thumb
                self.write_status()
        if is_thumbnail_destination:
            return

        progress = re.match(r"^\[download\]\s+([0-9]+(?:\.[0-9]+)?)%.*", line)
        if progress:
            if not self.download_stage:
                self.download_stage = "download"
            self.download_percent = progress.group(1)
            size = re.search(r"\sof\s+~?(\S+)", line)
            speed = re.search(r"\sat\s+(\S+/s)", line)
            eta = re.search(r"\sETA\s+(\S+)", line)
            self.download_size = size.group(1) if size else ""
            self.download_speed = speed.group(1) if speed else ""
            self.download_eta = eta.group(1) if eta else ""
            self.state = "downloading"
            self.current_type = type_name
            self.set_type_status(type_name, "downloading")
            bucket = str(int(float(self.download_percent)))
            if bucket != self.progress_bucket or bucket == "100":
                self.progress_bucket = bucket
                self.write_status()
            return

        if (
            "Merging formats into" in line
            or "Destination: " in line
            or re.search(r"\[(?:EmbedThumbnail|Metadata|ModifyChapters|FFmpeg|VideoConvertor)\]", line)
        ):
            self.state = "downloading"
            self.current_type = type_name
            self.set_type_status(type_name, "downloading")
            if "Destination: " in line:
                stage = self.download_stage
                self.reset_progress()
                self.download_stage = stage
            file_match = re.search(r'Merging formats into "?([^"]+)"?', line) or re.search(r"Destination: (.*)", line)
            if file_match:
                path = file_match.group(1).strip()
                title = self.status_title_from_path(Path(path))
                if title:
                    self.video_title = title
                thumb = self.find_status_thumbnail(path)
                if thumb:
                    self.video_thumbnail = thumb
            self.write_status()

    def run_yt_dlp(
        self,
        command: list[str],
        type_name: str,
        item_completed: Callable[[list[str]], None] | None = None,
        *,
        report_failure: bool = True,
    ) -> list[str]:
        lines: list[str] = []
        item_lines: list[str] = []
        playlist_item_started = False
        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=utf8_subprocess_env(),
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError:
            self.last_yt_dlp_return_code = 127
            if report_failure:
                self.log("❌ yt-dlp не найден")
                self.failed_count += 1
            return lines

        def finish_item(completed_lines: list[str]) -> None:
            if item_completed is None or not completed_lines:
                return
            try:
                item_completed(list(completed_lines))
            except Exception as exc:
                self.failed_count += 1
                self.log(f"   ❌ Ошибка обработки готового видео: {exc}")

            if not self.stop_file.exists():
                return
            if proc.poll() is None:
                with contextlib.suppress(OSError):
                    proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    with contextlib.suppress(OSError):
                        proc.kill()
                    with contextlib.suppress(OSError):
                        proc.wait(timeout=5)
            raise KeyboardInterrupt

        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = fix_mojibake(raw_line.rstrip("\n"))
            if item_completed is not None and PLAYLIST_ITEM_RE.match(line):
                if playlist_item_started:
                    finish_item(item_lines)
                    item_lines = []
                playlist_item_started = True

            self.update_status_from_line(line, type_name)
            if not re.match(r"^\[download\]\s+[0-9]+(?:\.[0-9]+)?%", line):
                if self.is_members_only_line(line):
                    message = self.members_only_log_line(line)
                    self.set_channel_paid_content_status(self.channel_url, PAID_CONTENT_HAS)
                    self.log(message)
                    lines.append(message)
                    if playlist_item_started:
                        item_lines.append(message)
                else:
                    if report_failure or not SUBTITLE_DOWNLOAD_ERROR_RE.search(line):
                        self.log(line)
                    lines.append(line)
                    if playlist_item_started:
                        item_lines.append(line)
        return_code = proc.wait()
        self.last_yt_dlp_return_code = return_code
        if return_code != 0:
            if self.output_is_members_only_only(lines):
                self.log("   🔒 Закрытое для участников видео пропущено без ошибки")
            elif report_failure:
                self.failed_count += 1
                self.log(f"   ❌ yt-dlp завершился с кодом {return_code}")
        if item_completed is not None:
            finish_item(item_lines if playlist_item_started else lines)
        return lines

    @staticmethod
    def failed_subtitle_languages(lines: list[str]) -> set[str]:
        return {
            match.group(1).strip().casefold()
            for line in lines
            if (match := SUBTITLE_DOWNLOAD_ERROR_RE.search(line))
        }

    @staticmethod
    def command_with_subtitles(command: list[str], selections: list[str], *, bypass_archive: bool) -> list[str]:
        subtitle_flags = {
            "--write-subs",
            "--no-write-subs",
            "--write-auto-subs",
            "--no-write-auto-subs",
            "--embed-subs",
            "--no-embed-subs",
        }
        cleaned: list[str] = []
        skip_next = False
        for argument in command:
            if skip_next:
                skip_next = False
                continue
            if argument == "--sub-langs":
                skip_next = True
                continue
            if argument in subtitle_flags:
                continue
            cleaned.append(argument)

        subtitle_args: list[str] = []
        if selections:
            languages = [selection.partition(":")[2] for selection in selections if selection.partition(":")[2]]
            modes = {selection.partition(":")[0] for selection in selections}
            subtitle_args.extend(["--sub-langs", ",".join(languages), "--embed-subs"])
            subtitle_args.append("--write-subs" if "manual" in modes else "--no-write-subs")
            subtitle_args.append("--write-auto-subs" if "auto" in modes else "--no-write-auto-subs")
        else:
            subtitle_args.extend(["--no-write-subs", "--no-write-auto-subs", "--no-embed-subs"])
        if bypass_archive and "--no-download-archive" not in cleaned:
            subtitle_args.append("--no-download-archive")

        insert_at = max(0, len(cleaned) - 1)
        cleaned[insert_at:insert_at] = subtitle_args
        return cleaned

    def run_yt_dlp_with_subtitle_fallback(self, command: list[str], type_name: str) -> list[str]:
        if not self.subtitle_selections:
            return self.run_yt_dlp(command, type_name)

        active_selections = list(self.subtitle_selections)
        active_command = list(command)
        collected_lines: list[str] = []
        while True:
            attempt_lines = self.run_yt_dlp(active_command, type_name, report_failure=False)
            collected_lines.extend(attempt_lines)
            if self.last_yt_dlp_return_code == 0 or self.output_is_members_only_only(attempt_lines):
                return collected_lines

            failed_languages = self.failed_subtitle_languages(attempt_lines)
            remaining = [
                selection
                for selection in active_selections
                if selection.partition(":")[2].strip().casefold() not in failed_languages
            ]
            if not failed_languages or len(remaining) == len(active_selections):
                self.log(f"   ❌ yt-dlp завершился с кодом {self.last_yt_dlp_return_code}")
                return collected_lines

            unavailable = ", ".join(sorted(failed_languages))
            reason = "HTTP 429" if any("HTTP Error 429" in line for line in attempt_lines) else "ошибка YouTube"
            self.log(f"   ⚠️ Субтитры {unavailable} недоступны ({reason}); повторяем без них")
            active_selections = remaining
            self.subtitle_selections = list(remaining)
            self.subtitle_selection = remaining[0] if remaining else "none"
            active_command = self.command_with_subtitles(command, remaining, bypass_archive=True)

    def is_members_only_line(self, line: str) -> bool:
        return bool(MEMBERS_ONLY_RE.search(line or ""))

    def members_only_log_line(self, line: str) -> str:
        match = re.search(r"\[youtube\]\s+([A-Za-z0-9_-]{11})", line or "")
        video_id = f" {match.group(1)}" if match else ""
        return f"   🔒 Закрыто для участников:{video_id}"

    def output_has_members_only(self, lines: list[str]) -> bool:
        return any(self.is_members_only_line(line) or "🔒 Закрыто для участников" in line for line in lines)

    def output_is_members_only_only(self, lines: list[str]) -> bool:
        has_members_only = False
        for line in lines:
            if self.is_members_only_line(line) or "🔒 Закрыто для участников" in line:
                has_members_only = True
                continue
            lowered = line.lower()
            if "error:" in lowered or "failed" in lowered or "traceback" in lowered:
                return False
        return has_members_only

    def downloaded_files_from_lines(self, lines: list[str]) -> list[Path]:
        found: set[Path] = set()
        for line in lines:
            candidates = []
            for pattern in (
                r'Merging formats into "?([^"]+\.mp4)"?',
                r"Destination: (.*\.mp4)",
                r"^\[download\] (.*\.mp4) has already been downloaded",
            ):
                match = re.search(pattern, line)
                if match:
                    candidates.append(match.group(1).strip())
            for item in candidates:
                if re.search(r"\.f[0-9]+\.mp4$", item):
                    continue
                found.add(Path(item))
        return sorted(found, key=str)

    def downloaded_files_from_temp(self, expected_type: str) -> list[Path]:
        found: list[Path] = []
        try:
            candidates = sorted(self.temp_dir.glob("*.mp4"), key=lambda item: item.stat().st_mtime)
        except OSError:
            return found
        for path in candidates:
            if not path.is_file() or re.search(r"\.f[0-9]+\.mp4$", path.name):
                continue
            match = MEDIA_FILE_RE.match(path.name)
            if expected_type and (not match or match.group("type") != expected_type):
                continue
            found.append(path)
        return found

    def downloaded_files(self, lines: list[str], expected_type: str) -> list[Path]:
        found: dict[str, Path] = {}
        missing_from_log = False
        for path in self.downloaded_files_from_lines(lines):
            if path.exists():
                found[str(path.resolve())] = path
            else:
                missing_from_log = True
        fallback_files = self.downloaded_files_from_temp(expected_type) if (missing_from_log or not found) else []
        for path in fallback_files:
            found.setdefault(str(path.resolve()), path)
        if missing_from_log and fallback_files:
            self.log("   🧭 Готовый файл найден в temp по фактическому имени")
        return sorted(found.values(), key=str)

    def unique_final_path(self, basename: str) -> Path:
        basename = self.short_final_basename(basename)
        candidate = self.final_dir / basename
        if not candidate.exists():
            return candidate
        stem = candidate.stem
        suffix = candidate.suffix
        for index in range(1, 1000):
            alternate = self.final_dir / f"{stem} ({index}){suffix}"
            if not alternate.exists():
                return alternate
        return self.final_dir / f"{stem} ({int(time.time())}){suffix}"

    def variant_final_basename(self, basename: str) -> str:
        tags: list[str] = []
        if self.audio_tracks:
            audio_labels = [
                re.sub(r"[^A-Za-z0-9_-]+", "-", str(track.get("language") or "track")).strip("-") or "track"
                for track in self.audio_tracks
            ]
            audio_label = "+".join(audio_labels)
            if len(audio_label) > 48:
                digest = hashlib.sha1("|".join(str(track.get("format_id") or "") for track in self.audio_tracks).encode("utf-8")).hexdigest()[:8]
                audio_label = f"{len(audio_labels)}-tracks-{digest}"
            tags.append(f"audio-{audio_label}")
        if self.subtitle_selections:
            subtitle_labels = []
            for subtitle_selection in self.subtitle_selections:
                mode, _separator, language = subtitle_selection.partition(":")
                safe_language = re.sub(r"[^A-Za-z0-9_-]+", "-", language or "sub").strip("-") or "sub"
                subtitle_labels.append(f"auto-{safe_language}" if mode == "auto" else safe_language)
            subtitle_label = "+".join(subtitle_labels)
            if len(subtitle_label) > 56:
                digest = hashlib.sha1("|".join(self.subtitle_selections).encode("utf-8")).hexdigest()[:8]
                subtitle_label = f"{len(subtitle_labels)}-tracks-{digest}"
            tags.append(f"subs-{subtitle_label}")
        if not tags:
            return basename
        path = Path(basename)
        return f"{path.stem} {' '.join(f'[{tag}]' for tag in tags)}{path.suffix}"

    def short_final_basename(self, basename: str) -> str:
        if os.name != "nt":
            return basename
        max_path_length = 240
        budget = max_path_length - len(str(self.final_dir)) - 1
        if budget >= len(basename):
            return basename
        suffix = Path(basename).suffix
        stem = Path(basename).stem
        digest = hashlib.sha1(basename.encode("utf-8", errors="replace")).hexdigest()[:8]
        if budget <= len(suffix) + 12:
            return f"YTH_{digest}{suffix or '.mp4'}"
        keep = max(1, budget - len(suffix) - len(digest) - 1)
        shortened = f"{stem[:keep].rstrip(' .')}_{digest}{suffix}"
        if len(shortened) > budget and len(suffix) < budget:
            shortened = shortened[: budget - len(suffix)].rstrip(" .") + suffix
        return shortened

    def process_type_lines(
        self,
        lines: list[str],
        channel_link: str,
        channel_name: str,
        expected_type: str,
        *,
        check_stop_after: bool = True,
    ) -> int:
        files = self.downloaded_files(lines, expected_type)
        if not files:
            return 0

        processed = 0
        for file_path in files:
            source_basename = file_path.name
            match = MEDIA_FILE_RE.match(source_basename)
            video_id = match.group("video_id") if match else "unknown"
            status_type = match.group("type") if match else "videos"
            base = match.group("base") if match else file_path.stem
            if " - " in base:
                title, uploader = base.rsplit(" - ", 1)
            else:
                title, uploader = base, channel_name
            title = fix_mojibake(title[:180])
            uploader = fix_mojibake(uploader)
            channel_name = fix_mojibake(channel_name)
            emoji, _label = TYPE_LABELS.get(status_type, TYPE_LABELS["videos"])

            self.new_count += 1
            processed += 1
            self.state = "downloading"
            self.current_type = status_type
            self.video_title = title
            self.video_thumbnail = self.find_status_thumbnail(file_path)
            self.download_percent = "100"
            self.download_speed = ""
            self.download_eta = ""
            self.progress_bucket = "100"
            self.set_type_status(status_type, "downloading")
            self.write_status()
            with contextlib.suppress(OSError):
                self.last_download_file.write_text(str(int(time.time())) + "\n", encoding="utf-8")

            self.log(f"   🔔 Найдено новое видео ({title})")
            self.log("   ⏬ Видео скачено")
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            post = (
                f'{emoji} <a href="{html.escape(video_url, quote=True)}">{html.escape(title, quote=False)}</a>\n'
                f'👤 <a href="{html.escape(channel_link, quote=True)}">{html.escape(uploader, quote=False)}</a>'
            )

            if not self.telegram_enabled:
                self.log("   🔕 Telegram отключён")
            else:
                if self.send_telegram_message(post):
                    self.log("   📨 Отправлено в канал")
                else:
                    self.log("   ❌ Не отправлено в канал")
                    self.log("   📁 Telegram не помешает сохранению файла")
                    self.failed_count += 1

            try:
                self.final_dir.mkdir(parents=True, exist_ok=True)
                final_path = self.unique_final_path(self.variant_final_basename(source_basename))
                shutil.move(str(file_path), str(final_path))
                self.ensure_video_in_archive(video_id)
                self.append_archive_details(video_id, video_url, title, uploader, channel_link, status_type, final_path)
                self.downloaded_counts[status_type] = self.downloaded_counts.get(status_type, 0) + 1
                self.log(f"   ⚓ Видео перемещено: {final_path}")
            except Exception as exc:
                self.log(f"   ❌ Видео не перемещено: {exc}")
                self.failed_count += 1
                self.remove_video_from_archive(video_id)

            self.set_type_status(status_type, "done")
            self.state = "searching"
            self.reset_progress()
            self.write_status()
            if check_stop_after:
                self.check_stop()
            time.sleep(3)
        return processed

    def yt_dlp_base_command(self, output_template: str) -> list[str]:
        command = yt_dlp_command() + [
            "-f",
            self.format_selector,
            "--merge-output-format",
            "mp4",
            "--write-thumbnail",
            "--embed-thumbnail",
            "--convert-thumbnails",
            "jpg",
            "--download-archive",
            str(self.archive_file),
            "--match-filter",
            "!is_live",
            "-o",
            output_template,
            "--embed-subs",
            "--embed-metadata",
            "--embed-chapters",
            "--ignore-errors",
            "--no-abort-on-error",
            "--no-warnings",
            "--retries",
            "20",
            "--fragment-retries",
            "20",
            "--no-cache-dir",
            "--js-runtimes",
            self.js_runtime_arg(),
            "--newline",
        ]
        if self.ffmpeg_dir:
            command.extend(["--ffmpeg-location", str(self.ffmpeg_dir)])
        if len(self.audio_tracks) > 1:
            command.append("--audio-multistreams")
        audio_metadata_args = self.audio_metadata_postprocessor_args()
        if audio_metadata_args:
            command.extend(["--postprocessor-args", audio_metadata_args])
        if self.audio_format_id and self.audio_player_client:
            command.extend(["--extractor-args", f"youtube:player_client={self.audio_player_client}"])
        if not self.subtitle_selections:
            command.extend(["--no-write-subs", "--no-write-auto-subs", "--no-embed-subs"])
        else:
            languages = [selection.partition(":")[2] for selection in self.subtitle_selections if selection.partition(":")[2]]
            modes = {selection.partition(":")[0] for selection in self.subtitle_selections}
            command.extend(["--sub-langs", ",".join(languages), "--sub-format", "vtt/best", "--embed-subs"])
            command.append("--write-subs" if "manual" in modes else "--no-write-subs")
            command.append("--write-auto-subs" if "auto" in modes else "--no-write-auto-subs")
        if os.name == "nt":
            command.append("--windows-filenames")
        return command

    def process_queue_urls(self, queued_urls: list[str], retry_failed: bool, *, allow_variants: bool = False) -> None:
        for url in queued_urls:
            self.check_stop()
            self.state = "searching"
            self.channel_url = url
            self.channel_name = "Очередь"
            self.current_type = "queue"
            self.video_title = ""
            self.video_thumbnail = ""
            self.reset_progress()
            self.write_status()

            self.log(f"📥 Очередь: {url}")
            video_id = extract_video_id(url)
            bypass_service_archive = False
            if video_id:
                if allow_variants:
                    if self.archive_details_has_variant(video_id):
                        self.log(f"   🗃 Такой вариант уже есть в архиве, пропускаем: {video_id}")
                        self.state = "searching"
                        self.write_status()
                        continue
                    bypass_service_archive = self.archive_has_video(video_id)
                elif self.archive_has_video(video_id):
                    self.log(f"   🗃 Уже есть в архиве, пропускаем: {video_id}")
                    self.state = "searching"
                    self.write_status()
                    continue

            before = self.new_count
            command = self.yt_dlp_base_command(str(self.temp_dir / "%(title).150s - %(uploader).80s [%(id)s] [queue] [%(height)sp].%(ext)s"))
            command.append("--no-playlist")
            if bypass_service_archive:
                command.append("--no-download-archive")
            command.append(url)
            lines = self.run_yt_dlp_with_subtitle_fallback(command, "queue")
            self.process_type_lines(lines, url, "Очередь", "queue")
            if self.new_count == before and not any("has already been recorded in the archive" in line for line in lines):
                if self.output_has_members_only(lines):
                    self.log("   🔒 Ссылка из очереди закрыта для участников, повтор не нужен")
                    continue
                if retry_failed:
                    with self.queue_file.open("a", encoding="utf-8") as queue:
                        queue.write(url + "\n")
                    self.log("   ⚠️ Не скачано из очереди, оставлено для повтора")
                else:
                    self.log("   ⚠️ Не скачано из очереди, повтор отключён")
                self.failed_count += 1

    def process_queue(self) -> None:
        queued_urls = self.read_nonempty_lines(self.queue_file)
        if not queued_urls:
            return
        self.save_queue([])
        self.process_queue_urls(queued_urls, self.retry_failed_queue)

    def process_channels(self) -> None:
        channels = self.read_nonempty_lines(self.channels_file)
        self.channels_total = len(channels)
        self.channels_checked = 0
        self.write_status()
        for raw_channel in channels:
            self.check_stop()
            channel = raw_channel.rstrip("/")
            self.state = "searching"
            self.channel_url = channel
            self.channel_name = short_channel_name(channel)
            self.current_type = ""
            self.type_status = {"videos": "idle", "shorts": "idle", "streams": "idle"}
            self.video_title = ""
            self.video_thumbnail = ""
            self.reset_progress()
            for initial_type in ("videos", "shorts", "streams"):
                if not self.channel_type_enabled(channel, initial_type):
                    self.set_type_status(initial_type, "disabled")
            self.write_status()

            self.log(f"👤 Смотрим {self.channel_name}")
            for type_name in ("videos", "shorts", "streams"):
                self.check_stop()
                emoji, label = TYPE_LABELS[type_name]
                if not self.channel_type_enabled(channel, type_name):
                    self.state = "searching"
                    self.current_type = type_name
                    self.video_title = ""
                    self.video_thumbnail = ""
                    self.reset_progress()
                    self.set_type_status(type_name, "disabled")
                    self.write_status()
                    self.log(f"-{emoji} Пропускаем - {label} отключены для канала")
                    continue

                self.state = "searching"
                self.current_type = type_name
                self.video_title = ""
                self.video_thumbnail = ""
                self.reset_progress()
                self.set_type_status(type_name, "searching")
                self.write_status()
                self.log(f"-{emoji} Ищем - {label}")

                before = self.new_count
                output_template = str(self.temp_dir / f"%(title).150s - %(uploader).80s [%(id)s] [{type_name}] [%(height)sp].%(ext)s")
                command = self.yt_dlp_base_command(output_template)
                command.extend(["--playlist-items", f"1-{self.type_limit(type_name)}", f"{channel}/{type_name}"])
                lines = self.run_yt_dlp(
                    command,
                    type_name,
                    item_completed=lambda completed_lines: self.process_type_lines(
                        completed_lines,
                        channel,
                        self.channel_name,
                        type_name,
                        check_stop_after=False,
                    ),
                )

                if self.new_count == before:
                    if any(MISSING_PAGE_RE.search(line) for line in lines):
                        self.set_type_status(type_name, "missing")
                    else:
                        self.set_type_status(type_name, "done")
                    self.state = "searching"
                    self.current_type = type_name
                    self.reset_progress()
                    self.write_status()
                time.sleep(1)
            self.channels_checked += 1
            self.state = "searching"
            self.current_type = ""
            self.reset_progress()
            self.write_status()

    def cleanup_temp_dir(self) -> None:
        self.log("Жёсткая очистка временной папки...")
        if not self.temp_dir.exists():
            return
        if not self.can_cleanup_temp_dir():
            self.log(f"⚠️ Очистка временной папки пропущена: небезопасный путь {self.temp_dir}")
            return
        for item in self.temp_dir.iterdir():
            if item == self.temp_marker_file:
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except OSError:
                pass

    def _path_contains(self, parent: Path, child: Path) -> bool:
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False

    def is_dedicated_temp_dir(self) -> bool:
        try:
            temp = self.temp_dir.resolve(strict=False)
        except OSError:
            temp = self.temp_dir
        name = temp.name.casefold()
        parent_name = temp.parent.name.casefold()
        dedicated_names = {"yth", "ytd", "yt-harvester", "youtube-harvester", "youtubeharvester"}
        if name in dedicated_names:
            return True
        return parent_name in {"temp", "tmp"} and any(part in name for part in dedicated_names)

    def can_cleanup_temp_dir(self) -> bool:
        try:
            temp = self.temp_dir.resolve(strict=False)
            final = self.final_dir.resolve(strict=False)
            forbidden = {
                Path(temp.anchor).resolve(strict=False),
                Path.home().resolve(strict=False),
                self.base_dir.resolve(strict=False),
                self.data_dir.resolve(strict=False),
                self.config_dir.resolve(strict=False),
                final,
            }
            if temp in forbidden:
                return False
            if self._path_contains(temp, final):
                return False
            if self.temp_marker_file.exists():
                return True
            if self.is_dedicated_temp_dir():
                self.temp_marker_file.write_text("YouTube Harvester temp directory\n", encoding="utf-8")
                return True
            return False
        except OSError:
            return False

    def rotate_logs(self, exit_code: int) -> int:
        self.log("Ротация логов...")
        self.log(f"=== Жатва завершена {_dt.datetime.now():%Y-%m-%d %H:%M:%S} ===")
        if self.state == "stopping":
            self.state = "stopped"
        elif self.state != "stopped":
            self.state = "sleep"
        self.run_completed_at = int(time.time())
        self.current_type = ""
        self.reset_progress()
        self.write_status()

        try:
            if self.log_file.exists():
                shutil.move(str(self.log_file), str(self.archived_log))
        except OSError:
            pass
        logs = sorted(self.data_dir.glob("download_*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
        for old_log in logs[self.log_keep_count :]:
            with contextlib.suppress(OSError):
                old_log.unlink()
        return exit_code

    def validate_telegram(self) -> bool:
        if not self.telegram_enabled:
            return True
        if not self.bot_token:
            safe_print(
                f"BOT_TOKEN is not set. Add it to {self.env_file} or disable Telegram notifications",
                file=sys.stderr,
            )
            return False
        if not self.channel_id:
            safe_print(
                f"CHANNEL_ID is not set. Add it to {self.env_file} or disable Telegram notifications",
                file=sys.stderr,
            )
            return False
        return True

    def run(self) -> int:
        self.prepare()
        if not self.validate_free_space():
            return self.rotate_logs(1)
        if not self.validate_telegram():
            return 1
        if os.name == "nt" and not self.ffmpeg_dir:
            self.log("❌ ffmpeg.exe и ffprobe.exe не найдены")
            self.log("   Windows-сборке нужны bundled ffmpeg/ffprobe для склейки видео и аудио")
            return self.rotate_logs(1)
        if os.name == "nt" and not self.deno_path:
            self.log("❌ deno.exe не найден")
            self.log("   Windows-сборке нужен bundled Deno для полной поддержки YouTube")
            return self.rotate_logs(1)
        self.log(f"=== Жатва началась {_dt.datetime.now():%Y-%m-%d %H:%M:%S} ===")
        self.log("🧩 Движок: Python")
        self.state = "searching"
        self.write_status()

        try:
            self.check_stop()
            if self.single_queue_url:
                self.process_queue_urls([self.single_queue_url], retry_failed=False, allow_variants=True)
            else:
                self.process_queue()
                self.process_channels()
                if self.read_nonempty_lines(self.queue_file):
                    self.log("📥 Повторная обработка очереди после проверки каналов")
                    self.process_queue()
        except KeyboardInterrupt:
            return self.rotate_logs(0)

        if self.new_count == 0:
            self.log("   📌Новых видео не найдено")
            if self.failed_count:
                self.log(f"⚠️ Были ошибки обработки: {self.failed_count}")
                self.log("⚠️ Временная папка не очищена, чтобы не потерять файлы для повтора/ручной проверки")
            elif self.cleanup_temp:
                self.cleanup_temp_dir()
            else:
                self.log("🧹 Очистка временной папки отключена")
            return self.rotate_logs(1 if self.failed_count else 0)

        self.log(f"✳️ Найдено новых видео: {self.new_count}")
        if self.failed_count == 0:
            if self.cleanup_temp:
                self.cleanup_temp_dir()
            else:
                self.log("🧹 Очистка временной папки отключена")
        else:
            self.log(f"⚠️ Были ошибки обработки: {self.failed_count}")
            self.log("⚠️ Временная папка не очищена, чтобы не потерять файлы для повтора/ручной проверки")
        return self.rotate_logs(1 if self.failed_count else 0)


def main() -> int:
    lock = SingleInstanceLock("yt_harvester_downloader.lock")
    if not lock.acquire():
        safe_print("Already running")
        return 0
    try:
        return Downloader().run()
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
