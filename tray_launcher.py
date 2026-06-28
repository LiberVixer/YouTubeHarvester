#!/usr/bin/env python3
"""
Tray launcher для run_download.sh
- Спящий режим (серый круг Zzz) - скрипт не работает
- Красный круг с прямоугольником - скрипт работает
- Зелёный круг с прямоугольником - приоритетная загрузка (файлы .part в папке)
"""

import sys
import subprocess
import threading
import os
import time
import shlex
import shutil
import importlib.util
import ctypes
import ctypes.wintypes
import re
import ast
from pathlib import Path
import urllib.request
import urllib.parse
import html
import tempfile
from PyQt5.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QMainWindow,
    QWidget,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QSpinBox,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QCheckBox,
    QMessageBox,
    QTextEdit,
    QPlainTextEdit,
    QLineEdit,
    QComboBox,
    QScrollArea,
    QInputDialog,
    QFileDialog,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QKeySequenceEdit,
    QSizePolicy,
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QFont, QPen, QDesktopServices, QTextCursor, QPalette, QKeySequence, QPainterPath
from PyQt5.QtCore import Qt, QTimer, QTime, QDate, QUrl, QPoint, QSize, pyqtSignal, QObject, QEvent, QAbstractNativeEventFilter
import json
import glob


class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


CHANNEL_TYPE_DEFAULTS = {
    "videos": True,
    "shorts": True,
    "streams": True,
}

CHANNEL_TYPE_BUTTONS = (
    ("videos", "🎬", "Видео"),
    ("shorts", "⚡", "Shorts"),
    ("streams", "🔴", "Трансляция"),
)

APP_NAME = "YouTube Harvester"
APP_VERSION = "0.2.5-beta"
APP_TITLE = f"{APP_NAME} {APP_VERSION}"
USAGE_RULES_VERSION = "2026-06-13"
DEFAULT_QUICK_DOWNLOAD_HOTKEY = "Ctrl+Shift+Alt+Y"

MOJIBAKE_HINTS = (
    "Рџ", "Р’", "Рђ", "РЅ", "Р°", "Рµ", "Рё", "Рѕ", "СЂ", "СЃ", "С‚", "СЊ",
    "Ð", "Ñ", "вЂ", "вњ", "вљ", "рџ", "�",
)


def text_quality(text: str) -> int:
    cyrillic = sum(1 for char in text if "\u0400" <= char <= "\u04ff")
    emoji = sum(1 for char in text if ord(char) >= 0x1F000)
    bad = sum(text.count(marker) for marker in MOJIBAKE_HINTS)
    bad += text.count("\ufffd") * 3
    return cyrillic + emoji * 2 - bad * 8


def fix_mojibake(value):
    if not isinstance(value, str) or not any(marker in value for marker in MOJIBAKE_HINTS):
        return value
    best = value
    best_score = text_quality(value)
    for encoding in ("cp1251", "latin1"):
        try:
            candidate = value.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        score = text_quality(candidate)
        if score > best_score + 2:
            best = candidate
            best_score = score
    return best


def normalize_text_value(value):
    if isinstance(value, str):
        return fix_mojibake(value)
    if isinstance(value, dict):
        return {key: normalize_text_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_text_value(item) for item in value]
    return value


def quick_hotkey_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.translate(32, 34)
    painter.rotate(-35)

    painter.setPen(QPen(QColor("#80d4ff"), 3))
    painter.setBrush(QColor("#f6fbff"))
    body = QPainterPath()
    body.addRoundedRect(-10, -20, 20, 34, 10, 10)
    painter.drawPath(body)

    painter.setPen(QPen(QColor("#17314f"), 2))
    painter.setBrush(QColor("#ff7a2f"))
    painter.drawPolygon(QPoint(0, -31), QPoint(-10, -17), QPoint(10, -17))
    painter.drawPolygon(QPoint(-10, 5), QPoint(-22, 19), QPoint(-7, 15))
    painter.drawPolygon(QPoint(10, 5), QPoint(22, 19), QPoint(7, 15))

    painter.setPen(QPen(QColor("#17314f"), 2))
    painter.setBrush(QColor("#55cfff"))
    painter.drawEllipse(-5, -12, 10, 10)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#ffd34d"))
    painter.drawPolygon(QPoint(-5, 15), QPoint(0, 30), QPoint(5, 15))
    painter.setBrush(QColor("#ff5a3c"))
    painter.drawPolygon(QPoint(-3, 15), QPoint(0, 24), QPoint(3, 15))
    painter.end()
    return QIcon(pixmap)


def read_text_for_display(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return fix_mojibake(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    return fix_mojibake(raw.decode("utf-8", errors="replace"))


def default_quick_request_file() -> Path:
    configured = os.environ.get("YTD_QUICK_REQUEST_FILE", "").strip()
    if configured:
        return Path(configured)
    settings_file = os.environ.get("YTD_SETTINGS_FILE", "").strip()
    if settings_file:
        return Path(settings_file).parent / "quick_download.request"
    config_dir = os.environ.get("YTD_CONFIG_DIR", "").strip()
    if config_dir:
        return Path(config_dir) / "quick_download.request"
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
        return root / "YouTubeHarvester" / "quick_download.request"
    return Path.home() / ".config" / "YTD" / "quick_download.request"


def write_quick_download_request() -> int:
    try:
        request_file = default_quick_request_file()
        request_file.parent.mkdir(parents=True, exist_ok=True)
        request_file.write_text(str(int(time.time())) + "\n", encoding="utf-8")
        return 0
    except Exception as exc:
        print(f"Cannot request quick download window: {exc}", file=sys.stderr)
        return 1


class WindowsGlobalHotkeyFilter(QAbstractNativeEventFilter):
    WM_HOTKEY = 0x0312
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    MOD_NOREPEAT = 0x4000

    MODIFIER_MAP = {
        "ctrl": MOD_CONTROL,
        "control": MOD_CONTROL,
        "shift": MOD_SHIFT,
        "alt": MOD_ALT,
        "meta": MOD_WIN,
        "win": MOD_WIN,
        "windows": MOD_WIN,
    }

    KEY_MAP = {
        **{chr(code): code for code in range(ord("A"), ord("Z") + 1)},
        **{str(number): ord(str(number)) for number in range(10)},
        **{f"f{number}": 0x70 + number - 1 for number in range(1, 25)},
        "space": 0x20,
        "enter": 0x0D,
        "return": 0x0D,
        "tab": 0x09,
        "escape": 0x1B,
        "esc": 0x1B,
        "insert": 0x2D,
        "delete": 0x2E,
        "home": 0x24,
        "end": 0x23,
        "pageup": 0x21,
        "pagedown": 0x22,
        "up": 0x26,
        "down": 0x28,
        "left": 0x25,
        "right": 0x27,
    }

    def __init__(self, callback, hwnd: int = 0):
        super().__init__()
        self.callback = callback
        self.hwnd = hwnd
        self.hotkey_id = 0x594854
        self.registered = False
        self.sequence = ""

    def parse_sequence(self, sequence: str):
        portable = QKeySequence(sequence or DEFAULT_QUICK_DOWNLOAD_HOTKEY).toString(QKeySequence.PortableText)
        first = (portable.split(",")[0] or sequence or DEFAULT_QUICK_DOWNLOAD_HOTKEY).strip()
        parts = [part.strip().lower() for part in re.split(r"\s*\+\s*", first) if part.strip()]
        if not parts:
            return None

        modifiers = 0
        key = 0
        for part in parts:
            mapped_modifier = self.MODIFIER_MAP.get(part)
            if mapped_modifier:
                modifiers |= mapped_modifier
                continue
            mapped_key = self.KEY_MAP.get(part) or self.KEY_MAP.get(part.upper())
            if mapped_key:
                key = mapped_key

        if not key:
            return None
        return modifiers | self.MOD_NOREPEAT, key

    def register(self, sequence: str) -> bool:
        self.unregister()
        parsed = self.parse_sequence(sequence)
        if not parsed:
            return False
        modifiers, key = parsed
        try:
            ok = bool(ctypes.windll.user32.RegisterHotKey(self.hwnd, self.hotkey_id, modifiers, key))
        except Exception:
            return False
        self.registered = ok
        self.sequence = sequence if ok else ""
        return ok

    def unregister(self):
        if not self.registered:
            return
        try:
            ctypes.windll.user32.UnregisterHotKey(self.hwnd, self.hotkey_id)
        except Exception:
            pass
        self.registered = False

    def nativeEventFilter(self, event_type, message):
        event_name = bytes(event_type).decode(errors="ignore") if not isinstance(event_type, str) else event_type
        if event_name not in {"windows_generic_MSG", "windows_dispatcher_MSG"}:
            return False, 0
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
        except Exception:
            return False, 0
        if msg.message == self.WM_HOTKEY and int(msg.wParam) == self.hotkey_id:
            QTimer.singleShot(0, self.callback)
            return True, 0
        return False, 0


class PynputGlobalHotkey(QObject):
    triggered = pyqtSignal()

    MODIFIER_MAP = {
        "ctrl": "<ctrl>",
        "control": "<ctrl>",
        "shift": "<shift>",
        "alt": "<alt>",
        "meta": "<cmd>",
        "win": "<cmd>",
        "windows": "<cmd>",
    }

    SPECIAL_KEY_MAP = {
        "space": "<space>",
        "enter": "<enter>",
        "return": "<enter>",
        "tab": "<tab>",
        "escape": "<esc>",
        "esc": "<esc>",
        "insert": "<insert>",
        "delete": "<delete>",
        "home": "<home>",
        "end": "<end>",
        "pageup": "<page_up>",
        "pagedown": "<page_down>",
        "up": "<up>",
        "down": "<down>",
        "left": "<left>",
        "right": "<right>",
    }

    def __init__(self, callback):
        super().__init__()
        self.triggered.connect(callback)
        self.listener = None
        self.sequence = ""
        self.last_error = ""

    def sequence_to_pynput(self, sequence: str):
        portable = QKeySequence(sequence or DEFAULT_QUICK_DOWNLOAD_HOTKEY).toString(QKeySequence.PortableText)
        first = (portable.split(",")[0] or sequence or DEFAULT_QUICK_DOWNLOAD_HOTKEY).strip()
        parts = [part.strip().lower() for part in re.split(r"\s*\+\s*", first) if part.strip()]
        keys = []
        for part in parts:
            if part in self.MODIFIER_MAP:
                keys.append(self.MODIFIER_MAP[part])
            elif part in self.SPECIAL_KEY_MAP:
                keys.append(self.SPECIAL_KEY_MAP[part])
            elif re.fullmatch(r"f(?:[1-9]|1[0-9]|2[0-4])", part):
                keys.append(f"<{part}>")
            elif len(part) == 1:
                keys.append(part)
        if len(keys) != len(parts) or not keys:
            return ""
        return "+".join(keys)

    def register(self, sequence: str) -> bool:
        self.unregister()
        hotkey = self.sequence_to_pynput(sequence)
        if not hotkey:
            self.last_error = "не удалось разобрать комбинацию"
            return False
        try:
            from pynput import keyboard

            self.listener = keyboard.GlobalHotKeys({hotkey: self.triggered.emit})
            self.listener.start()
        except Exception as exc:
            self.listener = None
            self.last_error = str(exc)
            return False
        self.sequence = sequence
        self.last_error = ""
        return True

    def unregister(self):
        if self.listener is None:
            return
        try:
            self.listener.stop()
        except Exception:
            pass
        self.listener = None


class AppLocalHotkeyFilter(QObject):
    MODIFIER_KEYS = {
        Qt.Key_Control,
        Qt.Key_Shift,
        Qt.Key_Alt,
        Qt.Key_Meta,
        Qt.Key_AltGr,
    }

    def __init__(self, callback, sequence_getter):
        super().__init__()
        self.callback = callback
        self.sequence_getter = sequence_getter

    def normalized_sequence(self, sequence: str):
        text = QKeySequence(sequence or DEFAULT_QUICK_DOWNLOAD_HOTKEY).toString(QKeySequence.PortableText)
        return (text.split(",")[0] or "").replace(" ", "").casefold()

    def event_sequence(self, event):
        key = int(event.key())
        if key in self.MODIFIER_KEYS or key == Qt.Key_unknown:
            return ""
        try:
            value = int(event.modifiers()) | key
        except TypeError:
            value = event.modifiers() | key
        return QKeySequence(value).toString(QKeySequence.PortableText).replace(" ", "").casefold()

    def eventFilter(self, obj, event):
        if event.type() != QEvent.KeyPress:
            return False
        try:
            if event.isAutoRepeat():
                return False
        except Exception:
            pass
        if isinstance(QApplication.focusWidget(), QKeySequenceEdit):
            return False
        configured = self.normalized_sequence(self.sequence_getter())
        pressed = self.event_sequence(event)
        if configured and pressed == configured:
            QTimer.singleShot(0, self.callback)
            return True
        return False


USAGE_RULES_HTML = f"""
<h2>{APP_NAME}: правила использования</h2>
<p><b>Важно:</b> программа не связана с YouTube, Google, Telegram или авторами yt-dlp.
Она является локальной оболочкой, которая запускает внешние инструменты на вашем компьютере.</p>

<h3>Что нужно понимать</h3>
<ul>
  <li>Скачивайте только те материалы, на которые у вас есть права, разрешение автора,
      либо законное основание для личного использования.</li>
  <li>Соблюдайте Условия использования YouTube, авторское право и законы вашей страны.</li>
  <li>Не используйте программу для обхода ограничений доступа, массового копирования,
      пиратского распространения, продажи или публичной трансляции чужого контента.</li>
  <li>Telegram-уведомления могут отправлять названия, ссылки и файлы в выбранный канал.
      Храните BOT_TOKEN и CHANNEL_ID аккуратно.</li>
  <li>Вы самостоятельно отвечаете за выбранные каналы, очередь, скачанные файлы и их дальнейшее использование.</li>
</ul>

<h3>Используемые компоненты</h3>
<ul>
  <li><b>yt-dlp</b> выполняет чтение страниц и скачивание медиафайлов.</li>
  <li><b>PyQt5/Qt</b> используется для графического интерфейса.</li>
  <li><b>curl</b> используется для Telegram-уведомлений в режиме SOCKS-прокси.</li>
  <li><b>pynput</b> используется для глобальной горячей клавиши в Linux/X11.</li>
  <li><b>bash-движок</b> оставлен в исходниках как устаревший, но отключён в интерфейсе и не используется.</li>
</ul>

<p>У каждого внешнего компонента есть собственная лицензия и документация.
Ссылки на основные правила и проекты есть в README.</p>
"""


class UsageRulesDialog(QDialog):
    def __init__(self, required: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Правила использования")
        self.setModal(True)
        self.setMinimumSize(620, 500)
        self.required = required

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(USAGE_RULES_HTML)
        layout.addWidget(text, 1)

        self.checkboxes = []
        if required:
            for label in (
                "Я прочитал(а) правила и понимаю, что отвечаю за использование программы.",
                "Я буду соблюдать правила YouTube, авторское право и законы своей страны.",
                "Я понимаю, что внешние инструменты поставляются со своими лицензиями и без гарантий.",
            ):
                checkbox = QCheckBox(label)
                checkbox.stateChanged.connect(self.update_accept_button)
                self.checkboxes.append(checkbox)
                layout.addWidget(checkbox)

        buttons = QDialogButtonBox(
            (QDialogButtonBox.Ok | QDialogButtonBox.Cancel) if required else QDialogButtonBox.Close
        )
        if required:
            buttons.button(QDialogButtonBox.Ok).setText("Принимаю")
            buttons.button(QDialogButtonBox.Cancel).setText("Не принимаю")
            buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        else:
            buttons.button(QDialogButtonBox.Close).setText("Закрыть")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.buttons = buttons

    def update_accept_button(self):
        if not self.required:
            return
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            all(checkbox.isChecked() for checkbox in self.checkboxes)
        )


class TrayLauncher:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.is_windows = os.name == "nt"
        bundled_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        self.app_dir = Path(os.environ.get("YTD_APP_DIR", bundled_dir))
        self.data_dir = Path(os.environ.get("YTD_DATA_DIR", self.default_data_dir()))
        self.config_dir = Path(os.environ.get("YTD_CONFIG_DIR", self.default_config_dir()))
        self.cache_dir = Path(os.environ.get("YTD_CACHE_DIR", self.default_cache_dir()))

        self.script_path = Path(os.environ.get("YTD_SCRIPT_PATH", self.app_dir / "run_download.sh"))
        self.python_downloader_path = Path(os.environ.get("YTD_PYTHON_DOWNLOADER_PATH", self.app_dir / "scripts" / "downloader.py"))
        self.mark_script_path = Path(os.environ.get("YTD_MARK_SCRIPT_PATH", self.app_dir / "scripts" / "mark_channel_archived.py"))
        self.migrate_script_path = Path(os.environ.get("YTD_MIGRATE_SCRIPT_PATH", self.app_dir / "scripts" / "migrate_archive_details.py"))
        self.check_sections_script_path = Path(os.environ.get("YTD_CHECK_SECTIONS_SCRIPT_PATH", self.app_dir / "scripts" / "check_channel_sections.py"))
        self.app_icon_path = Path(os.environ.get("YTD_APP_ICON", self.app_dir / "assets" / "yt-harvester.png"))
        self.channels_file = Path(os.environ.get("YTD_CHANNELS_FILE", self.data_dir / "channels.txt"))
        self.queue_file = Path(os.environ.get("YTD_QUEUE_FILE", self.data_dir / "queue.txt"))
        self.archive_file = Path(os.environ.get("YTD_ARCHIVE_FILE", self.data_dir / "yt_archive.txt"))
        self.archive_details_file = Path(os.environ.get("YTD_ARCHIVE_DETAILS_FILE", self.data_dir / "archive_details.jsonl"))
        self.log_file = Path(os.environ.get("YTD_LOG_FILE", self.data_dir / "download.log"))
        self.status_file = Path(os.environ.get("YTD_STATUS_FILE", self.data_dir / "status.json"))
        self.stop_file = Path(os.environ.get("YTD_STOP_FILE", self.data_dir / "stop_requested"))
        self.quick_request_file = default_quick_request_file()
        self.last_download_file = Path(os.environ.get("YTD_LAST_DOWNLOAD_FILE", self.data_dir / "last_download_at.txt"))
        self.overview_logo_path = Path(os.environ.get("YTD_OVERVIEW_LOGO", self.app_dir / "assets" / "overview-logo.png"))
        self.video_placeholder_path = Path(os.environ.get("YTD_VIDEO_PLACEHOLDER", self.app_dir / "assets" / "video-placeholder.png"))
        self.queue_art_path = Path(os.environ.get("YTD_QUEUE_ART", self.app_dir / "assets" / "queue-scheduler.png"))
        self.ffmpeg_dir = self.detect_ffmpeg_dir()
        self.deno_path = self.detect_deno_path()
        self.is_running = False
        self.state = "idle"
        self.current_process = None

        self.schedules_file = Path(os.environ.get("YTD_SCHEDULES_FILE", self.default_settings_dir() / "schedules.json"))
        self.settings_file = Path(os.environ.get("YTD_SETTINGS_FILE", self.default_settings_dir() / "settings.json"))
        self.env_file = Path(os.environ.get("YTD_ENV_FILE", self.config_dir / ".env"))
        self.channel_rules_file = Path(os.environ.get("YTD_CHANNEL_RULES_FILE", self.config_dir / "channel_rules.json"))
        self.app_settings = self.load_app_settings()
        self.apply_runtime_settings(self.app_settings)
        self.schedules = []
        self.main_window = None
        self.hotkey_filter = None
        self.hotkey_window = None
        self.local_hotkey_filter = AppLocalHotkeyFilter(
            self.open_quick_download_window,
            lambda: self.quick_download_hotkey,
        )
        self.app.installEventFilter(self.local_hotkey_filter)
        self.quick_telegram_override = None
        self.quick_single_url = ""
        self.last_tray_trigger_at = 0.0
        if self.app_icon_path.exists():
            self.app.setWindowIcon(QIcon(str(self.app_icon_path)))

        self.tray = QSystemTrayIcon(self.app)
        self.create_menu()
        self.update_icon()
        self.tray.show()

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_process_status)
        self.timer.start(1000)

        self.schedule_timer = QTimer()
        self.schedule_timer.timeout.connect(self.check_schedules)
        self.schedule_timer.start(15000)

        self.load_schedules()
        self.setup_global_hotkey()
        self.app.aboutToQuit.connect(self.cleanup_global_hotkey)
        QTimer.singleShot(700, self.show_initial_usage_rules)

    def create_colored_icon(self, color_rgb: tuple, rect: bool = False) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)

        color = QColor(*color_rgb)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(Qt.transparent))
        painter.drawEllipse(2, 2, 60, 60)

        if rect:
            painter.setBrush(QBrush(Qt.white))
            painter.drawRect(20, 20, 24, 24)
        else:
            font = QFont()
            font.setBold(True)
            font.setPixelSize(20)
            painter.setFont(font)
            painter.setPen(Qt.white)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "Zzz")

        painter.end()
        return QIcon(pixmap)

    def create_menu(self):
        menu = QMenu()
        self.tray_status_action = menu.addAction("😴 Статус: сон")
        self.tray_status_action.setEnabled(False)
        menu.addSeparator()

        overview_action = menu.addAction("📊 Обзор")
        overview_action.triggered.connect(lambda checked=False: self.open_main_window(0))
        channels_action = menu.addAction("📺 Каналы")
        channels_action.triggered.connect(lambda checked=False: self.open_main_window(1))
        queue_action = menu.addAction("📥 Очередь")
        queue_action.triggered.connect(lambda checked=False: self.open_main_window(2))
        settings_action = menu.addAction("⚙️ Настройки")
        settings_action.triggered.connect(lambda checked=False: self.open_main_window(3))
        menu.addSeparator()

        self.quick_download_action = menu.addAction(f"⚡ Быстрое скачивание ({self.quick_download_hotkey})")
        self.quick_download_action.triggered.connect(lambda checked=False: self.open_quick_download_window())
        self.tray_start_action = menu.addAction("⏬ Старт")
        self.tray_start_action.triggered.connect(self.run_script)
        self.tray_stop_action = menu.addAction("⏹ Стоп")
        self.tray_stop_action.triggered.connect(self.request_stop)
        menu.addSeparator()

        downloads_action = menu.addAction("📁 Загрузки")
        downloads_action.triggered.connect(lambda checked=False: self.open_path(self.final_dir))
        temp_action = menu.addAction("⌛ Врем.")
        temp_action.triggered.connect(lambda checked=False: self.open_path(self.temp_dir))
        menu.addSeparator()

        exit_action = menu.addAction("🚪 Выход")
        exit_action.triggered.connect(self.app.quit)

        self.tray_menu = menu
        menu.aboutToShow.connect(self.update_tray_menu)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_clicked)
        self.update_tray_menu()

    def update_tray_menu(self):
        if not hasattr(self, "tray_status_action"):
            return
        if self.state == "stopping":
            status_text = "⏹ Статус: останавливается"
        elif self.is_running:
            status_text = "⬇️ Статус: скачивание"
        elif glob.glob(str(self.temp_dir / "*.part")):
            status_text = "🟢 Статус: есть недокачанные"
        else:
            status_text = "😴 Статус: сон"

        self.tray_status_action.setText(status_text)
        self.quick_download_action.setText(f"⚡ Быстрое скачивание ({self.quick_download_hotkey})")
        self.tray_start_action.setEnabled(not self.is_running)
        self.tray_stop_action.setEnabled(self.is_running)

    def open_path(self, path: Path):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def on_tray_clicked(self, reason):
        from PyQt5.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.DoubleClick:
            self.open_main_window()
            self.last_tray_trigger_at = 0.0
            return

        if reason == QSystemTrayIcon.Trigger:
            now = time.monotonic()
            if now - self.last_tray_trigger_at <= 0.55:
                self.open_main_window()
                self.last_tray_trigger_at = 0.0
            else:
                self.last_tray_trigger_at = now

    def open_main_window(self, tab_index: int = 0):
        if not self.ensure_usage_rules_accepted():
            return
        if self.main_window is None:
            self.main_window = MainWindow(self)
        self.main_window.refresh_all()
        self.main_window.tabs.setCurrentIndex(tab_index)
        self.main_window.showNormal()
        self.main_window.setWindowState(self.main_window.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.main_window.raise_()
        self.main_window.activateWindow()

    def open_quick_download_window(self):
        if not self.ensure_usage_rules_accepted(self.main_window):
            self.show_notification("⚖️", "Быстрое скачивание", "Сначала нужно принять правила использования")
            return
        if self.main_window is None:
            self.main_window = MainWindow(self)
        self.main_window.open_quick_download_window()

    def is_wayland_session(self):
        return not self.is_windows and os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"

    def setup_global_hotkey(self):
        if self.is_windows:
            self.hotkey_window = QWidget()
            self.hotkey_window.setWindowTitle(f"{APP_NAME} Hotkey")
            hwnd = int(self.hotkey_window.winId())
            self.hotkey_filter = WindowsGlobalHotkeyFilter(self.open_quick_download_window, hwnd)
            self.app.installNativeEventFilter(self.hotkey_filter)
        else:
            self.hotkey_filter = PynputGlobalHotkey(self.open_quick_download_window)
        self.refresh_global_hotkey()

    def refresh_global_hotkey(self):
        if hasattr(self, "quick_download_action"):
            self.update_tray_menu()
        if self.hotkey_filter is None:
            return
        if self.is_wayland_session():
            self.hotkey_filter.unregister()
            return
        if not self.hotkey_filter.register(self.quick_download_hotkey):
            detail = getattr(self.hotkey_filter, "last_error", "")
            message = f"Не удалось назначить: {self.quick_download_hotkey}"
            if detail:
                message += f"\n{detail[:160]}"
            self.show_notification("⚠️", "Горячая клавиша", message)

    def cleanup_global_hotkey(self):
        if self.hotkey_filter is not None:
            self.hotkey_filter.unregister()
            if self.is_windows:
                self.app.removeNativeEventFilter(self.hotkey_filter)
        if self.hotkey_window is not None:
            self.hotkey_window.deleteLater()
            self.hotkey_window = None
        if self.local_hotkey_filter is not None:
            self.app.removeEventFilter(self.local_hotkey_filter)

    def gsettings_get(self, schema: str, key: str, path: str | None = None):
        command = ["gsettings"]
        if path:
            command.extend(["get", f"{schema}:{path}", key])
        else:
            command.extend(["get", schema, key])
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
                check=False,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def gsettings_set(self, schema: str, key: str, value: str, path: str | None = None) -> bool:
        command = ["gsettings"]
        if path:
            command.extend(["set", f"{schema}:{path}", key, value])
        else:
            command.extend(["set", schema, key, value])
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def gsettings_string(self, value: str):
        return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"

    def gsettings_strv(self, values):
        return "[" + ", ".join(self.gsettings_string(value) for value in values) + "]"

    def parse_gsettings_list(self, value: str | None):
        if not value:
            return []
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return []
        if isinstance(parsed, (list, tuple)):
            return [str(item) for item in parsed]
        return []

    def quick_hotkey_desktop_binding(self, sequence: str | None = None):
        portable = QKeySequence(sequence or self.quick_download_hotkey or DEFAULT_QUICK_DOWNLOAD_HOTKEY).toString(QKeySequence.PortableText)
        first = (portable.split(",")[0] or DEFAULT_QUICK_DOWNLOAD_HOTKEY).strip()
        parts = [part.strip().lower() for part in re.split(r"\s*\+\s*", first) if part.strip()]
        modifiers = {
            "<Primary>": False,
            "<Shift>": False,
            "<Alt>": False,
            "<Super>": False,
        }
        key = ""
        for part in parts:
            if part in {"ctrl", "control"}:
                modifiers["<Primary>"] = True
            elif part == "shift":
                modifiers["<Shift>"] = True
            elif part == "alt":
                modifiers["<Alt>"] = True
            elif part in {"meta", "win", "windows"}:
                modifiers["<Super>"] = True
            elif re.fullmatch(r"f(?:[1-9]|1[0-9]|2[0-4])", part):
                key = part.upper()
            elif len(part) == 1:
                key = part
            else:
                key = part
        if not key:
            return ""
        return "".join(name for name, enabled in modifiers.items() if enabled) + key

    def quick_download_command(self):
        installed = shutil.which("yt-harvester")
        if installed:
            return shlex.join([installed, "--quick-download"])
        start_script = self.app_dir / "start_tray.sh"
        if start_script.exists():
            return shlex.join([str(start_script), "--quick-download"])
        if getattr(sys, "frozen", False):
            return shlex.join([sys.executable, "--quick-download"])
        return shlex.join([sys.executable, str(Path(__file__).resolve()), "--quick-download"])

    def install_system_quick_hotkey(self, sequence: str | None = None):
        if self.is_windows:
            return False, "Системная установка нужна только для Linux Wayland"
        if not shutil.which("gsettings"):
            return False, "gsettings не найден"
        binding = self.quick_hotkey_desktop_binding(sequence)
        if not binding:
            return False, "Не удалось преобразовать комбинацию клавиш"
        command = self.quick_download_command()
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        errors = []
        if "cinnamon" in desktop:
            ok, message = self.install_cinnamon_quick_hotkey(binding, command)
            if ok:
                return True, message
            errors.append(message)
        ok, message = self.install_gnome_quick_hotkey(binding, command)
        if ok:
            return True, message
        errors.append(message)
        if "cinnamon" not in desktop:
            ok, message = self.install_cinnamon_quick_hotkey(binding, command)
            if ok:
                return True, message
            errors.append(message)
        return False, "; ".join(error for error in errors if error) or "Не удалось добавить системную комбинацию"

    def install_cinnamon_quick_hotkey(self, binding: str, command: str):
        list_schema = "org.cinnamon.desktop.keybindings"
        item_schema = "org.cinnamon.desktop.keybindings.custom-keybinding"
        current = self.gsettings_get(list_schema, "custom-list")
        if current is None:
            return False, "Cinnamon keybindings schema недоступна"
        names = self.parse_gsettings_list(current)
        target_name = "YouTube Harvester Quick Download"
        target = ""
        for name in names:
            path = f"/org/cinnamon/desktop/keybindings/custom-keybindings/{name}/"
            existing_name = self.gsettings_get(item_schema, "name", path)
            existing_command = self.gsettings_get(item_schema, "command", path)
            if target_name in str(existing_name or "") or "--quick-download" in str(existing_command or ""):
                target = name
                break
        if not target:
            used = set(names)
            index = 0
            while f"custom{index}" in used:
                index += 1
            target = f"custom{index}"
            names.append(target)
            if not self.gsettings_set(list_schema, "custom-list", self.gsettings_strv(names)):
                return False, "Не удалось обновить список Cinnamon custom-list"
        path = f"/org/cinnamon/desktop/keybindings/custom-keybindings/{target}/"
        ok = (
            self.gsettings_set(item_schema, "name", self.gsettings_string(target_name), path)
            and self.gsettings_set(item_schema, "command", self.gsettings_string(command), path)
            and self.gsettings_set(item_schema, "binding", self.gsettings_strv([binding]), path)
        )
        if not ok:
            return False, "Не удалось записать Cinnamon shortcut"
        return True, f"Системная комбинация Cinnamon установлена: {binding}"

    def install_gnome_quick_hotkey(self, binding: str, command: str):
        list_schema = "org.gnome.settings-daemon.plugins.media-keys"
        item_schema = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
        current = self.gsettings_get(list_schema, "custom-keybindings")
        if current is None:
            return False, "GNOME media-keys schema недоступна"
        paths = self.parse_gsettings_list(current)
        target_name = "YouTube Harvester Quick Download"
        target_path = ""
        for path in paths:
            existing_name = self.gsettings_get(item_schema, "name", path)
            existing_command = self.gsettings_get(item_schema, "command", path)
            if target_name in str(existing_name or "") or "--quick-download" in str(existing_command or ""):
                target_path = path
                break
        if not target_path:
            used = set(paths)
            index = 0
            while f"/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom{index}/" in used:
                index += 1
            target_path = f"/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom{index}/"
            paths.append(target_path)
            if not self.gsettings_set(list_schema, "custom-keybindings", self.gsettings_strv(paths)):
                return False, "Не удалось обновить GNOME custom-keybindings"
        ok = (
            self.gsettings_set(item_schema, "name", self.gsettings_string(target_name), target_path)
            and self.gsettings_set(item_schema, "command", self.gsettings_string(command), target_path)
            and self.gsettings_set(item_schema, "binding", self.gsettings_string(binding), target_path)
        )
        if not ok:
            return False, "Не удалось записать GNOME shortcut"
        return True, f"Системная комбинация GNOME установлена: {binding}"

    def load_app_settings(self):
        try:
            if self.settings_file.exists():
                data = json.loads(self.settings_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def save_app_settings(self):
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            self.settings_file.write_text(
                json.dumps(self.app_settings, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            self.show_notification("⚠️", "Настройки", str(e)[:200])

    def usage_rules_accepted(self):
        if os.environ.get("YTD_SKIP_USAGE_RULES") == "1":
            return True
        return self.app_settings.get("usage_rules_accepted_version") == USAGE_RULES_VERSION

    def show_initial_usage_rules(self):
        if self.usage_rules_accepted():
            return
        if not self.ensure_usage_rules_accepted():
            self.show_notification("⚖️", "Правила не приняты", "Программа будет закрыта")
            self.app.quit()

    def ensure_usage_rules_accepted(self, parent=None):
        if self.usage_rules_accepted():
            return True
        dialog = UsageRulesDialog(required=True, parent=parent)
        if dialog.exec_() == QDialog.Accepted:
            self.app_settings["usage_rules_accepted_version"] = USAGE_RULES_VERSION
            self.save_app_settings()
            if self.main_window is not None:
                self.main_window.ui_settings["usage_rules_accepted_version"] = USAGE_RULES_VERSION
            return True
        return False

    def windows_roaming_dir(self):
        base = os.environ.get("APPDATA")
        if base:
            return Path(base)
        return Path.home() / "AppData" / "Roaming"

    def windows_local_dir(self):
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base)
        return Path.home() / "AppData" / "Local"

    def default_data_dir(self):
        if self.is_windows:
            return self.windows_local_dir() / "YouTubeHarvester"
        return self.app_dir

    def default_config_dir(self):
        if self.is_windows:
            return self.windows_roaming_dir() / "YouTubeHarvester"
        return self.default_data_dir()

    def default_cache_dir(self):
        if self.is_windows:
            return self.windows_local_dir() / "YouTubeHarvester" / "cache"
        return Path.home() / ".cache" / "YTD"

    def default_settings_dir(self):
        if self.is_windows:
            return self.windows_roaming_dir() / "YouTubeHarvester"
        return Path.home() / ".config" / "YTD"

    def default_download_dir(self):
        return Path.home() / "Downloads" / "YouTubeHarvester"

    def default_temp_dir(self):
        if self.is_windows:
            return Path(os.environ.get("TEMP", str(self.windows_local_dir() / "Temp"))) / "YTH"
        return Path.home() / "temp" / "YTH"

    def default_download_engine(self):
        return "python"

    def command_exists(self, command: str):
        return shutil.which(command) is not None

    def detect_ffmpeg_dir(self):
        configured = os.environ.get("YTD_FFMPEG_DIR", "").strip()
        candidates = []
        if configured:
            candidates.append(Path(configured))
        candidates.extend([
            self.app_dir / "ffmpeg",
            self.app_dir / "ffmpeg" / "bin",
            self.app_dir / "bin",
            Path(sys.executable).resolve().parent / "ffmpeg",
            Path(sys.executable).resolve().parent / "ffmpeg" / "bin",
            Path(sys.executable).resolve().parent / "bin",
            self.app_dir / "tools" / "windows" / "ffmpeg" / "bin",
            self.app_dir / "tools" / "windows" / "ffmpeg",
        ])
        ffmpeg_path = shutil.which("ffmpeg")
        ffprobe_path = shutil.which("ffprobe")
        if ffmpeg_path and ffprobe_path and Path(ffmpeg_path).parent == Path(ffprobe_path).parent:
            candidates.append(Path(ffmpeg_path).parent)

        ffmpeg_name = "ffmpeg.exe" if self.is_windows else "ffmpeg"
        ffprobe_name = "ffprobe.exe" if self.is_windows else "ffprobe"
        for candidate in candidates:
            if (candidate / ffmpeg_name).exists() and (candidate / ffprobe_name).exists():
                return candidate
        return None

    def detect_deno_path(self):
        configured = os.environ.get("YTD_DENO_PATH", "").strip()
        candidates = []
        if configured:
            candidates.append(Path(configured))
        deno_name = "deno.exe" if self.is_windows else "deno"
        candidates.extend([
            self.app_dir / "deno" / deno_name,
            self.app_dir / "deno" / "bin" / deno_name,
            self.app_dir / "bin" / deno_name,
            Path(sys.executable).resolve().parent / "deno" / deno_name,
            Path(sys.executable).resolve().parent / "deno" / "bin" / deno_name,
            Path(sys.executable).resolve().parent / "bin" / deno_name,
            self.app_dir / "tools" / "windows" / "deno" / deno_name,
            self.app_dir / "tools" / "windows" / "deno" / "bin" / deno_name,
        ])
        deno_path = shutil.which("deno")
        if deno_path:
            candidates.append(Path(deno_path))

        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def yt_dlp_js_runtime_args(self):
        if self.deno_path:
            return ["--js-runtimes", f"deno:{self.deno_path}"]
        return ["--js-runtimes", "deno"]

    def yt_dlp_command(self):
        configured_json = os.environ.get("YTD_YT_DLP_COMMAND_JSON", "").strip()
        if configured_json:
            try:
                configured = json.loads(configured_json)
                if isinstance(configured, list) and all(isinstance(item, str) for item in configured):
                    return configured
            except json.JSONDecodeError:
                pass
        configured = os.environ.get("YTD_YT_DLP_COMMAND", "").strip()
        if configured:
            try:
                parts = shlex.split(configured, posix=(os.name != "nt"))
                if os.name == "nt":
                    parts = [part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part for part in parts]
                return parts
            except ValueError:
                return [configured]
        if getattr(sys, "frozen", False):
            return [sys.executable, "--run-yt-dlp"]
        return ["yt-dlp"]

    def can_use_bash_engine(self):
        return self.script_path.exists() and self.command_exists("bash")

    def can_use_python_engine(self):
        return self.python_downloader_path.exists()

    def python_script_command(self, script_path: Path):
        script_path = Path(script_path)
        if getattr(sys, "frozen", False):
            return [sys.executable, "--run-script", script_path.name]
        return [sys.executable, str(script_path)]

    def run_python_script_capture(self, script_path: Path, args: list[str], timeout: int):
        script_path = Path(script_path)
        return subprocess.run(
            self.python_script_command(script_path) + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=self.script_environment(),
        )

    def _setting_path(self, settings: dict, key: str, env_key: str, default_path: Path):
        value = str(settings.get(key) or os.environ.get(env_key) or default_path).strip()
        return Path(os.path.expanduser(value))

    def _setting_int(self, settings: dict, key: str, default: int, minimum: int = 1, maximum: int = 500):
        try:
            value = int(settings.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _setting_bool(self, settings: dict, key: str, default: bool):
        value = settings.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off", "нет"}
        return bool(value)

    def env_setting(self, key: str):
        try:
            if not self.env_file.exists():
                return None
            for line in self.env_file.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if not text or text.startswith("#"):
                    continue
                if text.startswith("export "):
                    text = text[7:].strip()
                try:
                    parts = shlex.split(text, comments=False, posix=True)
                except ValueError:
                    parts = [text]
                if parts and "=" in parts[0]:
                    env_key, value = parts[0].split("=", 1)
                    if env_key.strip() == key:
                        return value
        except Exception:
            return None
        return None

    def apply_runtime_settings(self, settings: dict):
        self.temp_dir = self._setting_path(settings, "temp_dir", "YTD_TEMP_DIR", self.default_temp_dir())
        self.final_dir = self._setting_path(settings, "download_dir", "YTD_FINAL_DIR", self.default_download_dir())
        self.videos_limit = self._setting_int(settings, "videos_limit", 5, 1, 100)
        self.shorts_limit = self._setting_int(settings, "shorts_limit", 5, 1, 100)
        self.streams_limit = self._setting_int(settings, "streams_limit", 5, 1, 100)
        self.log_keep_count = self._setting_int(settings, "log_keep_count", 3, 1, 50)
        self.cleanup_temp = self._setting_bool(settings, "cleanup_temp", True)
        self.retry_failed_queue = self._setting_bool(settings, "retry_failed_queue", True)
        self.quick_download_hotkey = str(
            settings.get("quick_download_hotkey")
            or os.environ.get("YTD_QUICK_DOWNLOAD_HOTKEY")
            or DEFAULT_QUICK_DOWNLOAD_HOTKEY
        ).strip() or DEFAULT_QUICK_DOWNLOAD_HOTKEY
        self.quick_download_telegram_notify = self._setting_bool(settings, "quick_download_telegram_notify", False)
        telegram_default = self._setting_bool({"telegram_enabled": self.env_setting("TELEGRAM_ENABLED")}, "telegram_enabled", True)
        self.telegram_enabled = self._setting_bool(settings, "telegram_enabled", telegram_default)
        self.download_engine = "python"
        resolution = str(settings.get("max_resolution") or os.environ.get("YTD_MAX_RESOLUTION") or "1080").strip()
        self.max_resolution = resolution if resolution in {"480", "720", "1080", "1440", "2160", "best"} else "1080"

    def validate_download_environment(self):
        if not self.python_downloader_path.exists():
            self.show_notification("❌", "Python-движок", f"Не найден файл: {self.python_downloader_path}")
            return False
        if self.is_windows and not self.ffmpeg_dir:
            self.show_notification(
                "❌",
                "ffmpeg не найден",
                "Windows-сборке нужны bundled ffmpeg.exe и ffprobe.exe",
            )
            return False
        if self.is_windows and not self.deno_path:
            self.show_notification(
                "❌",
                "Deno не найден",
                "Windows-сборке нужен bundled deno.exe для YouTube JS",
            )
            return False
        if (
            not getattr(sys, "frozen", False)
            and not os.environ.get("YTD_YT_DLP_COMMAND")
            and not os.environ.get("YTD_YT_DLP_COMMAND_JSON")
            and not self.command_exists("yt-dlp")
        ):
            self.show_notification("❌", "yt-dlp не найден", "Установите yt-dlp и проверьте PATH")
            return False
        return True

    def script_environment(self):
        env = os.environ.copy()
        yt_dlp_command = self.yt_dlp_command()
        telegram_enabled = self.telegram_enabled if self.quick_telegram_override is None else bool(self.quick_telegram_override)
        env.update({
            "PYTHONIOENCODING": "utf-8:replace",
            "PYTHONUTF8": "1",
            "PYTHONLEGACYWINDOWSSTDIO": "0",
            "PYTHONUNBUFFERED": "1",
            "YTD_APP_DIR": str(self.app_dir),
            "YTD_DATA_DIR": str(self.data_dir),
            "YTD_CONFIG_DIR": str(self.config_dir),
            "YTD_CACHE_DIR": str(self.cache_dir),
            "YTD_ENV_FILE": str(self.env_file),
            "YTD_CHANNEL_RULES_FILE": str(self.channel_rules_file),
            "YTD_ARCHIVE_DETAILS_FILE": str(self.archive_details_file),
            "YTD_TEMP_DIR": str(self.temp_dir),
            "YTD_FINAL_DIR": str(self.final_dir),
            "YTD_VIDEOS_LIMIT": str(self.videos_limit),
            "YTD_SHORTS_LIMIT": str(self.shorts_limit),
            "YTD_STREAMS_LIMIT": str(self.streams_limit),
            "YTD_MAX_RESOLUTION": str(self.max_resolution),
            "YTD_LOG_KEEP_COUNT": str(self.log_keep_count),
            "YTD_CLEANUP_TEMP": "1" if self.cleanup_temp else "0",
            "YTD_RETRY_FAILED_QUEUE": "1" if self.retry_failed_queue else "0",
            "YTD_TELEGRAM_ENABLED": "1" if telegram_enabled else "0",
            "YTD_DOWNLOAD_ENGINE": self.download_engine,
            "YTD_QUICK_DOWNLOAD_HOTKEY": self.quick_download_hotkey,
            "YTD_QUICK_DOWNLOAD_TELEGRAM_NOTIFY": "1" if self.quick_download_telegram_notify else "0",
            "YTD_YT_DLP_COMMAND": subprocess.list2cmdline(yt_dlp_command),
            "YTD_YT_DLP_COMMAND_JSON": json.dumps(yt_dlp_command, ensure_ascii=False),
        })
        if self.quick_single_url:
            env["YTD_SINGLE_QUEUE_URL"] = self.quick_single_url
        if self.ffmpeg_dir:
            env["YTD_FFMPEG_DIR"] = str(self.ffmpeg_dir)
        if self.deno_path:
            env["YTD_DENO_PATH"] = str(self.deno_path)
        return env

    def run_script(self, telegram_override=None, single_queue_url: str = ""):
        if self.is_running:
            self.show_notification("⚠️", "Скрипт уже запущен", "Подождите завершения...")
            return
        if not self.ensure_usage_rules_accepted(self.main_window):
            self.show_notification("⚖️", "Скачивание не запущено", "Сначала нужно принять правила использования")
            return
        if self.main_window is not None:
            try:
                self.main_window.save_settings_from_ui(show_message=False)
            except Exception as e:
                self.show_notification("⚠️", "Настройки", f"Не удалось применить настройки: {str(e)[:160]}")
        if not self.validate_download_environment():
            return

        try:
            self.stop_file.unlink(missing_ok=True)
        except Exception:
            pass

        self.is_running = True
        self.state = "running"
        self.quick_telegram_override = telegram_override
        self.quick_single_url = str(single_queue_url or "").strip()
        self.update_icon()
        self.update_tray_menu()
        self.show_notification("▶️", "Загрузка началась", "Скрипт запущен...")

        thread = threading.Thread(target=self._execute_script, daemon=True)
        thread.start()

    def _execute_script(self):
        proc = None
        try:
            command = self.python_script_command(self.python_downloader_path)
            proc = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self.script_environment(),
            )
            self.current_process = proc
            proc.wait()
        except Exception as e:
            self.show_notification("❌", "Ошибка", str(e)[:200])
        finally:
            self.current_process = None
            self.is_running = False
            self.state = "idle"
            self.quick_telegram_override = None
            self.quick_single_url = ""
            self.update_icon()
            self.update_tray_menu()

    def request_stop(self):
        if not self.is_running:
            return
        try:
            self.stop_file.write_text(str(int(time.time())) + "\n", encoding="utf-8")
            self.state = "stopping"
            self.update_icon()
            self.update_tray_menu()
            self.show_notification("⏹", "Остановка", "Скрипт завершится после текущего безопасного шага")
        except Exception as e:
            self.show_notification("❌", "Не удалось остановить", str(e)[:200])

    def update_icon(self):
        # Проверка приоритетной иконки
        part_files = glob.glob(str(self.temp_dir / "*.part"))
        if part_files:
            icon = self.create_colored_icon((40, 180, 40), rect=True)  # зелёный круг с прямоугольником
            tooltip = f"{APP_NAME} - есть загрузки .part"
        else:
            if self.state == "stopping":
                icon = self.create_colored_icon((230, 150, 40), rect=True)
                tooltip = f"{APP_NAME} - останавливается"
            elif self.state == "running":
                icon = self.create_colored_icon((220, 53, 69), rect=True)  # красный круг с прямоугольником
                tooltip = f"{APP_NAME} - работает"
            else:
                icon = self.create_colored_icon((120, 120, 120), rect=False)  # серый круг Zzz
                tooltip = f"{APP_NAME} - спит"

        self.tray.setIcon(icon)
        self.tray.setToolTip(tooltip)

    def check_process_status(self):
        self.check_quick_download_request()
        self.update_icon()
        if self.main_window is not None and self.main_window.isVisible():
            self.main_window.refresh_overview()

    def check_quick_download_request(self):
        try:
            if not self.quick_request_file.exists():
                return
            self.quick_request_file.unlink(missing_ok=True)
        except Exception:
            return
        self.open_quick_download_window()

    def show_notification(self, icon: str, title: str, message: str):
        try:
            self.tray.showMessage(f"{icon} {title}", message, QSystemTrayIcon.Information, 5000)
        except:
            pass

    # ------------------ Планировщик ------------------
    def open_schedule_window(self):
        self.open_main_window(2)

    def save_schedules(self):
        try:
            self.schedules_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.schedules_file, "w", encoding="utf-8") as f:
                json.dump(self.schedules, f, ensure_ascii=False, indent=2)
            if self.main_window is not None:
                self.main_window.refresh_schedules()
        except Exception as e:
            print("Error saving schedules:", e)

    def load_schedules(self):
        try:
            if self.schedules_file.exists():
                with open(self.schedules_file, "r", encoding="utf-8") as f:
                    self.schedules = json.load(f)
            else:
                self.schedules = []
        except Exception as e:
            print("Error loading schedules:", e)
            self.schedules = []

    def check_schedules(self):
        if self.is_running:
            return
        now = QTime.currentTime()
        today = QDate.currentDate().toString("yyyy-MM-dd")

        for sched in list(self.schedules):
            try:
                if not sched.get("enabled", True):
                    continue
                sch_hour = int(sched.get("hour", 0))
                if now.hour() == sch_hour:
                    marker = f"{today}-{sch_hour:02d}"
                    if sched.get("last_run_marker") != marker:
                        sched["last_run_marker"] = marker
                        self.save_schedules()
                        self.run_script()
            except Exception:
                continue

    def run(self):
        sys.exit(self.app.exec_())


class ArchiveWindow(QMainWindow):
    TYPE_LABELS = {
        "videos": "🎬 Видео",
        "shorts": "⚡ Shorts",
        "streams": "🔴 Трансляция",
        "queue": "📥 Очередь",
    }
    TYPE_EMOJIS = {
        "videos": "🎬",
        "shorts": "⚡",
        "streams": "●",
        "queue": "📥",
    }

    def __init__(self, launcher: TrayLauncher, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.setWindowTitle("Архив")
        self.resize(980, 560)
        self.setMinimumSize(760, 420)
        if self.launcher.app_icon_path.exists():
            self.setWindowIcon(QIcon(str(self.launcher.app_icon_path)))

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        title = QLabel("🗃 Архив скачиваний")
        title.setObjectName("sectionTitle")
        self.refresh_button = QPushButton("🔄 Обновить")
        self.refresh_button.setToolTip("Перечитать архив и проверить наличие файлов")
        self.refresh_button.clicked.connect(self.refresh)
        self.youtube_button = QPushButton("▶ YouTube")
        self.youtube_button.setToolTip("Открыть выбранное видео на YouTube")
        self.youtube_button.clicked.connect(self.open_selected_youtube)
        self.file_button = QPushButton("🎬 Файл")
        self.file_button.setToolTip("Открыть выбранное видео с диска")
        self.file_button.clicked.connect(self.open_selected_file)
        self.folder_button = QPushButton("📁 Папка")
        self.folder_button.setToolTip("Открыть папку выбранного видео")
        self.folder_button.clicked.connect(self.open_selected_folder)
        self.delete_button = QPushButton("🗑 Удалить")
        self.delete_button.setToolTip("Удалить выбранную запись из подробного и служебного архивов")
        self.delete_button.clicked.connect(self.delete_selected_entry)

        for button in (self.refresh_button, self.youtube_button, self.file_button, self.folder_button, self.delete_button):
            button.setObjectName("overviewButton")
            button.setFixedHeight(32)

        toolbar.addWidget(title)
        toolbar.addStretch()
        toolbar.addWidget(self.refresh_button)
        toolbar.addWidget(self.youtube_button)
        toolbar.addWidget(self.file_button)
        toolbar.addWidget(self.folder_button)
        toolbar.addWidget(self.delete_button)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "Тип", "Канал", "Название", "ID", "Дата"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.cellDoubleClicked.connect(self.open_cell_default)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.setCentralWidget(central)

    def refresh(self):
        entries = self.read_entries()
        self.table.setRowCount(0)
        self.table.setSortingEnabled(False)
        for entry in entries:
            self.add_entry_row(entry)
        self.table.setSortingEnabled(False)

    def read_entries(self):
        path = self.launcher.archive_details_file
        if not path.exists():
            return []

        entries = []
        for index, line in enumerate(read_text_for_display(path).splitlines()):
            text = line.strip()
            if not text:
                continue
            try:
                entry = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                entry = normalize_text_value(entry)
                entry["_index"] = index
                entries.append(entry)

        def sort_key(entry):
            value = entry.get("downloaded_at_ts")
            try:
                if value not in (None, ""):
                    return int(value)
            except (TypeError, ValueError):
                pass
            return int(entry.get("_index") or 0)

        entries.sort(key=sort_key, reverse=True)
        return entries

    def add_entry_row(self, entry: dict):
        row = self.table.rowCount()
        self.table.insertRow(row)

        file_path_text = str(entry.get("file_path") or "").strip()
        file_path = Path(file_path_text) if file_path_text else None
        exists = self.resolve_existing_path(file_path) is not None
        status_item = QTableWidgetItem("🟢" if exists else "❌")
        status_item.setToolTip("Файл есть на диске" if exists else "Файл не найден на диске")
        status_item.setTextAlignment(Qt.AlignCenter)
        status_item.setData(Qt.UserRole, entry)
        status_item.setForeground(QBrush(QColor("#2abf68" if exists else "#e54b4b")))
        self.table.setItem(row, 0, status_item)

        type_name = str(entry.get("type") or "").strip()
        type_emoji = self.TYPE_EMOJIS.get(type_name, type_name)
        video_id = str(entry.get("video_id") or "").strip()
        values = [
            type_emoji,
            fix_mojibake(str(entry.get("channel_name") or "")),
            fix_mojibake(str(entry.get("title") or "")),
            video_id,
            fix_mojibake(str(entry.get("downloaded_at") or "")),
        ]
        for col, value in enumerate(values, start=1):
            display_value = value.strip() or "-"
            item = QTableWidgetItem(display_value)
            if col == 1:
                item.setToolTip(self.TYPE_LABELS.get(type_name, type_name))
            else:
                item.setToolTip(value.strip())
            if col in (1, 4, 5):
                item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, col, item)

        self.table.setRowHeight(row, 28)

    def run_migration(self):
        script = self.launcher.migrate_script_path
        if not script.exists():
            QMessageBox.warning(self, "Архив", f"Не найден скрипт миграции:\n{script}")
            return

        scan_dirs = []
        for candidate in (self.launcher.final_dir, self.launcher.final_dir.parent):
            if candidate and candidate.exists() and candidate not in scan_dirs and candidate != Path("/"):
                scan_dirs.append(candidate)

        args = [
            "--archive",
            str(self.launcher.archive_file),
            "--details",
            str(self.launcher.archive_details_file),
            "--include-missing",
        ]
        for scan_dir in scan_dirs:
            args.extend(["--scan-dir", str(scan_dir)])

        try:
            result = self.launcher.run_python_script_capture(script, args, timeout=300)
        except Exception as exc:
            QMessageBox.warning(self, "Архив", f"Не удалось выполнить миграцию:\n{exc}")
            return

        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Скрипт миграции завершился с ошибкой").strip()
            QMessageBox.warning(self, "Архив", message)
            return

        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            payload = {}

        summary = payload.get("summary") or {}
        self.refresh()
        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh_overview"):
            parent.refresh_overview()

        QMessageBox.information(
            self,
            "Архив",
            (
                "Миграция завершена.\n\n"
                f"ID в старом архиве: {summary.get('archive_ids', 0)}\n"
                f"Проверено файлов: {summary.get('scanned_files', 0)}\n"
                f"Файлов по шаблону YTH: {summary.get('matched_files', 0)}\n"
                f"Добавлено с файлом: {summary.get('file_records_added', 0)}\n"
                f"Добавлено без файла: {summary.get('missing_records_added', 0)}\n"
                f"Всего добавлено: {summary.get('total_added', 0)}"
            ),
        )

    def delete_selected_entry(self):
        entry = self.selected_entry()
        if not entry:
            return

        video_id = str(entry.get("video_id") or "").strip()
        title = str(entry.get("title") or video_id or "выбранную запись").strip()
        answer = QMessageBox.question(
            self,
            "Архив",
            (
                f"Удалить из архивов запись «{title}»?\n\n"
                "Файл на диске удалён не будет. Запись исчезнет из подробного архива и из служебного yt_archive.txt."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        details_removed = self.remove_from_details_archive(entry)
        service_removed = self.remove_from_service_archive(video_id)
        self.refresh()
        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh_overview"):
            parent.refresh_overview()

        QMessageBox.information(
            self,
            "Архив",
            (
                "Запись удалена.\n\n"
                f"Подробный архив: удалено {details_removed}\n"
                f"Служебный архив: удалено {service_removed}"
            ),
        )

    def remove_from_details_archive(self, entry: dict) -> int:
        path = self.launcher.archive_details_file
        if not path.exists():
            return 0

        video_id = str(entry.get("video_id") or "").strip()
        selected_index = entry.get("_index")
        removed = 0
        kept_lines = []
        for index, raw_line in enumerate(read_text_for_display(path).splitlines()):
            should_remove = False
            try:
                current = json.loads(raw_line)
            except json.JSONDecodeError:
                current = None

            if isinstance(current, dict):
                current_id = str(current.get("video_id") or "").strip()
                if video_id and current_id == video_id:
                    should_remove = True
            if not should_remove and not video_id and selected_index == index:
                should_remove = True

            if should_remove:
                removed += 1
            else:
                kept_lines.append(raw_line)

        path.write_text("\n".join(kept_lines).rstrip() + ("\n" if kept_lines else ""), encoding="utf-8")
        return removed

    def remove_from_service_archive(self, video_id: str) -> int:
        video_id = str(video_id or "").strip()
        if not video_id or video_id == "unknown":
            return 0

        path = self.launcher.archive_file
        if not path.exists():
            return 0

        removed = 0
        kept_lines = []
        for raw_line in read_text_for_display(path).splitlines():
            if video_id in raw_line:
                removed += 1
            else:
                kept_lines.append(raw_line)

        path.write_text("\n".join(kept_lines).rstrip() + ("\n" if kept_lines else ""), encoding="utf-8")
        return removed

    def selected_entry(self, warn: bool = True):
        row = self.table.currentRow()
        if row < 0:
            if warn:
                QMessageBox.information(self, "Архив", "Выберите запись в таблице")
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        entry = item.data(Qt.UserRole)
        return entry if isinstance(entry, dict) else None

    def open_cell_default(self, row: int, column: int):
        self.table.setCurrentCell(row, column)
        if column == 1:
            self.open_selected_channel_section()
        elif column == 2:
            self.open_selected_channel()
        else:
            self.open_selected_file_or_youtube()

    def open_selected_file_or_youtube(self):
        entry = self.selected_entry()
        if not entry:
            return
        path_text = str(entry.get("file_path") or "").strip()
        existing_path = self.resolve_existing_path(Path(path_text)) if path_text else None
        if existing_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(existing_path)))
            return
        self.open_selected_youtube()

    def open_selected_youtube(self):
        entry = self.selected_entry()
        if not entry:
            return
        url = str(entry.get("youtube_url") or "").strip()
        if not url:
            video_id = str(entry.get("video_id") or "").strip()
            if video_id and video_id != "unknown":
                url = f"https://www.youtube.com/watch?v={video_id}"
        if not url:
            QMessageBox.information(self, "Архив", "В этой записи нет ссылки на YouTube")
            return
        QDesktopServices.openUrl(QUrl(url))

    def open_selected_channel(self):
        entry = self.selected_entry()
        if not entry:
            return
        url = self.channel_url_from_entry(entry)
        if not url:
            QMessageBox.information(self, "Архив", "В этой записи нет ссылки на канал")
            return
        QDesktopServices.openUrl(QUrl(url))

    def open_selected_channel_section(self):
        entry = self.selected_entry()
        if not entry:
            return
        url = self.channel_url_from_entry(entry)
        if not url:
            QMessageBox.information(self, "Архив", "В этой записи нет ссылки на канал")
            return
        type_name = str(entry.get("type") or "").strip()
        if type_name in {"videos", "shorts", "streams"}:
            url = url.rstrip("/") + f"/{type_name}"
        QDesktopServices.openUrl(QUrl(url))

    def channel_url_from_entry(self, entry: dict):
        url = str(entry.get("channel_url") or "").strip()
        if url:
            return url
        channel_name = str(entry.get("channel_name") or "").strip()
        if not channel_name or not self.launcher.channels_file.exists():
            return ""
        try:
            channels = [
                line.strip()
                for line in self.launcher.channels_file.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        except Exception:
            return ""

        for channel in channels:
            cache_path = self.channel_cache_path(channel).with_suffix(".json")
            title = ""
            try:
                if cache_path.exists():
                    meta = json.loads(cache_path.read_text(encoding="utf-8"))
                    title = str(meta.get("title") or "").strip()
            except Exception:
                title = ""
            fallback = self.channel_title_from_url(channel)
            if channel_name.casefold() in {title.casefold(), fallback.casefold()}:
                return channel
        return ""

    def channel_title_from_url(self, channel: str):
        text = str(channel or "").rstrip("/").split("/")[-1]
        return text[1:] if text.startswith("@") else text

    def channel_cache_path(self, channel: str):
        safe = "".join(ch if ch.isalnum() else "_" for ch in str(channel))[-80:]
        return self.launcher.cache_dir / "channels" / safe

    def open_selected_file(self):
        entry = self.selected_entry()
        if not entry:
            return
        path_text = str(entry.get("file_path") or "").strip()
        if not path_text:
            QMessageBox.information(self, "Архив", "В этой записи нет пути к файлу")
            return
        path = self.resolve_existing_path(Path(path_text))
        if path is None:
            QMessageBox.information(self, "Архив", "Файл не найден на диске")
            self.refresh()
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_selected_folder(self):
        entry = self.selected_entry()
        if not entry:
            return
        path_text = str(entry.get("file_path") or "").strip()
        original_path = Path(path_text) if path_text else None
        path = self.resolve_existing_path(original_path) or original_path
        folder = path.parent if path is not None else self.launcher.final_dir
        if not self.path_exists(folder):
            folder = self.launcher.final_dir
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def path_exists(self, path: Path | None):
        return self.resolve_existing_path(path) is not None

    def resolve_existing_path(self, path: Path | None):
        if path is None:
            return None
        candidates = [path]
        name = path.name
        if name and not name.startswith("+"):
            candidates.append(path.with_name("+" + name))
        elif name.startswith("+") and len(name) > 1:
            candidates.append(path.with_name(name[1:]))
        for candidate in candidates:
            try:
                if candidate.exists():
                    return candidate
            except OSError:
                continue
        return None


class QuickDownloadDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.launcher = main_window.launcher
        self.setWindowTitle("Быстрое скачивание")
        self.setModal(False)
        self.setFixedSize(900, 235)
        self._position_ready = False
        if self.launcher.app_icon_path.exists():
            self.setWindowIcon(QIcon(str(self.launcher.app_icon_path)))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 10, 10)
        layout.setSpacing(10)

        self.logo_label = QLabel()
        self.logo_label.setObjectName("quickLogo")
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setFixedSize(205, 205)
        self._load_logo()
        layout.addWidget(self.logo_label, 0, Qt.AlignTop)

        right_panel = QWidget()
        right_panel.setObjectName("toolPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 8, 10, 8)
        right_layout.setSpacing(8)
        layout.addWidget(right_panel, 1)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("YouTube URL")
        self.url_input.textChanged.connect(self.on_url_changed)
        self.download_button = QPushButton()
        self.download_button.setObjectName("primaryRunButton")
        self.download_button.setFixedSize(46, 46)
        self.download_button.setIconSize(QSize(44, 44))
        self.download_button.setIcon(self.main_window._run_button_icon(False))
        self.download_button.setToolTip("Скачать немедленно")
        self.download_button.clicked.connect(self.download_now)
        self.add_queue_button = QPushButton("Добавить в очередь")
        self.add_queue_button.setFixedHeight(32)
        self.add_queue_button.setToolTip("Добавить ссылку в очередь")
        self.add_queue_button.clicked.connect(self.add_to_queue)
        top_row.addWidget(self.url_input, 1)
        top_row.addWidget(self.download_button)
        top_row.addWidget(self.add_queue_button)
        right_layout.addLayout(top_row)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(10)
        self.thumbnail_label = QLabel("Обложка")
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setFixedSize(250, 132)
        self.thumbnail_label.setObjectName("quickThumbnail")
        preview_row.addWidget(self.thumbnail_label, 0, Qt.AlignTop)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)
        self.video_title_label = QLabel("Ожидаю ссылку YouTube")
        self.video_title_label.setObjectName("quickTitle")
        self.video_title_label.setWordWrap(True)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        self.video_title_label.setFont(title_font)
        self.video_uploader_label = QLabel("")
        self.video_uploader_label.setObjectName("subtleText")
        self.video_status_label = QLabel("")
        self.video_status_label.setObjectName("subtleText")
        self.video_status_label.setWordWrap(True)
        info_layout.addWidget(self.video_title_label)
        info_layout.addWidget(self.video_uploader_label)
        info_layout.addWidget(self.video_status_label)
        info_layout.addStretch()

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        self.telegram_check = QCheckBox("Отправлять в Telegram уведомление")
        self.telegram_check.setChecked(self.launcher.quick_download_telegram_notify)
        self.telegram_check.toggled.connect(self.save_telegram_setting)
        bottom_row.addWidget(self.telegram_check)
        info_layout.addLayout(bottom_row)
        preview_row.addLayout(info_layout, 1)
        right_layout.addLayout(preview_row, 1)

        self.update_actions(False)

    def restore_position(self):
        position = self.main_window.ui_settings.get("quick_download_window_position")
        if not isinstance(position, dict):
            return
        try:
            x = int(position.get("x"))
            y = int(position.get("y"))
        except (TypeError, ValueError):
            return
        screen = QApplication.screenAt(QPoint(x + self.width() // 2, y + self.height() // 2))
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            x = max(available.left(), min(x, available.right() - self.width() + 1))
            y = max(available.top(), min(y, available.bottom() - self.height() + 1))
        self.move(x, y)

    def save_position(self):
        if not self._position_ready or self.isMinimized():
            return
        position = {"x": int(self.x()), "y": int(self.y())}
        if self.main_window.ui_settings.get("quick_download_window_position") == position:
            return
        self.main_window.ui_settings["quick_download_window_position"] = position
        self.main_window.save_ui_settings()

    def moveEvent(self, event):
        super().moveEvent(event)
        self.save_position()

    def closeEvent(self, event):
        self.save_position()
        super().closeEvent(event)

    def accept(self):
        self.save_position()
        super().accept()

    def reject(self):
        self.save_position()
        super().reject()

    def _load_logo(self):
        for path in (self.launcher.overview_logo_path, self.launcher.app_icon_path):
            if path.exists():
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    self.logo_label.setPixmap(pixmap.scaled(
                        self.logo_label.size(),
                        Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation,
                    ))
                    return
        self.logo_label.setText(APP_NAME)

    def set_channel_logo(self, path_text: str):
        path = Path(path_text) if path_text else None
        if path and path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.logo_label.setPixmap(pixmap.scaled(
                    self.logo_label.size(),
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                ))
                return
        self._load_logo()

    def open_from_clipboard(self):
        clipboard_text = QApplication.clipboard().text().strip()
        self.main_window.current_previews["quick"] = {}
        self.thumbnail_label.setPixmap(QPixmap())
        self.thumbnail_label.setText("Обложка")
        self._load_logo()
        self.video_uploader_label.setText("")
        self.video_status_label.setText("")
        if self.main_window._looks_like_youtube_url(clipboard_text):
            self.url_input.setText(clipboard_text)
            self.url_input.selectAll()
            self.main_window.schedule_video_preview("quick")
        else:
            self.url_input.clear()
            self.video_title_label.setText("Ошибка")
            self.video_status_label.setText("В буфере обмена нет корректной ссылки YouTube")
            self.update_actions(False)
        self.telegram_check.setChecked(self.launcher.quick_download_telegram_notify)
        self.restore_position()
        self.show()
        self._position_ready = True
        self.raise_()
        self.activateWindow()

    def on_url_changed(self):
        valid = self.main_window._looks_like_youtube_url(self.url_input.text().strip())
        self.update_actions(valid)
        self.main_window.schedule_video_preview("quick")

    def update_actions(self, valid: bool):
        self.download_button.setEnabled(valid)
        self.add_queue_button.setEnabled(valid)

    def save_telegram_setting(self, checked: bool):
        self.main_window.ui_settings["quick_download_telegram_notify"] = bool(checked)
        self.main_window.save_ui_settings()
        self.launcher.app_settings = dict(self.main_window.ui_settings)
        self.launcher.apply_runtime_settings(self.launcher.app_settings)

    def add_to_queue(self):
        if self.main_window.add_video_to_queue("quick"):
            self.accept()

    def download_now(self):
        if self.main_window.quick_download_now():
            self.accept()


class MainWindow(QMainWindow):
    metadata_loaded = pyqtSignal(dict)
    metadata_failed = pyqtSignal(int, str)
    quick_channel_logo_loaded = pyqtSignal(dict)
    channel_metadata_loaded = pyqtSignal(dict)
    channel_marked_archived = pyqtSignal(dict)
    channel_mark_archive_failed = pyqtSignal(str)
    channel_sections_checked = pyqtSignal(dict)

    def __init__(self, launcher: TrayLauncher):
        super().__init__()
        self.launcher = launcher
        self.setWindowTitle(APP_TITLE)
        self.setFixedSize(900, 620)
        if self.launcher.app_icon_path.exists():
            self.setWindowIcon(QIcon(str(self.launcher.app_icon_path)))
        self.preview_request_id = 0
        self.preview_request_context = "queue"
        self.pending_preview_context = "queue"
        self.current_preview = {}
        self.current_previews = {"overview": {}, "queue": {}, "quick": {}}
        self.ui_settings = self.load_ui_settings()
        self._window_position_ready = False
        self.theme = self.ui_settings.get("theme", "dark")
        if self.theme not in {"dark", "light", "system"}:
            self.theme = "dark"
        self.channel_cards = {}
        self.channel_cache_dir = self.launcher.cache_dir / "channels"
        self.channel_rules = {}
        self.channel_section_results = {}
        self.channel_section_checks_running = set()
        self.archive_window = None
        self.quick_download_dialog = None

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.theme_corner = QWidget()
        self.theme_corner.setObjectName("themeCorner")
        self.theme_corner.setFixedSize(32, 32)
        theme_corner_layout = QVBoxLayout(self.theme_corner)
        theme_corner_layout.setContentsMargins(0, 1, 0, 0)
        theme_corner_layout.setSpacing(0)
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("themeButton")
        self.theme_button.setFixedSize(32, 32)
        self.theme_button.setToolTip("Ночной / дневной режим")
        self.theme_button.clicked.connect(self.toggle_theme)
        theme_corner_layout.addWidget(self.theme_button)
        self.tabs.setCornerWidget(self.theme_corner, Qt.TopRightCorner)

        self._build_overview_tab()
        self._build_channels_tab()
        self._build_queue_tab()
        self._build_logs_tab()

        self.metadata_loaded.connect(self.on_metadata_loaded)
        self.metadata_failed.connect(self.on_metadata_failed)
        self.quick_channel_logo_loaded.connect(self.on_quick_channel_logo_loaded)
        self.channel_metadata_loaded.connect(self.on_channel_metadata_loaded)
        self.channel_marked_archived.connect(self.on_channel_marked_archived)
        self.channel_mark_archive_failed.connect(self.on_channel_mark_archive_failed)
        self.channel_sections_checked.connect(self.on_channel_sections_checked)

        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.refresh_log_view)
        self.log_timer.start(5000)
        self.system_theme_timer = QTimer(self)
        self.system_theme_timer.timeout.connect(self.refresh_system_theme)
        self.system_theme_timer.start(30000)
        self.window_position_timer = QTimer(self)
        self.window_position_timer.setSingleShot(True)
        self.window_position_timer.timeout.connect(self.save_window_position)
        self.apply_theme()
        self.restore_window_position()
        self._window_position_ready = True

    def _build_overview_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(10)

        header_panel = QWidget()
        header_panel.setObjectName("overviewHeaderPanel")
        header_layout = QVBoxLayout(header_panel)
        header_layout.setContentsMargins(10, 5, 10, 10)
        header_layout.setSpacing(0)

        top_row = QHBoxLayout()
        top_row.setSpacing(5)
        self.overview_channels_label = QLabel()
        self.overview_queue_label = QLabel()
        self.overview_archive_label = QLabel()
        self.overview_last_download_label = QLabel()
        self.overview_temp_label = QLabel()
        for label in (
            self.overview_channels_label,
            self.overview_queue_label,
            self.overview_archive_label,
            self.overview_last_download_label,
            self.overview_temp_label,
        ):
            label.setObjectName("overviewMetricPill")
            label.setTextFormat(Qt.RichText)
            label.setWordWrap(False)
            label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(5)
        for label in (
            self.overview_channels_label,
            self.overview_queue_label,
            self.overview_archive_label,
            self.overview_last_download_label,
            self.overview_temp_label,
        ):
            metrics_row.addWidget(label)

        self.run_button = QPushButton()
        self.run_button.setObjectName("primaryRunButton")
        self.run_button.setFixedSize(54, 54)
        self.run_button.setIconSize(QSize(50, 50))
        self.run_button.setToolTip("Запустить проверку очереди и каналов")
        self.run_button.clicked.connect(self.toggle_download)
        final_btn = QPushButton("📁")
        final_btn.setObjectName("overviewButton")
        final_btn.setFixedSize(38, 32)
        final_btn.setToolTip("Открыть папку загрузок")
        final_btn.clicked.connect(lambda: self.open_folder(self.launcher.final_dir))
        temp_btn = QPushButton("⌛")
        temp_btn.setObjectName("overviewButton")
        temp_btn.setFixedSize(38, 32)
        temp_btn.setToolTip("Открыть временную папку")
        temp_btn.clicked.connect(lambda: self.open_folder(self.launcher.temp_dir))
        archive_btn = QPushButton("🗃 Архив")
        archive_btn.setObjectName("overviewButton")
        archive_btn.setFixedSize(102, 32)
        archive_btn.setToolTip("Открыть подробный архив скачиваний")
        archive_btn.clicked.connect(self.open_archive_window)
        top_row.addWidget(self.run_button, 0, Qt.AlignLeft | Qt.AlignTop)
        for button in (final_btn, temp_btn, archive_btn):
            top_row.addWidget(button, 0, Qt.AlignLeft | Qt.AlignVCenter)
        top_row.addStretch(1)
        top_row.addLayout(metrics_row)
        header_layout.addLayout(top_row)

        overview_queue_row = QHBoxLayout()
        overview_queue_row.setSpacing(8)
        self.overview_video_url_input = QLineEdit()
        self.overview_video_url_input.setPlaceholderText("YouTube URL")
        self.overview_video_url_input.textChanged.connect(lambda: self.schedule_video_preview("overview"))
        self.overview_add_video_button = QPushButton("Добавить в очередь")
        self.overview_add_video_button.setFixedHeight(30)
        self.overview_add_video_button.setToolTip("Добавить указанное YouTube-видео в очередь скачивания")
        self.overview_add_video_button.setEnabled(False)
        self.overview_add_video_button.clicked.connect(lambda: self.add_video_to_queue("overview"))
        overview_queue_row.addWidget(self.overview_video_url_input, 1)
        overview_queue_row.addWidget(self.overview_add_video_button, 0)
        header_layout.addLayout(overview_queue_row)

        layout.addWidget(header_panel)

        content = QHBoxLayout()
        content.setSpacing(10)

        media_panel = QWidget()
        media_panel.setObjectName("overviewMediaPanel")
        media_layout = QVBoxLayout(media_panel)
        media_layout.setContentsMargins(10, 12, 10, 8)
        media_layout.setSpacing(0)
        self.overview_main_image = QLabel()
        self.overview_main_image.setObjectName("overviewMainImage")
        self.overview_main_image.setAlignment(Qt.AlignCenter)
        self.overview_main_image.setFixedSize(232, 232)

        media_layout.addWidget(self.overview_main_image, 0, Qt.AlignHCenter | Qt.AlignVCenter)
        media_layout.addStretch()
        content.addWidget(media_panel, 0)

        activity_panel = QWidget()
        activity_panel.setObjectName("overviewActivityPanel")
        activity_layout = QVBoxLayout(activity_panel)
        activity_layout.setContentsMargins(12, 10, 12, 14)
        activity_layout.setSpacing(8)
        self.overview_activity_bar = QProgressBar()
        self.overview_activity_bar.setObjectName("overviewActivityBar")
        self.overview_activity_bar.setRange(0, 100)
        self.overview_activity_bar.setValue(0)
        self.overview_activity_bar.setTextVisible(True)
        self.overview_activity_bar.setAlignment(Qt.AlignCenter)
        self.overview_activity_bar.setFixedHeight(34)
        activity_layout.addWidget(self.overview_activity_bar)

        status_grid = QGridLayout()
        status_grid.setContentsMargins(0, 0, 0, 0)
        status_grid.setHorizontalSpacing(8)
        status_grid.setVerticalSpacing(4)
        self.overview_channel_label = self._overview_type_status_row(status_grid, 0, "📺", "Канал")
        self.overview_video_status_label = self._overview_type_status_row(status_grid, 1, "🎬", "Видео")
        self.overview_shorts_status_label = self._overview_type_status_row(status_grid, 2, "⚡", "Shorts")
        self.overview_streams_status_label = self._overview_type_status_row(status_grid, 3, "🔴", "Трансляция")
        activity_layout.addLayout(status_grid)

        self.overview_events_label = QLabel()
        self.overview_events_label.setObjectName("overviewEvents")
        self.overview_events_label.setTextFormat(Qt.RichText)
        self.overview_events_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.overview_events_label.setWordWrap(True)
        self.overview_events_label.setMinimumHeight(85)
        activity_layout.addWidget(self.overview_events_label, 1)

        download_panel = QWidget()
        download_panel.setObjectName("overviewDownloadPanel")
        download_layout = QHBoxLayout(download_panel)
        download_layout.setContentsMargins(12, 10, 12, 10)
        download_layout.setSpacing(12)

        self.overview_video_image = QLabel()
        self.overview_video_image.setObjectName("overviewVideoImage")
        self.overview_video_image.setAlignment(Qt.AlignCenter)
        self.overview_video_image.setFixedSize(270, 152)
        self.overview_video_image.setToolTip("Заставка текущего видео или заглушка")
        download_layout.addWidget(self.overview_video_image, 0, Qt.AlignLeft | Qt.AlignVCenter)

        download_details = QVBoxLayout()
        download_details.setContentsMargins(0, 0, 0, 0)
        download_details.setSpacing(8)
        self.overview_download_title_label = QLabel()
        self.overview_download_title_label.setObjectName("overviewDownloadTitle")
        self.overview_download_title_label.setTextFormat(Qt.RichText)
        self.overview_download_title_label.setWordWrap(True)
        self.overview_download_title_label.setFixedHeight(42)
        self.overview_download_title_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        download_details.addWidget(self.overview_download_title_label)
        self.overview_idle_uploader_label = QLabel("")
        self.overview_idle_uploader_label.setObjectName("subtleText")
        self.overview_idle_uploader_label.setTextFormat(Qt.RichText)
        self.overview_idle_status_label = QLabel("")
        self.overview_idle_status_label.setObjectName("subtleText")
        self.overview_idle_status_label.setTextFormat(Qt.RichText)
        download_details.addWidget(self.overview_idle_uploader_label)
        download_details.addWidget(self.overview_idle_status_label)

        self.overview_progress_panel = QWidget()
        self.overview_progress_panel.setObjectName("overviewProgressPanel")
        progress_layout = QVBoxLayout(self.overview_progress_panel)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(5)
        self.overview_progress_header_label = QLabel()
        self.overview_progress_header_label.setObjectName("subtleText")
        self.overview_progress_bar = QProgressBar()
        self.overview_progress_bar.setObjectName("overviewProgressBar")
        self.overview_progress_bar.setRange(0, 100)
        self.overview_progress_bar.setTextVisible(False)
        self.overview_progress_bar.setFixedHeight(14)
        self.overview_progress_detail_label = QLabel()
        self.overview_progress_detail_label.setObjectName("overviewProgressDetail")
        self.overview_progress_detail_label.setTextFormat(Qt.RichText)
        progress_layout.addWidget(self.overview_progress_header_label)
        progress_layout.addWidget(self.overview_progress_bar)
        progress_layout.addWidget(self.overview_progress_detail_label)
        download_details.addWidget(self.overview_progress_panel)
        download_layout.addLayout(download_details, 1)

        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 3, 0, 0)
        right_column.setSpacing(10)
        right_column.addWidget(activity_panel, 1)
        content.addLayout(right_column, 1)
        layout.addLayout(content, 1)
        layout.addWidget(download_panel, 0)

        self.tabs.addTab(tab, "📊 Обзор")

    def _overview_type_status_row(self, grid: QGridLayout, row: int, emoji: str, title: str):
        name = QLabel(f"{emoji} {title}")
        name.setObjectName("overviewTypeName")
        name.setFixedWidth(112)
        name.setFixedHeight(25)
        name.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        status = QLabel()
        status.setObjectName("overviewTypeStatus")
        status.setTextFormat(Qt.RichText)
        status.setFixedHeight(25)
        status.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        grid.addWidget(name, row, 0)
        grid.addWidget(status, row, 1)
        grid.setRowMinimumHeight(row, 25)
        return status

    def _build_channels_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 10, 16, 16)
        layout.setSpacing(8)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.check_channel_sections_button = QPushButton("🔎 Проверить разделы")
        self.check_channel_sections_button.setObjectName("overviewButton")
        self.check_channel_sections_button.setFixedHeight(32)
        self.check_channel_sections_button.setToolTip("Проверить, есть ли у каналов Видео, Shorts и Трансляция")
        self.check_channel_sections_button.clicked.connect(self.check_all_channel_sections)
        self.channel_sections_status_label = QLabel("")
        self.channel_sections_status_label.setObjectName("subtleText")
        tools.addWidget(self.check_channel_sections_button)
        tools.addWidget(self.channel_sections_status_label)
        tools.addStretch()
        layout.addLayout(tools)

        self.channels_scroll = QScrollArea()
        self.channels_scroll.setWidgetResizable(True)
        self.channels_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.channels_scroll.setFrameShape(QScrollArea.NoFrame)
        self.channels_content = QWidget()
        self.channels_grid = QGridLayout(self.channels_content)
        self.channels_grid.setContentsMargins(0, 0, 0, 0)
        self.channels_grid.setHorizontalSpacing(12)
        self.channels_grid.setVerticalSpacing(6)
        self.channels_scroll.setWidget(self.channels_content)
        layout.addWidget(self.channels_scroll)

        self.tabs.addTab(tab, "📺 Каналы")

    def _build_queue_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)

        schedule_panel = QWidget()
        schedule_panel.setObjectName("toolPanel")
        schedule_panel.setFixedWidth(318)
        schedule_layout = QVBoxLayout(schedule_panel)
        schedule_layout.setContentsMargins(10, 8, 10, 10)
        schedule_layout.setSpacing(8)

        self.queue_art_label = QLabel()
        self.queue_art_label.setObjectName("queueArt")
        self.queue_art_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.queue_art_label.setFixedSize(292, 255)
        if self.launcher.queue_art_path.exists():
            pixmap = QPixmap(str(self.launcher.queue_art_path))
            if not pixmap.isNull():
                self.queue_art_label.setPixmap(
                    pixmap.scaled(self.queue_art_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
        schedule_layout.addWidget(self.queue_art_label, 0, Qt.AlignLeft | Qt.AlignTop)

        schedule_header = QHBoxLayout()
        schedule_title = QLabel("Планировщик")
        schedule_title.setObjectName("sectionTitle")
        self.schedule_summary_label = QLabel("")
        self.schedule_summary_label.setObjectName("subtleText")
        schedule_header.addWidget(schedule_title)
        schedule_header.addStretch()
        schedule_header.addWidget(self.schedule_summary_label)
        schedule_layout.addLayout(schedule_header)

        top = QGridLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        self.schedule_hour_spin = QSpinBox()
        self.schedule_hour_spin.setRange(0, 23)
        self.schedule_hour_spin.setSuffix(":00")
        self.schedule_hour_spin.setValue(QTime.currentTime().hour())
        self.schedule_enabled_check = QCheckBox("Включено")
        self.schedule_enabled_check.setToolTip("Новая запись расписания будет активной")
        self.schedule_enabled_check.setChecked(True)
        add_btn = QPushButton("Добавить")
        add_btn.setFixedHeight(30)
        add_btn.setToolTip("Добавить запуск в выбранный час")
        add_btn.clicked.connect(self.add_schedule)
        toggle_btn = QPushButton("Вкл / выкл")
        toggle_btn.setFixedHeight(30)
        toggle_btn.setToolTip("Включить или выключить выбранное расписание")
        toggle_btn.clicked.connect(self.toggle_selected_schedule)
        remove_btn = QPushButton("Удалить")
        remove_btn.setFixedHeight(30)
        remove_btn.setToolTip("Удалить выбранную запись расписания")
        remove_btn.clicked.connect(self.remove_selected_schedule)
        top.addWidget(QLabel("Запуск в"), 0, 0)
        top.addWidget(self.schedule_hour_spin, 0, 1)
        top.addWidget(self.schedule_enabled_check, 0, 2)
        top.addWidget(add_btn, 1, 0, 1, 3)
        top.addWidget(toggle_btn, 2, 0, 1, 2)
        top.addWidget(remove_btn, 2, 2)
        top.setColumnStretch(2, 1)
        schedule_layout.addLayout(top)

        self.schedule_list = QListWidget()
        self.schedule_list.setAlternatingRowColors(True)
        self.schedule_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.schedule_list.setFixedHeight(132)
        schedule_layout.addWidget(self.schedule_list)
        schedule_layout.addStretch()
        layout.addWidget(schedule_panel)

        queue_panel = QWidget()
        queue_panel.setObjectName("toolPanel")
        queue_layout = QVBoxLayout(queue_panel)
        queue_layout.setContentsMargins(10, 8, 10, 10)
        queue_layout.setSpacing(8)

        queue_header = QHBoxLayout()
        queue_title = QLabel("Очередь видео")
        queue_title.setObjectName("sectionTitle")
        self.queue_summary_label = QLabel("")
        self.queue_summary_label.setObjectName("subtleText")
        queue_header.addWidget(queue_title)
        queue_header.addStretch()
        queue_header.addWidget(self.queue_summary_label)
        queue_layout.addLayout(queue_header)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.video_url_input = QLineEdit()
        self.video_url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.video_url_input.textChanged.connect(lambda: self.schedule_video_preview("queue"))
        self.add_video_button = QPushButton("Добавить в очередь")
        self.add_video_button.setFixedHeight(30)
        self.add_video_button.setToolTip("Добавить указанное YouTube-видео в очередь скачивания")
        self.add_video_button.setEnabled(False)
        self.add_video_button.clicked.connect(lambda: self.add_video_to_queue("queue"))
        input_row.addWidget(self.video_url_input)
        input_row.addWidget(self.add_video_button)
        queue_layout.addLayout(input_row)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(12)
        self.thumbnail_label = QLabel("Обложка")
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setFixedSize(220, 124)
        self.thumbnail_label.setStyleSheet("border: 1px solid #555; background: #202020; color: #bbb;")
        preview_row.addWidget(self.thumbnail_label, 0, Qt.AlignTop)

        preview_info = QVBoxLayout()
        self.video_title_label = QLabel("Введите адрес YouTube-видео")
        self.video_title_label.setWordWrap(True)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        self.video_title_label.setFont(title_font)
        self.video_uploader_label = QLabel("")
        self.video_status_label = QLabel("")
        preview_info.addWidget(self.video_title_label)
        preview_info.addWidget(self.video_uploader_label)
        preview_info.addWidget(self.video_status_label)
        preview_info.addStretch()
        preview_row.addLayout(preview_info)
        queue_layout.addLayout(preview_row)

        queue_buttons = QHBoxLayout()
        queue_buttons.setSpacing(8)
        remove_btn = QPushButton("Удалить выбранное")
        remove_btn.setFixedHeight(30)
        remove_btn.setToolTip("Удалить выбранную ссылку из очереди")
        remove_btn.clicked.connect(self.remove_selected_queued_video)
        reload_btn = QPushButton("Перечитать очередь")
        reload_btn.setFixedHeight(30)
        reload_btn.setToolTip("Перечитать список очереди из файла")
        reload_btn.clicked.connect(self.refresh_queue)
        queue_buttons.addWidget(remove_btn)
        queue_buttons.addWidget(reload_btn)
        queue_buttons.addStretch()
        queue_layout.addLayout(queue_buttons)

        self.queue_list = QListWidget()
        self.queue_list.setAlternatingRowColors(True)
        self.queue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        queue_layout.addWidget(self.queue_list, 1)
        layout.addWidget(queue_panel, 1)

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.fetch_video_preview)

        self.tabs.addTab(tab, "📥 Очередь")

    def _build_logs_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(10)

        download_panel = QWidget()
        download_panel.setObjectName("toolPanel")
        download_layout = QVBoxLayout(download_panel)
        download_layout.setContentsMargins(10, 8, 10, 10)
        download_layout.setSpacing(8)

        download_title = QLabel("Загрузка")
        download_title.setObjectName("sectionTitle")
        download_layout.addWidget(download_title)

        self.download_dir_input = QLineEdit()
        self.download_dir_input.setToolTip("Куда складывать готовые скачанные видео")
        download_layout.addLayout(self._path_setting_row(
            "📁 Загрузки",
            self.download_dir_input,
            lambda: self.choose_directory(self.download_dir_input),
        ))

        self.temp_dir_input = QLineEdit()
        self.temp_dir_input.setToolTip("Где хранить временные файлы и недокачанные части")
        download_layout.addLayout(self._path_setting_row(
            "⌛ Врем.",
            self.temp_dir_input,
            lambda: self.choose_directory(self.temp_dir_input),
        ))

        self.videos_limit_spin = self._limit_spin()
        self.videos_limit_spin.setToolTip("Сколько последних обычных видео проверять на каждом канале")
        self.shorts_limit_spin = self._limit_spin()
        self.shorts_limit_spin.setToolTip("Сколько последних Shorts проверять на каждом канале")
        self.streams_limit_spin = self._limit_spin()
        self.streams_limit_spin.setToolTip("Сколько последних трансляций проверять на каждом канале")
        limits_row = QHBoxLayout()
        limits_row.setSpacing(6)
        limits_font = QFont(self.font())
        limits_font.setPointSize(max(8, limits_font.pointSize() - 2))
        limits_title = QLabel("🔢Лимиты:")
        limits_title.setFixedWidth(80)
        limits_title.setFont(limits_font)
        limits_title.setToolTip("Сколько последних элементов проверять на каждом канале")
        limits_row.addWidget(limits_title)
        for label_text, spin, label_width in (
            ("🎬Видео", self.videos_limit_spin, 56),
            ("⚡Shorts", self.shorts_limit_spin, 58),
            ("🔴Трансляции", self.streams_limit_spin, 92),
        ):
            spin.setButtonSymbols(QSpinBox.NoButtons)
            spin.setAlignment(Qt.AlignCenter)
            spin.setFixedWidth(40)
            spin.setFont(limits_font)
            label = QLabel(label_text)
            label.setFixedWidth(label_width)
            label.setFont(limits_font)
            label.setToolTip(spin.toolTip())
            limits_row.addWidget(label)
            limits_row.addWidget(spin)
        limits_row.addStretch()
        download_layout.addLayout(limits_row)

        resolution_row = QHBoxLayout()
        resolution_row.setSpacing(8)
        self.resolution_combo = QComboBox()
        self.resolution_combo.setToolTip("Максимальное качество для yt-dlp; по умолчанию 1080p")
        for label, value in (
            ("480p", "480"),
            ("720p", "720"),
            ("1080p", "1080"),
            ("1440p", "1440"),
            ("2160p", "2160"),
            ("Лучшее доступное", "best"),
        ):
            self.resolution_combo.addItem(label, value)
        resolution_row.addWidget(QLabel("📺 Разрешение"))
        resolution_row.addWidget(self.resolution_combo, 1)
        download_layout.addLayout(resolution_row)

        engine_row = QHBoxLayout()
        engine_row.setSpacing(8)
        self.download_engine_combo = QComboBox()
        self.download_engine_combo.setToolTip("Используется только Python-движок. Bash-движок отключён как устаревший.")
        self.download_engine_combo.addItem("Python", "python")
        self.download_engine_combo.setEnabled(False)
        engine_row.addWidget(QLabel("🧩 Движок"))
        engine_row.addWidget(self.download_engine_combo, 1)
        download_layout.addLayout(engine_row)

        options_row = QHBoxLayout()
        options_row.setSpacing(3)
        options_font = QFont(self.font())
        options_font.setPointSize(max(8, options_font.pointSize() - 2))
        self.cleanup_temp_check = QCheckBox("🧹 Врем.")
        self.cleanup_temp_check.setToolTip("Очищать временную папку после успешной обработки")
        self.retry_queue_check = QCheckBox("🔁 Очередь")
        self.retry_queue_check.setToolTip("Возвращать неудачные ссылки обратно в очередь для повтора")
        self.autostart_check = QCheckBox("🚀 Авто")
        self.autostart_check.setToolTip(f"Запускать {APP_NAME} при входе в систему")
        self.cleanup_temp_check.setFont(options_font)
        self.retry_queue_check.setFont(options_font)
        self.autostart_check.setFont(options_font)
        self.log_keep_spin = self._limit_spin(1, 50)
        self.log_keep_spin.setFixedWidth(38)
        self.log_keep_spin.setToolTip("Сколько архивных логов хранить")
        log_keep_label = QLabel("📝 Логов")
        log_keep_label.setFont(options_font)
        options_row.addWidget(self.cleanup_temp_check)
        options_row.addWidget(self.retry_queue_check)
        options_row.addWidget(self.autostart_check)
        options_row.addWidget(log_keep_label)
        options_row.addWidget(self.log_keep_spin)
        rules_btn = QPushButton("⚖")
        rules_btn.setFixedSize(30, 28)
        rules_btn.setToolTip("Открыть правила использования и сведения о внешних компонентах")
        rules_btn.clicked.connect(self.open_usage_rules)
        options_row.addWidget(rules_btn)
        self.quick_hotkey_button = QPushButton()
        self.quick_hotkey_button.setIcon(quick_hotkey_icon())
        self.quick_hotkey_button.setIconSize(QSize(20, 20))
        self.quick_hotkey_button.setFixedSize(30, 28)
        self.quick_hotkey_button.clicked.connect(self.open_quick_hotkey_dialog)
        options_row.addWidget(self.quick_hotkey_button)
        options_row.addStretch()
        download_layout.addLayout(options_row)

        telegram_panel = QWidget()
        telegram_panel.setObjectName("toolPanel")
        telegram_layout = QVBoxLayout(telegram_panel)
        telegram_layout.setContentsMargins(10, 8, 10, 10)
        telegram_layout.setSpacing(8)

        telegram_header = QHBoxLayout()
        telegram_title = QLabel("Telegram")
        telegram_title.setObjectName("sectionTitle")
        self.telegram_enabled_button = QPushButton()
        self.telegram_enabled_button.setObjectName("telegramToggleButton")
        self.telegram_enabled_button.setCheckable(True)
        self.telegram_enabled_button.setFixedHeight(30)
        self.telegram_enabled_button.clicked.connect(self.on_telegram_enabled_clicked)
        telegram_header.addWidget(telegram_title)
        telegram_header.addStretch()
        telegram_header.addWidget(self.telegram_enabled_button)
        telegram_layout.addLayout(telegram_header)

        self.bot_token_input, self.bot_token_eye = self._secret_input()
        telegram_layout.addLayout(self._secret_setting_row("BOT_TOKEN", self.bot_token_input, self.bot_token_eye))
        self.channel_id_input, self.channel_id_eye = self._secret_input()
        telegram_layout.addLayout(self._secret_setting_row("CHANNEL_ID", self.channel_id_input, self.channel_id_eye))
        self.proxy_url_input, self.proxy_url_eye = self._secret_input()
        telegram_layout.addLayout(self._secret_setting_row("PROXY_URL", self.proxy_url_input, self.proxy_url_eye))

        save_row = QHBoxLayout()
        save_row.setSpacing(8)
        save_btn = QPushButton("Сохранить настройки")
        save_btn.setFixedHeight(30)
        save_btn.setToolTip("Сохранить все настройки, включая Telegram и папки")
        save_btn.clicked.connect(lambda: self.save_settings_from_ui(show_message=True))
        open_env_btn = QPushButton("Открыть .env")
        open_env_btn.setFixedHeight(30)
        open_env_btn.setToolTip("Открыть файл Telegram-настроек")
        open_env_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.launcher.env_file))))
        save_row.addWidget(save_btn)
        save_row.addWidget(open_env_btn)
        save_row.addStretch()
        telegram_layout.addLayout(save_row)

        settings_row.addWidget(download_panel, 4)
        settings_row.addWidget(telegram_panel, 2)
        layout.addLayout(settings_row)

        logs_panel = QWidget()
        logs_panel.setObjectName("toolPanel")
        logs_layout = QVBoxLayout(logs_panel)
        logs_layout.setContentsMargins(10, 8, 10, 10)
        logs_layout.setSpacing(8)

        top = QHBoxLayout()
        logs_title = QLabel("Логи")
        logs_title.setObjectName("sectionTitle")
        self.log_combo = QComboBox()
        refresh_btn = QPushButton("Обновить список")
        refresh_btn.setFixedHeight(30)
        refresh_btn.setToolTip("Обновить список доступных логов")
        refresh_btn.clicked.connect(self.refresh_logs)
        reload_btn = QPushButton("Перечитать лог")
        reload_btn.setFixedHeight(30)
        reload_btn.setToolTip("Заново прочитать выбранный лог")
        reload_btn.clicked.connect(self.refresh_log_view)
        top.addWidget(logs_title)
        top.addWidget(self.log_combo)
        top.addWidget(refresh_btn)
        top.addWidget(reload_btn)
        logs_layout.addLayout(top)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        logs_layout.addWidget(self.log_view, 1)
        layout.addWidget(logs_panel, 1)

        self.refresh_settings_controls()
        self.download_engine_combo.currentIndexChanged.connect(self.on_download_engine_changed)

        self.tabs.addTab(tab, "⚙ Настройки")

    def _limit_spin(self, minimum: int = 1, maximum: int = 100):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setFixedWidth(46)
        return spin

    def _path_setting_row(self, label_text: str, line_edit: QLineEdit, callback):
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(label_text)
        label.setFixedWidth(96)
        button = QPushButton("...")
        button.setFixedSize(34, 30)
        button.setToolTip(f"Выбрать: {label_text}")
        button.clicked.connect(callback)
        row.addWidget(label)
        row.addWidget(line_edit, 1)
        row.addWidget(button)
        return row

    def _secret_input(self):
        line_edit = QLineEdit()
        line_edit.setEchoMode(QLineEdit.Password)
        button = QPushButton("👁")
        button.setCheckable(True)
        button.setFixedSize(34, 30)
        button.setToolTip("Показать или скрыть значение поля")
        button.clicked.connect(lambda checked=False, field=line_edit: self.toggle_secret_visibility(field, checked))
        return line_edit, button

    def _secret_setting_row(self, label_text: str, line_edit: QLineEdit, eye_button: QPushButton):
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(label_text)
        label.setFixedWidth(104)
        line_edit.setToolTip(f"{label_text}: значение скрыто, нажмите глаз для просмотра")
        row.addWidget(label)
        row.addWidget(line_edit, 1)
        row.addWidget(eye_button)
        return row

    def toggle_secret_visibility(self, field: QLineEdit, visible: bool):
        field.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)

    def update_telegram_enabled_button(self):
        enabled = self.telegram_enabled_button.isChecked()
        if enabled:
            self.telegram_enabled_button.setText("🔔 Уведомления включены")
            self.telegram_enabled_button.setToolTip("Telegram-уведомления включены. Нажмите, чтобы выключить.")
        else:
            self.telegram_enabled_button.setText("🔕 Уведомления выключены")
            self.telegram_enabled_button.setToolTip("Telegram-уведомления выключены. Нажмите, чтобы включить.")

    def on_telegram_enabled_clicked(self, checked: bool):
        self.update_telegram_enabled_button()
        self.save_settings_from_ui(show_message=False)

    def on_download_engine_changed(self):
        self.save_settings_from_ui(show_message=False)
        if self.download_engine_combo.currentData() != self.launcher.download_engine:
            self.refresh_settings_controls()

    def update_quick_hotkey_button(self):
        hotkey = self.launcher.quick_download_hotkey or DEFAULT_QUICK_DOWNLOAD_HOTKEY
        self.quick_hotkey_button.setToolTip(f"Горячая клавиша быстрого скачивания: {hotkey}")

    def install_current_system_hotkey(self, editor: QKeySequenceEdit):
        sequence = editor.keySequence().toString(QKeySequence.NativeText).strip() or DEFAULT_QUICK_DOWNLOAD_HOTKEY
        self.ui_settings["quick_download_hotkey"] = sequence
        self.save_settings_from_ui(show_message=False)
        self.launcher.quick_download_hotkey = sequence
        self.launcher.refresh_global_hotkey()
        self.update_quick_hotkey_button()
        ok, message = self.launcher.install_system_quick_hotkey(sequence)
        if ok:
            QMessageBox.information(self, "Горячая клавиша", message)
        else:
            QMessageBox.warning(self, "Горячая клавиша", message)

    def open_quick_hotkey_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Быстрое скачивание")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        label = QLabel("Горячая клавиша")
        label.setObjectName("sectionTitle")
        layout.addWidget(label)

        editor = QKeySequenceEdit(QKeySequence(self.launcher.quick_download_hotkey or DEFAULT_QUICK_DOWNLOAD_HOTKEY))
        editor.setToolTip("Комбинация для быстрого скачивания")
        layout.addWidget(editor)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        default_button = buttons.addButton("По умолчанию", QDialogButtonBox.ResetRole)
        system_button = buttons.addButton("В систему", QDialogButtonBox.ActionRole)
        default_button.clicked.connect(lambda checked=False: editor.setKeySequence(QKeySequence(DEFAULT_QUICK_DOWNLOAD_HOTKEY)))
        system_button.clicked.connect(lambda checked=False: self.install_current_system_hotkey(editor))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec_() == QDialog.Accepted:
            sequence = editor.keySequence().toString(QKeySequence.NativeText).strip() or DEFAULT_QUICK_DOWNLOAD_HOTKEY
            self.ui_settings["quick_download_hotkey"] = sequence
            self.save_settings_from_ui(show_message=False)
            self.launcher.quick_download_hotkey = sequence
            self.launcher.refresh_global_hotkey()
            self.update_quick_hotkey_button()
            if self.launcher.is_wayland_session():
                ok, message = self.launcher.install_system_quick_hotkey(sequence)
                icon = "⌨️" if ok else "⚠️"
                self.launcher.show_notification(icon, "Горячая клавиша", message)

    def open_usage_rules(self):
        required = not self.launcher.usage_rules_accepted()
        dialog = UsageRulesDialog(required=required, parent=self)
        if dialog.exec_() == QDialog.Accepted and required:
            self.ui_settings["usage_rules_accepted_version"] = USAGE_RULES_VERSION
            self.save_ui_settings()
            self.launcher.app_settings = dict(self.ui_settings)
            self.launcher.apply_runtime_settings(self.launcher.app_settings)

    def choose_directory(self, field: QLineEdit):
        current = field.text().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Выбрать папку", current)
        if selected:
            field.setText(selected)
            field.setCursorPosition(0)
            self.save_settings_from_ui(show_message=False)

    def refresh_settings_controls(self):
        env_values = self.read_env_values()
        self.download_dir_input.setText(str(self.launcher.final_dir))
        self.temp_dir_input.setText(str(self.launcher.temp_dir))
        self.download_dir_input.setCursorPosition(0)
        self.temp_dir_input.setCursorPosition(0)
        self.videos_limit_spin.setValue(self.launcher.videos_limit)
        self.shorts_limit_spin.setValue(self.launcher.shorts_limit)
        self.streams_limit_spin.setValue(self.launcher.streams_limit)
        self.log_keep_spin.setValue(self.launcher.log_keep_count)
        self.cleanup_temp_check.setChecked(self.launcher.cleanup_temp)
        self.retry_queue_check.setChecked(self.launcher.retry_failed_queue)
        self.telegram_enabled_button.setChecked(self.launcher.telegram_enabled)
        self.update_telegram_enabled_button()
        self.update_quick_hotkey_button()
        self.autostart_check.setChecked(self.is_autostart_enabled())

        resolution_index = self.resolution_combo.findData(self.launcher.max_resolution)
        self.resolution_combo.blockSignals(True)
        self.resolution_combo.setCurrentIndex(resolution_index if resolution_index >= 0 else 2)
        self.resolution_combo.blockSignals(False)
        engine_index = self.download_engine_combo.findData(self.launcher.download_engine)
        self.download_engine_combo.blockSignals(True)
        self.download_engine_combo.setCurrentIndex(engine_index if engine_index >= 0 else 0)
        self.download_engine_combo.blockSignals(False)

        self.bot_token_input.setText(env_values.get("BOT_TOKEN", ""))
        self.channel_id_input.setText(env_values.get("CHANNEL_ID", ""))
        self.proxy_url_input.setText(env_values.get("PROXY_URL", ""))

    def save_settings_from_ui(self, show_message: bool = True):
        self.ui_settings.update({
            "download_dir": self.download_dir_input.text().strip() or str(self.launcher.default_download_dir()),
            "temp_dir": self.temp_dir_input.text().strip() or str(self.launcher.default_temp_dir()),
            "videos_limit": int(self.videos_limit_spin.value()),
            "shorts_limit": int(self.shorts_limit_spin.value()),
            "streams_limit": int(self.streams_limit_spin.value()),
            "max_resolution": self.resolution_combo.currentData() or "1080",
            "download_engine": self.download_engine_combo.currentData() or self.launcher.default_download_engine(),
            "log_keep_count": int(self.log_keep_spin.value()),
            "cleanup_temp": self.cleanup_temp_check.isChecked(),
            "retry_failed_queue": self.retry_queue_check.isChecked(),
            "telegram_enabled": self.telegram_enabled_button.isChecked(),
            "quick_download_hotkey": self.ui_settings.get("quick_download_hotkey") or self.launcher.quick_download_hotkey or DEFAULT_QUICK_DOWNLOAD_HOTKEY,
            "quick_download_telegram_notify": self.ui_settings.get("quick_download_telegram_notify", self.launcher.quick_download_telegram_notify),
        })
        self.save_ui_settings()
        self.launcher.app_settings = dict(self.ui_settings)
        self.launcher.apply_runtime_settings(self.launcher.app_settings)
        self.launcher.refresh_global_hotkey()
        self.launcher.temp_dir.mkdir(parents=True, exist_ok=True)
        self.launcher.final_dir.mkdir(parents=True, exist_ok=True)
        self.write_env_values({
            "TELEGRAM_ENABLED": "1" if self.telegram_enabled_button.isChecked() else "0",
            "BOT_TOKEN": self.bot_token_input.text(),
            "CHANNEL_ID": self.channel_id_input.text(),
            "PROXY_URL": self.proxy_url_input.text(),
        })
        self.set_autostart_enabled(self.autostart_check.isChecked())
        self.refresh_overview()
        self.launcher.update_icon()
        if show_message:
            QMessageBox.information(self, "Настройки", "Настройки сохранены")

    def read_env_values(self):
        values = {}
        try:
            if not self.launcher.env_file.exists():
                return values
            for line in self.launcher.env_file.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if not text or text.startswith("#"):
                    continue
                if text.startswith("export "):
                    text = text[7:].strip()
                try:
                    parts = shlex.split(text, comments=False, posix=True)
                except ValueError:
                    parts = [text]
                if not parts or "=" not in parts[0]:
                    continue
                key, value = parts[0].split("=", 1)
                values[key.strip()] = value
        except Exception:
            return values
        return values

    def write_env_values(self, values: dict):
        keys = set(values)
        self.launcher.env_file.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        seen = set()
        if self.launcher.env_file.exists():
            lines = self.launcher.env_file.read_text(encoding="utf-8").splitlines()
        else:
            lines = [
                f"# Telegram settings for {APP_NAME}.",
                "# Values are edited from the application settings tab.",
            ]

        updated_lines = []
        for line in lines:
            stripped = line.strip()
            body = stripped[7:].strip() if stripped.startswith("export ") else stripped
            key = body.split("=", 1)[0].strip() if "=" in body else ""
            if key in keys:
                updated_lines.append(f"{key}={self.env_quote(values[key])}")
                seen.add(key)
            else:
                updated_lines.append(line)

        for key in ("TELEGRAM_ENABLED", "BOT_TOKEN", "CHANNEL_ID", "PROXY_URL"):
            if key in keys and key not in seen:
                updated_lines.append(f"{key}={self.env_quote(values[key])}")

        self.launcher.env_file.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")

    def env_quote(self, value):
        text = str(value or "")
        if not text:
            return "''"
        return "'" + text.replace("'", "'\"'\"'") + "'"

    def autostart_file(self):
        return Path.home() / ".config" / "autostart" / "yt-harvester.desktop"

    def is_autostart_enabled(self):
        if self.launcher.is_windows:
            return self.is_windows_autostart_enabled()
        return self.autostart_file().exists()

    def set_autostart_enabled(self, enabled: bool):
        try:
            if self.launcher.is_windows:
                self.set_windows_autostart_enabled(enabled)
                return

            path = self.autostart_file()
            if enabled:
                path.parent.mkdir(parents=True, exist_ok=True)
                exec_path = Path("/usr/bin/yt-harvester")
                exec_line = "yt-harvester" if exec_path.exists() else str(self.launcher.app_dir / "start_tray.sh")
                path.write_text(
                    "[Desktop Entry]\n"
                    "Type=Application\n"
                    f"Name={APP_NAME}\n"
                    f"Exec={exec_line}\n"
                    "Icon=yt-harvester\n"
                    "Terminal=false\n"
                    "X-GNOME-Autostart-enabled=true\n",
                    encoding="utf-8",
                )
            elif path.exists():
                path.unlink()
        except Exception as e:
            QMessageBox.warning(self, "Автозапуск", str(e))

    def windows_autostart_key_path(self):
        return r"Software\Microsoft\Windows\CurrentVersion\Run"

    def windows_autostart_value_name(self):
        return APP_NAME

    def windows_autostart_command(self):
        if getattr(sys, "frozen", False):
            command = [str(Path(sys.executable))]
        else:
            python_exe = Path(sys.executable)
            pythonw_exe = python_exe.with_name("pythonw.exe")
            if pythonw_exe.exists():
                python_exe = pythonw_exe
            command = [str(python_exe), str(Path(__file__).resolve())]
        return subprocess.list2cmdline(command)

    def is_windows_autostart_enabled(self):
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.windows_autostart_key_path(),
                0,
                winreg.KEY_READ,
            ) as key:
                value, _kind = winreg.QueryValueEx(key, self.windows_autostart_value_name())
                return bool(str(value).strip())
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def set_windows_autostart_enabled(self, enabled: bool):
        import winreg

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            self.windows_autostart_key_path(),
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key,
                    self.windows_autostart_value_name(),
                    0,
                    winreg.REG_SZ,
                    self.windows_autostart_command(),
                )
            else:
                try:
                    winreg.DeleteValue(key, self.windows_autostart_value_name())
                except FileNotFoundError:
                    pass

    def refresh_all(self):
        self.refresh_overview()
        self.refresh_channels()
        self.refresh_schedules()
        self.refresh_queue()
        self.refresh_logs()

    def moveEvent(self, event):
        super().moveEvent(event)
        if getattr(self, "_window_position_ready", False) and not self.isMinimized():
            self.window_position_timer.start(600)

    def closeEvent(self, event):
        if getattr(self, "_window_position_ready", False):
            if self.window_position_timer.isActive():
                self.window_position_timer.stop()
            self.save_window_position()
        super().closeEvent(event)

    def load_ui_settings(self):
        try:
            if self.launcher.settings_file.exists():
                return json.loads(self.launcher.settings_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def save_ui_settings(self):
        try:
            self.launcher.settings_file.parent.mkdir(parents=True, exist_ok=True)
            self.launcher.settings_file.write_text(
                json.dumps(self.ui_settings, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            QMessageBox.warning(self, "Настройки", str(e))

    def restore_window_position(self):
        position = self.ui_settings.get("window_position")
        if not isinstance(position, dict):
            return
        try:
            x = int(position.get("x"))
            y = int(position.get("y"))
        except (TypeError, ValueError):
            return

        screen = QApplication.screenAt(QPoint(x + self.width() // 2, y + self.height() // 2))
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            x = max(available.left(), min(x, available.right() - self.width() + 1))
            y = max(available.top(), min(y, available.bottom() - self.height() + 1))
        self.move(x, y)

    def save_window_position(self):
        if not getattr(self, "_window_position_ready", False) or self.isMinimized():
            return
        position = {"x": int(self.x()), "y": int(self.y())}
        if self.ui_settings.get("window_position") == position:
            return
        self.ui_settings["window_position"] = position
        self.save_ui_settings()

    def toggle_theme(self):
        if self.theme == "dark":
            self.theme = "light"
        elif self.theme == "light":
            self.theme = "system"
        else:
            self.theme = "dark"
        self.ui_settings["theme"] = self.theme
        self.save_ui_settings()
        self.apply_theme()

    def apply_theme(self):
        effective_theme = self.effective_theme()
        if self.theme == "system":
            self.theme_button.setText("◐")
            mode = "темный" if effective_theme == "dark" else "светлый"
            self.theme_button.setToolTip(f"Как в системе: {mode}")
        elif self.theme == "dark":
            self.theme_button.setText("☀")
            self.theme_button.setToolTip("Включить дневной режим")
        else:
            self.theme_button.setText("☾")
            self.theme_button.setToolTip("Включить режим как в системе")

        if effective_theme == "light":
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background: #f4f6f8;
                    color: #17202a;
                }
                QTabWidget::pane {
                    border: 1px solid #c7d0d9;
                    background: #ffffff;
                }
                QTabBar::tab {
                    background: #e7ecf1;
                    color: #17202a;
                    min-height: 30px;
                    padding: 0 12px;
                    border: 1px solid #c7d0d9;
                    border-bottom: none;
                }
                QTabBar::tab:selected {
                    background: #ffffff;
                }
                QPushButton {
                    background: #ffffff;
                    color: #17202a;
                    border: 1px solid #b9c3cc;
                    padding: 6px 10px;
                }
                QPushButton:hover {
                    background: #edf3f8;
                }
                QToolTip {
                    background: #ffffff;
                    color: #17202a;
                    border: 1px solid #b9c3cc;
                    border-radius: 4px;
                    padding: 6px 8px;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 12px;
                }
                QWidget#toolPanel {
                    background: #ffffff;
                    border: 1px solid #d7dfe7;
                    border-radius: 4px;
                }
                QWidget#toolPanel QLabel, QWidget#toolPanel QCheckBox {
                    background: transparent;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                }
                QLabel#sectionTitle {
                    background: transparent;
                    font-size: 14px;
                    font-weight: bold;
                }
                QLabel#subtleText {
                    background: transparent;
                    color: #5c6670;
                    font-size: 12px;
                }
                QWidget#themeCorner {
                    background: #eef2f6;
                    border: none;
                    margin: 0;
                    padding: 0;
                }
                QPushButton#themeButton {
                    background: #eef2f6;
                    color: #17202a;
                    border: 1px solid #c7d0d9;
                    border-right: none;
                    padding: 0;
                    margin: 0;
                    font-size: 22px;
                    font-weight: bold;
                    text-align: center;
                }
                QPushButton#themeButton:hover {
                    background: #dfe8f1;
                }
                QLabel#overviewMetric {
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-weight: bold;
                    font-size: 13px;
                }
                QLabel#overviewLine {
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 15px;
                    font-weight: bold;
                }
                QPushButton#overviewButton {
                    font-family: "Noto Color Emoji", "Noto Sans", "DejaVu Sans", sans-serif;
                    font-size: 15px;
                    font-weight: bold;
                    padding: 4px 10px;
                }
                QPushButton#primaryRunButton {
                    background: transparent;
                    border: none;
                    border-radius: 27px;
                    padding: 0;
                    margin-top: 0;
                }
                QPushButton#primaryRunButton:hover {
                    background: rgba(50, 190, 108, 58);
                }
                QPushButton#primaryRunButton[danger="true"]:hover {
                    background: rgba(235, 75, 75, 64);
                }
                QPushButton#telegramToggleButton {
                    font-family: "Noto Color Emoji", "Noto Sans", "DejaVu Sans", sans-serif;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 5px 10px;
                    min-width: 188px;
                    background: #fff1f1;
                    color: #8a1f1f;
                    border: 1px solid #e0a0a0;
                }
                QPushButton#telegramToggleButton:checked {
                    background: #e8f7ee;
                    color: #0f5d35;
                    border: 1px solid #7cc898;
                }
                QPushButton#telegramToggleButton:hover {
                    background: #ffe7e7;
                }
                QPushButton#telegramToggleButton:checked:hover {
                    background: #d9f1e3;
                }
                QWidget#overviewHeaderPanel, QWidget#overviewMediaPanel, QWidget#overviewActivityPanel, QWidget#overviewDownloadPanel {
                    background: #ffffff;
                    border: 1px solid #d7dfe7;
                    border-radius: 4px;
                }
                QLabel#overviewMetricPill {
                    background: #eef2f6;
                    color: #17202a;
                    border: 1px solid #d7dfe7;
                    border-radius: 4px;
                    padding: 4px 7px;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-weight: bold;
                    font-size: 12px;
                }
                QProgressBar#overviewActivityBar {
                    background: #f2f5f8;
                    color: #17202a;
                    border: 1px solid #d7dfe7;
                    border-radius: 4px;
                    text-align: center;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 15px;
                    font-weight: bold;
                }
                QProgressBar#overviewActivityBar::chunk {
                    background: #8fc2ed;
                    border-radius: 3px;
                }
                QLabel#overviewProgramTitle {
                    background: transparent;
                    color: #17202a;
                    font-family: "Noto Sans", "DejaVu Sans", sans-serif;
                    font-size: 17px;
                    font-weight: bold;
                }
                QLabel#overviewChannelLine, QLabel#overviewDownloadTitle {
                    background: transparent;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                }
                QLabel#overviewTypeName {
                    background: transparent;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                }
                QLabel#overviewTypeStatus {
                    background: #f2f5f8;
                    color: #17202a;
                    border: 1px solid #d7dfe7;
                    border-radius: 4px;
                    padding: 0 8px;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                }
                QWidget#overviewProgressPanel {
                    background: transparent;
                    border: none;
                }
                QProgressBar#overviewProgressBar {
                    background: #e4eaf0;
                    border: none;
                    border-radius: 4px;
                }
                QProgressBar#overviewProgressBar::chunk {
                    background: #2d7dd2;
                    border-radius: 4px;
                }
                QLabel#overviewProgressDetail, QLabel#overviewEvents {
                    background: transparent;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 13px;
                }
                QLabel#overviewEvents {
                    color: #33404d;
                    border: 1px solid #d7dfe7;
                    border-radius: 4px;
                    padding: 8px 8px 10px 8px;
                }
                QLabel#overviewMainImage, QLabel#overviewVideoImage {
                    background: #ffffff;
                    border: 1px solid #b9c3cc;
                }
                QWidget#overviewQueuePreview {
                    background: transparent;
                    border: none;
                }
                QLabel#overviewPreviewTitle {
                    background: transparent;
                    color: #17202a;
                    font-size: 13px;
                    font-weight: bold;
                }
                QLabel#queueArt {
                    background: transparent;
                    border: none;
                }
                QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QComboBox, QSpinBox, QTableWidget {
                    background: #ffffff;
                    alternate-background-color: #f2f5f8;
                    color: #17202a;
                    border: 1px solid #b9c3cc;
                    selection-background-color: #2d7dd2;
                    selection-color: #ffffff;
                }
                QHeaderView::section {
                    background: #e7ecf1;
                    color: #17202a;
                    border: 1px solid #c7d0d9;
                    padding: 5px 6px;
                    font-weight: bold;
                }
                QTableWidget::item {
                    padding: 4px 6px;
                }
                QLineEdit {
                    padding: 6px 8px;
                }
                QListWidget::item {
                    min-height: 28px;
                    padding: 4px 8px;
                }
                QListWidget::item:selected {
                    background: #2d7dd2;
                    color: #ffffff;
                }
                QListWidget::item:selected:!active {
                    background: #2d7dd2;
                    color: #ffffff;
                }
            """)
            self._apply_preview_thumbnail_style("border: 1px solid #b9c3cc; background: #ffffff; color: #5c6670;")
        else:
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background: #171a1f;
                    color: #e8edf2;
                }
                QTabWidget::pane {
                    border: 1px solid #303844;
                    background: #1f242b;
                }
                QTabBar::tab {
                    background: #232a32;
                    color: #d7dee6;
                    min-height: 30px;
                    padding: 0 12px;
                    border: 1px solid #303844;
                    border-bottom: none;
                }
                QTabBar::tab:selected {
                    background: #2d3540;
                    color: #ffffff;
                }
                QPushButton {
                    background: #2d3540;
                    color: #f0f4f8;
                    border: 1px solid #46515f;
                    padding: 6px 10px;
                }
                QPushButton:hover {
                    background: #384454;
                }
                QToolTip {
                    background: #232a32;
                    color: #f0f4f8;
                    border: 1px solid #46515f;
                    border-radius: 4px;
                    padding: 6px 8px;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 12px;
                }
                QWidget#toolPanel {
                    background: #1c222a;
                    border: 1px solid #303844;
                    border-radius: 4px;
                }
                QWidget#toolPanel QLabel, QWidget#toolPanel QCheckBox {
                    background: transparent;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                }
                QLabel#sectionTitle {
                    background: transparent;
                    font-size: 14px;
                    font-weight: bold;
                }
                QLabel#subtleText {
                    background: transparent;
                    color: #aeb8c2;
                    font-size: 12px;
                }
                QWidget#themeCorner {
                    background: #232a32;
                    border: none;
                    margin: 0;
                    padding: 0;
                }
                QPushButton#themeButton {
                    background: #232a32;
                    color: #f0f4f8;
                    border: 1px solid #303844;
                    border-right: none;
                    padding: 0;
                    margin: 0;
                    font-size: 22px;
                    font-weight: bold;
                    text-align: center;
                }
                QPushButton#themeButton:hover {
                    background: #2d3540;
                }
                QLabel#overviewMetric {
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-weight: bold;
                    font-size: 13px;
                }
                QLabel#overviewLine {
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 15px;
                    font-weight: bold;
                }
                QPushButton#overviewButton {
                    font-family: "Noto Color Emoji", "Noto Sans", "DejaVu Sans", sans-serif;
                    font-size: 15px;
                    font-weight: bold;
                    padding: 4px 10px;
                }
                QPushButton#primaryRunButton {
                    background: transparent;
                    border: none;
                    border-radius: 27px;
                    padding: 0;
                    margin-top: 0;
                }
                QPushButton#primaryRunButton:hover {
                    background: rgba(54, 210, 122, 58);
                }
                QPushButton#primaryRunButton[danger="true"]:hover {
                    background: rgba(238, 82, 82, 70);
                }
                QPushButton#telegramToggleButton {
                    font-family: "Noto Color Emoji", "Noto Sans", "DejaVu Sans", sans-serif;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 5px 10px;
                    min-width: 188px;
                    background: #3a2326;
                    color: #ffd6d6;
                    border: 1px solid #7a3b3b;
                }
                QPushButton#telegramToggleButton:checked {
                    background: #183829;
                    color: #d7f7e3;
                    border: 1px solid #397a55;
                }
                QPushButton#telegramToggleButton:hover {
                    background: #4a2a2e;
                }
                QPushButton#telegramToggleButton:checked:hover {
                    background: #204a35;
                }
                QWidget#overviewHeaderPanel, QWidget#overviewMediaPanel, QWidget#overviewActivityPanel, QWidget#overviewDownloadPanel {
                    background: #1c222a;
                    border: 1px solid #303844;
                    border-radius: 4px;
                }
                QLabel#overviewMetricPill {
                    background: #232a32;
                    color: #f0f4f8;
                    border: 1px solid #303844;
                    border-radius: 4px;
                    padding: 4px 7px;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-weight: bold;
                    font-size: 12px;
                }
                QProgressBar#overviewActivityBar {
                    background: #151a20;
                    color: #f0f4f8;
                    border: 1px solid #303844;
                    border-radius: 4px;
                    text-align: center;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 15px;
                    font-weight: bold;
                }
                QProgressBar#overviewActivityBar::chunk {
                    background: #2f6f9f;
                    border-radius: 3px;
                }
                QLabel#overviewProgramTitle {
                    background: transparent;
                    color: #f0f4f8;
                    font-family: "Noto Sans", "DejaVu Sans", sans-serif;
                    font-size: 17px;
                    font-weight: bold;
                }
                QLabel#overviewChannelLine, QLabel#overviewDownloadTitle {
                    background: transparent;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                }
                QLabel#overviewTypeName {
                    background: transparent;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                }
                QLabel#overviewTypeStatus {
                    background: #151a20;
                    color: #e8edf2;
                    border: 1px solid #303844;
                    border-radius: 4px;
                    padding: 0 8px;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                }
                QWidget#overviewProgressPanel {
                    background: transparent;
                    border: none;
                }
                QProgressBar#overviewProgressBar {
                    background: #2a313a;
                    border: none;
                    border-radius: 4px;
                }
                QProgressBar#overviewProgressBar::chunk {
                    background: #3b8edb;
                    border-radius: 4px;
                }
                QLabel#overviewProgressDetail, QLabel#overviewEvents {
                    background: transparent;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 13px;
                }
                QLabel#overviewEvents {
                    color: #c9d2dc;
                    border: 1px solid #303844;
                    border-radius: 4px;
                    padding: 8px 8px 10px 8px;
                }
                QLabel#overviewMainImage, QLabel#overviewVideoImage {
                    background: #101317;
                    border: 1px solid #3a4350;
                }
                QWidget#overviewQueuePreview {
                    background: transparent;
                    border: none;
                }
                QLabel#overviewPreviewTitle {
                    background: transparent;
                    color: #f0f4f8;
                    font-size: 13px;
                    font-weight: bold;
                }
                QLabel#queueArt {
                    background: transparent;
                    border: none;
                }
                QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QComboBox, QSpinBox, QTableWidget {
                    background: #101317;
                    alternate-background-color: #151a20;
                    color: #e8edf2;
                    border: 1px solid #3a4350;
                    selection-background-color: #2d7dd2;
                    selection-color: #ffffff;
                }
                QHeaderView::section {
                    background: #232a32;
                    color: #f0f4f8;
                    border: 1px solid #303844;
                    padding: 5px 6px;
                    font-weight: bold;
                }
                QTableWidget::item {
                    padding: 4px 6px;
                }
                QLineEdit {
                    padding: 6px 8px;
                }
                QListWidget::item {
                    min-height: 28px;
                    padding: 4px 8px;
                }
                QListWidget::item:selected {
                    background: #2d7dd2;
                    color: #ffffff;
                }
                QListWidget::item:selected:!active {
                    background: #2d7dd2;
                    color: #ffffff;
                }
            """)
            self._apply_preview_thumbnail_style("border: 1px solid #3a4350; background: #101317; color: #aeb8c2;")

        if self.archive_window is not None:
            self.archive_window.setStyleSheet(self.styleSheet())
        if self.quick_download_dialog is not None:
            self.quick_download_dialog.setStyleSheet(self.styleSheet())

    def _apply_preview_thumbnail_style(self, style: str):
        for label_name in ("thumbnail_label", "overview_thumbnail_label"):
            label = getattr(self, label_name, None)
            if label is not None:
                label.setStyleSheet(style)
        if self.quick_download_dialog is not None:
            self.quick_download_dialog.thumbnail_label.setStyleSheet(style)

    def effective_theme(self):
        if self.theme != "system":
            return self.theme
        detected = self.detect_system_theme()
        if detected:
            return detected
        window_color = QApplication.palette().color(QPalette.Window)
        return "dark" if window_color.lightness() < 128 else "light"

    def detect_system_theme(self):
        if self.launcher.is_windows:
            try:
                import winreg

                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                )
                value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
                winreg.CloseKey(key)
                return "light" if int(value) == 1 else "dark"
            except Exception:
                return None

        color_scheme = self.read_gsettings("org.gnome.desktop.interface", "color-scheme")
        if color_scheme:
            value = color_scheme.lower()
            if "prefer-dark" in value:
                return "dark"
            if "prefer-light" in value:
                return "light"

        prefer_dark = self.read_gsettings("org.gnome.desktop.interface", "gtk-application-prefer-dark-theme")
        if prefer_dark:
            value = prefer_dark.lower()
            if "true" in value:
                return "dark"
            if "false" in value:
                return "light"

        for schema in ("org.cinnamon.desktop.interface", "org.gnome.desktop.interface"):
            gtk_theme = self.read_gsettings(schema, "gtk-theme")
            if not gtk_theme:
                continue
            value = gtk_theme.strip("'\"").lower()
            if "dark" in value:
                return "dark"
            return "light"

        return None

    def read_gsettings(self, schema: str, key: str):
        try:
            result = subprocess.run(
                ["gsettings", "get", schema, key],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            return None
        return None

    def refresh_system_theme(self):
        if self.theme == "system":
            self.apply_theme()

    def toggle_download(self):
        if self.launcher.is_running:
            self.launcher.request_stop()
        else:
            self.launcher.run_script()
        self.refresh_overview()

    def open_archive_window(self):
        if self.archive_window is None:
            self.archive_window = ArchiveWindow(self.launcher, self)
        self.archive_window.setStyleSheet(self.styleSheet())
        self.archive_window.refresh()
        self.archive_window.show()
        self.archive_window.raise_()
        self.archive_window.activateWindow()

    def open_quick_download_window(self):
        if self.quick_download_dialog is None:
            self.quick_download_dialog = QuickDownloadDialog(self)
            self.quick_download_dialog.setStyleSheet(self.styleSheet())
        self.quick_download_dialog.open_from_clipboard()

    def quick_download_now(self):
        if self.launcher.is_running:
            QMessageBox.information(self, "Быстрое скачивание", "Скачивание уже идёт. Ссылка добавится в очередь обычной кнопкой.")
            return False
        widgets = self._preview_widgets("quick")
        preview = self.current_previews.get("quick", {})
        url = (preview.get("url") or widgets["input"].text()).strip()
        if not self._looks_like_youtube_url(url):
            QMessageBox.warning(self, "Быстрое скачивание", "Нужна ссылка на YouTube-видео")
            return False
        video_id = (preview.get("video_id") or self.youtube_video_id_from_url(url)).strip()
        if video_id and self.archive_contains_video(video_id):
            QMessageBox.information(self, "Быстрое скачивание", "Это видео уже есть в архиве")
            widgets["status"].setText("Видео уже есть в архиве")
            return False

        telegram_notify = False
        if self.quick_download_dialog is not None:
            telegram_notify = self.quick_download_dialog.telegram_check.isChecked()
        self.launcher.run_script(telegram_override=telegram_notify, single_queue_url=url)
        self.refresh_overview()
        return True

    def read_status(self):
        try:
            if self.launcher.status_file.exists():
                return json.loads(self.launcher.status_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _emoji_html(self, emoji: str):
        return (
            '<span style="font-family: \'Noto Color Emoji\'; '
            f'font-weight: normal;">{html.escape(emoji)}</span>'
        )

    def _html_text(self, text):
        return html.escape(fix_mojibake(str(text)), quote=False)

    def _run_button_icon(self, stopping: bool = False):
        pixmap = QPixmap(50, 50)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        circle_color = QColor("#df4b4b" if stopping else "#2f8de4")
        border_color = QColor("#8fd0ff" if not stopping else "#ffb1b1")
        painter.setPen(QPen(border_color, 2))
        painter.setBrush(QBrush(circle_color))
        painter.drawEllipse(4, 4, 42, 42)

        painter.setPen(QPen(QColor("#ffffff"), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if stopping:
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.drawRoundedRect(18, 18, 14, 14, 2, 2)
        else:
            painter.drawLine(25, 12, 25, 30)
            painter.drawLine(16, 22, 25, 31)
            painter.drawLine(34, 22, 25, 31)
            painter.setPen(QPen(QColor("#ffffff"), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(15, 38, 35, 38)
        painter.end()
        return QIcon(pixmap)

    def _set_run_button_state(self, stopping: bool, enabled: bool, tooltip: str):
        self.run_button.setText("")
        self.run_button.setIcon(self._run_button_icon(stopping))
        self.run_button.setToolTip(tooltip)
        self.run_button.setEnabled(enabled)
        self.run_button.setProperty("danger", "true" if stopping else "false")
        self.run_button.style().unpolish(self.run_button)
        self.run_button.style().polish(self.run_button)

    def refresh_overview(self):
        status_info = self.read_status()
        temp_count = self._count_files(self.launcher.temp_dir)
        part_count = self._count_files(self.launcher.temp_dir, "*.part")
        channels_count = self._count_lines(self.launcher.channels_file, skip_comments=True)
        queue_count = self._count_lines(self.launcher.queue_file, skip_comments=True)
        archive_count = self._archive_entries_count()

        state = status_info.get("state") or "sleep"
        stop_requested = self.launcher.stop_file.exists()
        if self.launcher.is_running:
            if stop_requested or state == "stopping":
                state = "stopping"
            elif state not in {"searching", "downloading"}:
                state = "searching"
        else:
            state = "sleep"

        self.overview_channels_label.setText(f"{self._emoji_html('📺')} Каналов: {channels_count}")
        self.overview_queue_label.setText(f"{self._emoji_html('📥')} Очередь: {queue_count}")
        self.overview_archive_label.setText(f"{self._emoji_html('🗃')} Архив: {archive_count}")
        last_download_text = self._last_download_text(status_info)
        self.overview_last_download_label.setText(
            f"{self._emoji_html('⏱️')}: {self._html_text(last_download_text)}"
        )
        self.overview_last_download_label.setToolTip(
            f"Последнее скаченное видео: {last_download_text}"
        )
        self.overview_temp_label.setText(
            f"Файлы{self._emoji_html('⌛')}:{temp_count}  {self._emoji_html('⚠')}:{part_count}"
        )
        self.overview_temp_label.setToolTip(
            f"Временных файлов: {temp_count}\nНедокачанных файлов: {part_count}"
        )

        if self.launcher.is_running and stop_requested:
            self._set_run_button_state(
                True,
                False,
                "Остановка уже запрошена; скрипт завершится на безопасном шаге",
            )
        elif self.launcher.is_running:
            self._set_run_button_state(
                True,
                True,
                "Мягко остановить скачивание после текущего безопасного шага",
            )
        else:
            self._set_run_button_state(False, True, "Запустить проверку очереди и каналов")

        channel_url = status_info.get("channel_url") or ""
        channel_name = self._channel_display_name(channel_url, status_info.get("channel_name") or "")
        if self.launcher.is_running and channel_url:
            channel_image = self.channel_cache_path(channel_url).with_suffix(".jpg")
            main_image = channel_image if channel_image.exists() else self.launcher.overview_logo_path
        else:
            main_image = self.launcher.overview_logo_path
        self._set_label_image(self.overview_main_image, main_image, channel_name or "YT")

        overview_preview = self.current_previews.get("overview", {})
        overview_url = self.overview_video_url_input.text().strip() if hasattr(self, "overview_video_url_input") else ""
        thumb_path = None
        if self.launcher.is_running and state == "downloading":
            thumb_path = self._current_video_thumbnail_path(status_info)
        elif overview_preview.get("thumbnail_path"):
            candidate = Path(overview_preview.get("thumbnail_path"))
            if candidate.is_file():
                thumb_path = candidate
        if not thumb_path and self.launcher.video_placeholder_path.exists():
            thumb_path = self.launcher.video_placeholder_path
        if thumb_path:
            self.overview_video_image.show()
            self._set_label_image(self.overview_video_image, thumb_path, "YT")
        else:
            self.overview_video_image.hide()

        self._refresh_overview_activity(status_info, state, channels_count)
        if channel_name and self.launcher.is_running:
            self.overview_channel_label.setText(self._html_text(channel_name))
            self.overview_channel_label.setToolTip(channel_name)
        else:
            self.overview_channel_label.setText("-")
            self.overview_channel_label.setToolTip("")

        if state == "sleep":
            video_status = shorts_status = streams_status = "idle"
        else:
            video_status = status_info.get("videos_status")
            shorts_status = status_info.get("shorts_status")
            streams_status = status_info.get("streams_status")
        if status_info.get("current_type") == "queue" and state == "downloading":
            video_status = "downloading"
        self.overview_video_status_label.setText(
            self._type_status_detail_text(video_status)
        )
        self.overview_shorts_status_label.setText(
            self._type_status_detail_text(shorts_status)
        )
        self.overview_streams_status_label.setText(
            self._type_status_detail_text(streams_status)
        )

        title = (status_info.get("video_title") or "").strip()
        if self.launcher.is_running and state == "downloading" and title:
            self.overview_download_title_label.show()
            self.overview_download_title_label.setText(f"Скачивается видео: {self._html_text(title)}")
            self.overview_download_title_label.setToolTip(title)
            self.overview_idle_uploader_label.clear()
            self.overview_idle_status_label.clear()
        elif overview_url or overview_preview:
            preview_title = overview_preview.get("title") or self.overview_download_title_label.text() or "Загрузка данных..."
            self.overview_download_title_label.show()
            self.overview_download_title_label.setText(self._html_text(preview_title))
            self.overview_download_title_label.setToolTip(preview_title)
            uploader = overview_preview.get("uploader") or ""
            self.overview_idle_uploader_label.setText(f"Канал: {self._html_text(uploader)}" if uploader else "")
            if not self.overview_idle_status_label.text():
                self.overview_idle_status_label.setText("Готово к добавлению в очередь" if overview_preview else "Читаю название и обложку...")
        else:
            self.overview_download_title_label.show()
            self.overview_download_title_label.setText("Ожидаем скачивания")
            self.overview_download_title_label.setToolTip("")
            self.overview_idle_uploader_label.clear()
            if self.overview_idle_status_label.text() != "Добавлено в очередь":
                self.overview_idle_status_label.clear()

        self._refresh_overview_progress(status_info, state)
        self.overview_events_label.setText(self._recent_events_html(status_info, state))

    def _overview_state_text(self, state: str):
        return {
            "sleep": f"{self._emoji_html('😴')} Сон",
            "searching": f"{self._emoji_html('🔎')} Идет поиск",
            "downloading": f"{self._emoji_html('⬇️')} Идет скачивание",
            "stopping": f"{self._emoji_html('⏹')} Остановка",
            "stopped": f"{self._emoji_html('⏹')} Остановлено",
        }.get(state, f"{self._emoji_html('😴')} Сон")

    def _refresh_overview_activity(self, status_info: dict, state: str, channels_count: int):
        if state in {"searching", "downloading"}:
            try:
                total = max(0, int(status_info.get("channels_total") or channels_count))
                checked = max(0, min(total, int(status_info.get("channels_checked") or 0)))
            except (TypeError, ValueError):
                total, checked = channels_count, 0
            self.overview_activity_bar.setRange(0, max(1, total))
            self.overview_activity_bar.setValue(checked)
            self.overview_activity_bar.setFormat(f"Проверено каналов: {checked} / {total}")
            return

        self.overview_activity_bar.setRange(0, 100)
        if state == "stopping":
            self.overview_activity_bar.setValue(100)
            self.overview_activity_bar.setFormat("Остановка")
        elif state == "stopped":
            self.overview_activity_bar.setValue(0)
            self.overview_activity_bar.setFormat("Остановлено")
        else:
            self.overview_activity_bar.setValue(0)
            self.overview_activity_bar.setFormat("Сон")

    def _overview_header_state_text(self, state: str):
        return {
            "sleep": self._emoji_html("😴"),
            "searching": self._emoji_html("🔎"),
            "downloading": self._emoji_html("⬇️"),
            "stopping": self._emoji_html("⏹"),
            "stopped": self._emoji_html("⏹"),
        }.get(state, self._emoji_html("😴"))

    def _type_status_text(self, status: str):
        return {
            "searching": self._emoji_html("🔎"),
            "done": self._emoji_html("✅"),
            "missing": self._emoji_html("❌"),
            "downloading": self._emoji_html("⬇️"),
            "disabled": self._emoji_html("🚫"),
            "idle": self._emoji_html("😴"),
        }.get(status or "idle", self._emoji_html("😴"))

    def _type_status_detail_text(self, status: str):
        emoji, text = {
            "searching": ("🔎", "Поиск"),
            "done": ("✅", "Проверено"),
            "missing": ("❌", "Страница отсутствует"),
            "downloading": ("⬇️", "Скачивание"),
            "disabled": ("🚫", "Отключено"),
            "idle": ("😴", "Ожидание"),
        }.get(status or "idle", ("😴", "Ожидание"))
        return f"{self._emoji_html(emoji)} {self._html_text(text)}"

    def _refresh_overview_progress(self, status_info: dict, state: str):
        self.overview_progress_panel.setVisible(state == "downloading")
        if state != "downloading":
            self.overview_progress_bar.setValue(0)
            self.overview_progress_header_label.clear()
            self.overview_progress_detail_label.clear()
            return

        stage = str(status_info.get("download_stage") or "download").strip().lower()
        stage_text = {
            "video": "Скачивается видео",
            "audio": "Скачивается аудио",
            "merge": "Объединение видео и аудио",
            "postprocess": "Обработка файла",
            "download": "Скачивание",
        }.get(stage, "Скачивание")
        self.overview_progress_header_label.setText(stage_text)

        percent_text = str(status_info.get("download_percent") or "").replace(",", ".").strip()
        try:
            percent = max(0.0, min(100.0, float(percent_text)))
        except (TypeError, ValueError):
            percent = None

        if percent is not None:
            self.overview_progress_bar.setValue(int(round(percent)))
            percent_label = f"{percent:.1f}".rstrip("0").rstrip(".")
            details = [f"{percent_label}%"]
            speed = str(status_info.get("download_speed") or "").strip()
            eta = str(status_info.get("download_eta") or "").strip()
            size = str(status_info.get("download_size") or "").strip()
            if speed:
                details.append(f"{self._emoji_html('🚀')} {self._html_text(speed)}")
            if eta:
                details.append(f"{self._emoji_html('⏳')} {self._html_text(eta)}")
            if size:
                details.append(f"{self._emoji_html('💾')} {self._html_text(size)}")
            self.overview_progress_detail_label.setText(" &nbsp; ".join(details))
        else:
            self.overview_progress_bar.setValue(0)
            self.overview_progress_detail_label.setText("Ожидаю данные прогресса от yt-dlp")

    def _recent_events_html(self, status_info: dict, state: str, limit: int = 6):
        if not self.launcher.is_running and state in {"sleep", "stopped"}:
            report = self._last_run_report_html(status_info)
            if report:
                return report

        try:
            lines = read_text_for_display(self.launcher.log_file).splitlines()
        except Exception:
            lines = []

        events = []
        for line in reversed(lines):
            text = fix_mojibake(line).strip()
            if not text or text.startswith("[download]"):
                continue
            events.append(text)
            if len(events) >= limit:
                break
        if not events:
            return self._html_text("Событий пока нет")
        return "<br>".join(self._html_text(line) for line in reversed(events))

    def _last_run_report_html(self, status_info: dict):
        completed_at = self._valid_timestamp(status_info.get("last_run_completed_at"))
        if not completed_at:
            return ""

        def count(key: str) -> int:
            try:
                return max(0, int(status_info.get(key) or 0))
            except (TypeError, ValueError):
                return 0

        stopped = bool(status_info.get("last_run_stopped"))
        title_emoji = "⏹" if stopped else "✅"
        title = "Последняя проверка остановлена" if stopped else "Последняя проверка завершена"
        finished = time.strftime("%d.%m.%Y в %H:%M", time.localtime(completed_at))
        lines = [
            (
                f"{self._emoji_html(title_emoji)} <b>{self._html_text(title)}</b>"
                f" &nbsp; {self._emoji_html('🕒')} {self._html_text(finished)}"
            ),
        ]

        total = count("last_run_new_count")
        if total:
            media_counts = (
                f"{self._emoji_html('🎬')} {count('last_run_videos')}"
                f" &nbsp; {self._emoji_html('⚡')} {count('last_run_shorts')}"
                f" &nbsp; {self._emoji_html('🔴')} {count('last_run_streams')}"
            )
            queue_count = count("last_run_queue")
            if queue_count:
                media_counts += f" &nbsp; {self._emoji_html('📥')} {queue_count}"
            lines.append(f"{self._emoji_html('📦')} Скачано: <b>{total}</b> &nbsp; {media_counts}")
        else:
            lines.append(f"{self._emoji_html('📭')} Новых видео не найдено")

        checked = count("last_run_channels_checked")
        channels_total = count("last_run_channels_total")
        failed = count("last_run_failed_count")
        lines.append(
            f"{self._emoji_html('📺')} Проверено каналов: {checked} / {channels_total}"
            f" &nbsp; {self._emoji_html('⚠️' if failed else '✨')} "
            f"{self._html_text(f'Ошибок: {failed}' if failed else 'Без ошибок')}"
        )
        return "<br>".join(lines)

    def _last_download_text(self, status_info: dict):
        timestamps = []

        if self.launcher.last_download_file.exists():
            try:
                timestamp = self._valid_timestamp(self.launcher.last_download_file.read_text(encoding="utf-8").strip())
                if timestamp:
                    timestamps.append(timestamp)
            except Exception:
                pass

        timestamp = self._valid_timestamp(status_info.get("last_download_at"))
        if timestamp:
            timestamps.append(timestamp)

        timestamp = self._latest_final_video_timestamp()
        if timestamp:
            timestamps.append(timestamp)

        if not timestamps:
            return "нет"
        timestamp = max(timestamps)
        elapsed = max(0, int(time.time() - timestamp))
        if elapsed < 60:
            return "только что"
        days, rem = divmod(elapsed, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        parts = []
        if days:
            parts.append(f"{days}д")
        if hours or days:
            parts.append(f"{hours}ч")
        parts.append(f"{minutes}м")
        return " ".join(parts[:3]) + " назад"

    def _valid_timestamp(self, value):
        try:
            timestamp = float(str(value or "").strip())
        except (TypeError, ValueError):
            return None
        if timestamp <= 0 or timestamp > time.time() + 300:
            return None
        return timestamp

    def _latest_final_video_timestamp(self):
        if not self.launcher.final_dir.exists():
            return None
        latest = None
        try:
            for path in self.launcher.final_dir.rglob("*.mp4"):
                if path.is_file():
                    mtime = path.stat().st_mtime
                    latest = mtime if latest is None else max(latest, mtime)
        except Exception:
            return latest
        return latest

    def _current_video_thumbnail_path(self, status_info: dict):
        thumb_text = (status_info.get("video_thumbnail") or "").strip()
        if thumb_text:
            thumb_path = Path(thumb_text)
            if thumb_path.is_file():
                return thumb_path
            jpg_path = thumb_path.with_suffix(".jpg")
            if jpg_path.is_file():
                return jpg_path

        if not self.launcher.temp_dir.exists():
            return None
        try:
            images = [
                item
                for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp")
                for item in self.launcher.temp_dir.glob(pattern)
                if item.is_file()
            ]
            if images:
                return max(images, key=lambda item: item.stat().st_mtime)
        except Exception:
            return None
        return None

    def _count_files(self, path: Path, pattern: str = "*"):
        if not path.exists():
            return 0
        try:
            return sum(1 for item in path.rglob(pattern) if item.is_file())
        except Exception:
            return 0

    def _archive_entries_count(self):
        detailed_count = self._count_lines(self.launcher.archive_details_file)
        return detailed_count if detailed_count > 0 else self._count_lines(self.launcher.archive_file)

    def _channel_display_name(self, channel_url: str, fallback: str):
        if channel_url and self._looks_like_youtube_channel_url(channel_url):
            meta_path = self.channel_cache_path(channel_url).with_suffix(".json")
            try:
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    title = (meta.get("title") or "").strip()
                    if title:
                        return title
            except Exception:
                pass
        if fallback:
            return fallback
        if channel_url and self._looks_like_youtube_channel_url(channel_url):
            return self.channel_title_from_url(channel_url)
        return ""

    def _set_label_image(self, label: QLabel, path, placeholder: str):
        pixmap = QPixmap()
        path_obj = Path(path) if path else None
        if path_obj and path_obj.is_file():
            pixmap = QPixmap(str(path_obj))
        if pixmap.isNull():
            pixmap = self.placeholder_pixmap(placeholder or "YT")
        label.setText("")
        label.setPixmap(pixmap.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def refresh_channels(self):
        self._clear_layout(self.channels_grid)
        self.channel_cards = {}
        self.channel_rules = self.load_channel_rules()
        for row in range(self.channels_grid.rowCount()):
            self.channels_grid.setRowMinimumHeight(row, 0)

        channels = self._read_channels()
        for idx, channel in enumerate(channels):
            row = idx // 4
            col = idx % 4
            card = self.create_channel_card(channel)
            self.channels_grid.addWidget(card, row, col)
            self.channel_cards[channel] = card
            self.load_cached_channel_metadata(channel, card)
            self.apply_channel_section_result(channel, card)
            if os.environ.get("YTD_SKIP_CHANNEL_METADATA") != "1" and not self.channel_cache_complete(channel):
                thread = threading.Thread(target=self._channel_metadata_worker, args=(channel,), daemon=True)
                thread.start()

        plus_row = len(channels) // 4
        plus_col = len(channels) % 4
        self.channels_grid.addWidget(self.create_add_channel_card(), plus_row, plus_col)

        total_rows = ((len(channels) + 1) + 3) // 4
        for row in range(total_rows):
            self.channels_grid.setRowMinimumHeight(row, 244)
        for col in range(4):
            self.channels_grid.setColumnStretch(col, 1)

    def add_channel(self):
        text, ok = QInputDialog.getText(self, "Добавить канал", "Ссылка на YouTube-канал:")
        if not ok:
            return
        text = text.strip()
        if not text:
            return
        if not self._looks_like_youtube_channel_url(text):
            QMessageBox.warning(self, "Каналы", "Нужна ссылка на YouTube-канал")
            return
        text = text.rstrip("/")
        existing = self._read_channels()
        if text in existing:
            QMessageBox.information(self, "Каналы", "Такой канал уже есть")
            return
        self.save_channel_urls(self._read_channels() + [text])
        self.refresh_channels()
        self.refresh_overview()
        self.check_channel_sections(text)

    def remove_channel(self, channel: str):
        channels = [item for item in self._read_channels() if item != channel]
        self.save_channel_urls(channels)
        key = self.normalize_channel_key(channel)
        if key in self.channel_rules:
            self.channel_rules.pop(key, None)
            self.save_channel_rules()
        self.channel_section_results.pop(key, None)
        self.channel_section_checks_running.discard(key)
        self.refresh_channels()
        self.refresh_overview()

    def save_channel_urls(self, channels):
        channels = [c.strip().rstrip("/") for c in channels if c.strip()]
        try:
            self.launcher.channels_file.write_text("\n".join(channels) + "\n", encoding="utf-8-sig")
        except Exception as e:
            QMessageBox.warning(self, "Каналы", str(e))

    def normalize_channel_key(self, channel: str):
        return str(channel or "").strip().rstrip("/")

    def load_channel_rules(self):
        try:
            if not self.launcher.channel_rules_file.exists():
                return {}
            data = json.loads(self.launcher.channel_rules_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            rules = {}
            for channel, values in data.items():
                key = self.normalize_channel_key(channel)
                if not key or not isinstance(values, dict):
                    continue
                channel_rules = {}
                for type_name, default in CHANNEL_TYPE_DEFAULTS.items():
                    channel_rules[type_name] = bool(values.get(type_name, default))
                if channel_rules != CHANNEL_TYPE_DEFAULTS:
                    rules[key] = channel_rules
            return rules
        except Exception:
            return {}

    def save_channel_rules(self):
        try:
            self.launcher.channel_rules_file.parent.mkdir(parents=True, exist_ok=True)
            self.launcher.channel_rules_file.write_text(
                json.dumps(self.channel_rules, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            QMessageBox.warning(self, "Каналы", str(e))

    def channel_rule(self, channel: str):
        key = self.normalize_channel_key(channel)
        rules = dict(CHANNEL_TYPE_DEFAULTS)
        rules.update(self.channel_rules.get(key, {}))
        return rules

    def set_channel_type_enabled(self, channel: str, type_name: str, enabled: bool):
        if type_name not in CHANNEL_TYPE_DEFAULTS:
            return
        key = self.normalize_channel_key(channel)
        rules = self.channel_rule(channel)
        rules[type_name] = bool(enabled)
        if rules == CHANNEL_TYPE_DEFAULTS:
            self.channel_rules.pop(key, None)
        else:
            self.channel_rules[key] = rules
        self.save_channel_rules()

    def check_all_channel_sections(self):
        channels = self._read_channels()
        if not channels:
            self.channel_sections_status_label.setText("Каналов нет")
            return
        if not self.launcher.check_sections_script_path.exists():
            QMessageBox.warning(self, "Каналы", f"Не найден скрипт:\n{self.launcher.check_sections_script_path}")
            return

        self.check_channel_sections_button.setEnabled(False)
        self.channel_sections_status_label.setText(f"Проверка: 0/{len(channels)}")
        for channel in channels:
            self.mark_channel_section_checking(channel)
        thread = threading.Thread(target=self._check_channel_sections_many_worker, args=(channels,), daemon=True)
        thread.start()

    def check_channel_sections(self, channel: str):
        if not self.launcher.check_sections_script_path.exists():
            return
        self.mark_channel_section_checking(channel)
        thread = threading.Thread(target=self._check_channel_sections_worker, args=(channel, False), daemon=True)
        thread.start()

    def mark_channel_section_checking(self, channel: str):
        key = self.normalize_channel_key(channel)
        self.channel_section_checks_running.add(key)
        card = self.channel_cards.get(channel)
        if not card:
            return
        for type_name, button in getattr(card, "type_buttons", {}).items():
            button.setText("…")
            button.setToolTip(f"{self.channel_type_label(type_name)}: проверяется наличие раздела")

    def _check_channel_sections_many_worker(self, channels: list):
        total = len(channels)
        done = 0
        for channel in channels:
            self._check_channel_sections_worker(channel, True)
            done += 1
            self.channel_sections_checked.emit({"progress_done": done, "progress_total": total})
        self.channel_sections_checked.emit({"batch_finished": True, "progress_total": total})

    def _check_channel_sections_worker(self, channel: str, called_from_batch: bool):
        args = [
            "--channel",
            channel,
        ]
        payload = {"channel": channel, "sections": {}, "error": ""}
        try:
            result = self.launcher.run_python_script_capture(self.launcher.check_sections_script_path, args, timeout=180)
            if result.returncode != 0:
                payload["error"] = (result.stderr or result.stdout or "Не удалось проверить канал").strip()
            else:
                payload.update(json.loads(result.stdout.strip() or "{}"))
        except Exception as e:
            payload["error"] = str(e)

        payload["called_from_batch"] = called_from_batch
        self.channel_sections_checked.emit(payload)

    def on_channel_sections_checked(self, info: dict):
        if info.get("progress_done") is not None:
            self.channel_sections_status_label.setText(
                f"Проверка: {info.get('progress_done')}/{info.get('progress_total')}"
            )
            return
        if info.get("batch_finished"):
            self.check_channel_sections_button.setEnabled(True)
            self.channel_sections_status_label.setText(f"Проверено каналов: {info.get('progress_total', 0)}")
            return

        channel = info.get("channel")
        if not channel:
            return
        key = self.normalize_channel_key(channel)
        self.channel_section_checks_running.discard(key)
        sections = info.get("sections") or {}
        if isinstance(sections, dict) and sections:
            self.channel_section_results[key] = sections
        card = self.channel_cards.get(channel)
        if card:
            self.apply_channel_section_result(channel, card)
        error = (info.get("error") or "").strip()
        if error and not info.get("called_from_batch"):
            self.channel_sections_status_label.setText("Проверка не удалась")

    def apply_channel_section_result(self, channel: str, card=None):
        card = card or self.channel_cards.get(channel)
        if not card:
            return
        key = self.normalize_channel_key(channel)
        if key in self.channel_section_checks_running:
            for type_name, button in getattr(card, "type_buttons", {}).items():
                button.setText("…")
                button.setToolTip(f"{self.channel_type_label(type_name)}: проверяется наличие раздела")
            return

        sections = self.channel_section_results.get(key) or {}
        for type_name, button in getattr(card, "type_buttons", {}).items():
            base_emoji = self.channel_type_emoji(type_name)
            section = sections.get(type_name) or {}
            status = section.get("status") if isinstance(section, dict) else ""
            if status == "missing":
                button.setText("❌")
                button.setToolTip(f"{self.channel_type_label(type_name)}: раздел не найден; настройка скачивания не изменена")
            elif status == "error":
                button.setText(base_emoji)
                error = (section.get("error") or "").strip() if isinstance(section, dict) else ""
                button.setToolTip(f"{self.channel_type_label(type_name)}: не удалось проверить" + (f" ({error[:120]})" if error else ""))
            else:
                button.setText(base_emoji)
                if status == "available":
                    button.setToolTip(f"{self.channel_type_label(type_name)}: раздел найден; зелёный - скачивать, красный - пропускать")
                else:
                    button.setToolTip(f"{self.channel_type_label(type_name)}: зелёный - скачивать, красный - пропускать")

    def channel_type_emoji(self, type_name: str):
        for item_type, emoji, _label in CHANNEL_TYPE_BUTTONS:
            if item_type == type_name:
                return emoji
        return "?"

    def channel_type_label(self, type_name: str):
        for item_type, _emoji, label in CHANNEL_TYPE_BUTTONS:
            if item_type == type_name:
                return label
        return type_name

    def mark_channel_archived(self, channel: str):
        if self.launcher.is_running:
            QMessageBox.warning(
                self,
                "Архив",
                "Сначала остановите скачивание, чтобы архив не записывался одновременно из двух мест.",
            )
            return
        if not self.launcher.mark_script_path.exists():
            QMessageBox.warning(self, "Архив", f"Не найден скрипт:\n{self.launcher.mark_script_path}")
            return

        title = self._channel_display_name(channel, self.channel_title_from_url(channel)) or channel
        answer = QMessageBox.question(
            self,
            "Архив",
            (
                f"Пометить последние элементы разделов Видео, Shorts и Трансляция канала «{title}» как уже скачанные?\n\n"
                "Скачивание не запустится. Найденные ролики будут добавлены в архив."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        thread = threading.Thread(target=self._mark_channel_archived_worker, args=(channel,), daemon=True)
        thread.start()

    def _mark_channel_archived_worker(self, channel: str):
        args = [
            "--channel",
            channel,
            "--archive",
            str(self.launcher.archive_file),
            "--videos-limit",
            str(self.launcher.videos_limit),
            "--shorts-limit",
            str(self.launcher.shorts_limit),
            "--streams-limit",
            str(self.launcher.streams_limit),
        ]
        try:
            result = self.launcher.run_python_script_capture(self.launcher.mark_script_path, args, timeout=240)
            if result.returncode != 0:
                message = (result.stderr or result.stdout or "Не удалось обновить архив").strip()
                self.channel_mark_archive_failed.emit(message)
                return
            try:
                payload = json.loads(result.stdout.strip() or "{}")
            except json.JSONDecodeError:
                payload = {"channel": channel, "summary": {}, "raw": result.stdout}
            self.channel_marked_archived.emit(payload)
        except Exception as e:
            self.channel_mark_archive_failed.emit(str(e))

    def on_channel_marked_archived(self, info: dict):
        summary = info.get("summary") or {}
        type_info = info.get("types") or {}
        labels = {
            "videos": "Видео",
            "shorts": "Shorts",
            "streams": "Трансляция",
        }
        lines = [
            f"Найдено: {summary.get('total_found', 0)}",
            f"Добавлено в архив: {summary.get('total_added', 0)}",
        ]
        for type_name in ("videos", "shorts", "streams"):
            details = type_info.get(type_name) or {}
            line = f"{labels[type_name]}: найдено {details.get('found', 0)}, добавлено {details.get('added', 0)}"
            error = (details.get("error") or "").strip()
            if error:
                line += f", ошибка: {error}"
            lines.append(line)
        QMessageBox.information(self, "Архив", "\n".join(lines))
        self.refresh_overview()

    def on_channel_mark_archive_failed(self, message: str):
        QMessageBox.warning(self, "Архив", message or "Не удалось обновить архив")

    def create_channel_card(self, channel: str):
        card = QWidget()
        card.setFixedSize(190, 242)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        image_box = QWidget()
        image_box.setFixedSize(190, 190)
        image = ClickableLabel(image_box)
        image.setGeometry(0, 0, 190, 190)
        image.setAlignment(Qt.AlignCenter)
        image.setPixmap(self.placeholder_pixmap(self.channel_title_from_url(channel)).scaled(190, 190, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        image.setStyleSheet("background: #333;")
        image.setCursor(Qt.PointingHandCursor)
        image.setToolTip("Открыть канал")
        image.clicked.connect(lambda c=channel: self.open_channel(c))

        delete_btn = QPushButton("X", image_box)
        delete_btn.setGeometry(156, 4, 30, 30)
        delete_btn.setToolTip("Удалить канал")
        delete_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 0, 0, 110);
                color: white;
                border: none;
                font-size: 24px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                background: rgba(180, 40, 40, 190);
            }
        """)
        delete_btn.clicked.connect(lambda checked=False, c=channel: self.remove_channel(c))
        delete_btn.raise_()

        rules = self.channel_rule(channel)
        type_buttons = {}
        for idx, (type_name, emoji, label) in enumerate(CHANNEL_TYPE_BUTTONS):
            type_btn = QPushButton(emoji, image_box)
            type_btn.setCheckable(True)
            type_btn.setChecked(rules.get(type_name, True))
            type_btn.setGeometry(156, 38 + idx * 34, 30, 30)
            type_btn.setToolTip(f"{label}: зелёный - скачивать, красный - пропускать")
            type_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(185, 48, 48, 190);
                    color: white;
                    border: none;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 18px;
                    font-weight: bold;
                    padding: 0;
                    text-align: center;
                }
                QPushButton:checked {
                    background: rgba(37, 150, 80, 190);
                }
                QPushButton:hover {
                    background: rgba(180, 40, 40, 210);
                }
                QPushButton:checked:hover {
                    background: rgba(37, 150, 80, 220);
                }
            """)
            type_btn.clicked.connect(
                lambda checked=False, c=channel, t=type_name: self.set_channel_type_enabled(c, t, checked)
            )
            type_btn.raise_()
            type_buttons[type_name] = type_btn

        archive_btn = QPushButton("✅", image_box)
        archive_btn.setGeometry(156, 140, 30, 30)
        archive_btn.setToolTip("Пометить последние элементы разделов Видео, Shorts и Трансляция как уже скачанные")
        archive_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 0, 0, 115);
                color: white;
                border: none;
                font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                font-size: 18px;
                font-weight: bold;
                padding: 0;
                text-align: center;
            }
            QPushButton:hover {
                background: rgba(35, 120, 210, 210);
            }
        """)
        archive_btn.clicked.connect(lambda checked=False, c=channel: self.mark_channel_archived(c))
        archive_btn.raise_()

        title = QLabel(self.channel_title_from_url(channel))
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setFixedHeight(44)
        title.setToolTip(self.channel_title_from_url(channel))
        font = QFont("Serif")
        font.setPointSize(12)
        font.setBold(True)
        title.setFont(font)

        layout.addWidget(image_box)
        layout.addWidget(title)

        card.image_label = image
        card.title_label = title
        card.type_buttons = type_buttons
        return card

    def create_add_channel_card(self):
        card = QWidget()
        card.setFixedSize(190, 242)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        button = QPushButton("+")
        button.setFixedSize(190, 190)
        button.setToolTip("Добавить канал")
        button.clicked.connect(self.add_channel)
        button.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: white;
                border: none;
                font-size: 96px;
            }
            QPushButton:hover {
                background: #4a4a4a;
            }
        """)
        title = QLabel("")
        title.setFixedHeight(44)
        layout.addWidget(button)
        layout.addWidget(title)
        return card

    def load_cached_channel_metadata(self, channel: str, card):
        cache = self.channel_cache_path(channel)
        image_path = cache.with_suffix(".jpg")
        meta_path = cache.with_suffix(".json")
        try:
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                title = meta.get("title") or self.channel_title_from_url(channel)
                card.title_label.setText(title)
                card.title_label.setToolTip(title)
            if image_path.exists():
                pixmap = QPixmap(str(image_path))
                if not pixmap.isNull():
                    card.image_label.setPixmap(pixmap.scaled(190, 190, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        except Exception:
            pass

    def channel_cache_complete(self, channel: str):
        cache = self.channel_cache_path(channel)
        return cache.with_suffix(".jpg").exists() and cache.with_suffix(".json").exists()

    def _channel_metadata_worker(self, channel: str):
        try:
            metadata_url = f"{channel.rstrip('/')}/videos"
            result = subprocess.run(
                self.launcher.yt_dlp_command()
                + self.launcher.yt_dlp_js_runtime_args()
                + ["--dump-single-json", "--skip-download", "--flat-playlist", "--playlist-items", "1", metadata_url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self.launcher.script_environment(),
                timeout=45,
            )
            if result.returncode != 0:
                return
            data = json.loads(result.stdout)
            title = data.get("channel") or data.get("uploader") or data.get("title") or self.channel_title_from_url(channel)
            thumbnails = data.get("thumbnails") or []
            thumbnail_url = ""
            if thumbnails:
                thumbnail_url = thumbnails[-1].get("url") or ""

            image_path = ""
            cache = self.channel_cache_path(channel)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.with_suffix(".json").write_text(json.dumps({"title": title}, ensure_ascii=False), encoding="utf-8")
            cached_image = cache.with_suffix(".jpg")
            if cached_image.exists():
                image_path = str(cached_image)
            elif thumbnail_url:
                image_path = str(cache.with_suffix(".jpg"))
                try:
                    urllib.request.urlretrieve(thumbnail_url, image_path)
                except Exception:
                    image_path = ""

            self.channel_metadata_loaded.emit({"channel": channel, "title": title, "image_path": image_path})
        except Exception:
            return

    def on_channel_metadata_loaded(self, info: dict):
        channel = info.get("channel")
        card = self.channel_cards.get(channel)
        if not card:
            return
        title = info.get("title")
        if title:
            card.title_label.setText(title)
            card.title_label.setToolTip(title)
        image_path = info.get("image_path")
        if image_path:
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                card.image_label.setPixmap(pixmap.scaled(190, 190, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))

    def open_channel(self, channel: str):
        QDesktopServices.openUrl(QUrl(channel.rstrip("/")))

    def placeholder_pixmap(self, title: str):
        pixmap = QPixmap(200, 200)
        pixmap.fill(QColor("#2c3440"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QColor("#ffffff"))
        font = QFont("Serif")
        font.setBold(True)
        font.setPixelSize(48)
        painter.setFont(font)
        initials = "".join(part[:1] for part in title.replace("_", " ").split()[:2]).upper() or "YT"
        painter.drawText(pixmap.rect(), Qt.AlignCenter, initials)
        painter.end()
        return pixmap

    def channel_title_from_url(self, channel: str):
        text = channel.rstrip("/").split("/")[-1]
        return text[1:] if text.startswith("@") else text

    def channel_cache_path(self, channel: str):
        safe = "".join(ch if ch.isalnum() else "_" for ch in channel)[-80:]
        return self.channel_cache_dir / safe

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def refresh_schedules(self):
        self.schedule_list.clear()
        enabled_count = 0
        for idx, sched in enumerate(self.launcher.schedules):
            is_enabled = sched.get("enabled", True)
            enabled_count += 1 if is_enabled else 0
            enabled = "ВКЛ" if is_enabled else "ВЫКЛ"
            hour = int(sched.get("hour", 0))
            marker = sched.get("last_run_marker", "")
            last_run = marker if marker else "не запускался"
            item = QListWidgetItem(f"{hour:02d}:00    {enabled}    {last_run}")
            item.setData(Qt.UserRole, idx)
            self.schedule_list.addItem(item)
        if hasattr(self, "schedule_summary_label"):
            total = len(self.launcher.schedules)
            self.schedule_summary_label.setText(f"{enabled_count} включено / {total} всего")

    def add_schedule(self):
        entry = {
            "hour": int(self.schedule_hour_spin.value()),
            "enabled": self.schedule_enabled_check.isChecked(),
            "last_run_marker": "",
        }
        self.launcher.schedules.append(entry)
        self.launcher.save_schedules()
        self.refresh_schedules()

    def toggle_selected_schedule(self):
        idx = self._selected_schedule_index()
        if idx is None:
            return
        self.launcher.schedules[idx]["enabled"] = not self.launcher.schedules[idx].get("enabled", True)
        self.launcher.save_schedules()
        self.refresh_schedules()

    def remove_selected_schedule(self):
        idx = self._selected_schedule_index()
        if idx is None:
            return
        self.launcher.schedules.pop(idx)
        self.launcher.save_schedules()
        self.refresh_schedules()

    def _preview_widgets(self, context: str):
        if context == "overview":
            return {
                "input": self.overview_video_url_input,
                "button": self.overview_add_video_button,
                "thumbnail": self.overview_video_image,
                "title": self.overview_download_title_label,
                "uploader": self.overview_idle_uploader_label,
                "status": self.overview_idle_status_label,
            }
        if context == "quick" and self.quick_download_dialog is not None:
            dialog = self.quick_download_dialog
            return {
                "input": dialog.url_input,
                "button": dialog.add_queue_button,
                "thumbnail": dialog.thumbnail_label,
                "title": dialog.video_title_label,
                "uploader": dialog.video_uploader_label,
                "status": dialog.video_status_label,
            }
        return {
            "input": self.video_url_input,
            "button": self.add_video_button,
            "thumbnail": self.thumbnail_label,
            "title": self.video_title_label,
            "uploader": self.video_uploader_label,
            "status": self.video_status_label,
        }

    def _clear_video_preview(self, context: str):
        widgets = self._preview_widgets(context)
        self.current_previews[context] = {}
        if context == "queue":
            self.current_preview = {}
        widgets["status"].setText("")
        widgets["uploader"].setText("")
        widgets["thumbnail"].setPixmap(QPixmap())
        widgets["thumbnail"].setText("Обложка")
        widgets["button"].setEnabled(False)
        widgets["title"].setText("Ожидаю ссылку YouTube" if context == "quick" else "Введите адрес YouTube-видео")
        if context == "quick" and self.quick_download_dialog is not None:
            self.quick_download_dialog.update_actions(False)
            self.quick_download_dialog.set_channel_logo("")

    def schedule_video_preview(self, context: str = "queue"):
        widgets = self._preview_widgets(context)
        self.current_previews[context] = {}
        if context == "queue":
            self.current_preview = {}
        widgets["status"].setText("")
        widgets["uploader"].setText("")
        widgets["thumbnail"].setPixmap(QPixmap())
        widgets["thumbnail"].setText("Обложка")
        text = widgets["input"].text().strip()
        valid = self._looks_like_youtube_url(text)
        widgets["button"].setEnabled(valid)
        if context == "quick" and self.quick_download_dialog is not None:
            self.quick_download_dialog.update_actions(valid)
        if not text:
            widgets["title"].setText("Ожидаю ссылку YouTube" if context == "quick" else "Введите адрес YouTube-видео")
            return
        if not self._looks_like_youtube_url(text):
            widgets["title"].setText("Ошибка" if context == "quick" else "Введите ссылку на YouTube-видео")
            if context == "quick":
                widgets["status"].setText("Нужна корректная ссылка YouTube")
            return
        widgets["title"].setText("Загрузка данных...")
        self.pending_preview_context = context
        self.preview_timer.start(800)

    def fetch_video_preview(self):
        context = self.pending_preview_context
        widgets = self._preview_widgets(context)
        url = widgets["input"].text().strip()
        if not self._looks_like_youtube_url(url):
            widgets["title"].setText("Введите ссылку на YouTube-видео")
            widgets["status"].setText("")
            return

        self.preview_request_id += 1
        request_id = self.preview_request_id
        self.preview_request_context = context
        widgets["status"].setText("Читаю название и обложку...")

        thread = threading.Thread(target=self._metadata_worker, args=(request_id, context, url), daemon=True)
        thread.start()

    def _metadata_worker(self, request_id: int, context: str, url: str):
        try:
            result = subprocess.run(
                self.launcher.yt_dlp_command()
                + self.launcher.yt_dlp_js_runtime_args()
                + ["--dump-single-json", "--no-playlist", "--skip-download", url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self.launcher.script_environment(),
                timeout=45,
            )
            if result.returncode != 0:
                message = result.stderr.strip() or "Не удалось получить данные видео"
                self.metadata_failed.emit(request_id, message[-300:])
                return

            data = json.loads(result.stdout)
            thumbnail_url = data.get("thumbnail") or ""
            thumbnail_path = ""
            if thumbnail_url:
                preview_dir = self.launcher.cache_dir / "previews"
                preview_dir.mkdir(parents=True, exist_ok=True)
                thumbnail_path = str(preview_dir / f"ytd_preview_{request_id}.jpg")
                try:
                    urllib.request.urlretrieve(thumbnail_url, thumbnail_path)
                except Exception:
                    fallback_path = Path(tempfile.gettempdir()) / f"ytd_preview_{request_id}.jpg"
                    try:
                        urllib.request.urlretrieve(thumbnail_url, str(fallback_path))
                        thumbnail_path = str(fallback_path)
                    except Exception:
                        thumbnail_path = ""

            channel_url = data.get("channel_url") or data.get("uploader_url") or ""
            if not channel_url and data.get("channel_id"):
                channel_url = f"https://www.youtube.com/channel/{data.get('channel_id')}"
            if not channel_url and data.get("uploader_id"):
                uploader_id = str(data.get("uploader_id")).strip()
                if uploader_id.startswith("@"):
                    channel_url = f"https://www.youtube.com/{uploader_id}"
                elif uploader_id:
                    channel_url = f"https://www.youtube.com/channel/{uploader_id}"

            channel_thumbnail_url = data.get("channel_thumbnail") or data.get("uploader_thumbnail") or ""
            channel_thumbnail_path = ""
            if context == "quick" and channel_thumbnail_url:
                preview_dir = self.launcher.cache_dir / "previews"
                preview_dir.mkdir(parents=True, exist_ok=True)
                channel_thumbnail_path = str(preview_dir / f"ytd_channel_{request_id}.jpg")
                try:
                    urllib.request.urlretrieve(channel_thumbnail_url, channel_thumbnail_path)
                except Exception:
                    channel_thumbnail_path = ""

            self.metadata_loaded.emit({
                "request_id": request_id,
                "context": context,
                "url": data.get("webpage_url") or url,
                "video_id": data.get("id") or self.youtube_video_id_from_url(url),
                "title": data.get("title") or "Без названия",
                "uploader": data.get("uploader") or "",
                "thumbnail_path": thumbnail_path,
                "channel_thumbnail_path": channel_thumbnail_path,
                "channel_url": channel_url,
            })
            if context == "quick" and not channel_thumbnail_path and channel_url:
                loaded_path = self.fetch_quick_channel_logo(channel_url, request_id)
                if loaded_path:
                    self.quick_channel_logo_loaded.emit({
                        "request_id": request_id,
                        "image_path": loaded_path,
                    })
        except Exception as e:
            self.metadata_failed.emit(request_id, str(e))

    def fetch_quick_channel_logo(self, channel_url: str, request_id: int) -> str:
        channel_url = str(channel_url or "").strip().rstrip("/")
        if not channel_url:
            return ""
        try:
            cache = self.channel_cache_path(channel_url)
            cached_image = cache.with_suffix(".jpg")
            if cached_image.exists():
                return str(cached_image)

            result = subprocess.run(
                self.launcher.yt_dlp_command()
                + self.launcher.yt_dlp_js_runtime_args()
                + ["--dump-single-json", "--skip-download", "--flat-playlist", "--playlist-items", "1", f"{channel_url}/videos"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self.launcher.script_environment(),
                timeout=18,
            )
            if result.returncode != 0:
                return ""
            data = json.loads(result.stdout)
            title = data.get("channel") or data.get("uploader") or data.get("title") or self.channel_title_from_url(channel_url)
            thumbnails = data.get("thumbnails") or []
            thumbnail_url = ""
            if thumbnails:
                thumbnail_url = thumbnails[-1].get("url") or ""
            if not thumbnail_url:
                return ""

            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.with_suffix(".json").write_text(json.dumps({"title": title}, ensure_ascii=False), encoding="utf-8")
            image_path = str(cached_image)
            urllib.request.urlretrieve(thumbnail_url, image_path)
            return image_path
        except Exception:
            return ""

    def on_metadata_loaded(self, info: dict):
        if info.get("request_id") != self.preview_request_id:
            return
        context = info.get("context") or self.preview_request_context
        widgets = self._preview_widgets(context)
        self.current_previews[context] = info
        if context == "queue":
            self.current_preview = info
        widgets["title"].setText(info.get("title", "Без названия"))
        uploader = info.get("uploader") or ""
        widgets["uploader"].setText(f"Канал: {uploader}" if uploader else "")
        widgets["status"].setText("Готово к добавлению в очередь")
        widgets["button"].setEnabled(True)
        if context == "quick" and self.quick_download_dialog is not None:
            self.quick_download_dialog.update_actions(True)
            self.quick_download_dialog.set_channel_logo(info.get("channel_thumbnail_path") or "")

        thumbnail_path = info.get("thumbnail_path")
        if thumbnail_path:
            pixmap = QPixmap(thumbnail_path)
            if not pixmap.isNull():
                thumbnail = widgets["thumbnail"]
                thumbnail.setText("")
                thumbnail.setPixmap(pixmap.scaled(thumbnail.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def on_quick_channel_logo_loaded(self, info: dict):
        if info.get("request_id") != self.preview_request_id:
            return
        if self.quick_download_dialog is not None:
            self.quick_download_dialog.set_channel_logo(info.get("image_path") or "")

    def on_metadata_failed(self, request_id: int, message: str):
        if request_id != self.preview_request_id:
            return
        context = self.preview_request_context
        widgets = self._preview_widgets(context)
        self.current_previews[context] = {}
        if context == "queue":
            self.current_preview = {}
        widgets["button"].setEnabled(self._looks_like_youtube_url(widgets["input"].text().strip()))
        if context == "quick" and self.quick_download_dialog is not None:
            self.quick_download_dialog.update_actions(self._looks_like_youtube_url(widgets["input"].text().strip()))
            self.quick_download_dialog.set_channel_logo("")
        widgets["title"].setText("Не удалось прочитать видео")
        widgets["status"].setText(f"{message}\nМожно добавить ссылку в очередь без предпросмотра.")

    def add_video_to_queue(self, context: str = "queue", *, front: bool = False, clear_after: bool = True, quiet: bool = False):
        widgets = self._preview_widgets(context)
        preview = self.current_previews.get(context, {})
        url = (preview.get("url") or widgets["input"].text()).strip()
        if not self._looks_like_youtube_url(url):
            if not quiet:
                QMessageBox.warning(self, "Очередь", "Нужна ссылка на YouTube-видео")
            return False

        video_id = (preview.get("video_id") or self.youtube_video_id_from_url(url)).strip()
        if video_id and self.archive_contains_video(video_id):
            if not quiet:
                QMessageBox.information(self, "Очередь", "Это видео уже есть в архиве")
            widgets["status"].setText("Видео уже есть в архиве")
            return False

        queued = self._read_queue()
        queued_ids = {self.youtube_video_id_from_url(item) for item in queued}
        if url in queued or (video_id and video_id in queued_ids):
            if not front:
                if not quiet:
                    QMessageBox.information(self, "Очередь", "Это видео уже есть в очереди")
                return False
            queued = [
                item for item in queued
                if item != url and (not video_id or self.youtube_video_id_from_url(item) != video_id)
            ]

        try:
            self.launcher.queue_file.parent.mkdir(parents=True, exist_ok=True)
            if front:
                self._save_queue([url] + queued)
            else:
                with open(self.launcher.queue_file, "a", encoding="utf-8") as f:
                    f.write(url + "\n")
            self.refresh_queue()
            self.refresh_overview()
            if clear_after:
                widgets["input"].clear()
                self._clear_video_preview(context)
            widgets["status"].setText("Поставлено первым в очередь" if front else "Добавлено в очередь")
            return True
        except Exception as e:
            if not quiet:
                QMessageBox.warning(self, "Очередь", str(e))
            return False

    def refresh_queue(self):
        self.queue_list.clear()
        for url in self._read_queue():
            self.queue_list.addItem(url)
        if hasattr(self, "queue_summary_label"):
            count = self.queue_list.count()
            if count == 1:
                text = "1 видео"
            elif 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
                text = f"{count} видео"
            else:
                text = f"{count} видео"
            self.queue_summary_label.setText(text)

    def remove_selected_queued_video(self):
        row = self.queue_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "Очередь", "Не выбрано видео")
            return
        self.queue_list.takeItem(row)
        self._save_queue([self.queue_list.item(i).text() for i in range(self.queue_list.count())])
        self.refresh_queue()
        self.refresh_overview()

    def refresh_logs(self):
        selected = self.log_combo.currentData()
        self.log_combo.blockSignals(True)
        self.log_combo.clear()
        for path in self._log_files():
            self.log_combo.addItem(path.name, str(path))
        if selected:
            index = self.log_combo.findData(selected)
            if index >= 0:
                self.log_combo.setCurrentIndex(index)
        self.log_combo.blockSignals(False)
        self.refresh_log_view()

    def refresh_log_view(self):
        path_text = self.log_combo.currentData()
        if not path_text:
            self.log_view.clear()
            return
        path = Path(path_text)
        self.log_view.setPlainText(self._tail_text(path, 500))
        self.log_view.moveCursor(QTextCursor.End)

    def open_folder(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _selected_schedule_index(self):
        item = self.schedule_list.currentItem()
        if not item:
            QMessageBox.information(self, "Планировщик", "Не выбрана запись")
            return None
        return item.data(Qt.UserRole)

    def _read_channels(self):
        if not self.launcher.channels_file.exists():
            return []
        lines = self.launcher.channels_file.read_text(encoding="utf-8-sig").splitlines()
        return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]

    def _read_queue(self):
        if not self.launcher.queue_file.exists():
            return []
        lines = self.launcher.queue_file.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
        return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]

    def _save_queue(self, urls):
        self.launcher.queue_file.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")

    def _looks_like_youtube_url(self, url: str):
        return url.startswith(("https://www.youtube.com/", "https://youtube.com/", "https://youtu.be/"))

    def _looks_like_youtube_channel_url(self, url: str):
        if not url.startswith(("https://www.youtube.com/", "https://youtube.com/")):
            return False
        return "/@" in url or "/channel/" in url or "/c/" in url or "/user/" in url

    def youtube_video_id_from_url(self, url: str):
        text = str(url or "").strip()
        if not text:
            return ""
        try:
            parsed = urllib.parse.urlparse(text)
            host = parsed.netloc.lower()
            if host.endswith("youtu.be"):
                candidate = parsed.path.strip("/").split("/")[0]
                if len(candidate) == 11:
                    return candidate
            query = urllib.parse.parse_qs(parsed.query)
            candidate = (query.get("v") or [""])[0]
            if len(candidate) == 11:
                return candidate
            parts = [part for part in parsed.path.split("/") if part]
            for marker in ("shorts", "live", "embed"):
                if marker in parts:
                    idx = parts.index(marker)
                    if idx + 1 < len(parts) and len(parts[idx + 1]) == 11:
                        return parts[idx + 1]
        except Exception:
            return ""
        return ""

    def archive_contains_video(self, video_id: str):
        video_id = str(video_id or "").strip()
        if not video_id:
            return False
        try:
            if self.launcher.archive_file.exists():
                for line in read_text_for_display(self.launcher.archive_file).splitlines():
                    if video_id in line.split():
                        return True
        except Exception:
            pass
        try:
            if self.launcher.archive_details_file.exists():
                needle = f'"video_id":"{video_id}"'
                for line in read_text_for_display(self.launcher.archive_details_file).splitlines():
                    if needle in line.replace(" ", ""):
                        return True
        except Exception:
            pass
        return False

    def _count_lines(self, path: Path, skip_comments: bool = False):
        if not path.exists():
            return 0
        count = 0
        for line in read_text_for_display(path).splitlines():
            text = line.strip()
            if not text:
                continue
            if skip_comments and text.startswith("#"):
                continue
            count += 1
        return count

    def _log_files(self):
        paths = []
        if self.launcher.log_file.exists():
            paths.append(self.launcher.log_file)
        paths.extend(sorted(self.launcher.data_dir.glob("download_*.log"), key=lambda p: p.stat().st_mtime, reverse=True))
        return paths

    def _latest_log_file(self):
        logs = self._log_files()
        return logs[0] if logs else None

    def _tail_text(self, path: Path, lines: int):
        if not path or not path.exists():
            return ""
        data = read_text_for_display(path).splitlines()
        return "\n".join(fix_mojibake(item) for item in data[-lines:])

    def _last_interesting_line(self, path: Path):
        if not path or not path.exists():
            return "нет"
        interesting = ("Найдено", "Новых видео", "Отправлено", "Не отправлено", "Видео перемещено", "Жатва завершена")
        for line in reversed(read_text_for_display(path).splitlines()):
            text = fix_mojibake(line).strip()
            if any(marker in text for marker in interesting):
                return text
        return "нет"


def run_python_script_helper(script_name: str, args: list[str]) -> int:
    allowed = {
        "downloader.py",
        "check_channel_sections.py",
        "mark_channel_archived.py",
        "migrate_archive_details.py",
    }
    if script_name not in allowed:
        print(f"Unknown helper script: {script_name}", file=sys.stderr)
        return 2

    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    script_path = base_dir / "scripts" / script_name
    if not script_path.exists():
        print(f"Helper script not found: {script_path}", file=sys.stderr)
        return 2

    spec = importlib.util.spec_from_file_location(f"yth_helper_{script_path.stem}", script_path)
    if spec is None or spec.loader is None:
        print(f"Cannot load helper script: {script_path}", file=sys.stderr)
        return 2

    module = importlib.util.module_from_spec(spec)
    old_argv = sys.argv[:]
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    fallback_stdout = None
    fallback_stderr = None
    try:
        if sys.stdout is None:
            fallback_stdout = open(os.devnull, "w", encoding="utf-8")
            sys.stdout = fallback_stdout
        if sys.stderr is None:
            fallback_stderr = open(os.devnull, "w", encoding="utf-8")
            sys.stderr = fallback_stderr
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                try:
                    reconfigure(encoding="utf-8", errors="replace")
                except (OSError, ValueError):
                    pass
        sys.argv = [str(script_path)] + list(args)
        spec.loader.exec_module(module)
        main_func = getattr(module, "main", None)
        if callable(main_func):
            return int(main_func() or 0)
        return 0
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            return code
        if code in (None, ""):
            return 0
        print(str(code), file=sys.stderr)
        return 1
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        if fallback_stdout is not None:
            fallback_stdout.close()
        if fallback_stderr is not None:
            fallback_stderr.close()


def run_yt_dlp_helper(args: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    try:
        from yt_dlp import main as yt_dlp_main
    except Exception as exc:
        print(f"Cannot load bundled yt-dlp: {exc}", file=sys.stderr)
        return 2
    try:
        result = yt_dlp_main(list(args))
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return 0 if exc.code in (None, "") else 1
    return int(result or 0)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--quick-download":
        raise SystemExit(write_quick_download_request())

    if len(sys.argv) >= 2 and sys.argv[1] == "--run-yt-dlp":
        raise SystemExit(run_yt_dlp_helper(sys.argv[2:]))

    if len(sys.argv) >= 3 and sys.argv[1] == "--run-script":
        raise SystemExit(run_python_script_helper(sys.argv[2], sys.argv[3:]))

    launcher = TrayLauncher()
    launcher.run()
