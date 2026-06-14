#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="${GITHUB_REPOSITORY:-LiberVixer/YouTubeHarvester}"
TARGET_BRANCH="${YTH_RELEASE_TARGET:-main}"
TAG="${YTH_RELEASE_TAG:-v0.2.2-beta}"
TITLE="${YTH_RELEASE_TITLE:-YouTube Harvester 0.2.2 Beta}"
BUNDLE_ROOT="${YTH_RELEASE_ROOT:-/media/sf_Data/Git/YouTubeHarvester-0.2.2-beta-offline}"
LINUX_DIR="$BUNDLE_ROOT/release-linux"
WINDOWS_DIR="$BUNDLE_ROOT/release-windows"
BODY_FILE="${YTH_RELEASE_BODY:-$ROOT_DIR/docs/releases/0.2.2-beta.md}"
TOKEN_FILE="${GITHUB_TOKEN_FILE:-$HOME/.config/youtube-harvester/github-token}"

ASSETS=(
    "$WINDOWS_DIR/YouTubeHarvester_0.2.2-beta_windows_portable.zip"
    "$WINDOWS_DIR/YouTubeHarvester_0.2.2-beta_windows_setup.exe"
    "$WINDOWS_DIR/YouTubeHarvester_0.2.2-beta_windows_x64.msi"
    "$WINDOWS_DIR/SHA256SUMS-windows.txt"
    "$LINUX_DIR/YouTubeHarvester_0.2.2-beta_linux_all.deb"
    "$LINUX_DIR/YouTubeHarvester_0.2.2-beta_source.tar.gz"
    "$LINUX_DIR/SHA256SUMS-linux.txt"
)

for path in "$BODY_FILE" "${ASSETS[@]}"; do
    if [ ! -f "$path" ]; then
        echo "Required file was not found: $path" >&2
        exit 1
    fi
done

cd "$ROOT_DIR"

if [ -n "$(git status --porcelain)" ]; then
    echo "The git working tree is not clean. Commit or stash changes before publishing." >&2
    git status --short >&2
    exit 1
fi

if ! git rev-parse "$TAG" >/dev/null 2>&1; then
    git tag -a "$TAG" -m "$TITLE"
fi

if [ -z "${GITHUB_USERNAME:-}" ]; then
    read -r -p "GitHub username [LiberVixer]: " GITHUB_USERNAME
    GITHUB_USERNAME="${GITHUB_USERNAME:-LiberVixer}"
fi

if [ -z "${GITHUB_TOKEN:-}" ] && [ -f "$TOKEN_FILE" ]; then
    GITHUB_TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
fi

if [ -z "${GITHUB_TOKEN:-}" ]; then
    read -r -s -p "GitHub token: " GITHUB_TOKEN
    echo
fi

if [ -z "$GITHUB_TOKEN" ]; then
    echo "GitHub token is empty." >&2
    exit 1
fi
export GITHUB_USERNAME GITHUB_TOKEN

ASKPASS="$(mktemp)"
cleanup() {
    rm -f "$ASKPASS"
}
trap cleanup EXIT

cat >"$ASKPASS" <<'EOF'
#!/bin/sh
case "$1" in
    *Username*) printf '%s\n' "${GITHUB_USERNAME:-x-access-token}" ;;
    *Password*) printf '%s\n' "$GITHUB_TOKEN" ;;
    *) printf '\n' ;;
esac
EOF
chmod 700 "$ASKPASS"

REMOTE_URL="https://github.com/$REPO.git"
echo "Pushing HEAD to $REPO:$TARGET_BRANCH"
GIT_ASKPASS="$ASKPASS" GIT_TERMINAL_PROMPT=0 git push "$REMOTE_URL" HEAD:"$TARGET_BRANCH"

echo "Pushing tag $TAG"
GIT_ASKPASS="$ASKPASS" GIT_TERMINAL_PROMPT=0 git push "$REMOTE_URL" "$TAG"

export GITHUB_TOKEN REPO TARGET_BRANCH TAG TITLE BODY_FILE

python3 - "${ASSETS[@]}" <<'PY'
import json
import mimetypes
import os
from pathlib import Path
import sys
from urllib import error, parse, request


token = os.environ["GITHUB_TOKEN"]
repo = os.environ["REPO"]
tag = os.environ["TAG"]
target = os.environ["TARGET_BRANCH"]
title = os.environ["TITLE"]
body_file = Path(os.environ["BODY_FILE"])
assets = [Path(item) for item in sys.argv[1:]]
api_base = f"https://api.github.com/repos/{repo}"


def call(method, url, payload=None, headers=None, raw=False):
    data = None
    req_headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "YouTube-Harvester-release-publisher",
    }
    if headers:
        req_headers.update(headers)
    if payload is not None:
        if raw:
            data = payload
        else:
            data = json.dumps(payload).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
    req = request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with request.urlopen(req, timeout=120) as response:
            body = response.read()
            if not body:
                return response.status, None
            return response.status, json.loads(body.decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 404:
            return exc.code, None
        raise RuntimeError(f"GitHub API {method} {url} failed: HTTP {exc.code}\n{body}") from exc


release_payload = {
    "tag_name": tag,
    "target_commitish": target,
    "name": title,
    "body": body_file.read_text(encoding="utf-8"),
    "draft": False,
    "prerelease": True,
}

status, release = call("GET", f"{api_base}/releases/tags/{parse.quote(tag, safe='')}")
if status == 404:
    print(f"Creating GitHub Release {tag}")
    _, release = call("POST", f"{api_base}/releases", release_payload)
else:
    print(f"Updating GitHub Release {tag}")
    _, release = call("PATCH", f"{api_base}/releases/{release['id']}", release_payload)

upload_url = release["upload_url"].split("{", 1)[0]
existing = {asset["name"]: asset["id"] for asset in release.get("assets", [])}

for asset_path in assets:
    name = asset_path.name
    if name in existing:
        print(f"Deleting existing asset: {name}")
        call("DELETE", f"{api_base}/releases/assets/{existing[name]}")
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    upload_target = f"{upload_url}?name={parse.quote(name)}"
    print(f"Uploading asset: {name}")
    call(
        "POST",
        upload_target,
        payload=asset_path.read_bytes(),
        headers={"Content-Type": content_type},
        raw=True,
    )

print(f"Release is ready: https://github.com/{repo}/releases/tag/{tag}")
PY
