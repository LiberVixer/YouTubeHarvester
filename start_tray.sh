#!/bin/bash
# Запуск tray_launcher с проверкой зависимостей

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$HOME/.deno/bin:$PATH"
PYTHON="${YTD_PYTHON:-python3}"
if [ -z "${YTD_PYTHON:-}" ] && [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
fi

# Проверяем PyQt5
"$PYTHON" -c "import PyQt5" 2>/dev/null || {
    echo "PyQt5 не установлен. Установите пакет python3-pyqt5."
    exit 1
}

# Запускаем launcher
exec "$PYTHON" "$SCRIPT_DIR/tray_launcher.py" "$@"
