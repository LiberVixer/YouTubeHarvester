#!/usr/bin/env python3
"""Build detailed YouTube Harvester archive records from old archive and files."""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
ARCHIVE_ID_RE = re.compile(r"\b([A-Za-z0-9_-]{11})\b")
MEDIA_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}
YTD_FILE_RE = re.compile(
    r"^(?P<title>.+) - (?P<channel>.+?) "
    r"\[(?P<video_id>[A-Za-z0-9_-]{11})\] "
    r"\[(?P<type>videos|shorts|streams|queue)\] "
    r"\[(?P<quality>[^\]]+)\]\.(?P<ext>[^.]+)$"
)


def read_archive_ids(path: Path) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    if not path.exists():
        return ids
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        for video_id in ARCHIVE_ID_RE.findall(line):
            if video_id not in seen:
                ids.append(video_id)
                seen.add(video_id)
    return ids


def read_existing_details(path: Path) -> tuple[set[str], set[str]]:
    video_ids: set[str] = set()
    file_paths: set[str] = set()
    if not path.exists():
        return video_ids, file_paths
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("video_id") or "").strip()
        file_path = str(entry.get("file_path") or "").strip()
        if VIDEO_ID_RE.match(video_id):
            video_ids.add(video_id)
        if file_path:
            file_paths.add(str(Path(file_path)))
    return video_ids, file_paths


def iter_media_files(scan_dirs: list[Path]):
    seen: set[Path] = set()
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        if scan_dir.is_file():
            candidates = [scan_dir]
        else:
            candidates = scan_dir.rglob("*")
        for path in candidates:
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in seen or not path.is_file():
                continue
            if path.suffix.lower() not in MEDIA_EXTENSIONS:
                continue
            seen.add(resolved)
            yield path


def entry_from_file(path: Path) -> dict | None:
    match = YTD_FILE_RE.match(path.name)
    if not match:
        return None

    info = match.groupdict()
    try:
        timestamp = int(path.stat().st_mtime)
    except OSError:
        timestamp = 0
    downloaded_at = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "неизвестно"

    video_id = info["video_id"]
    return {
        "video_id": video_id,
        "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
        "title": info["title"].strip(),
        "channel_name": info["channel"].strip(),
        "channel_url": "",
        "downloaded_at": downloaded_at,
        "downloaded_at_ts": timestamp,
        "type": info["type"],
        "file_path": str(path),
        "filename": path.name,
        "migrated": True,
        "migration_source": "file",
    }


def entry_from_archive_id(video_id: str) -> dict:
    return {
        "video_id": video_id,
        "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
        "title": f"ID: {video_id}",
        "channel_name": "",
        "channel_url": "",
        "downloaded_at": "неизвестно",
        "type": "",
        "file_path": "",
        "filename": "",
        "migrated": True,
        "migration_source": "yt_archive",
    }


def append_entries(path: Path, entries: list[dict]) -> None:
    if not entries:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as details:
        for entry in entries:
            details.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate YouTube Harvester archive to detailed JSONL archive.")
    parser.add_argument("--archive", required=True, help="Old yt-dlp archive file")
    parser.add_argument("--details", required=True, help="Detailed JSONL archive file")
    parser.add_argument("--scan-dir", action="append", default=[], help="Directory or file to scan for downloaded videos")
    parser.add_argument("--include-missing", action="store_true", help="Add old archive IDs even when no file is found")
    args = parser.parse_args()

    archive_path = Path(args.archive)
    details_path = Path(args.details)
    scan_dirs = [Path(item).expanduser() for item in args.scan_dir]

    archive_ids = read_archive_ids(archive_path)
    archive_id_set = set(archive_ids)
    known_ids, known_paths = read_existing_details(details_path)

    entries: list[dict] = []
    file_ids: set[str] = set()
    scanned_files = 0
    matched_files = 0

    for path in iter_media_files(scan_dirs):
        scanned_files += 1
        entry = entry_from_file(path)
        if entry is None:
            continue
        matched_files += 1
        video_id = entry["video_id"]
        file_path = entry["file_path"]
        file_ids.add(video_id)
        if video_id in known_ids or file_path in known_paths:
            continue
        entries.append(entry)
        known_ids.add(video_id)
        known_paths.add(file_path)

    file_entries_added = len(entries)
    missing_entries_added = 0
    if args.include_missing:
        for video_id in archive_ids:
            if video_id in known_ids or video_id in file_ids:
                continue
            entry = entry_from_archive_id(video_id)
            entries.append(entry)
            known_ids.add(video_id)
            missing_entries_added += 1

    append_entries(details_path, entries)

    payload = {
        "summary": {
            "archive_ids": len(archive_ids),
            "scanned_files": scanned_files,
            "matched_files": matched_files,
            "file_records_added": file_entries_added,
            "missing_records_added": missing_entries_added,
            "total_added": len(entries),
            "already_known": len(archive_id_set & known_ids) - missing_entries_added,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
