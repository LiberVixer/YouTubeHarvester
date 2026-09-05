#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEB_VERSION="${1:-1.2.0~beta1}"
RELEASE_VERSION="${2:-1.2.0-beta}"
RELEASE_DIR="${3:-$ROOT_DIR/dist/release}"
mkdir -p "$RELEASE_DIR"
RELEASE_DIR="$(cd "$RELEASE_DIR" && pwd)"
SOURCE_TAR="$RELEASE_DIR/YouTubeHarvester_${RELEASE_VERSION}_source.tar.gz"
DEB_SOURCE="$ROOT_DIR/dist/yt-harvester_${DEB_VERSION}_all.deb"
DEB_TARGET="$RELEASE_DIR/YouTubeHarvester_${RELEASE_VERSION}_linux_all.deb"

"$ROOT_DIR/packaging/build_deb.sh" "$DEB_VERSION"
cp "$DEB_SOURCE" "$DEB_TARGET"

SOURCE_ROOT="YouTubeHarvester-${RELEASE_VERSION}"
if git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    SOURCE_LIST="$(mktemp)"
    trap 'rm -f "$SOURCE_LIST"' EXIT
    git -C "$ROOT_DIR" ls-files -z > "$SOURCE_LIST"
    if [ -f "$ROOT_DIR/yth_common.py" ] && ! grep -z -q -x -F -- "yth_common.py" "$SOURCE_LIST"; then
        printf 'yth_common.py\0' >> "$SOURCE_LIST"
    fi
    if [ -f "$ROOT_DIR/yth_updater.py" ] && ! grep -z -q -x -F -- "yth_updater.py" "$SOURCE_LIST"; then
        printf 'yth_updater.py\0' >> "$SOURCE_LIST"
    fi
    if [ -f "$ROOT_DIR/yth_app_updater.py" ] && ! grep -z -q -x -F -- "yth_app_updater.py" "$SOURCE_LIST"; then
        printf 'yth_app_updater.py\0' >> "$SOURCE_LIST"
    fi
    if [ -f "$ROOT_DIR/i18n_locales.py" ] && ! grep -z -q -x -F -- "i18n_locales.py" "$SOURCE_LIST"; then
        printf 'i18n_locales.py\0' >> "$SOURCE_LIST"
    fi
    for required_file in \
        requirements-build.txt \
        requirements-windows-lock.txt \
        .github/dependabot.yml \
        "docs/releases/${RELEASE_VERSION}.md" \
        tests/test_channel_sources.py \
        tests/test_channel_sources_ui.py \
        tests/test_media_sources.py \
        tests/test_preview_download.py; do
        if [ -f "$ROOT_DIR/$required_file" ] && ! grep -z -q -x -F -- "$required_file" "$SOURCE_LIST"; then
            printf '%s\0' "$required_file" >> "$SOURCE_LIST"
        fi
    done
    tar --null \
        --transform "s#^#${SOURCE_ROOT}/#" \
        -czf "$SOURCE_TAR" \
        -C "$ROOT_DIR" \
        -T "$SOURCE_LIST"
else
    tar \
        --exclude-vcs \
        --exclude='./.env' \
        --exclude='./.agents' \
        --exclude='./.codex' \
        --exclude='./.sentry-native' \
        --exclude='./.vscode' \
        --exclude='./.venv' \
        --exclude='./.ruff_cache' \
        --exclude='./android' \
        --exclude='./docs/android-ui-reference' \
        --exclude='./__pycache__' \
        --exclude='./scripts/__pycache__' \
        --exclude='./dist' \
        --exclude='./backups' \
        --exclude='./ffmpeg' \
        --exclude='./deno' \
        --exclude='./tools/windows/ffmpeg' \
        --exclude='./tools/windows/deno' \
        --exclude='./wheelhouse' \
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
        --transform "s#^\\.#${SOURCE_ROOT}#" \
        -czf "$SOURCE_TAR" \
        -C "$ROOT_DIR" .
fi

(
    cd "$RELEASE_DIR"
    sha256sum "YouTubeHarvester_${RELEASE_VERSION}_linux_all.deb" \
              "YouTubeHarvester_${RELEASE_VERSION}_source.tar.gz" > "SHA256SUMS-linux.txt"
)

echo "Release files:"
echo "  $DEB_TARGET"
echo "  $SOURCE_TAR"
echo "  $RELEASE_DIR/SHA256SUMS-linux.txt"
