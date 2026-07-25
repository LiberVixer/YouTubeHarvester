#!/usr/bin/env python3
"""Check which YouTube channel sections are available."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from yth_common import deno_runtime_arg, utf8_subprocess_env, yt_dlp_command  # noqa: E402


SECTIONS = ("videos", "shorts", "streams")
PAID_CONTENT_STATUS_KEY = "paid_content_status"
PAID_CONTENT_UNKNOWN = "unknown"
PAID_CONTENT_HAS = "has_paid"
PAID_CONTENT_FREE = "free_only"
MISSING_PATTERNS = (
    "does not have",
    "no entries",
    "no video",
    "no videos",
    "no shorts",
    "no streams",
    "not available",
)
MEMBERS_ONLY_RE = re.compile(
    r"members-only|join this channel|get access to members-only|exclusive perks|channel members",
    re.IGNORECASE,
)


def section_url(channel: str, section: str) -> str:
    return channel.strip().rstrip("/") + "/" + section


def check_section(yt_dlp: list[str], channel: str, section: str, timeout: int) -> dict:
    url = section_url(channel, section)
    command = yt_dlp + [
        "--js-runtimes",
        deno_runtime_arg(),
        "--flat-playlist",
        "--playlist-items",
        "1",
        "--print",
        "%(id)s",
        "--no-warnings",
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
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "url": url, "error": "timeout"}
    except Exception as exc:
        return {"status": "error", "url": url, "error": str(exc)}

    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    combined = (output + "\n" + error).lower()
    if result.returncode == 0 and output:
        return {"status": "available", "url": url, "error": ""}
    if any(pattern in combined for pattern in MISSING_PATTERNS):
        return {"status": "missing", "url": url, "error": error or output}
    if result.returncode == 0:
        return {"status": "available", "url": url, "error": ""}
    return {"status": "error", "url": url, "error": error or output or "yt-dlp error"}


def has_members_only_text(text: str) -> bool:
    return bool(MEMBERS_ONLY_RE.search(text or ""))


def check_paid_content(yt_dlp: list[str], channel: str, sections: dict, timeout: int) -> str:
    checked = False
    for section in SECTIONS:
        section_info = sections.get(section) or {}
        if section_info.get("status") == "missing":
            continue
        url = section_url(channel, section)
        command = yt_dlp + [
            "--js-runtimes",
            deno_runtime_arg(),
            "--playlist-items",
            "1-5",
            "--skip-download",
            "--simulate",
            "--no-warnings",
            "--print",
            "%(id)s",
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
                timeout=timeout,
                check=False,
            )
        except Exception:
            continue

        combined = "\n".join((result.stdout or "", result.stderr or ""))
        if has_members_only_text(combined):
            return PAID_CONTENT_HAS
        if result.returncode == 0:
            checked = True
    return PAID_CONTENT_FREE if checked else PAID_CONTENT_UNKNOWN


def parse_sections(value: str) -> dict:
    selected = {item.strip() for item in (value or "").split(",") if item.strip()}
    return {
        section: {"status": "available" if section in selected else "missing", "url": section_url("", section), "error": ""}
        for section in SECTIONS
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check YouTube channel sections.")
    parser.add_argument("--channel", required=True, help="YouTube channel URL")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--section", choices=SECTIONS, help="Check only one channel section.")
    parser.add_argument(
        "--paid-content-only",
        action="store_true",
        help="Check only members-only markers, using --available-sections as a section hint.",
    )
    parser.add_argument(
        "--available-sections",
        default="",
        help="Comma-separated sections that should be scanned by --paid-content-only.",
    )
    parser.add_argument(
        "--skip-paid-content",
        action="store_true",
        help="Do not scan channel sections for members-only entries.",
    )
    args = parser.parse_args()

    yt_dlp = yt_dlp_command(allow_missing=False)
    if not yt_dlp:
        print("yt-dlp не найден", file=sys.stderr)
        return 2

    channel = args.channel.strip().rstrip("/")
    if args.paid_content_only:
        sections = parse_sections(args.available_sections)
        for section, info in sections.items():
            info["url"] = section_url(channel, section)
        payload = {
            "channel": channel,
            "sections": {},
            "paid_content_checked": True,
            PAID_CONTENT_STATUS_KEY: check_paid_content(yt_dlp, channel, sections, max(5, args.timeout)),
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if args.section:
        sections = {
            args.section: check_section(yt_dlp, channel, args.section, max(5, args.timeout)),
        }
    else:
        sections = {
            section: check_section(yt_dlp, channel, section, max(5, args.timeout))
            for section in SECTIONS
        }
    payload = {
        "channel": channel,
        "sections": sections,
        "paid_content_checked": not args.skip_paid_content,
    }
    if not args.skip_paid_content:
        payload[PAID_CONTENT_STATUS_KEY] = check_paid_content(yt_dlp, channel, sections, max(5, args.timeout))
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
