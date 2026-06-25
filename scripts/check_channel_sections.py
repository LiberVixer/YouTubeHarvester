#!/usr/bin/env python3
"""Check which YouTube channel sections are available."""

import argparse
import json
import os
import shutil
import shlex
import subprocess
import sys
from pathlib import Path


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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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
