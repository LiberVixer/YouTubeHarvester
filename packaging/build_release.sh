#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEB_VERSION="${1:-0.2.2~beta}"
RELEASE_VERSION="${2:-0.2.2-beta}"
RELEASE_DIR="$ROOT_DIR/dist/release"
SOURCE_TAR="$RELEASE_DIR/YouTubeHarvester_${RELEASE_VERSION}_source.tar.gz"
DEB_SOURCE="$ROOT_DIR/dist/yt-harvester_${DEB_VERSION}_all.deb"
DEB_TARGET="$RELEASE_DIR/YouTubeHarvester_${RELEASE_VERSION}_linux_all.deb"

mkdir -p "$RELEASE_DIR"

"$ROOT_DIR/packaging/build_deb.sh" "$DEB_VERSION"
cp "$DEB_SOURCE" "$DEB_TARGET"

tar \
    --exclude-vcs \
    --exclude='./.env' \
    --exclude='./.agents' \
    --exclude='./.codex' \
    --exclude='./.vscode' \
    --exclude='./.venv' \
    --exclude='./__pycache__' \
    --exclude='./scripts/__pycache__' \
    --exclude='./dist' \
    --exclude='./backups' \
    --exclude='./channel_rules.json' \
    --exclude='./channels.txt' \
    --exclude='./queue.txt' \
    --exclude='./yt_archive.txt' \
    --exclude='./archive_details.jsonl' \
    --exclude='./status.json' \
    --exclude='./last_download_at.txt' \
    --exclude='./stop_requested' \
    --exclude='./download.log' \
    --exclude='./download_*.log' \
    --exclude='./run_download-v*.sh' \
    --exclude='./run_download.sh-old' \
    --exclude='./tray_launcher (*)*.py' \
    --transform "s#^\\.#YouTubeHarvester-${RELEASE_VERSION}#" \
    -czf "$SOURCE_TAR" \
    -C "$ROOT_DIR" .

(
    cd "$RELEASE_DIR"
    sha256sum "YouTubeHarvester_${RELEASE_VERSION}_linux_all.deb" \
              "YouTubeHarvester_${RELEASE_VERSION}_source.tar.gz" > "SHA256SUMS-linux.txt"
)

echo "Release files:"
echo "  $DEB_TARGET"
echo "  $SOURCE_TAR"
echo "  $RELEASE_DIR/SHA256SUMS-linux.txt"
