#!/usr/bin/env python3
"""Mark recent channel entries as already downloaded in yt-dlp archive."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from yth_common import (  # noqa: E402
    channel_section_url, channel_sections, deno_runtime_arg, media_key,
    media_source_from_url, normalize_channel_url, normalize_media_source,
    utf8_subprocess_env, yt_dlp_command,
)


VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
RUTUBE_ID_RE = re.compile(r"^[a-z0-9]{32}$")


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def collect_ids(yt_dlp: list[str], channel: str, section: str, limit: int) -> tuple[list[str], str]:
    url = channel_section_url(channel, section)
    if not url:
        return [], ""
    id_pattern = RUTUBE_ID_RE if media_source_from_url(channel) == "rutube" else VIDEO_ID_RE
    command = yt_dlp + [
        "--ignore-config",
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
            capture_output=True,
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
        if id_pattern.fullmatch(item) and item not in seen:
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
    for raw_line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lines.add(line)
        parts = line.split()
        if len(parts) == 2:
            key = media_key(normalize_media_source(parts[0]), parts[1])
            if key:
                ids.add(key)
    return lines, ids


def append_archive(path: Path, video_ids: list[str], known_lines: set[str], known_ids: set[str], source: str = "youtube") -> int:
    source = normalize_media_source(source)
    if source not in {"youtube", "rutube"}:
        raise ValueError("Unsupported channel source")
    new_lines = []
    for video_id in video_ids:
        archive_line = f"{source} {video_id}"
        key = media_key(source, video_id)
        if key in known_ids or archive_line in known_lines:
            continue
        known_ids.add(key)
        known_lines.add(archive_line)
        new_lines.append(archive_line)

    if not new_lines:
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = False
    if path.exists() and path.stat().st_size:
        with path.open("rb") as existing:
            existing.seek(-1, 2)
            needs_newline = existing.read(1) not in {b"\n", b"\r"}
    with path.open("a", encoding="utf-8") as archive:
        if needs_newline:
            archive.write("\n")
        for line in new_lines:
            archive.write(line + "\n")
    return len(new_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark recent YouTube or Rutube channel items as downloaded.")
    parser.add_argument("--channel", required=True, help="YouTube or Rutube channel URL")
    parser.add_argument("--archive", required=True, help="yt-dlp archive file")
    parser.add_argument("--videos-limit", type=positive_int, default=5)
    parser.add_argument("--shorts-limit", type=positive_int, default=5)
    parser.add_argument("--streams-limit", type=positive_int, default=5)
    args = parser.parse_args()
    args.channel = normalize_channel_url(args.channel)
    if not args.channel:
        parser.error("Invalid YouTube or Rutube channel URL")
    source = media_source_from_url(args.channel)

    yt_dlp = yt_dlp_command(allow_missing=False)
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
        if section not in channel_sections(args.channel):
            continue
        ids, error = collect_ids(yt_dlp, args.channel, section, limit)
        added = append_archive(archive_path, ids, known_lines, known_ids, source)
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
