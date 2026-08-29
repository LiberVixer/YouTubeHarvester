"""Safe, user-local updater for the yt-dlp executable."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

LATEST_RELEASE_URL = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
OFFICIAL_DOWNLOAD_PREFIX = "https://github.com/yt-dlp/yt-dlp/releases/download/"
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024
ProgressCallback = Callable[[int, str], None]


class YtDlpUpdateError(RuntimeError):
    """Raised when an update cannot be verified or installed."""


def managed_yt_dlp_path() -> Path:
    configured = os.environ.get("YTD_MANAGED_YT_DLP_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()

    configured_dir = os.environ.get("YTD_YT_DLP_DIR", "").strip()
    if configured_dir:
        tools_dir = Path(configured_dir).expanduser()
    elif os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        root = (
            Path(local_app_data)
            if local_app_data
            else Path.home() / "AppData" / "Local"
        )
        tools_dir = root / "YouTubeHarvester" / "tools"
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME", "").strip()
        root = (
            Path(xdg_data).expanduser()
            if xdg_data
            else Path.home() / ".local" / "share"
        )
        tools_dir = root / "yt-harvester" / "tools"
    return tools_dir / ("yt-dlp.exe" if os.name == "nt" else "yt-dlp")


def release_asset_name(system: str | None = None) -> str:
    system_name = (system or platform.system()).lower()
    return "yt-dlp.exe" if system_name == "windows" else "yt-dlp"


def _open_with_retries(
    request: urllib.request.Request, timeout: int, attempts: int = 3
):
    last_error = None
    for attempt in range(attempts):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.0 + attempt)
    raise YtDlpUpdateError(str(last_error or "network request failed"))


def latest_yt_dlp_release(*, user_agent: str, timeout: int = 12) -> dict:
    request = urllib.request.Request(
        LATEST_RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with _open_with_retries(request, timeout) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise YtDlpUpdateError("GitHub release metadata is unexpectedly large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise YtDlpUpdateError(f"invalid GitHub release metadata: {exc}") from exc

    version = str(payload.get("tag_name") or "").strip().lstrip("v")
    if not re.fullmatch(r"\d{4}\.\d{1,2}\.\d{1,2}(?:[.\w-]*)?", version):
        raise YtDlpUpdateError("GitHub returned an invalid yt-dlp version")

    wanted_name = release_asset_name()
    asset = next(
        (
            item
            for item in payload.get("assets") or []
            if item.get("name") == wanted_name
        ),
        None,
    )
    if not isinstance(asset, dict):
        raise YtDlpUpdateError(f"release asset {wanted_name} was not found")

    url = str(asset.get("browser_download_url") or "")
    digest = str(asset.get("digest") or "")
    size = int(asset.get("size") or 0)
    if not url.startswith(OFFICIAL_DOWNLOAD_PREFIX):
        raise YtDlpUpdateError("GitHub returned an unexpected download URL")
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise YtDlpUpdateError("GitHub did not provide a valid SHA-256 digest")
    if not 0 < size <= MAX_DOWNLOAD_BYTES:
        raise YtDlpUpdateError("yt-dlp release asset has an unexpected size")

    return {
        "version": version,
        "asset_name": wanted_name,
        "url": url,
        "sha256": digest.split(":", 1)[1].lower(),
        "size": size,
    }


def _download_release_asset(
    release: dict,
    temporary_path: Path,
    *,
    user_agent: str,
    progress: ProgressCallback | None,
    timeout: int,
) -> None:
    expected_size = int(release["size"])
    temporary_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if temporary_path.exists():
        metadata = temporary_path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > expected_size:
            temporary_path.unlink()

    last_error = None
    for attempt in range(4):
        downloaded = temporary_path.stat().st_size if temporary_path.exists() else 0
        if downloaded == expected_size:
            break
        headers = {"Accept": "application/octet-stream", "User-Agent": user_agent}
        if downloaded:
            headers["Range"] = f"bytes={downloaded}-"
        request = urllib.request.Request(str(release["url"]), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                append = downloaded > 0 and response.getcode() == 206
                if not append:
                    downloaded = 0
                with temporary_path.open("ab" if append else "wb") as output:
                    while True:
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        downloaded += len(chunk)
                        if downloaded > expected_size:
                            raise YtDlpUpdateError(
                                "downloaded yt-dlp is larger than expected"
                            )
                        if progress:
                            progress(
                                min(99, int(downloaded * 100 / expected_size)),
                                "download",
                            )
                    output.flush()
                    os.fsync(output.fileno())
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt + 1 < 4:
                time.sleep(1.0 + attempt)
                continue
        if temporary_path.exists() and temporary_path.stat().st_size == expected_size:
            break

    actual_size = temporary_path.stat().st_size if temporary_path.exists() else 0
    if actual_size != expected_size:
        detail = f"{actual_size} of {expected_size} bytes"
        raise YtDlpUpdateError(
            f"incomplete yt-dlp download ({detail}): {last_error or ''}".strip()
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_yt_dlp_release(
    release: dict,
    *,
    target: Path | None = None,
    user_agent: str,
    progress: ProgressCallback | None = None,
    timeout: int = 30,
) -> dict:
    target = Path(target or managed_yt_dlp_path())
    temporary = target.with_name(f".{target.stem}.download{target.suffix}")
    _download_release_asset(
        release,
        temporary,
        user_agent=user_agent,
        progress=progress,
        timeout=timeout,
    )

    if progress:
        progress(99, "verify")
    actual_digest = _sha256(temporary)
    if actual_digest != str(release["sha256"]).lower():
        temporary.unlink(missing_ok=True)
        raise YtDlpUpdateError("downloaded yt-dlp failed SHA-256 verification")

    if os.name != "nt":
        temporary.chmod(0o700)
    try:
        result = subprocess.run(
            [str(temporary), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        temporary.unlink(missing_ok=True)
        raise YtDlpUpdateError(f"downloaded yt-dlp could not start: {exc}") from exc
    installed_version = (
        (result.stdout or "").strip().splitlines()[0] if result.returncode == 0 else ""
    )
    if installed_version != str(release["version"]):
        temporary.unlink(missing_ok=True)
        detail = (result.stderr or result.stdout or "version mismatch").strip()
        raise YtDlpUpdateError(f"downloaded yt-dlp verification failed: {detail}")

    if progress:
        progress(100, "install")
    os.replace(temporary, target)
    if os.name != "nt":
        target.chmod(0o700)
    return {"version": installed_version, "path": str(target)}


def update_yt_dlp(
    *,
    user_agent: str,
    target: Path | None = None,
    release: dict | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    selected_release = release or latest_yt_dlp_release(user_agent=user_agent)
    return install_yt_dlp_release(
        selected_release,
        target=target,
        user_agent=user_agent,
        progress=progress,
    )
