#!/usr/bin/env python3
"""Experimental Python downloader engine for YouTube Harvester.

The stable engine is still run_download.sh. This file mirrors the same public
contract: status.json, queue.txt, yt_archive.txt, archive_details.jsonl and the
same YTD_* environment variables.
"""

from __future__ import annotations

import datetime as _dt
import glob
import html
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path


TYPE_LABELS = {
    "videos": ("🎬", "Видео"),
    "shorts": ("📱", "Shorts"),
    "streams": ("🔴", "Трансляция"),
    "queue": ("📥", "Очередь"),
}

MEDIA_FILE_RE = re.compile(
    r"^(?P<base>.*) \[(?P<video_id>[A-Za-z0-9_-]{11})\] "
    r"\[(?P<type>videos|shorts|streams|queue)\] \[[^]]+\]\.mp4$"
)

MISSING_PAGE_RE = re.compile(
    r"does not have.*tab|No entries|No items|No video|No shorts|No streams|does not exist|not found|HTTP Error 404",
    re.IGNORECASE,
)


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "да"}


def positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def safe_print(message: object, *, file=None) -> None:
    stream = file if file is not None else sys.stdout
    if stream is None:
        return
    text = str(message)
    try:
        print(text, file=stream)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_text, file=stream)


def env_quote_value(line: str) -> tuple[str, str] | None:
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    if text.startswith("export "):
        text = text[7:].strip()
    try:
        parts = shlex.split(text, comments=False, posix=True)
    except ValueError:
        parts = [text]
    if not parts or "=" not in parts[0]:
        return None
    key, value = parts[0].split("=", 1)
    return key.strip(), value


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore").replace("\r\n", "\n")
    except OSError:
        return values
    for line in text.splitlines():
        item = env_quote_value(line)
        if item:
            values[item[0]] = item[1]
    return values


def yt_dlp_command() -> list[str]:
    configured = os.environ.get("YTD_YT_DLP_COMMAND", "").strip()
    if configured:
        try:
            return shlex.split(configured, posix=(os.name != "nt"))
        except ValueError:
            return [configured]
    found = shutil.which("yt-dlp")
    return [found] if found else ["yt-dlp"]


def short_channel_name(channel: str) -> str:
    text = channel.rstrip("/")
    if "/@" in text:
        return text.rsplit("/@", 1)[-1]
    return text.rsplit("/", 1)[-1]


def extract_video_id(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.netloc.lower().endswith("youtu.be"):
            candidate = parsed.path.strip("/").split("/")[0]
            if len(candidate) == 11:
                return candidate
        query = urllib.parse.parse_qs(parsed.query)
        candidate = (query.get("v") or [""])[0]
        if len(candidate) == 11:
            return candidate
        parts = [part for part in parsed.path.split("/") if part]
        for marker in ("shorts", "live", "embed"):
            if marker in parts:
                index = parts.index(marker)
                if index + 1 < len(parts) and len(parts[index + 1]) == 11:
                    return parts[index + 1]
    except Exception:
        return ""
    return ""


class SingleInstanceLock:
    def __init__(self) -> None:
        lock_dir = Path(tempfile.gettempdir())
        self.path = lock_dir / "yt_harvester.lock"
        self.handle = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        try:
            if os.name == "nt":
                import msvcrt

                try:
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    return False
            else:
                import fcntl

                try:
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    return False
        except Exception:
            return True
        return True

    def release(self) -> None:
        if not self.handle:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            self.handle.close()
        except Exception:
            pass


class Downloader:
    def __init__(self) -> None:
        self.base_dir = Path(os.environ.get("YTD_APP_DIR", Path(__file__).resolve().parents[1]))
        self.data_dir = Path(os.environ.get("YTD_DATA_DIR", self.base_dir))
        self.config_dir = Path(os.environ.get("YTD_CONFIG_DIR", self.data_dir))
        self.channels_file = Path(os.environ.get("YTD_CHANNELS_FILE", self.data_dir / "channels.txt"))
        self.queue_file = Path(os.environ.get("YTD_QUEUE_FILE", self.data_dir / "queue.txt"))
        self.archive_file = Path(os.environ.get("YTD_ARCHIVE_FILE", self.data_dir / "yt_archive.txt"))
        self.archive_details_file = Path(os.environ.get("YTD_ARCHIVE_DETAILS_FILE", self.data_dir / "archive_details.jsonl"))
        self.env_file = Path(os.environ.get("YTD_ENV_FILE", self.config_dir / ".env"))
        self.status_file = Path(os.environ.get("YTD_STATUS_FILE", self.data_dir / "status.json"))
        self.stop_file = Path(os.environ.get("YTD_STOP_FILE", self.data_dir / "stop_requested"))
        self.last_download_file = Path(os.environ.get("YTD_LAST_DOWNLOAD_FILE", self.data_dir / "last_download_at.txt"))
        self.channel_rules_file = Path(os.environ.get("YTD_CHANNEL_RULES_FILE", self.config_dir / "channel_rules.json"))
        self.temp_dir = Path(os.environ.get("YTD_TEMP_DIR", Path.home() / "temp" / "YTH"))
        self.final_dir = Path(os.environ.get("YTD_FINAL_DIR", Path.home() / "Downloads" / "YouTubeHarvester"))
        self.log_file = Path(os.environ.get("YTD_LOG_FILE", self.data_dir / "download.log"))

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
        self.format_selector = self.build_format_selector(self.max_resolution)

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
        self.archived_log = self.data_dir / f"download_{_dt.datetime.now():%Y-%m-%d_%H-%M}.log"

    def build_format_selector(self, value: str) -> str:
        if value in {"480", "720", "1080", "1440", "2160"}:
            return (
                f"bestvideo[ext=mp4][height<={value}]+bestaudio[ext=m4a]/"
                f"best[ext=mp4][height<={value}]/best[height<={value}]"
            )
        self.max_resolution = "best" if value.lower() == "best" else "1080"
        if self.max_resolution == "best":
            return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        return "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best[height<=1080]"

    def prepare(self) -> None:
        for path in (self.data_dir, self.config_dir, self.temp_dir, self.final_dir):
            path.mkdir(parents=True, exist_ok=True)
        for path in (self.channels_file, self.archive_file, self.archive_details_file, self.log_file, self.queue_file):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        try:
            self.stop_file.unlink(missing_ok=True)
        except OSError:
            pass

    def log(self, message: str) -> None:
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
        if isinstance(value, str) and value.strip().lower() in {"0", "false", "no", "off"}:
            return False
        return True

    def archive_has_video(self, video_id: str) -> bool:
        if not video_id:
            return False
        try:
            if self.archive_file.exists() and video_id in self.archive_file.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            pass
        return self.archive_details_has_video(video_id)

    def archive_details_has_video(self, video_id: str) -> bool:
        if not video_id:
            return False
        needle = f'"video_id":"{video_id}"'
        try:
            return needle in self.archive_details_file.read_text(encoding="utf-8", errors="ignore").replace(" ", "")
        except OSError:
            return False

    def remove_video_from_archive(self, video_id: str) -> None:
        if not video_id or not self.archive_file.exists():
            return
        try:
            lines = self.archive_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            kept = [line for line in lines if video_id not in line]
            self.archive_file.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
            self.log(f"   ↩️ Убран из архива для повтора: {video_id}")
        except OSError:
            pass

    def append_archive_details(self, video_id: str, url: str, title: str, channel: str, channel_url: str, type_name: str, file_path: Path) -> None:
        if video_id != "unknown" and self.archive_details_has_video(video_id):
            self.log(f"   🗃 Запись уже есть в архиве: {video_id}")
            return
        entry = {
            "video_id": video_id,
            "youtube_url": url,
            "title": title,
            "channel_name": channel,
            "channel_url": channel_url,
            "downloaded_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "downloaded_at_ts": int(time.time()),
            "type": type_name,
            "file_path": str(file_path),
            "filename": file_path.name,
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
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60, check=False)
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

    def run_yt_dlp(self, command: list[str], type_name: str) -> list[str]:
        lines: list[str] = []
        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError:
            self.log("❌ yt-dlp не найден")
            self.failed_count += 1
            return lines

        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.rstrip("\n")
            self.update_status_from_line(line, type_name)
            if not re.match(r"^\[download\]\s+[0-9]+(?:\.[0-9]+)?%", line):
                self.log(line)
                lines.append(line)
        proc.wait()
        return lines

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
        return sorted(found, key=lambda item: str(item))

    def process_type_lines(self, lines: list[str], channel_link: str, channel_name: str) -> int:
        files = self.downloaded_files_from_lines(lines)
        if not files:
            return 0

        processed = 0
        for file_path in files:
            basename = file_path.name
            match = MEDIA_FILE_RE.match(basename)
            video_id = match.group("video_id") if match else "unknown"
            status_type = match.group("type") if match else "videos"
            base = match.group("base") if match else file_path.stem
            if " - " in base:
                title, uploader = base.rsplit(" - ", 1)
            else:
                title, uploader = base, channel_name
            title = title[:180]
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
            try:
                self.last_download_file.write_text(str(int(time.time())) + "\n", encoding="utf-8")
            except OSError:
                pass

            self.log(f"   🔔 Найдено новое видео ({title})")
            self.log("   ⏬ Видео скачено")
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            post = (
                f'{emoji} <a href="{html.escape(video_url, quote=True)}">{html.escape(title, quote=False)}</a>\n'
                f'👤 <a href="{html.escape(channel_link, quote=True)}">{html.escape(uploader, quote=False)}</a>'
            )

            if not self.telegram_enabled:
                self.log("   🔕 Telegram отключён")
                sent_ok = True
            else:
                sent_ok = self.send_telegram_message(post)
                if sent_ok:
                    self.log("   📨 Отправлено в канал")
                else:
                    self.log("   ❌ Не отправлено в канал")
                    self.failed_count += 1
                    self.remove_video_from_archive(video_id)

            if sent_ok:
                try:
                    final_path = self.final_dir / basename
                    shutil.move(str(file_path), str(final_path))
                    self.append_archive_details(video_id, video_url, title, uploader, channel_link, status_type, final_path)
                    self.log("   ⚓ Видео перемещено")
                except Exception:
                    self.log("   ❌ Видео не перемещено")
                    self.failed_count += 1
                    self.remove_video_from_archive(video_id)
            else:
                self.log(f"   ⚠️ Файл оставлен во временной папке: {basename}")

            self.set_type_status(status_type, "done")
            self.state = "searching"
            self.reset_progress()
            self.write_status()
            self.check_stop()
            time.sleep(3)
        return processed

    def yt_dlp_base_command(self, output_template: str) -> list[str]:
        return yt_dlp_command() + [
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
            "deno",
            "--newline",
        ]

    def process_queue(self) -> None:
        queued_urls = self.read_nonempty_lines(self.queue_file)
        if not queued_urls:
            return
        self.save_queue([])

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
            if video_id and self.archive_has_video(video_id):
                self.log(f"   🗃 Уже есть в архиве, пропускаем: {video_id}")
                self.state = "searching"
                self.write_status()
                continue

            before = self.new_count
            command = self.yt_dlp_base_command(str(self.temp_dir / "%(title)s - %(uploader)s [%(id)s] [queue] [%(height)sp].%(ext)s"))
            command.append("--no-playlist")
            command.append(url)
            lines = self.run_yt_dlp(command, "queue")
            self.process_type_lines(lines, url, "Очередь")
            if self.new_count == before and not any("has already been recorded in the archive" in line for line in lines):
                if self.retry_failed_queue:
                    with self.queue_file.open("a", encoding="utf-8") as queue:
                        queue.write(url + "\n")
                    self.log("   ⚠️ Не скачано из очереди, оставлено для повтора")
                else:
                    self.log("   ⚠️ Не скачано из очереди, повтор отключён")
                self.failed_count += 1

    def process_channels(self) -> None:
        channels = self.read_nonempty_lines(self.channels_file)
        self.channels_total = len(channels)
        self.channels_checked = 0
        self.write_status()
        for channel in channels:
            self.check_stop()
            channel = channel.rstrip("/")
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
                output_template = str(self.temp_dir / f"%(title)s - %(uploader)s [%(id)s] [{type_name}] [%(height)sp].%(ext)s")
                command = self.yt_dlp_base_command(output_template)
                command.extend(["--playlist-items", f"1-{self.type_limit(type_name)}", f"{channel}/{type_name}"])
                lines = self.run_yt_dlp(command, type_name)
                self.process_type_lines(lines, channel, self.channel_name)

                if self.new_count == before:
                    if any(MISSING_PAGE_RE.search(line) for line in lines):
                        self.set_type_status(type_name, "missing")
                    else:
                        self.set_type_status(type_name, "done")
                    self.state = "searching"
                    self.current_type = type_name
                    self.reset_progress()
                    self.write_status()
                if type_name == "streams":
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
        for item in self.temp_dir.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except OSError:
                pass

    def rotate_logs(self, exit_code: int) -> int:
        self.log("Ротация логов...")
        self.log(f"=== Жатва завершена {_dt.datetime.now():%Y-%m-%d %H:%M:%S} ===")
        if self.state == "stopping":
            self.state = "stopped"
        elif self.state != "stopped":
            self.state = "sleep"
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
            try:
                old_log.unlink()
            except OSError:
                pass
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
        if not self.validate_telegram():
            return 1
        self.log(f"=== Жатва началась {_dt.datetime.now():%Y-%m-%d %H:%M:%S} ===")
        self.log("🧩 Движок: Python")
        self.state = "searching"
        self.write_status()

        try:
            self.check_stop()
            self.process_queue()
            self.process_channels()
        except KeyboardInterrupt:
            return self.rotate_logs(0)

        if self.new_count == 0:
            self.log("   📌Новых видео не найдено")
            if self.cleanup_temp:
                self.cleanup_temp_dir()
            else:
                self.log("🧹 Очистка временной папки отключена")
            return self.rotate_logs(0)

        self.log(f"✳️ Найдено новых видео: {self.new_count}")
        if self.failed_count == 0:
            if self.cleanup_temp:
                self.cleanup_temp_dir()
            else:
                self.log("🧹 Очистка временной папки отключена")
        else:
            self.log(f"⚠️ Были ошибки обработки: {self.failed_count}")
            self.log("⚠️ Временная папка не очищена, чтобы не потерять файлы для повтора/ручной проверки")
        return self.rotate_logs(0)


def main() -> int:
    lock = SingleInstanceLock()
    if not lock.acquire():
        safe_print("Already running")
        return 0
    try:
        return Downloader().run()
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
