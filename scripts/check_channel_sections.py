#!/usr/bin/env python3
"""Check which YouTube channel sections are available."""

import argparse
import json
import os
import shutil
import shlex
import subprocess
import sys


SECTIONS = ("videos", "shorts", "streams")
MISSING_PATTERNS = (
    "does not have",
    "no entries",
    "no video",
    "no videos",
    "no shorts",
    "no streams",
    "not available",
)


def section_url(channel: str, section: str) -> str:
    return channel.strip().rstrip("/") + "/" + section


def yt_dlp_command() -> list[str]:
    configured = os.environ.get("YTD_YT_DLP_COMMAND", "").strip()
    if configured:
        try:
            return shlex.split(configured, posix=(os.name != "nt"))
        except ValueError:
            return [configured]
    found = shutil.which("yt-dlp")
    return [found] if found else []


def check_section(yt_dlp: list[str], channel: str, section: str, timeout: int) -> dict:
    url = section_url(channel, section)
    command = yt_dlp + [
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Check YouTube channel sections.")
    parser.add_argument("--channel", required=True, help="YouTube channel URL")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    yt_dlp = yt_dlp_command()
    if not yt_dlp:
        print("yt-dlp не найден", file=sys.stderr)
        return 2

    channel = args.channel.strip().rstrip("/")
    payload = {
        "channel": channel,
        "sections": {
            section: check_section(yt_dlp, channel, section, max(5, args.timeout))
            for section in SECTIONS
        },
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
