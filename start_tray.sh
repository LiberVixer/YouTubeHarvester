#!/bin/bash
# Запуск tray_launcher с проверкой зависимостей

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Проверяем PyQt5
python3 -c "import PyQt5" 2>/dev/null || {
    echo "PyQt5 не установлен. Установите пакет python3-pyqt5."
    exit 1
}

# Запускаем launcher
exec python3 "$SCRIPT_DIR/tray_launcher.py" "$@"
