"""Verified GitHub Release updater for YouTube Harvester packages."""

from __future__ import annotations

import hashlib
import json
import ntpath
import os
import platform
import re
import stat
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path


REPOSITORY = "LiberVixer/YouTubeHarvester"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
OFFICIAL_DOWNLOAD_PREFIX = f"https://github.com/{REPOSITORY}/releases/download/"
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_CHECKSUM_BYTES = 128 * 1024
MAX_ASSET_BYTES = 1024 * 1024 * 1024
ProgressCallback = Callable[[int, str], None]

INSTALLATION_ASSETS = {
    "windows_setup": ("YouTubeHarvester_{version}_windows_setup.exe", "SHA256SUMS-windows.txt", "installer"),
    "windows_msi": ("YouTubeHarvester_{version}_windows_x64.msi", "SHA256SUMS-windows.txt", "installer"),
    "windows_portable": ("YouTubeHarvester_{version}_windows_portable.zip", "SHA256SUMS-windows.txt", "folder"),
    "linux_deb": ("YouTubeHarvester_{version}_linux_all.deb", "SHA256SUMS-linux.txt", "package"),
    "source": ("YouTubeHarvester_{version}_source.tar.gz", "SHA256SUMS-linux.txt", "folder"),
}


class AppUpdateError(RuntimeError):
    """Raised when application update metadata or a package is unsafe."""


def version_key(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(version or "").strip())
    if not match:
        return ()
    return tuple(int(part) for part in match.groups())


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def installation_kind(
    *,
    system: str | None = None,
    frozen: bool | None = None,
    executable_path: str | Path | None = None,
    app_dir: str | Path | None = None,
) -> str:
    system_name = (system or platform.system()).lower()
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else bool(frozen)
    executable = Path(executable_path or sys.executable)
    application_dir = Path(app_dir or os.environ.get("YTD_APP_DIR") or Path(__file__).resolve().parent)

    if system_name == "windows":
        if not is_frozen:
            return "source"
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if is_frozen and local_app_data:
            installed_root = ntpath.normcase(
                ntpath.normpath(ntpath.join(local_app_data, "Programs", "YouTube Harvester"))
            )
            executable_text = ntpath.normcase(ntpath.normpath(str(executable)))
            try:
                if ntpath.commonpath([executable_text, installed_root]) == installed_root:
                    return "windows_setup"
            except ValueError:
                pass
        for environment_name in ("ProgramFiles", "PROGRAMFILES", "ProgramFiles(x86)", "PROGRAMFILES(X86)"):
            program_files = os.environ.get(environment_name, "").strip()
            if not is_frozen or not program_files:
                continue
            installed_root = ntpath.normcase(
                ntpath.normpath(ntpath.join(program_files, "YouTube Harvester"))
            )
            executable_text = ntpath.normcase(ntpath.normpath(str(executable)))
            try:
                if ntpath.commonpath([executable_text, installed_root]) == installed_root:
                    return "windows_msi"
            except ValueError:
                continue
        return "windows_portable"

    if system_name == "linux" and _is_relative_to(application_dir, Path("/opt/yt-harvester")):
        return "linux_deb"
    return "source"


def _open_with_retries(request: urllib.request.Request, timeout: int, attempts: int = 4):
    last_error = None
    for attempt in range(attempts):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.0 + attempt)
    raise AppUpdateError(str(last_error or "network request failed"))


def _read_limited(url: str, *, user_agent: str, limit: int, timeout: int) -> bytes:
    if not url.startswith(OFFICIAL_DOWNLOAD_PREFIX):
        raise AppUpdateError("GitHub returned an unexpected download URL")
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/octet-stream", "User-Agent": user_agent},
    )
    with _open_with_retries(request, timeout) as response:
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise AppUpdateError("GitHub response is unexpectedly large")
    return payload


def _checksum_for_asset(payload: bytes, asset_name: str) -> str:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppUpdateError("release checksum file is not valid UTF-8") from exc
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", line.strip())
        if match and match.group(2).strip() == asset_name:
            return match.group(1).lower()
    raise AppUpdateError(f"SHA-256 for {asset_name} was not found")


def latest_app_release(
    *,
    current_version: str,
    user_agent: str,
    kind: str | None = None,
    timeout: int = 15,
) -> dict:
    selected_kind = kind or installation_kind()
    if selected_kind not in INSTALLATION_ASSETS:
        raise AppUpdateError(f"unsupported installation type: {selected_kind}")

    request = urllib.request.Request(
        LATEST_RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with _open_with_retries(request, timeout) as response:
        raw = response.read(MAX_METADATA_BYTES + 1)
    if len(raw) > MAX_METADATA_BYTES:
        raise AppUpdateError("GitHub release metadata is unexpectedly large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppUpdateError(f"invalid GitHub release metadata: {exc}") from exc

    version = str(payload.get("tag_name") or "").strip().lstrip("v")
    if not version_key(version):
        raise AppUpdateError("GitHub returned an invalid application version")
    if payload.get("draft") or payload.get("prerelease"):
        raise AppUpdateError("GitHub latest release is not a stable published release")

    asset_template, checksum_name, action = INSTALLATION_ASSETS[selected_kind]
    asset_name = asset_template.format(version=version)
    assets = {
        str(item.get("name") or ""): item
        for item in payload.get("assets") or []
        if isinstance(item, dict)
    }
    asset = assets.get(asset_name)
    checksum_asset = assets.get(checksum_name)
    if not asset or not checksum_asset:
        raise AppUpdateError(f"release files for {selected_kind} are incomplete")

    url = str(asset.get("browser_download_url") or "")
    checksum_url = str(checksum_asset.get("browser_download_url") or "")
    if not url.startswith(OFFICIAL_DOWNLOAD_PREFIX) or not checksum_url.startswith(OFFICIAL_DOWNLOAD_PREFIX):
        raise AppUpdateError("GitHub returned an unexpected download URL")
    size = int(asset.get("size") or 0)
    if not 0 < size <= MAX_ASSET_BYTES:
        raise AppUpdateError("application release asset has an unexpected size")

    checksum_payload = _read_limited(
        checksum_url,
        user_agent=user_agent,
        limit=MAX_CHECKSUM_BYTES,
        timeout=timeout,
    )
    checksum = _checksum_for_asset(checksum_payload, asset_name)
    github_digest = str(asset.get("digest") or "").strip().lower()
    if github_digest:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", github_digest):
            raise AppUpdateError("GitHub returned an invalid asset digest")
        if github_digest.partition(":")[2] != checksum:
            raise AppUpdateError("GitHub asset digest does not match SHA256SUMS")

    return {
        "current_version": current_version,
        "version": version,
        "update_available": version_key(version) > version_key(current_version),
        "kind": selected_kind,
        "action": action,
        "asset_name": asset_name,
        "url": url,
        "sha256": checksum,
        "size": size,
        "release_url": str(payload.get("html_url") or ""),
        "published_at": str(payload.get("published_at") or ""),
    }


def default_update_dir() -> Path:
    configured = os.environ.get("YTD_APP_UPDATE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "Downloads" / "YouTubeHarvester Updates"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_app_release(
    release: dict,
    *,
    target_dir: Path | None = None,
    user_agent: str,
    progress: ProgressCallback | None = None,
    timeout: int = 45,
) -> dict:
    asset_name = str(release.get("asset_name") or "")
    if not re.fullmatch(r"YouTubeHarvester_[A-Za-z0-9._-]+", asset_name):
        raise AppUpdateError("unsafe application release filename")
    expected_size = int(release.get("size") or 0)
    expected_digest = str(release.get("sha256") or "").lower()
    url = str(release.get("url") or "")
    if not 0 < expected_size <= MAX_ASSET_BYTES:
        raise AppUpdateError("application release asset has an unexpected size")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise AppUpdateError("application release has no valid SHA-256")
    if not url.startswith(OFFICIAL_DOWNLOAD_PREFIX):
        raise AppUpdateError("application release URL is not official")

    destination_dir = Path(target_dir or default_update_dir())
    destination_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = destination_dir / asset_name
    temporary = destination_dir / f".{asset_name}.part"

    if target.is_file() and target.stat().st_size == expected_size and _sha256(target) == expected_digest:
        if progress:
            progress(100, "ready")
        return {**release, "path": str(target)}
    if target.exists():
        target.unlink()
    if temporary.exists():
        metadata = temporary.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > expected_size:
            temporary.unlink()

    last_error = None
    for attempt in range(5):
        downloaded = temporary.stat().st_size if temporary.exists() else 0
        if downloaded == expected_size:
            break
        headers = {"Accept": "application/octet-stream", "User-Agent": user_agent}
        if downloaded:
            headers["Range"] = f"bytes={downloaded}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                append = downloaded > 0 and response.getcode() == 206
                if not append:
                    downloaded = 0
                with temporary.open("ab" if append else "wb") as output:
                    while True:
                        chunk = response.read(512 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        downloaded += len(chunk)
                        if downloaded > expected_size:
                            raise AppUpdateError("downloaded application package is larger than expected")
                        if progress:
                            progress(min(99, int(downloaded * 100 / expected_size)), "download")
                    output.flush()
                    os.fsync(output.fileno())
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt + 1 < 5:
                time.sleep(1.0 + attempt)
                continue
        if temporary.exists() and temporary.stat().st_size == expected_size:
            break

    actual_size = temporary.stat().st_size if temporary.exists() else 0
    if actual_size != expected_size:
        raise AppUpdateError(
            f"incomplete application download ({actual_size} of {expected_size} bytes): {last_error or ''}".strip()
        )
    if progress:
        progress(99, "verify")
    if _sha256(temporary) != expected_digest:
        temporary.unlink(missing_ok=True)
        raise AppUpdateError("downloaded application package failed SHA-256 verification")

    os.replace(temporary, target)
    if os.name != "nt":
        target.chmod(0o600)
    if progress:
        progress(100, "ready")
    return {**release, "path": str(target)}
