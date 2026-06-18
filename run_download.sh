#!/bin/bash
# =============================================
# YouTube Harvester - v33
# Правки: env-секреты, flock, корректная ротация,
# проверка Telegram API, HTML-ссылки, безопасная зачистка временной папки
# =============================================

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${YTD_DATA_DIR:-$BASE_DIR}"
CONFIG_DIR="${YTD_CONFIG_DIR:-$DATA_DIR}"

cd "$BASE_DIR" || exit 1

LOCKFILE="/tmp/yt_harvester.lock"
exec 9>"$LOCKFILE"
flock -n 9 || {
    echo "Already running"
    exit 0
}

CHANNELS="${YTD_CHANNELS_FILE:-$DATA_DIR/channels.txt}"
QUEUE="${YTD_QUEUE_FILE:-$DATA_DIR/queue.txt}"
ARCHIVE="${YTD_ARCHIVE_FILE:-$DATA_DIR/yt_archive.txt}"
ARCHIVE_DETAILS="${YTD_ARCHIVE_DETAILS_FILE:-$DATA_DIR/archive_details.jsonl}"
ENV_FILE="${YTD_ENV_FILE:-$CONFIG_DIR/.env}"
STATUS_FILE="${YTD_STATUS_FILE:-$DATA_DIR/status.json}"
STOP_FILE="${YTD_STOP_FILE:-$DATA_DIR/stop_requested}"
LAST_DOWNLOAD_FILE="${YTD_LAST_DOWNLOAD_FILE:-$DATA_DIR/last_download_at.txt}"
CHANNEL_RULES="${YTD_CHANNEL_RULES_FILE:-$CONFIG_DIR/channel_rules.json}"

TEMP_DIR="${YTD_TEMP_DIR:-$HOME/temp/YTH}"
FINAL_DIR="${YTD_FINAL_DIR:-$HOME/Downloads/YouTubeHarvester}"

LOGFILE="${YTD_LOG_FILE:-$DATA_DIR/download.log}"
TEMP_LOG=$(mktemp)

if [ -f "$ENV_FILE" ]; then
    LC_ALL=C sed -i '1s/^\xEF\xBB\xBF//' "$ENV_FILE" 2>/dev/null || true
    sed -i 's/\r$//' "$ENV_FILE" 2>/dev/null || true
    # shellcheck disable=SC1090
    . "$ENV_FILE"
fi

TELEGRAM_ENABLED="${YTD_TELEGRAM_ENABLED:-${TELEGRAM_ENABLED:-1}}"
VIDEOS_LIMIT="${YTD_VIDEOS_LIMIT:-${VIDEOS_LIMIT:-5}}"
SHORTS_LIMIT="${YTD_SHORTS_LIMIT:-${SHORTS_LIMIT:-5}}"
STREAMS_LIMIT="${YTD_STREAMS_LIMIT:-${STREAMS_LIMIT:-5}}"
MAX_RESOLUTION="${YTD_MAX_RESOLUTION:-${MAX_RESOLUTION:-1080}}"
LOG_KEEP_COUNT="${YTD_LOG_KEEP_COUNT:-${LOG_KEEP_COUNT:-3}}"
CLEANUP_TEMP="${YTD_CLEANUP_TEMP:-${CLEANUP_TEMP:-1}}"
RETRY_FAILED_QUEUE="${YTD_RETRY_FAILED_QUEUE:-${RETRY_FAILED_QUEUE:-1}}"

PROXY_ARGS=()
if [ -n "${PROXY_URL:-}" ]; then
    PROXY_ARGS=(--socks5-hostname "$PROXY_URL")
fi

mkdir -p "$DATA_DIR" "$CONFIG_DIR" "$TEMP_DIR" "$FINAL_DIR"
touch "$CHANNELS" "$ARCHIVE" "$ARCHIVE_DETAILS" "$LOGFILE" "$QUEUE"
rm -f "$STOP_FILE"

STATUS_STATE="sleep"
STATUS_CHANNEL_URL=""
STATUS_CHANNEL_NAME=""
STATUS_CURRENT_TYPE=""
STATUS_VIDEOS="idle"
STATUS_SHORTS="idle"
STATUS_STREAMS="idle"
STATUS_VIDEO_TITLE=""
STATUS_VIDEO_THUMBNAIL=""
STATUS_DOWNLOAD_PERCENT=""
STATUS_DOWNLOAD_SPEED=""
STATUS_DOWNLOAD_ETA=""
STATUS_DOWNLOAD_SIZE=""
STATUS_DOWNLOAD_STAGE=""
STATUS_PROGRESS_BUCKET=""
STATUS_CHANNELS_TOTAL=0
STATUS_CHANNELS_CHECKED=0

log_console() {
    printf '%s\n' "$@" | tee -a "$LOGFILE"
}

is_truthy() {
    case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on|да) return 0 ;;
        *) return 1 ;;
    esac
}

positive_int_or_default() {
    VALUE="$1"
    DEFAULT="$2"
    if printf '%s' "$VALUE" | grep -Eq '^[0-9]+$' && [ "$VALUE" -gt 0 ]; then
        printf '%s' "$VALUE"
    else
        printf '%s' "$DEFAULT"
    fi
}

VIDEOS_LIMIT=$(positive_int_or_default "$VIDEOS_LIMIT" 5)
SHORTS_LIMIT=$(positive_int_or_default "$SHORTS_LIMIT" 5)
STREAMS_LIMIT=$(positive_int_or_default "$STREAMS_LIMIT" 5)
LOG_KEEP_COUNT=$(positive_int_or_default "$LOG_KEEP_COUNT" 3)

case "$MAX_RESOLUTION" in
    480|720|1080|1440|2160)
        FORMAT_SELECTOR="bestvideo[ext=mp4][height<=${MAX_RESOLUTION}]+bestaudio[ext=m4a]/best[ext=mp4][height<=${MAX_RESOLUTION}]/best[height<=${MAX_RESOLUTION}]"
        ;;
    best|BEST|Best)
        FORMAT_SELECTOR="bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        MAX_RESOLUTION="best"
        ;;
    *)
        MAX_RESOLUTION="1080"
        FORMAT_SELECTOR="bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best[height<=1080]"
        ;;
esac

if is_truthy "$TELEGRAM_ENABLED"; then
    if [ -z "${BOT_TOKEN:-}" ]; then
        echo "BOT_TOKEN is not set. Add it to $ENV_FILE or disable Telegram notifications" >&2
        exit 1
    fi

    if [ -z "${CHANNEL_ID:-}" ]; then
        echo "CHANNEL_ID is not set. Add it to $ENV_FILE or disable Telegram notifications" >&2
        exit 1
    fi
fi

type_limit() {
    case "$1" in
        videos) printf '%s' "$VIDEOS_LIMIT" ;;
        shorts) printf '%s' "$SHORTS_LIMIT" ;;
        streams) printf '%s' "$STREAMS_LIMIT" ;;
        *) printf '%s' 5 ;;
    esac
}

cleanup_temp_dir() {
    log_console "Жёсткая очистка временной папки..."
    find "$TEMP_DIR" -type f -delete 2>/dev/null || true
    rm -rf "$TEMP_DIR"/* 2>/dev/null || true
}

rotate_logs_and_exit() {
    EXIT_CODE="${1:-0}"

    log_console "Ротация логов..."
    log_console "=== Жатва завершена $(date '+%Y-%m-%d %H:%M:%S') ==="

    if [ "$STATUS_STATE" = "stopping" ]; then
        STATUS_STATE="stopped"
    elif [ "$STATUS_STATE" != "stopped" ]; then
        STATUS_STATE="sleep"
    fi
    STATUS_CURRENT_TYPE=""
    reset_download_progress
    write_status

    rm -f "$TEMP_LOG"
    mv -f "$LOGFILE" "$ARCHIVED_LOG" 2>/dev/null || true
    find "$DATA_DIR" -maxdepth 1 -type f -name 'download_*.log' -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | awk -v keep="$LOG_KEEP_COUNT" 'NR > keep {sub(/^[^ ]+ /, ""); print}' \
        | xargs -r rm -f -- 2>/dev/null || true

    exit "$EXIT_CODE"
}

remove_video_from_archive() {
    VIDEO_ID_TO_REMOVE="$1"
    [ -n "$VIDEO_ID_TO_REMOVE" ] || return 0
    [ -s "$ARCHIVE" ] || return 0

    ARCHIVE_TMP=$(mktemp)
    grep -vF "$VIDEO_ID_TO_REMOVE" "$ARCHIVE" > "$ARCHIVE_TMP" || true
    mv -f "$ARCHIVE_TMP" "$ARCHIVE"
    log_console "   ↩️ Убран из архива для повтора: $VIDEO_ID_TO_REMOVE"
}

extract_video_id_from_url() {
    printf '%s\n' "$1" | sed -nE \
        -e 's#.*[?&]v=([A-Za-z0-9_-]{11}).*#\1#p' \
        -e 's#.*youtu\.be/([A-Za-z0-9_-]{11}).*#\1#p' \
        -e 's#.*/shorts/([A-Za-z0-9_-]{11}).*#\1#p' \
        -e 's#.*/live/([A-Za-z0-9_-]{11}).*#\1#p' \
        -e 's#.*/embed/([A-Za-z0-9_-]{11}).*#\1#p' | head -n 1
}

archive_has_video() {
    VIDEO_ID_TO_FIND="$1"
    [ -n "$VIDEO_ID_TO_FIND" ] || return 1
    if [ -s "$ARCHIVE" ] && grep -Fq "$VIDEO_ID_TO_FIND" "$ARCHIVE"; then
        return 0
    fi
    if [ -s "$ARCHIVE_DETAILS" ] && grep -Fq "\"video_id\":\"$VIDEO_ID_TO_FIND\"" "$ARCHIVE_DETAILS"; then
        return 0
    fi
    return 1
}

archive_details_has_video() {
    VIDEO_ID_TO_FIND="$1"
    [ -n "$VIDEO_ID_TO_FIND" ] || return 1
    [ -s "$ARCHIVE_DETAILS" ] || return 1
    grep -Fq "\"video_id\":\"$VIDEO_ID_TO_FIND\"" "$ARCHIVE_DETAILS"
}

html_escape() {
    local s="$1"
    s=${s//&/\&amp;}
    s=${s//</\&lt;}
    s=${s//>/\&gt;}
    s=${s//\"/\&quot;}
    printf '%s' "$s"
}

send_telegram_message() {
    MESSAGE_TEXT="$1"

    TG_RESPONSE=$(curl "${PROXY_ARGS[@]}" -sS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="$CHANNEL_ID" \
        -d parse_mode=HTML \
        --data-urlencode "text=$MESSAGE_TEXT" 2>&1)
    CURL_STATUS=$?

    if [ "$CURL_STATUS" -eq 0 ] && printf '%s' "$TG_RESPONSE" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
        return 0
    fi

    log_console "   ❌ Telegram API error: $TG_RESPONSE"
    return 1
}

json_escape() {
    local s="$1"
    s=${s//\\/\\\\}
    s=${s//\"/\\\"}
    s=${s//$'\n'/\\n}
    s=${s//$'\r'/\\r}
    s=${s//$'\t'/\\t}
    printf '%s' "$s"
}

append_archive_details() {
    DETAIL_VIDEO_ID="$1"
    DETAIL_VIDEO_URL="$2"
    DETAIL_TITLE="$3"
    DETAIL_CHANNEL_NAME="$4"
    DETAIL_CHANNEL_URL="$5"
    DETAIL_TYPE="$6"
    DETAIL_FILE_PATH="$7"
    DETAIL_FILENAME="$8"
    DETAIL_TS=$(date +%s)
    DETAIL_DATE=$(date '+%Y-%m-%d %H:%M:%S')

    if [ "$DETAIL_VIDEO_ID" != "unknown" ] && archive_details_has_video "$DETAIL_VIDEO_ID"; then
        log_console "   🗃 Запись уже есть в архиве: $DETAIL_VIDEO_ID"
        return 0
    fi

    printf '{"video_id":"%s","youtube_url":"%s","title":"%s","channel_name":"%s","channel_url":"%s","downloaded_at":"%s","downloaded_at_ts":%s,"type":"%s","file_path":"%s","filename":"%s"}\n' \
        "$(json_escape "$DETAIL_VIDEO_ID")" \
        "$(json_escape "$DETAIL_VIDEO_URL")" \
        "$(json_escape "$DETAIL_TITLE")" \
        "$(json_escape "$DETAIL_CHANNEL_NAME")" \
        "$(json_escape "$DETAIL_CHANNEL_URL")" \
        "$(json_escape "$DETAIL_DATE")" \
        "$DETAIL_TS" \
        "$(json_escape "$DETAIL_TYPE")" \
        "$(json_escape "$DETAIL_FILE_PATH")" \
        "$(json_escape "$DETAIL_FILENAME")" >> "$ARCHIVE_DETAILS" 2>/dev/null || true
}

write_status() {
    STATUS_TMP="${STATUS_FILE}.tmp"
    STATUS_LAST_DOWNLOAD=""
    if [ -f "$LAST_DOWNLOAD_FILE" ]; then
        STATUS_LAST_DOWNLOAD=$(cat "$LAST_DOWNLOAD_FILE" 2>/dev/null || true)
    fi
    STATUS_STOP_REQUESTED=false
    [ -f "$STOP_FILE" ] && STATUS_STOP_REQUESTED=true

    cat > "$STATUS_TMP" <<EOF
{
  "state": "$(json_escape "$STATUS_STATE")",
  "channel_url": "$(json_escape "$STATUS_CHANNEL_URL")",
  "channel_name": "$(json_escape "$STATUS_CHANNEL_NAME")",
  "current_type": "$(json_escape "$STATUS_CURRENT_TYPE")",
  "videos_status": "$(json_escape "$STATUS_VIDEOS")",
  "shorts_status": "$(json_escape "$STATUS_SHORTS")",
  "streams_status": "$(json_escape "$STATUS_STREAMS")",
  "video_title": "$(json_escape "$STATUS_VIDEO_TITLE")",
  "video_thumbnail": "$(json_escape "$STATUS_VIDEO_THUMBNAIL")",
  "download_percent": "$(json_escape "$STATUS_DOWNLOAD_PERCENT")",
  "download_speed": "$(json_escape "$STATUS_DOWNLOAD_SPEED")",
  "download_eta": "$(json_escape "$STATUS_DOWNLOAD_ETA")",
  "download_size": "$(json_escape "$STATUS_DOWNLOAD_SIZE")",
  "download_stage": "$(json_escape "$STATUS_DOWNLOAD_STAGE")",
  "channels_total": $STATUS_CHANNELS_TOTAL,
  "channels_checked": $STATUS_CHANNELS_CHECKED,
  "last_download_at": "$(json_escape "$STATUS_LAST_DOWNLOAD")",
  "stop_requested": $STATUS_STOP_REQUESTED,
  "updated_at": $(date +%s)
}
EOF
    mv -f "$STATUS_TMP" "$STATUS_FILE" 2>/dev/null || true
}

set_type_status() {
    case "$1" in
        videos) STATUS_VIDEOS="$2" ;;
        shorts) STATUS_SHORTS="$2" ;;
        streams) STATUS_STREAMS="$2" ;;
    esac
}

reset_download_progress() {
    STATUS_DOWNLOAD_PERCENT=""
    STATUS_DOWNLOAD_SPEED=""
    STATUS_DOWNLOAD_ETA=""
    STATUS_DOWNLOAD_SIZE=""
    STATUS_DOWNLOAD_STAGE=""
    STATUS_PROGRESS_BUCKET=""
}

channel_type_enabled() {
    CHANNEL_RULE_CHANNEL="${1%/}"
    CHANNEL_RULE_TYPE="$2"
    [ -s "$CHANNEL_RULES" ] || return 0

    python3 - "$CHANNEL_RULES" "$CHANNEL_RULE_CHANNEL" "$CHANNEL_RULE_TYPE" <<'PY'
import json
import sys

path, channel, type_name = sys.argv[1:4]
channel = channel.rstrip("/")

try:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    sys.exit(0)

rules = None
if isinstance(data, dict):
    rules = data.get(channel)
    if rules is None:
        for key, value in data.items():
            if str(key).rstrip("/") == channel:
                rules = value
                break

if not isinstance(rules, dict):
    sys.exit(0)

value = rules.get(type_name, True)
if value is False:
    sys.exit(1)
if isinstance(value, str) and value.strip().lower() in {"0", "false", "no", "off"}:
    sys.exit(1)

sys.exit(0)
PY
    [ "$?" -eq 1 ] && return 1
    return 0
}

status_title_from_path() {
    STATUS_PATH_BASENAME=$(basename "$1")
    STATUS_PATH_BASENAME=${STATUS_PATH_BASENAME%.part}
    STATUS_PATH_BASENAME=$(printf '%s\n' "$STATUS_PATH_BASENAME" | sed -E 's/\.f[0-9]+(\.[^.]+)$/\1/')
    STATUS_PATH_TITLE=$(printf '%s\n' "$STATUS_PATH_BASENAME" | sed -E 's/ \[[A-Za-z0-9_-]{11}\] \[(videos|shorts|streams|queue)\] \[[^]]+\]\.[^.]+$//')
    if [[ "$STATUS_PATH_TITLE" == *" - "* ]]; then
        STATUS_PATH_TITLE=${STATUS_PATH_TITLE% - *}
    fi
    printf '%s' "$STATUS_PATH_TITLE" | cut -c1-180
}

status_base_without_ext() {
    STATUS_PATH_NO_PART=${1%.part}
    printf '%s\n' "$STATUS_PATH_NO_PART" | sed -E 's/\.f[0-9]+(\.[^.]+)$/\1/' | sed -E 's/\.[^.]+$//'
}

find_status_thumbnail() {
    STATUS_VIDEO_PATH="$1"
    STATUS_BASE_NO_EXT=$(status_base_without_ext "$STATUS_VIDEO_PATH")
    for ext in jpg jpeg png webp; do
        if [ -f "${STATUS_BASE_NO_EXT}.${ext}" ]; then
            printf '%s' "${STATUS_BASE_NO_EXT}.${ext}"
            return 0
        fi
    done

    STATUS_THUMB=$(find "$TEMP_DIR" -maxdepth 1 -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) -printf '%T@ %p\n' 2>/dev/null | sort -nr | awk 'NR==1 {sub(/^[^ ]+ /, ""); print}')
    [ -n "$STATUS_THUMB" ] && printf '%s' "$STATUS_THUMB"
}

update_status_from_thumbnail_line() {
    THUMBNAIL_LINE="$1"
    STATUS_THUMBNAIL_FROM_LINE=$(printf '%s\n' "$THUMBNAIL_LINE" | sed -nE \
        -e 's/.*[Ww]riting video thumbnail [0-9]+ to: (.*)$/\1/p' \
        -e 's/.*[Cc]onverting thumbnail "?([^"]+)"? to .*/\1/p' \
        -e 's/.*[Dd]estination: (.*\.(jpg|jpeg|png|webp)).*/\1/p' | head -n 1)

    if [ -z "$STATUS_THUMBNAIL_FROM_LINE" ]; then
        return 0
    fi

    STATUS_THUMBNAIL_JPG="${STATUS_THUMBNAIL_FROM_LINE%.*}.jpg"
    if [ -f "$STATUS_THUMBNAIL_JPG" ]; then
        STATUS_VIDEO_THUMBNAIL="$STATUS_THUMBNAIL_JPG"
    elif [ -f "$STATUS_THUMBNAIL_FROM_LINE" ]; then
        STATUS_VIDEO_THUMBNAIL="$STATUS_THUMBNAIL_FROM_LINE"
    fi

    [ -n "$STATUS_VIDEO_THUMBNAIL" ] && write_status
}

is_ytdlp_progress_line() {
    printf '%s\n' "$1" | grep -Eq '^\[download\][[:space:]]+[0-9]+([.][0-9]+)?%'
}

update_status_from_progress_line() {
    PROGRESS_LINE="$1"
    TYPE_NAME="$2"

    is_ytdlp_progress_line "$PROGRESS_LINE" || return 1

    PROGRESS_PERCENT=$(printf '%s\n' "$PROGRESS_LINE" | sed -nE 's/^\[download\][[:space:]]+([0-9]+([.][0-9]+)?)%.*/\1/p' | head -n 1)
    [ -n "$PROGRESS_PERCENT" ] || return 1

    STATUS_DOWNLOAD_PERCENT="$PROGRESS_PERCENT"
    [ -n "$STATUS_DOWNLOAD_STAGE" ] || STATUS_DOWNLOAD_STAGE="download"
    STATUS_DOWNLOAD_SIZE=$(printf '%s\n' "$PROGRESS_LINE" | sed -nE 's/.* of[[:space:]]+~?([^[:space:]]+).*/\1/p' | head -n 1)
    STATUS_DOWNLOAD_SPEED=$(printf '%s\n' "$PROGRESS_LINE" | sed -nE 's/.* at[[:space:]]+([^[:space:]]+\/s).*/\1/p' | head -n 1)
    STATUS_DOWNLOAD_ETA=$(printf '%s\n' "$PROGRESS_LINE" | sed -nE 's/.* ETA[[:space:]]+([^[:space:]]+).*/\1/p' | head -n 1)

    STATUS_STATE="downloading"
    STATUS_CURRENT_TYPE="$TYPE_NAME"
    set_type_status "$TYPE_NAME" "downloading"

    PROGRESS_BUCKET=$(printf '%s\n' "$STATUS_DOWNLOAD_PERCENT" | sed -E 's/^([0-9]+).*/\1/')
    [ -n "$PROGRESS_BUCKET" ] || PROGRESS_BUCKET="0"
    if [ "$PROGRESS_BUCKET" != "$STATUS_PROGRESS_BUCKET" ] || [ "$PROGRESS_BUCKET" = "100" ]; then
        STATUS_PROGRESS_BUCKET="$PROGRESS_BUCKET"
        write_status
    fi
    return 0
}

update_status_from_ytdlp_line() {
    YTDLP_LINE="$1"
    TYPE_NAME="$2"

    update_status_from_thumbnail_line "$YTDLP_LINE"
    if printf '%s' "$YTDLP_LINE" | grep -q 'Destination: ' \
        && printf '%s' "$YTDLP_LINE" | grep -Eiq '\.(jpe?g|png|webp)(["'\'']?|)$'; then
        return 0
    fi
    update_status_from_progress_line "$YTDLP_LINE" "$TYPE_NAME" && return 0

    if printf '%s' "$YTDLP_LINE" | grep -q 'Merging formats into'; then
        STATUS_DOWNLOAD_STAGE="merge"
    elif printf '%s' "$YTDLP_LINE" | grep -Eq '\[(EmbedThumbnail|Metadata|ModifyChapters|FFmpeg|VideoConvertor)\]'; then
        STATUS_DOWNLOAD_STAGE="postprocess"
    elif printf '%s' "$YTDLP_LINE" | grep -q 'Destination: ' \
        && ! printf '%s' "$YTDLP_LINE" | grep -Eiq '\.(jpe?g|png|webp)(["'\'']?|)$'; then
        if [ "$STATUS_DOWNLOAD_STAGE" = "video" ]; then
            STATUS_DOWNLOAD_STAGE="audio"
        else
            STATUS_DOWNLOAD_STAGE="video"
        fi
    fi

    printf '%s' "$YTDLP_LINE" | grep -Eq 'Merging formats into|Destination: |\[(EmbedThumbnail|Metadata|ModifyChapters|FFmpeg|VideoConvertor)\]' || return 0

    STATUS_STATE="downloading"
    STATUS_CURRENT_TYPE="$TYPE_NAME"
    set_type_status "$TYPE_NAME" "downloading"
    if printf '%s' "$YTDLP_LINE" | grep -q 'Destination: '; then
        DOWNLOAD_STAGE="$STATUS_DOWNLOAD_STAGE"
        reset_download_progress
        STATUS_DOWNLOAD_STAGE="$DOWNLOAD_STAGE"
    fi

    STATUS_FILE_FROM_LINE=$(printf '%s\n' "$YTDLP_LINE" | sed -nE 's/.*Merging formats into "?([^"]+)"?.*/\1/p; s/.*Destination: (.*)/\1/p' | head -n 1)
    if [ -n "$STATUS_FILE_FROM_LINE" ]; then
        STATUS_TITLE_FROM_FILE=$(status_title_from_path "$STATUS_FILE_FROM_LINE")
        if [ -n "$STATUS_TITLE_FROM_FILE" ]; then
            STATUS_VIDEO_TITLE="$STATUS_TITLE_FROM_FILE"
        fi

        STATUS_THUMBNAIL_CANDIDATE=$(find_status_thumbnail "$STATUS_FILE_FROM_LINE")
        if [ -n "$STATUS_THUMBNAIL_CANDIDATE" ]; then
            STATUS_VIDEO_THUMBNAIL="$STATUS_THUMBNAIL_CANDIDATE"
        fi
    fi

    write_status
}

check_stop_requested() {
    if [ -f "$STOP_FILE" ]; then
        log_console "⏹ Запрошена мягкая остановка"
        STATUS_STATE="stopping"
        write_status
        rotate_logs_and_exit 0
    fi
}

process_type_log() {
    TYPE_LOG="$1"
    CHANNEL_LINK="$2"
    CHANNEL_NAME="$3"

    TYPE_NEW_FILES=$(grep -E 'Merging formats into|Destination: .*\.mp4|^\[download\] .*\.mp4 has already been downloaded' "$TYPE_LOG" | sed -E 's/.*Merging formats into "?([^\"]+\.mp4)"?.*/\1/; s/.*Destination: (.*\.mp4).*/\1/; s/^\[download\] (.*\.mp4) has already been downloaded.*/\1/' | grep -vE '\.f[0-9]+\.mp4$' | sort -u || true)
    if [ -z "$TYPE_NEW_FILES" ]; then
        return 0
    fi

    while IFS= read -r NEW_FILE; do
        BASENAME=$(basename "$NEW_FILE")
        NEW_COUNT=$((NEW_COUNT + 1))

        EMOJI="🎬"
        STATUS_TYPE="videos"
        [[ "$BASENAME" == *"[streams]"* ]] && EMOJI="🔴" && STATUS_TYPE="streams"
        [[ "$BASENAME" == *"[shorts]"* ]] && EMOJI="📱" && STATUS_TYPE="shorts"
        [[ "$BASENAME" == *"[queue]"* ]] && EMOJI="📥" && STATUS_TYPE="queue"

        VIDEO_ID=$(printf '%s\n' "$BASENAME" | sed -nE 's/.* \[([A-Za-z0-9_-]{11})\] \[(videos|shorts|streams|queue)\] \[[^]]+\]\.mp4$/\1/p')
        [ -n "$VIDEO_ID" ] || VIDEO_ID="unknown"

        BASE_NO_SUFFIX=$(printf '%s\n' "$BASENAME" | sed -E 's/ \[[A-Za-z0-9_-]{11}\] \[(videos|shorts|streams|queue)\] \[[^]]+\]\.mp4$//')
        if [[ "$BASE_NO_SUFFIX" == *" - "* ]]; then
            VIDEO_TITLE=${BASE_NO_SUFFIX% - *}
            UPLOADER=${BASE_NO_SUFFIX##* - }
        else
            VIDEO_TITLE="$BASE_NO_SUFFIX"
            UPLOADER="$CHANNEL_NAME"
        fi

        VIDEO_TITLE=$(printf '%s' "$VIDEO_TITLE" | cut -c1-180)
        STATUS_STATE="downloading"
        STATUS_CURRENT_TYPE="$STATUS_TYPE"
        STATUS_VIDEO_TITLE="$VIDEO_TITLE"
        STATUS_VIDEO_THUMBNAIL=""
        STATUS_DOWNLOAD_PERCENT="100"
        STATUS_DOWNLOAD_SPEED=""
        STATUS_DOWNLOAD_ETA=""
        STATUS_PROGRESS_BUCKET="100"
        THUMBNAIL_CANDIDATE=$(find_status_thumbnail "$NEW_FILE")
        [ -n "$THUMBNAIL_CANDIDATE" ] && STATUS_VIDEO_THUMBNAIL="$THUMBNAIL_CANDIDATE"
        set_type_status "$STATUS_TYPE" "downloading"
        write_status
        date +%s > "$LAST_DOWNLOAD_FILE" 2>/dev/null || true

        log_console "   🔔 Найдено новое видео ($VIDEO_TITLE)"
        log_console "   ⏬ Видео скачено"
        VIDEO_URL="https://www.youtube.com/watch?v=${VIDEO_ID}"

        VIDEO_TITLE_HTML=$(html_escape "$VIDEO_TITLE")
        UPLOADER_HTML=$(html_escape "$UPLOADER")
        VIDEO_URL_HTML=$(html_escape "$VIDEO_URL")
        CHANNEL_LINK_HTML=$(html_escape "$CHANNEL_LINK")

        POST=$(printf '%s <a href="%s">%s</a>\n👤 <a href="%s">%s</a>' "$EMOJI" "$VIDEO_URL_HTML" "$VIDEO_TITLE_HTML" "$CHANNEL_LINK_HTML" "$UPLOADER_HTML")

        if ! is_truthy "$TELEGRAM_ENABLED"; then
            log_console "   🔕 Telegram отключён"
            SENT_OK=1
        elif send_telegram_message "$POST"; then
            log_console "   📨 Отправлено в канал"
            SENT_OK=1
        else
            log_console "   ❌ Не отправлено в канал"
            SENT_OK=0
            FAILED_COUNT=$((FAILED_COUNT + 1))
            remove_video_from_archive "$VIDEO_ID"
        fi

        if [ "$SENT_OK" -eq 1 ]; then
            if mv -f "$NEW_FILE" "$FINAL_DIR/" 2>/dev/null; then
                FINAL_FILE_PATH="$FINAL_DIR/$BASENAME"
                append_archive_details "$VIDEO_ID" "$VIDEO_URL" "$VIDEO_TITLE" "$UPLOADER" "$CHANNEL_LINK" "$STATUS_TYPE" "$FINAL_FILE_PATH" "$BASENAME"
                log_console "   ⚓ Видео перемещено"
            else
                log_console "   ❌ Видео не перемещено"
                FAILED_COUNT=$((FAILED_COUNT + 1))
                remove_video_from_archive "$VIDEO_ID"
            fi
        else
            log_console "   ⚠️ Файл оставлен во временной папке: $BASENAME"
        fi

        set_type_status "$STATUS_TYPE" "done"
        STATUS_STATE="searching"
        reset_download_progress
        write_status
        check_stop_requested
        sleep 3
    done <<< "$TYPE_NEW_FILES"
}

TIMESTAMP=$(date '+%Y-%m-%d_%H-%M')
ARCHIVED_LOG="$DATA_DIR/download_${TIMESTAMP}.log"
NEW_COUNT=0
FAILED_COUNT=0

log_console "=== Жатва началась $(date '+%Y-%m-%d %H:%M:%S') ==="
log_console "🧩 Движок: Bash"
STATUS_STATE="searching"
write_status
check_stop_requested

# ====================== ОЧЕРЕДЬ ВИДЕО ======================
if [ -s "$QUEUE" ]; then
    QUEUE_WORK=$(mktemp)
    cp "$QUEUE" "$QUEUE_WORK"
    : > "$QUEUE"

    while IFS= read -r queued_url || [ -n "$queued_url" ]; do
        queued_url=$(printf '%s' "$queued_url" | sed 's/^\xef\xbb\xbf//; s/^[[:space:]]*//; s/[[:space:]]*$//')
        [[ -z "$queued_url" || "$queued_url" =~ ^# ]] && continue

        check_stop_requested
        STATUS_STATE="searching"
        STATUS_CHANNEL_URL="$queued_url"
        STATUS_CHANNEL_NAME="Очередь"
        STATUS_CURRENT_TYPE="queue"
        STATUS_VIDEO_TITLE=""
        STATUS_VIDEO_THUMBNAIL=""
        reset_download_progress
        write_status

        log_console "📥 Очередь: $queued_url"
        QUEUED_VIDEO_ID=$(extract_video_id_from_url "$queued_url")
        if [ -n "$QUEUED_VIDEO_ID" ] && archive_has_video "$QUEUED_VIDEO_ID"; then
            log_console "   🗃 Уже есть в архиве, пропускаем: $QUEUED_VIDEO_ID"
            set_type_status "queue" "done"
            STATUS_STATE="searching"
            write_status
            continue
        fi

        TYPE_LOG=$(mktemp)
        yt-dlp \
          -f "$FORMAT_SELECTOR" \
          --merge-output-format mp4 \
          --write-thumbnail --embed-thumbnail --convert-thumbnails jpg \
          --download-archive "$ARCHIVE" \
          --match-filter "!is_live" \
          -o "$TEMP_DIR/%(title)s - %(uploader)s [%(id)s] [queue] [%(height)sp].%(ext)s" \
          --embed-subs --embed-metadata --embed-chapters \
          --ignore-errors --no-abort-on-error --no-warnings \
          --retries 20 --fragment-retries 20 \
          --no-cache-dir --js-runtimes deno --no-playlist --newline \
          "$queued_url" 2>&1 | while IFS= read -r ytdlp_line; do
              if is_ytdlp_progress_line "$ytdlp_line"; then
                  update_status_from_ytdlp_line "$ytdlp_line" "queue"
              else
                  printf '%s\n' "$ytdlp_line" | tee -a "$LOGFILE" "$TEMP_LOG" "$TYPE_LOG" >/dev/null
                  update_status_from_ytdlp_line "$ytdlp_line" "queue"
              fi
          done

        BEFORE_QUEUE_COUNT="$NEW_COUNT"
        process_type_log "$TYPE_LOG" "$queued_url" "Очередь"
        if [ "$NEW_COUNT" -eq "$BEFORE_QUEUE_COUNT" ] && ! grep -q 'has already been recorded in the archive' "$TYPE_LOG"; then
            if is_truthy "$RETRY_FAILED_QUEUE"; then
                printf '%s\n' "$queued_url" >> "$QUEUE"
                log_console "   ⚠️ Не скачано из очереди, оставлено для повтора"
            else
                log_console "   ⚠️ Не скачано из очереди, повтор отключён"
            fi
            FAILED_COUNT=$((FAILED_COUNT + 1))
        fi
        rm -f "$TYPE_LOG"
        check_stop_requested
    done < "$QUEUE_WORK"

    rm -f "$QUEUE_WORK"
fi

# ====================== СКАЧИВАНИЕ ======================
STATUS_CHANNELS_TOTAL=$(awk '{sub(/^\xef\xbb\xbf/, ""); gsub(/^[[:space:]]+|[[:space:]]+$/, ""); if ($0 != "" && $0 !~ /^#/) count++} END {print count + 0}' "$CHANNELS")
STATUS_CHANNELS_CHECKED=0
write_status
while IFS= read -r channel || [ -n "$channel" ]; do
    channel=$(echo "$channel" | sed 's/^\xef\xbb\xbf//')
    [[ -z "$channel" || "$channel" =~ ^# ]] && continue

    check_stop_requested
    CHANNEL_NAME=$(echo "$channel" | sed 's|.*/@@||; s|.*/@||; s|/$||')
    STATUS_STATE="searching"
    STATUS_CHANNEL_URL="${channel%/}"
    STATUS_CHANNEL_NAME="$CHANNEL_NAME"
    STATUS_CURRENT_TYPE=""
    STATUS_VIDEOS="idle"
    STATUS_SHORTS="idle"
    STATUS_STREAMS="idle"
    STATUS_VIDEO_TITLE=""
    STATUS_VIDEO_THUMBNAIL=""
    reset_download_progress

    for initial_type in videos shorts streams; do
        if ! channel_type_enabled "$channel" "$initial_type"; then
            set_type_status "$initial_type" "disabled"
        fi
    done
    write_status

    log_console "👤 Смотрим $CHANNEL_NAME"

    for type in videos shorts streams; do
        check_stop_requested
        case $type in
            videos) EMOJI="🎬"; TYPE_LABEL="Видео" ;;
            shorts) EMOJI="📱"; TYPE_LABEL="Shorts" ;;
            streams) EMOJI="🔴"; TYPE_LABEL="Трансляция" ;;
        esac

        if ! channel_type_enabled "$channel" "$type"; then
            STATUS_STATE="searching"
            STATUS_CURRENT_TYPE="$type"
            STATUS_VIDEO_TITLE=""
            STATUS_VIDEO_THUMBNAIL=""
            reset_download_progress
            set_type_status "$type" "disabled"
            write_status
            log_console "-${EMOJI} Пропускаем - ${TYPE_LABEL} отключены для канала"
            continue
        fi

        STATUS_STATE="searching"
        STATUS_CURRENT_TYPE="$type"
        STATUS_VIDEO_TITLE=""
        STATUS_VIDEO_THUMBNAIL=""
        reset_download_progress
        set_type_status "$type" "searching"
        write_status

        log_console "-${EMOJI} Ищем - ${TYPE_LABEL}"

        # Полный вывод yt-dlp ТОЛЬКО в лог + temp для парсинга
        TYPE_LIMIT=$(type_limit "$type")
        TYPE_LOG=$(mktemp)
        yt-dlp \
          -f "$FORMAT_SELECTOR" \
          --merge-output-format mp4 \
          --write-thumbnail --embed-thumbnail --convert-thumbnails jpg \
          --download-archive "$ARCHIVE" \
          --playlist-items "1-${TYPE_LIMIT}" \
          --match-filter "!is_live" \
          -o "$TEMP_DIR/%(title)s - %(uploader)s [%(id)s] [${type}] [%(height)sp].%(ext)s" \
          --embed-subs --embed-metadata --embed-chapters \
          --ignore-errors --no-abort-on-error --no-warnings \
          --retries 20 --fragment-retries 20 \
          --no-cache-dir --js-runtimes deno --newline \
          "$channel/$type" 2>&1 | while IFS= read -r ytdlp_line; do
              if is_ytdlp_progress_line "$ytdlp_line"; then
                  update_status_from_ytdlp_line "$ytdlp_line" "$type"
              else
                  printf '%s\n' "$ytdlp_line" | tee -a "$LOGFILE" "$TEMP_LOG" "$TYPE_LOG" >/dev/null
                  update_status_from_ytdlp_line "$ytdlp_line" "$type"
              fi
          done

        BEFORE_TYPE_COUNT="$NEW_COUNT"
        process_type_log "$TYPE_LOG" "${channel%/}" "$CHANNEL_NAME"
        if [ "$NEW_COUNT" -eq "$BEFORE_TYPE_COUNT" ]; then
            if grep -Eiq 'does not have.*tab|No entries|No items|No video|No shorts|No streams|does not exist|not found|HTTP Error 404' "$TYPE_LOG"; then
                set_type_status "$type" "missing"
            else
                set_type_status "$type" "done"
            fi
            STATUS_STATE="searching"
            STATUS_CURRENT_TYPE="$type"
            reset_download_progress
            write_status
        fi
        rm -f "$TYPE_LOG"
        sleep 1
        check_stop_requested
    done
    STATUS_CHANNELS_CHECKED=$((STATUS_CHANNELS_CHECKED + 1))
    STATUS_STATE="searching"
    STATUS_CURRENT_TYPE=""
    reset_download_progress
    write_status
done < "$CHANNELS"

# ====================== ПОИСК НОВЫХ ======================
if [ "${NEW_COUNT:-0}" -eq 0 ]; then
    log_console "   📌Новых видео не найдено"
    if is_truthy "$CLEANUP_TEMP"; then
        cleanup_temp_dir
    else
        log_console "🧹 Очистка временной папки отключена"
    fi
    rotate_logs_and_exit 0
fi

log_console "✳️ Найдено новых видео: $NEW_COUNT"

# ====================== ЗАЧИСТКА ======================
if [ "${FAILED_COUNT:-0}" -eq 0 ]; then
    if is_truthy "$CLEANUP_TEMP"; then
        cleanup_temp_dir
    else
        log_console "🧹 Очистка временной папки отключена"
    fi
else
    log_console "⚠️ Были ошибки обработки: $FAILED_COUNT"
    log_console "⚠️ Временная папка не очищена, чтобы не потерять файлы для повтора/ручной проверки"
fi

rotate_logs_and_exit 0
