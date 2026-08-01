from __future__ import annotations

import json
import contextlib
import os
import re
import shlex
import shutil
import sys
import tempfile
import urllib.parse
from pathlib import Path


MOJIBAKE_HINTS = (
    "Рџ", "Р’", "Рђ", "РЅ", "Р°", "Рµ", "Рё", "Рѕ", "СЂ", "СЃ", "С‚", "СЊ",
    "Ð", "Ñ", "вЂ", "вњ", "вљ", "рџ", "�",
)

YOUTUBE_URL_PREFIXES = (
    "https://www.youtube.com/",
    "https://youtube.com/",
    "https://m.youtube.com/",
    "https://youtu.be/",
)

MEDIA_RESOLUTION_RE = re.compile(r"\[(?P<height>\d{3,4})p\]", re.IGNORECASE)


def text_quality(text: str) -> int:
    cyrillic = sum(1 for char in text if "\u0400" <= char <= "\u04ff")
    emoji = sum(1 for char in text if ord(char) >= 0x1F000)
    bad = sum(text.count(marker) for marker in MOJIBAKE_HINTS)
    bad += text.count("\ufffd") * 3
    return cyrillic + emoji * 2 - bad * 8


def fix_mojibake(value):
    if not isinstance(value, str) or not any(marker in value for marker in MOJIBAKE_HINTS):
        return value
    best = value
    best_score = text_quality(value)
    for encoding in ("cp1251", "latin1"):
        try:
            candidate = value.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        score = text_quality(candidate)
        if score > best_score + 2:
            best = candidate
            best_score = score
    return best


def normalize_text_value(value):
    if isinstance(value, str):
        return fix_mojibake(value)
    if isinstance(value, dict):
        return {key: normalize_text_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_text_value(item) for item in value]
    return value


def read_text_for_display(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return fix_mojibake(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    return fix_mojibake(raw.decode("utf-8", errors="replace"))


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "да"}


def positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return default
    return parsed if parsed > 0 else default


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


def yt_dlp_command(allow_missing: bool = True) -> list[str]:
    configured_json = os.environ.get("YTD_YT_DLP_COMMAND_JSON", "").strip()
    if configured_json:
        try:
            configured = json.loads(configured_json)
            if isinstance(configured, list) and all(isinstance(item, str) for item in configured):
                return configured
        except json.JSONDecodeError:
            pass
    configured = os.environ.get("YTD_YT_DLP_COMMAND", "").strip()
    if configured:
        try:
            parts = shlex.split(configured, posix=(os.name != "nt"))
            if os.name == "nt":
                parts = [part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part for part in parts]
            return parts
        except ValueError:
            return [configured]
    found = shutil.which("yt-dlp")
    if found:
        return [found]
    return ["yt-dlp"] if allow_missing else []


def deno_runtime_arg() -> str:
    configured = os.environ.get("YTD_DENO_PATH", "").strip()
    if configured and Path(configured).is_file():
        return f"deno:{configured}"
    found = shutil.which("deno")
    if found:
        return f"deno:{found}"
    return "deno"


def utf8_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8:replace"
    env["PYTHONLEGACYWINDOWSSTDIO"] = "0"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def safe_print(message: object, *, file=None) -> None:
    stream = file if file is not None else sys.stdout
    if stream is None:
        return
    text = fix_mojibake(str(message))
    try:
        print(text, file=stream)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_text, file=stream)


def looks_like_youtube_url(url: str) -> bool:
    return str(url or "").strip().startswith(YOUTUBE_URL_PREFIXES)


def extract_video_id(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(str(url or "").strip())
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


def media_resolution_from_path(value: str | Path | None) -> str:
    match = MEDIA_RESOLUTION_RE.search(str(value or ""))
    return match.group("height") if match else ""


def archive_entry_file_exists(entry: dict) -> bool:
    path_text = str(entry.get("file_path") or "").strip()
    if not path_text:
        return False
    path = Path(path_text)
    candidates = [path]
    if path.name and not path.name.startswith("+"):
        candidates.append(path.with_name("+" + path.name))
    elif path.name.startswith("+") and len(path.name) > 1:
        candidates.append(path.with_name(path.name[1:]))
    for candidate in candidates:
        try:
            if candidate.is_file():
                return True
        except OSError:
            continue
    return False


def archive_entry_matches_variant(
    entry: dict,
    *,
    resolution: str,
    audio_format_id: str = "",
    audio_language: str = "",
    subtitle_selection: str = "none",
    audio_format_ids: list[str] | None = None,
    audio_languages: list[str] | None = None,
    subtitle_selections: list[str] | None = None,
) -> bool:
    requested_resolution = str(entry.get("requested_resolution") or entry.get("resolution") or "").strip().lower()
    if not requested_resolution:
        requested_resolution = media_resolution_from_path(entry.get("filename") or entry.get("file_path"))
    if requested_resolution.rstrip("p") != str(resolution or "").strip().lower().rstrip("p"):
        return False

    selected_audio_ids = sorted({
        str(value or "").strip()
        for value in (audio_format_ids if audio_format_ids is not None else [audio_format_id])
        if str(value or "").strip()
    })
    selected_audio_languages = sorted({
        str(value or "").strip().lower()
        for value in (audio_languages if audio_languages is not None else [audio_language])
        if str(value or "").strip().lower() not in {"", "auto"}
    })
    entry_audio_tracks = entry.get("audio_tracks")
    if isinstance(entry_audio_tracks, list):
        entry_audio_ids = sorted({
            str(track.get("format_id") or "").strip()
            for track in entry_audio_tracks
            if isinstance(track, dict) and str(track.get("format_id") or "").strip()
        })
        entry_audio_languages = sorted({
            str(track.get("language") or "").strip().lower()
            for track in entry_audio_tracks
            if isinstance(track, dict) and str(track.get("language") or "").strip().lower() not in {"", "auto"}
        })
    else:
        entry_audio_id = str(entry.get("audio_format_id") or "").strip()
        entry_audio_ids = [entry_audio_id] if entry_audio_id else []
        entry_audio_language = str(entry.get("audio_language") or "").strip().lower()
        entry_audio_languages = [entry_audio_language] if entry_audio_language not in {"", "auto"} else []
    if selected_audio_ids:
        if entry_audio_ids:
            if entry_audio_ids != selected_audio_ids:
                return False
        elif not selected_audio_languages or entry_audio_languages != selected_audio_languages:
            return False
    elif entry_audio_ids or entry_audio_languages:
        return False

    selected_subtitles = sorted({
        str(value or "").strip().lower()
        for value in (subtitle_selections if subtitle_selections is not None else [subtitle_selection])
        if str(value or "").strip().lower() not in {"", "none"}
    })
    entry_subtitle_values = entry.get("subtitle_selections")
    if isinstance(entry_subtitle_values, list):
        entry_subtitles = sorted({
            str(value or "").strip().lower()
            for value in entry_subtitle_values
            if str(value or "").strip().lower() not in {"", "none"}
        })
    else:
        legacy_subtitle = str(entry.get("subtitle_selection") or "none").strip().lower()
        entry_subtitles = [] if legacy_subtitle in {"", "none"} else [legacy_subtitle]
    return entry_subtitles == selected_subtitles


class SingleInstanceLock:
    def __init__(self, name: str) -> None:
        lock_dir = Path(os.environ.get("YTD_LOCK_DIR") or tempfile.gettempdir())
        if os.name == "nt":
            lock_dir = Path(os.environ.get("TEMP", str(lock_dir)))
        self.path = lock_dir / name
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
        with contextlib.suppress(Exception):
            self.handle.close()
        self.handle = None
