#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE="yt-harvester"
VERSION="${1:-0.2.2~beta}"
ARCH="all"
BUILD_DIR="$ROOT_DIR/dist/deb-build"
PKG_DIR="$BUILD_DIR/${PACKAGE}_${VERSION}_${ARCH}"
APP_DIR="$PKG_DIR/opt/yt-harvester"
BIN_DIR="$PKG_DIR/usr/bin"
DESKTOP_DIR="$PKG_DIR/usr/share/applications"
ICON_DIR="$PKG_DIR/usr/share/icons/hicolor/256x256/apps"
DOC_DIR="$PKG_DIR/usr/share/doc/$PACKAGE"

rm -rf "$PKG_DIR"
mkdir -p "$APP_DIR/assets" "$APP_DIR/scripts" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR" "$DOC_DIR" "$PKG_DIR/DEBIAN"

install -m 0755 "$ROOT_DIR/tray_launcher.py" "$APP_DIR/tray_launcher.py"
install -m 0755 "$ROOT_DIR/run_download.sh" "$APP_DIR/run_download.sh"
install -m 0755 "$ROOT_DIR/start_tray.sh" "$APP_DIR/start_tray.sh"
install -m 0755 "$ROOT_DIR/scripts/downloader.py" "$APP_DIR/scripts/downloader.py"
install -m 0755 "$ROOT_DIR/scripts/mark_channel_archived.py" "$APP_DIR/scripts/mark_channel_archived.py"
install -m 0755 "$ROOT_DIR/scripts/migrate_archive_details.py" "$APP_DIR/scripts/migrate_archive_details.py"
install -m 0755 "$ROOT_DIR/scripts/check_channel_sections.py" "$APP_DIR/scripts/check_channel_sections.py"
install -m 0644 "$ROOT_DIR/assets/YTH-logo.png" "$APP_DIR/assets/YTH-logo.png"
install -m 0644 "$ROOT_DIR/assets/yt-harvester.png" "$APP_DIR/assets/yt-harvester.png"
install -m 0644 "$ROOT_DIR/assets/overview-logo.png" "$APP_DIR/assets/overview-logo.png"
install -m 0644 "$ROOT_DIR/assets/video-placeholder.png" "$APP_DIR/assets/video-placeholder.png"
install -m 0644 "$ROOT_DIR/assets/queue-scheduler.png" "$APP_DIR/assets/queue-scheduler.png"
install -m 0644 "$ROOT_DIR/assets/YTH-logo.png" "$ICON_DIR/yt-harvester.png"

cat > "$BIN_DIR/yt-harvester" <<'EOF'
#!/bin/sh
APP_DIR="/opt/yt-harvester"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/yt-harvester"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/yt-harvester"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/yt-harvester"

mkdir -p "$DATA_DIR" "$CONFIG_DIR" "$CACHE_DIR" "$DATA_DIR/temp" "$HOME/Videos/YouTube Harvester"
touch "$DATA_DIR/channels.txt" "$DATA_DIR/queue.txt" "$DATA_DIR/yt_archive.txt" "$DATA_DIR/archive_details.jsonl"

if [ ! -f "$CONFIG_DIR/.env" ]; then
    cat > "$CONFIG_DIR/.env" <<'ENVEOF'
# Telegram settings for YouTube Harvester.
# Fill these values before running downloads:
# BOT_TOKEN=your-telegram-bot-token
# CHANNEL_ID=your-telegram-channel-id
#
# Optional:
# PROXY_URL=127.0.0.1:9050
ENVEOF
    chmod 0600 "$CONFIG_DIR/.env" 2>/dev/null || true
fi

export YTD_APP_DIR="$APP_DIR"
export YTD_DATA_DIR="$DATA_DIR"
export YTD_CONFIG_DIR="$CONFIG_DIR"
export YTD_CACHE_DIR="$CACHE_DIR"
export YTD_ENV_FILE="$CONFIG_DIR/.env"
export YTD_SETTINGS_FILE="$CONFIG_DIR/settings.json"
export YTD_SCHEDULES_FILE="$CONFIG_DIR/schedules.json"
export YTD_CHANNEL_RULES_FILE="$CONFIG_DIR/channel_rules.json"
export YTD_TEMP_DIR="${YTD_TEMP_DIR:-$HOME/temp/YTH}"
export YTD_FINAL_DIR="${YTD_FINAL_DIR:-$HOME/Downloads/YouTubeHarvester}"

exec python3 "$APP_DIR/tray_launcher.py" "$@"
EOF
chmod 0755 "$BIN_DIR/yt-harvester"

cat > "$DESKTOP_DIR/yt-harvester.desktop" <<'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=YouTube Harvester
Name[ru]=YouTube Harvester
GenericName=YouTube downloader
GenericName[ru]=Загрузчик YouTube
Comment=YouTube downloader with tray interface
Comment[ru]=Загрузчик YouTube с интерфейсом в трее
Exec=yt-harvester
Icon=yt-harvester
Terminal=false
Categories=Network;
StartupNotify=false
EOF

cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Section: net
Priority: optional
Architecture: $ARCH
Depends: python3, python3-pyqt5, yt-dlp, curl, bash, coreutils, findutils, grep, sed
Maintainer: YouTube Harvester <noreply@users.noreply.github.com>
Description: YouTube downloader with tray interface
 YouTube Harvester watches configured YouTube channels and a manual queue,
 downloads new videos through yt-dlp, and can notify a Telegram channel.
EOF

cat > "$PKG_DIR/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 0755 "$PKG_DIR/DEBIAN/postinst"

cat > "$PKG_DIR/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 0755 "$PKG_DIR/DEBIAN/postrm"

cat > "$DOC_DIR/README.Debian" <<'EOF'
YouTube Harvester stores user data outside /opt:

- data:   ~/.local/share/yt-harvester
- config: ~/.config/yt-harvester/.env
- cache:  ~/.cache/yt-harvester

Edit ~/.config/yt-harvester/.env and fill BOT_TOKEN and CHANNEL_ID
before starting downloads.
EOF
gzip -9n < "$DOC_DIR/README.Debian" > "$DOC_DIR/README.Debian.gz"
rm -f "$DOC_DIR/README.Debian"

find "$PKG_DIR" -type d -exec chmod 0755 {} +
find "$PKG_DIR" -type f -exec chmod 0644 {} +
chmod 0755 "$BIN_DIR/yt-harvester"
chmod 0755 "$APP_DIR/tray_launcher.py" "$APP_DIR/run_download.sh" "$APP_DIR/start_tray.sh" "$APP_DIR/scripts/downloader.py" "$APP_DIR/scripts/mark_channel_archived.py" "$APP_DIR/scripts/migrate_archive_details.py" "$APP_DIR/scripts/check_channel_sections.py"
chmod 0755 "$PKG_DIR/DEBIAN/postinst" "$PKG_DIR/DEBIAN/postrm"

dpkg-deb --root-owner-group --build "$PKG_DIR" "$ROOT_DIR/dist/${PACKAGE}_${VERSION}_${ARCH}.deb"
