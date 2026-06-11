#!/bin/bash
# =============================================
# YT HARVESTER FINAL - v33
# Правки: env-секреты, flock, корректная ротация,
# проверка Telegram API, HTML-ссылки, безопасная зачистка TEMP_DIR
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
ENV_FILE="${YTD_ENV_FILE:-$CONFIG_DIR/.env}"
STATUS_FILE="${YTD_STATUS_FILE:-$DATA_DIR/status.json}"
STOP_FILE="${YTD_STOP_FILE:-$DATA_DIR/stop_requested}"
LAST_DOWNLOAD_FILE="${YTD_LAST_DOWNLOAD_FILE:-$DATA_DIR/last_download_at.txt}"

TEMP_DIR="${YTD_TEMP_DIR:-/media/sf_T/!/DWN/YTD}"
FINAL_DIR="${YTD_FINAL_DIR:-/media/sf_T/!/DWN/Смотреть}"

LOGFILE="${YTD_LOG_FILE:-$DATA_DIR/download.log}"
TEMP_LOG=$(mktemp)

if [ -f "$ENV_FILE" ]; then
    LC_ALL=C sed -i '1s/^\xEF\xBB\xBF//' "$ENV_FILE" 2>/dev/null || true
    sed -i 's/\r$//' "$ENV_FILE" 2>/dev/null || true
    # shellcheck disable=SC1090
    . "$ENV_FILE"
fi

if [ -z "${BOT_TOKEN:-}" ]; then
    echo "BOT_TOKEN is not set. Add it to $ENV_FILE" >&2
    exit 1
fi

if [ -z "${CHANNEL_ID:-}" ]; then
    echo "CHANNEL_ID is not set. Add it to $ENV_FILE" >&2
    exit 1
fi

PROXY_ARGS=()
if [ -n "${PROXY_URL:-}" ]; then
    PROXY_ARGS=(--socks5-hostname "$PROXY_URL")
fi

mkdir -p "$DATA_DIR" "$CONFIG_DIR" "$TEMP_DIR" "$FINAL_DIR"
touch "$CHANNELS" "$ARCHIVE" "$LOGFILE" "$QUEUE"
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

log_console() {
    printf '%s\n' "$@" | tee -a "$LOGFILE"
}

cleanup_temp_dir() {
    log_console "Жёсткая зачистка TEMP_DIR..."
    find "$TEMP_DIR" -type f -delete 2>/dev/null || true
    rm -rf "$TEMP_DIR"/* 2>/dev/null || true
}

rotate_logs_and_exit() {
    EXIT_CODE="${1:-0}"

    log_console "Ротация логов..."
    log_console "=== ЖАТВА ЗАВЕРШЕНА $(date '+%Y-%m-%d %H:%M:%S') ==="

    if [ "$STATUS_STATE" = "stopping" ]; then
        STATUS_STATE="stopped"
    elif [ "$STATUS_STATE" != "stopped" ]; then
        STATUS_STATE="sleep"
    fi
    STATUS_CURRENT_TYPE=""
    write_status

    rm -f "$TEMP_LOG"
    mv -f "$LOGFILE" "$ARCHIVED_LOG" 2>/dev/null || true
    find "$DATA_DIR" -maxdepth 1 -type f -name 'download_*.log' -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | awk 'NR > 3 {sub(/^[^ ]+ /, ""); print}' \
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

update_status_from_ytdlp_line() {
    YTDLP_LINE="$1"
    TYPE_NAME="$2"

    update_status_from_thumbnail_line "$YTDLP_LINE"

    printf '%s' "$YTDLP_LINE" | grep -Eq 'Merging formats into|Destination: ' || return 0

    STATUS_STATE="downloading"
    STATUS_CURRENT_TYPE="$TYPE_NAME"
    set_type_status "$TYPE_NAME" "downloading"

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

    TYPE_NEW_FILES=$(grep -E 'Merging formats into|Destination: .*\.mp4' "$TYPE_LOG" | sed -E 's/.*Merging formats into "?([^\"]+\.mp4)"?.*/\1/; s/.*Destination: (.*\.mp4).*/\1/' | grep -vE '\.f[0-9]+\.mp4$' | sort -u || true)
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

        if send_telegram_message "$POST"; then
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
        write_status
        check_stop_requested
        sleep 3
    done <<< "$TYPE_NEW_FILES"
}

TIMESTAMP=$(date '+%Y-%m-%d_%H-%M')
ARCHIVED_LOG="$DATA_DIR/download_${TIMESTAMP}.log"
NEW_COUNT=0
FAILED_COUNT=0

log_console "=== ЖАТВА НАЧАЛАСЬ $(date '+%Y-%m-%d %H:%M:%S') ==="
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
        write_status

        log_console "📥 Очередь: $queued_url"
        TYPE_LOG=$(mktemp)
        yt-dlp \
          -f "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]" \
          --merge-output-format mp4 \
          --write-thumbnail --embed-thumbnail --convert-thumbnails jpg \
          --download-archive "$ARCHIVE" \
          --match-filter "!is_live" \
          -o "$TEMP_DIR/%(title)s - %(uploader)s [%(id)s] [queue] [%(height)sp].%(ext)s" \
          --embed-subs --embed-metadata --embed-chapters \
          --ignore-errors --no-abort-on-error --no-warnings \
          --retries 20 --fragment-retries 20 \
          --no-cache-dir --js-runtimes deno --no-playlist \
          "$queued_url" 2>&1 | while IFS= read -r ytdlp_line; do
              printf '%s\n' "$ytdlp_line" | tee -a "$LOGFILE" "$TEMP_LOG" "$TYPE_LOG" >/dev/null
              update_status_from_ytdlp_line "$ytdlp_line" "queue"
          done

        BEFORE_QUEUE_COUNT="$NEW_COUNT"
        process_type_log "$TYPE_LOG" "$queued_url" "Очередь"
        if [ "$NEW_COUNT" -eq "$BEFORE_QUEUE_COUNT" ] && ! grep -q 'has already been recorded in the archive' "$TYPE_LOG"; then
            printf '%s\n' "$queued_url" >> "$QUEUE"
            FAILED_COUNT=$((FAILED_COUNT + 1))
            log_console "   ⚠️ Не скачано из очереди, оставлено для повтора"
        fi
        rm -f "$TYPE_LOG"
        check_stop_requested
    done < "$QUEUE_WORK"

    rm -f "$QUEUE_WORK"
fi

# ====================== СКАЧИВАНИЕ ======================
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
    write_status

    log_console "👤 Смотрим $CHANNEL_NAME"

    for type in videos shorts streams; do
        check_stop_requested
        case $type in
            videos) EMOJI="🎬" ;;
            shorts) EMOJI="📱" ;;
            streams) EMOJI="🔴" ;;
        esac
        STATUS_STATE="searching"
        STATUS_CURRENT_TYPE="$type"
        STATUS_VIDEO_TITLE=""
        STATUS_VIDEO_THUMBNAIL=""
        set_type_status "$type" "searching"
        write_status

        log_console "-${EMOJI} Ищем - ${type^}"

        # Полный вывод yt-dlp ТОЛЬКО в лог + temp для парсинга
        TYPE_LOG=$(mktemp)
        yt-dlp \
          -f "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]" \
          --merge-output-format mp4 \
          --write-thumbnail --embed-thumbnail --convert-thumbnails jpg \
          --download-archive "$ARCHIVE" \
          --playlist-items 1-5 \
          --match-filter "!is_live" \
          -o "$TEMP_DIR/%(title)s - %(uploader)s [%(id)s] [${type}] [%(height)sp].%(ext)s" \
          --embed-subs --embed-metadata --embed-chapters \
          --ignore-errors --no-abort-on-error --no-warnings \
          --retries 20 --fragment-retries 20 \
          --no-cache-dir --js-runtimes deno \
          "$channel/$type" 2>&1 | while IFS= read -r ytdlp_line; do
              printf '%s\n' "$ytdlp_line" | tee -a "$LOGFILE" "$TEMP_LOG" "$TYPE_LOG" >/dev/null
              update_status_from_ytdlp_line "$ytdlp_line" "$type"
          done

        BEFORE_TYPE_COUNT="$NEW_COUNT"
        process_type_log "$TYPE_LOG" "${channel%/}" "$CHANNEL_NAME"
        if [ "$NEW_COUNT" -eq "$BEFORE_TYPE_COUNT" ]; then
            if grep -Eiq 'does not have.*tab|No entries|No video|No shorts|No streams' "$TYPE_LOG"; then
                set_type_status "$type" "missing"
            else
                set_type_status "$type" "done"
            fi
            STATUS_STATE="searching"
            STATUS_CURRENT_TYPE="$type"
            write_status
        fi
        rm -f "$TYPE_LOG"
        check_stop_requested
    done
done < "$CHANNELS"

# ====================== ПОИСК НОВЫХ ======================
if [ "${NEW_COUNT:-0}" -eq 0 ]; then
    log_console "   📌Новых видео не найдено"
    cleanup_temp_dir
    rotate_logs_and_exit 0
fi

log_console "✳️ Найдено новых видео: $NEW_COUNT"

# ====================== ЗАЧИСТКА ======================
if [ "${FAILED_COUNT:-0}" -eq 0 ]; then
    cleanup_temp_dir
else
    log_console "⚠️ Были ошибки обработки: $FAILED_COUNT"
    log_console "⚠️ TEMP_DIR не очищен, чтобы не потерять файлы для повтора/ручной проверки"
fi

rotate_logs_and_exit 0
