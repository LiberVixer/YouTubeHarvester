#!/usr/bin/env python3
"""Build detailed YouTube Harvester archive records from old archive and files."""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from yth_common import (  # noqa: E402
    archive_entry_media_id,
    archive_entry_source,
    canonical_media_url,
    normalize_media_source,
)

MEDIA_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}
YTD_FILE_RE = re.compile(
    r"^(?P<title>.+) - (?P<channel>.+?) "
    r"\[(?:(?P<source>[A-Za-z0-9_.:-]+)\] \[)?(?P<video_id>[^]]+)\] "
    r"\[(?P<type>videos|shorts|streams|queue)\] "
    r"\[(?P<quality>[^\]]+)\]\.(?P<ext>[^.]+)$"
)


def read_archive_ids(path: Path) -> list[tuple[str, str]]:
    ids: list[tuple[str, str]] = []
    seen: set[str] = set()
    if not path.exists():
        return ids
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        source = normalize_media_source(parts[0])
        video_id = parts[1].strip()
        key = f"{source}:{video_id}"
        if source and video_id and key not in seen:
            ids.append((source, video_id))
            seen.add(key)
    return ids


def read_existing_details(path: Path) -> tuple[set[str], set[str]]:
    media_keys: set[str] = set()
    file_paths: set[str] = set()
    if not path.exists():
        return media_keys, file_paths
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        source = archive_entry_source(entry)
        video_id = archive_entry_media_id(entry)
        file_path = str(entry.get("file_path") or "").strip()
        if source and video_id:
            media_keys.add(f"{source}:{video_id}")
        if file_path:
            file_paths.add(str(Path(file_path)))
    return media_keys, file_paths


def iter_media_files(scan_dirs: list[Path]):
    seen: set[Path] = set()
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        candidates = [scan_dir] if scan_dir.is_file() else scan_dir.rglob("*")
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


def entry_from_file(path: Path, sources_by_id: dict[str, set[str]] | None = None) -> dict | None:
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
    source = normalize_media_source(info.get("source"))
    if not source:
        source_candidates = (sources_by_id or {}).get(video_id, set())
        if len(source_candidates) == 1:
            source = next(iter(source_candidates))
        elif len(source_candidates) > 1:
            return None
        elif len(video_id) == 32 and re.fullmatch(r"[a-z0-9]+", video_id, re.IGNORECASE):
            source = "rutube"
        elif len(video_id) != 11 and re.fullmatch(r"-?\d+_\d+", video_id):
            source = "vk"
        else:
            source = "youtube"
    source_url = canonical_media_url(source, video_id)
    return {
        "source": source,
        "extractor": source,
        "media_id": video_id,
        "video_id": video_id,
        "source_url": source_url,
        "youtube_url": source_url if source == "youtube" else "",
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


def entry_from_archive_id(source: str, video_id: str) -> dict:
    source_url = canonical_media_url(source, video_id)
    return {
        "source": source,
        "extractor": source,
        "media_id": video_id,
        "video_id": video_id,
        "source_url": source_url,
        "youtube_url": source_url if source == "youtube" else "",
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
    archive_id_set = {f"{source}:{video_id}" for source, video_id in archive_ids}
    sources_by_id: dict[str, set[str]] = {}
    for source, video_id in archive_ids:
        sources_by_id.setdefault(video_id, set()).add(source)
    known_ids, known_paths = read_existing_details(details_path)

    entries: list[dict] = []
    file_ids: set[str] = set()
    scanned_files = 0
    matched_files = 0

    for path in iter_media_files(scan_dirs):
        scanned_files += 1
        entry = entry_from_file(path, sources_by_id)
        if entry is None:
            continue
        matched_files += 1
        source = entry["source"]
        video_id = entry["video_id"]
        media_key = f"{source}:{video_id}"
        file_path = entry["file_path"]
        file_ids.add(media_key)
        if media_key in known_ids or file_path in known_paths:
            continue
        entries.append(entry)
        known_ids.add(media_key)
        known_paths.add(file_path)

    file_entries_added = len(entries)
    missing_entries_added = 0
    if args.include_missing:
        for source, video_id in archive_ids:
            media_key = f"{source}:{video_id}"
            if media_key in known_ids or media_key in file_ids:
                continue
            entry = entry_from_archive_id(source, video_id)
            entries.append(entry)
            known_ids.add(media_key)
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
