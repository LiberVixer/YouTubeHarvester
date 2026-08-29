#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE="yt-harvester"
VERSION="${1:-1.2.0~beta1}"
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
install -m 0644 "$ROOT_DIR/yth_common.py" "$APP_DIR/yth_common.py"
install -m 0644 "$ROOT_DIR/yth_updater.py" "$APP_DIR/yth_updater.py"
install -m 0644 "$ROOT_DIR/yth_app_updater.py" "$APP_DIR/yth_app_updater.py"
install -m 0644 "$ROOT_DIR/i18n_locales.py" "$APP_DIR/i18n_locales.py"
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
install -m 0644 "$ROOT_DIR/assets/ui.dat" "$APP_DIR/assets/ui.dat"
install -m 0644 "$ROOT_DIR/assets/YTH-logo.png" "$ICON_DIR/yt-harvester.png"

cat > "$BIN_DIR/yt-harvester" <<'EOF'
#!/bin/sh
APP_DIR="/opt/yt-harvester"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/yt-harvester"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/yt-harvester"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/yt-harvester"

mkdir -p "$DATA_DIR" "$CONFIG_DIR" "$CACHE_DIR" "$DATA_DIR/temp"
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
export YTD_QUICK_REQUEST_FILE="$CONFIG_DIR/requests/quick_download.request"
export YTD_SHOW_MAIN_REQUEST_FILE="$CONFIG_DIR/requests/show_main.request"
export YTD_COMPLETION_EVENT_DIR="$CONFIG_DIR/completion-events"
export YTD_TEMP_DIR="${YTD_TEMP_DIR:-$HOME/temp/YTH}"
export YTD_FINAL_DIR="${YTD_FINAL_DIR:-$HOME/Downloads/YouTubeHarvester}"
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$HOME/.deno/bin:$PATH"

exec python3 "$APP_DIR/tray_launcher.py" "$@"
EOF
chmod 0755 "$BIN_DIR/yt-harvester"

cat > "$DESKTOP_DIR/yt-harvester.desktop" <<'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=YouTube Harvester
Name[ru]=YouTube Harvester
Name[uk]=YouTube Harvester
Name[fr]=YouTube Harvester
Name[es]=YouTube Harvester
Name[hi]=YouTube Harvester
Name[zh]=YouTube Harvester
Name[ar]=YouTube Harvester
Name[ja]=YouTube Harvester
Name[be]=YouTube Harvester
GenericName=Video downloader
GenericName[ru]=Загрузчик видео
GenericName[uk]=Завантажувач відео
GenericName[fr]=Téléchargeur de vidéos
GenericName[es]=Descargador de vídeos
GenericName[hi]=वीडियो डाउनलोडर
GenericName[zh]=视频下载器
GenericName[ar]=أداة تنزيل الفيديو
GenericName[ja]=動画ダウンローダー
GenericName[be]=Загрузнік відэа
Comment=Video downloader with tray interface
Comment[ru]=Загрузчик видео с интерфейсом в трее
Comment[uk]=Завантажувач відео з інтерфейсом у системному треї
Comment[fr]=Téléchargeur de vidéos avec interface de zone de notification
Comment[es]=Descargador de vídeos con interfaz de bandeja del sistema
Comment[hi]=सिस्टम ट्रे इंटरफ़ेस के साथ वीडियो डाउनलोडर
Comment[zh]=带系统托盘界面的视频下载器
Comment[ar]=أداة تنزيل الفيديو بواجهة علبة النظام
Comment[ja]=システムトレイ対応の動画ダウンローダー
Comment[be]=Загрузнік відэа з інтэрфейсам у сістэмным трэі
Exec=yt-harvester
Icon=yt-harvester
Terminal=false
Categories=Network;
StartupNotify=false
StartupWMClass=YouTubeHarvester
EOF

cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Section: net
Priority: optional
Architecture: $ARCH
Depends: python3, python3-pyqt5, python3-pynput, python3-dbus, yt-dlp, ffmpeg, curl
Recommends: wl-clipboard
Suggests: deno
Maintainer: YouTube Harvester <noreply@users.noreply.github.com>
Description: Video downloader with tray interface
 YouTube Harvester watches configured YouTube channels, processes a manual
 YouTube, Rutube, and VK queue through yt-dlp, and can send Telegram notices.
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
