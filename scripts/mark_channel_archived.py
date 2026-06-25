#!/usr/bin/env python3
"""Mark recent channel entries as already downloaded in yt-dlp archive."""

import argparse
import json
import os
import re
import shutil
import shlex
import subprocess
import sys
from pathlib import Path


VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
ARCHIVE_ID_RE = re.compile(r"\b([A-Za-z0-9_-]{11})\b")


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def channel_section_url(channel: str, section: str) -> str:
    return channel.strip().rstrip("/") + "/" + section


def yt_dlp_command() -> list[str]:
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
    return [found] if found else []


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
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def collect_ids(yt_dlp: list[str], channel: str, section: str, limit: int) -> tuple[list[str], str]:
    url = channel_section_url(channel, section)
    command = yt_dlp + [
        "--js-runtimes",
        deno_runtime_arg(),
        "--flat-playlist",
        "--playlist-items",
        f"1-{limit}",
        "--print",
        "%(id)s",
        "--no-warnings",
        "--ignore-errors",
        url,
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=utf8_subprocess_env(),
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [], "таймаут yt-dlp"
    except Exception as exc:
        return [], str(exc)

    ids: list[str] = []
    seen = set()
    for line in result.stdout.splitlines():
        item = line.strip()
        if VIDEO_ID_RE.match(item) and item not in seen:
            ids.append(item)
            seen.add(item)

    error = ""
    if result.returncode != 0 and not ids:
        error = (result.stderr or "yt-dlp не смог прочитать раздел").strip()
    return ids, error


def read_archive(path: Path) -> tuple[set[str], set[str]]:
    lines = set()
    ids = set()
    if not path.exists():
        return lines, ids
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lines.add(line)
        for match in ARCHIVE_ID_RE.findall(line):
            ids.add(match)
    return lines, ids


def append_archive(path: Path, video_ids: list[str], known_lines: set[str], known_ids: set[str]) -> int:
    new_lines = []
    for video_id in video_ids:
        archive_line = f"youtube {video_id}"
        if video_id in known_ids or archive_line in known_lines:
            continue
        known_ids.add(video_id)
        known_lines.add(archive_line)
        new_lines.append(archive_line)

    if not new_lines:
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as archive:
        for line in new_lines:
            archive.write(line + "\n")
    return len(new_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark recent YouTube channel items as downloaded.")
    parser.add_argument("--channel", required=True, help="YouTube channel URL")
    parser.add_argument("--archive", required=True, help="yt-dlp archive file")
    parser.add_argument("--videos-limit", type=positive_int, default=5)
    parser.add_argument("--shorts-limit", type=positive_int, default=5)
    parser.add_argument("--streams-limit", type=positive_int, default=5)
    args = parser.parse_args()

    yt_dlp = yt_dlp_command()
    if not yt_dlp:
        print("yt-dlp не найден", file=sys.stderr)
        return 2

    archive_path = Path(args.archive)
    known_lines, known_ids = read_archive(archive_path)
    sections = (
        ("videos", "videos", args.videos_limit),
        ("shorts", "shorts", args.shorts_limit),
        ("streams", "streams", args.streams_limit),
    )

    payload = {
        "channel": args.channel,
        "summary": {
            "total_found": 0,
            "total_added": 0,
        },
        "types": {},
    }

    for type_name, section, limit in sections:
        ids, error = collect_ids(yt_dlp, args.channel, section, limit)
        added = append_archive(archive_path, ids, known_lines, known_ids)
        payload["types"][type_name] = {
            "found": len(ids),
            "added": added,
            "error": error,
        }
        payload["summary"]["total_found"] += len(ids)
        payload["summary"]["total_added"] += added

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
