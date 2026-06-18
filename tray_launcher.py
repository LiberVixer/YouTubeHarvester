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
import io
import contextlib
from pathlib import Path
import urllib.request
import urllib.parse
import html
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
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QFont, QPen, QDesktopServices, QTextCursor, QPalette
from PyQt5.QtCore import Qt, QTimer, QTime, QDate, QUrl, QPoint, pyqtSignal
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
    ("shorts", "📱", "Shorts"),
    ("streams", "🔴", "Трансляция"),
)

APP_NAME = "YouTube Harvester"
APP_VERSION = "0.2.2-beta"
APP_TITLE = f"{APP_NAME} {APP_VERSION}"
USAGE_RULES_VERSION = "2026-06-13"


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
  <li><b>curl</b> используется для Telegram-уведомлений в Bash-движке и режиме SOCKS-прокси.</li>
  <li><b>bash и GNU coreutils/findutils/grep/sed</b> используются в Linux Bash-скрипте скачивания.</li>
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
        self.last_download_file = Path(os.environ.get("YTD_LAST_DOWNLOAD_FILE", self.data_dir / "last_download_at.txt"))
        self.overview_logo_path = Path(os.environ.get("YTD_OVERVIEW_LOGO", self.app_dir / "assets" / "overview-logo.png"))
        self.video_placeholder_path = Path(os.environ.get("YTD_VIDEO_PLACEHOLDER", self.app_dir / "assets" / "video-placeholder.png"))
        self.queue_art_path = Path(os.environ.get("YTD_QUEUE_ART", self.app_dir / "assets" / "queue-scheduler.png"))
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
        return "python" if self.is_windows else "bash"

    def command_exists(self, command: str):
        return shutil.which(command) is not None

    def yt_dlp_command(self):
        configured = os.environ.get("YTD_YT_DLP_COMMAND", "").strip()
        if configured:
            try:
                return shlex.split(configured, posix=(os.name != "nt"))
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
        if getattr(sys, "frozen", False):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                return_code = run_python_script_helper(script_path.name, args)
            return subprocess.CompletedProcess(
                self.python_script_command(script_path) + list(args),
                return_code,
                stdout.getvalue(),
                stderr.getvalue(),
            )
        return subprocess.run(
            self.python_script_command(script_path) + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
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
        telegram_default = self._setting_bool({"telegram_enabled": self.env_setting("TELEGRAM_ENABLED")}, "telegram_enabled", True)
        self.telegram_enabled = self._setting_bool(settings, "telegram_enabled", telegram_default)
        engine = str(settings.get("download_engine") or os.environ.get("YTD_DOWNLOAD_ENGINE") or self.default_download_engine()).strip().lower()
        if self.is_windows:
            self.download_engine = "python"
        else:
            self.download_engine = engine if engine in {"bash", "python"} else self.default_download_engine()
        resolution = str(settings.get("max_resolution") or os.environ.get("YTD_MAX_RESOLUTION") or "1080").strip()
        self.max_resolution = resolution if resolution in {"480", "720", "1080", "1440", "2160", "best"} else "1080"

    def validate_download_environment(self):
        if self.download_engine == "python":
            if not self.python_downloader_path.exists():
                self.show_notification("❌", "Python-движок", f"Не найден файл: {self.python_downloader_path}")
                return False
        else:
            if not self.script_path.exists():
                self.show_notification("❌", "Bash-движок", f"Не найден файл: {self.script_path}")
                return False
            if not self.command_exists("bash"):
                self.show_notification("❌", "Bash не найден", "Выберите Python-движок в настройках")
                return False
        if not getattr(sys, "frozen", False) and not os.environ.get("YTD_YT_DLP_COMMAND") and not self.command_exists("yt-dlp"):
            self.show_notification("❌", "yt-dlp не найден", "Установите yt-dlp и проверьте PATH")
            return False
        return True

    def script_environment(self):
        env = os.environ.copy()
        env.update({
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
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
            "YTD_TELEGRAM_ENABLED": "1" if self.telegram_enabled else "0",
            "YTD_DOWNLOAD_ENGINE": self.download_engine,
            "YTD_YT_DLP_COMMAND": subprocess.list2cmdline(self.yt_dlp_command()),
        })
        return env

    def run_script(self):
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
        self.update_icon()
        self.update_tray_menu()
        self.show_notification("▶️", "Загрузка началась", "Скрипт запущен...")

        thread = threading.Thread(target=self._execute_script, daemon=True)
        thread.start()

    def _execute_script(self):
        proc = None
        try:
            if self.download_engine == "python":
                command = self.python_script_command(self.python_downloader_path)
            else:
                command = ["bash", str(self.script_path)]
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
        self.update_icon()
        if self.main_window is not None and self.main_window.isVisible():
            self.main_window.refresh_overview()

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
        "shorts": "📱 Shorts",
        "streams": "🔴 Трансляция",
        "queue": "📥 Очередь",
    }
    TYPE_EMOJIS = {
        "videos": "🎬",
        "shorts": "📱",
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
        for index, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines()):
            text = line.strip()
            if not text:
                continue
            try:
                entry = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
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
            str(entry.get("channel_name") or ""),
            str(entry.get("title") or ""),
            video_id,
            str(entry.get("downloaded_at") or ""),
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
        for index, raw_line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines()):
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
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
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


class MainWindow(QMainWindow):
    metadata_loaded = pyqtSignal(dict)
    metadata_failed = pyqtSignal(int, str)
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
        self.current_preview = {}
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
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(8)

        metrics = QHBoxLayout()
        metrics.setSpacing(6)
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
        for label in (
            self.overview_channels_label,
            self.overview_queue_label,
            self.overview_archive_label,
            self.overview_last_download_label,
            self.overview_temp_label,
        ):
            metrics.addWidget(label)
        metrics.addStretch()
        header_layout.addLayout(metrics)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.run_button = QPushButton("⏬ Скачать")
        self.run_button.setObjectName("overviewButton")
        self.run_button.setFixedHeight(32)
        self.run_button.setToolTip("Запустить проверку очереди и каналов")
        self.run_button.clicked.connect(self.toggle_download)
        final_btn = QPushButton("📁 Загрузки")
        final_btn.setObjectName("overviewButton")
        final_btn.setFixedHeight(32)
        final_btn.setToolTip("Открыть папку загрузок")
        final_btn.clicked.connect(lambda: self.open_folder(self.launcher.final_dir))
        temp_btn = QPushButton("⌛ Врем.")
        temp_btn.setObjectName("overviewButton")
        temp_btn.setFixedHeight(32)
        temp_btn.setToolTip("Открыть временную папку")
        temp_btn.clicked.connect(lambda: self.open_folder(self.launcher.temp_dir))
        archive_btn = QPushButton("🗃 Архив")
        archive_btn.setObjectName("overviewButton")
        archive_btn.setFixedHeight(32)
        archive_btn.setToolTip("Открыть подробный архив скачиваний")
        archive_btn.clicked.connect(self.open_archive_window)
        buttons.addWidget(self.run_button)
        buttons.addWidget(final_btn)
        buttons.addWidget(temp_btn)
        buttons.addWidget(archive_btn)
        buttons.addStretch()
        header_layout.addLayout(buttons)
        layout.addWidget(header_panel)

        content = QHBoxLayout()
        content.setSpacing(10)

        media_panel = QWidget()
        media_panel.setObjectName("overviewMediaPanel")
        media_layout = QVBoxLayout(media_panel)
        media_layout.setContentsMargins(10, 10, 10, 10)
        media_layout.setSpacing(8)
        self.overview_program_title_label = QLabel(APP_NAME)
        self.overview_program_title_label.setObjectName("overviewProgramTitle")
        self.overview_program_title_label.setAlignment(Qt.AlignCenter)
        self.overview_program_title_label.setFixedHeight(24)
        self.overview_main_image = QLabel()
        self.overview_main_image.setObjectName("overviewMainImage")
        self.overview_main_image.setAlignment(Qt.AlignCenter)
        self.overview_main_image.setFixedSize(230, 230)

        media_layout.addWidget(self.overview_program_title_label, 0, Qt.AlignHCenter | Qt.AlignTop)
        media_layout.addSpacing(6)
        media_layout.addWidget(self.overview_main_image, 0, Qt.AlignHCenter | Qt.AlignTop)
        media_layout.addStretch()
        content.addWidget(media_panel, 0)

        activity_panel = QWidget()
        activity_panel.setObjectName("overviewActivityPanel")
        activity_layout = QVBoxLayout(activity_panel)
        activity_layout.setContentsMargins(12, 10, 12, 10)
        activity_layout.setSpacing(7)
        self.overview_activity_label = QLabel()
        self.overview_activity_label.setObjectName("overviewActivityTitle")
        self.overview_activity_label.setTextFormat(Qt.RichText)
        self.overview_activity_label.setAlignment(Qt.AlignCenter)
        self.overview_activity_label.setFixedHeight(34)
        activity_layout.addWidget(self.overview_activity_label)

        status_grid = QGridLayout()
        status_grid.setContentsMargins(0, 2, 0, 2)
        status_grid.setHorizontalSpacing(8)
        status_grid.setVerticalSpacing(5)
        self.overview_channel_label = self._overview_type_status_row(status_grid, 0, "📺", "Канал")
        self.overview_video_status_label = self._overview_type_status_row(status_grid, 1, "🎬", "Видео")
        self.overview_shorts_status_label = self._overview_type_status_row(status_grid, 2, "📱", "Shorts")
        self.overview_streams_status_label = self._overview_type_status_row(status_grid, 3, "🔴", "Трансляция")
        activity_layout.addLayout(status_grid)

        self.overview_events_label = QLabel()
        self.overview_events_label.setObjectName("overviewEvents")
        self.overview_events_label.setTextFormat(Qt.RichText)
        self.overview_events_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.overview_events_label.setMinimumHeight(112)
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

        self.overview_progress_panel = QWidget()
        self.overview_progress_panel.setObjectName("overviewProgressPanel")
        progress_layout = QVBoxLayout(self.overview_progress_panel)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(5)
        self.overview_progress_header_label = QLabel("Прогресс")
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
        right_column.setContentsMargins(0, 0, 0, 0)
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
        name.setFixedHeight(27)
        name.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        status = QLabel()
        status.setObjectName("overviewTypeStatus")
        status.setTextFormat(Qt.RichText)
        status.setFixedHeight(27)
        status.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        grid.addWidget(name, row, 0)
        grid.addWidget(status, row, 1)
        grid.setRowMinimumHeight(row, 32)
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
        self.video_url_input.textChanged.connect(self.schedule_video_preview)
        self.add_video_button = QPushButton("Добавить в очередь")
        self.add_video_button.setFixedHeight(30)
        self.add_video_button.setToolTip("Добавить указанное YouTube-видео в очередь скачивания")
        self.add_video_button.setEnabled(False)
        self.add_video_button.clicked.connect(self.add_video_to_queue)
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
        limits_row.setSpacing(4)
        limits_font = QFont(self.font())
        limits_font.setPointSize(max(8, limits_font.pointSize() - 2))
        limits_title = QLabel("🔢Лимиты:")
        limits_title.setFixedWidth(80)
        limits_title.setFont(limits_font)
        limits_title.setToolTip("Сколько последних элементов проверять на каждом канале")
        limits_row.addWidget(limits_title)
        for label_text, spin, label_width in (
            ("🎬Видео", self.videos_limit_spin, 64),
            ("📱Shorts", self.shorts_limit_spin, 66),
            ("🔴Трансляции", self.streams_limit_spin, 136),
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
        if self.launcher.is_windows:
            self.download_engine_combo.setToolTip("Windows-сборка использует только переносимый Python-движок")
            self.download_engine_combo.addItem("Python (Windows)", "python")
            self.download_engine_combo.setEnabled(False)
        else:
            self.download_engine_combo.setToolTip("Bash - стабильный Linux-скрипт; Python - переносимый движок для тестов")
            self.download_engine_combo.addItem("Bash (Linux, стабильный)", "bash")
            self.download_engine_combo.addItem("Python (тестовый)", "python")
        engine_row.addWidget(QLabel("🧩 Движок"))
        engine_row.addWidget(self.download_engine_combo, 1)
        download_layout.addLayout(engine_row)

        options_row = QHBoxLayout()
        options_row.setSpacing(8)
        self.cleanup_temp_check = QCheckBox("🧹 Врем.")
        self.cleanup_temp_check.setToolTip("Очищать временную папку после успешной обработки")
        self.retry_queue_check = QCheckBox("🔁 Очередь")
        self.retry_queue_check.setToolTip("Возвращать неудачные ссылки обратно в очередь для повтора")
        self.autostart_check = QCheckBox("🚀 Автозапуск")
        self.autostart_check.setToolTip(f"Запускать {APP_NAME} при входе в систему")
        self.log_keep_spin = self._limit_spin(1, 50)
        self.log_keep_spin.setToolTip("Сколько архивных логов хранить")
        options_row.addWidget(self.cleanup_temp_check)
        options_row.addWidget(self.retry_queue_check)
        options_row.addWidget(self.autostart_check)
        options_row.addWidget(QLabel("📝 Логов"))
        options_row.addWidget(self.log_keep_spin)
        rules_btn = QPushButton("⚖")
        rules_btn.setFixedSize(34, 28)
        rules_btn.setToolTip("Открыть правила использования и сведения о внешних компонентах")
        rules_btn.clicked.connect(self.open_usage_rules)
        options_row.addWidget(rules_btn)
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
        })
        self.save_ui_settings()
        self.launcher.app_settings = dict(self.ui_settings)
        self.launcher.apply_runtime_settings(self.launcher.app_settings)
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
                QLabel#overviewActivityTitle {
                    background: #f2f5f8;
                    color: #17202a;
                    border: 1px solid #d7dfe7;
                    border-radius: 4px;
                    padding: 0 8px;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 18px;
                    font-weight: bold;
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
                    padding: 7px;
                }
                QLabel#overviewMainImage, QLabel#overviewVideoImage {
                    background: #ffffff;
                    border: 1px solid #b9c3cc;
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
            self.thumbnail_label.setStyleSheet("border: 1px solid #b9c3cc; background: #ffffff; color: #5c6670;")
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
                QLabel#overviewActivityTitle {
                    background: #151a20;
                    color: #f0f4f8;
                    border: 1px solid #303844;
                    border-radius: 4px;
                    padding: 0 8px;
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 18px;
                    font-weight: bold;
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
                    padding: 7px;
                }
                QLabel#overviewMainImage, QLabel#overviewVideoImage {
                    background: #101317;
                    border: 1px solid #3a4350;
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
            self.thumbnail_label.setStyleSheet("border: 1px solid #3a4350; background: #101317; color: #aeb8c2;")

        if self.archive_window is not None:
            self.archive_window.setStyleSheet(self.styleSheet())

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
        return html.escape(str(text), quote=False)

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

        state_text = self._overview_state_text(state)
        self.overview_channels_label.setText(f"{self._emoji_html('📺')} Каналов: {channels_count}")
        self.overview_queue_label.setText(f"{self._emoji_html('📥')} Очередь: {queue_count}")
        self.overview_archive_label.setText(f"{self._emoji_html('🗃')} Архив: {archive_count}")
        self.overview_last_download_label.setText(
            f"{self._emoji_html('⏱')} Последнее: {self._html_text(self._last_download_text(status_info))}"
        )
        self.overview_temp_label.setText(
            f"{self._emoji_html('⌛')} Врем.: {temp_count}  {self._emoji_html('⚠')} Недокаченных: {part_count}"
        )

        if self.launcher.is_running and stop_requested:
            self.run_button.setText("⏹ Останавливается")
            self.run_button.setToolTip("Остановка уже запрошена; скрипт завершится на безопасном шаге")
            self.run_button.setEnabled(False)
        elif self.launcher.is_running:
            self.run_button.setText("⏹ Остановить")
            self.run_button.setToolTip("Мягко остановить скачивание после текущего безопасного шага")
            self.run_button.setEnabled(True)
        else:
            self.run_button.setText("⏬ Скачать")
            self.run_button.setToolTip("Запустить проверку очереди и каналов")
            self.run_button.setEnabled(True)

        channel_url = status_info.get("channel_url") or ""
        channel_name = self._channel_display_name(channel_url, status_info.get("channel_name") or "")
        if self.launcher.is_running and channel_url:
            channel_image = self.channel_cache_path(channel_url).with_suffix(".jpg")
            main_image = channel_image if channel_image.exists() else self.launcher.overview_logo_path
        else:
            main_image = self.launcher.overview_logo_path
        self._set_label_image(self.overview_main_image, main_image, channel_name or "YT")

        thumb_path = None
        if self.launcher.is_running and state == "downloading":
            thumb_path = self._current_video_thumbnail_path(status_info)
        if not thumb_path and self.launcher.video_placeholder_path.exists():
            thumb_path = self.launcher.video_placeholder_path
        if thumb_path:
            self.overview_video_image.show()
            self._set_label_image(self.overview_video_image, thumb_path, "YT")
        else:
            self.overview_video_image.hide()

        self.overview_activity_label.setText(state_text)
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
        else:
            self.overview_download_title_label.show()
            self.overview_download_title_label.setText("Ожидаем скачивания")
            self.overview_download_title_label.setToolTip("")

        self._refresh_overview_progress(status_info, state)
        self.overview_events_label.setText(self._recent_events_html())

    def _overview_state_text(self, state: str):
        return {
            "sleep": f"{self._emoji_html('😴')} Сон",
            "searching": f"{self._emoji_html('🔎')} Идет поиск",
            "downloading": f"{self._emoji_html('⬇️')} Идет скачивание",
            "stopping": f"{self._emoji_html('⏹')} Остановка",
            "stopped": f"{self._emoji_html('⏹')} Остановлено",
        }.get(state, f"{self._emoji_html('😴')} Сон")

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
        percent_text = str(status_info.get("download_percent") or "").replace(",", ".").strip()
        try:
            percent = max(0.0, min(100.0, float(percent_text)))
        except (TypeError, ValueError):
            percent = None

        if state == "downloading" and percent is not None:
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
        elif state == "downloading":
            self.overview_progress_bar.setValue(0)
            self.overview_progress_detail_label.setText("Ожидаю данные прогресса от yt-dlp")
        else:
            self.overview_progress_bar.setValue(0)
            self.overview_progress_detail_label.setText("Прогресс появится во время скачивания")

    def _recent_events_html(self, limit: int = 6):
        try:
            lines = self.launcher.log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            lines = []

        events = []
        for line in reversed(lines):
            text = line.strip()
            if not text or text.startswith("[download]"):
                continue
            events.append(text)
            if len(events) >= limit:
                break
        if not events:
            return self._html_text("Событий пока нет")
        return "<br>".join(self._html_text(line) for line in reversed(events))

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
                self.launcher.yt_dlp_command() + ["--dump-single-json", "--skip-download", "--flat-playlist", "--playlist-items", "1", metadata_url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
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

    def schedule_video_preview(self):
        self.current_preview = {}
        self.video_status_label.setText("")
        self.video_uploader_label.setText("")
        self.thumbnail_label.setPixmap(QPixmap())
        self.thumbnail_label.setText("Обложка")
        text = self.video_url_input.text().strip()
        self.add_video_button.setEnabled(self._looks_like_youtube_url(text))
        if not text:
            self.video_title_label.setText("Введите адрес YouTube-видео")
            return
        if not self._looks_like_youtube_url(text):
            self.video_title_label.setText("Введите ссылку на YouTube-видео")
            return
        self.video_title_label.setText("Загрузка данных...")
        self.preview_timer.start(800)

    def fetch_video_preview(self):
        url = self.video_url_input.text().strip()
        if not self._looks_like_youtube_url(url):
            self.video_title_label.setText("Введите ссылку на YouTube-видео")
            self.video_status_label.setText("")
            return

        self.preview_request_id += 1
        request_id = self.preview_request_id
        self.video_status_label.setText("Читаю название и обложку...")

        thread = threading.Thread(target=self._metadata_worker, args=(request_id, url), daemon=True)
        thread.start()

    def _metadata_worker(self, request_id: int, url: str):
        try:
            result = subprocess.run(
                self.launcher.yt_dlp_command() + ["--dump-single-json", "--no-playlist", "--skip-download", url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
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
                thumbnail_path = f"/tmp/ytd_preview_{request_id}.jpg"
                try:
                    urllib.request.urlretrieve(thumbnail_url, thumbnail_path)
                except Exception:
                    thumbnail_path = ""

            self.metadata_loaded.emit({
                "request_id": request_id,
                "url": data.get("webpage_url") or url,
                "video_id": data.get("id") or self.youtube_video_id_from_url(url),
                "title": data.get("title") or "Без названия",
                "uploader": data.get("uploader") or "",
                "thumbnail_path": thumbnail_path,
            })
        except Exception as e:
            self.metadata_failed.emit(request_id, str(e))

    def on_metadata_loaded(self, info: dict):
        if info.get("request_id") != self.preview_request_id:
            return
        self.current_preview = info
        self.video_title_label.setText(info.get("title", "Без названия"))
        uploader = info.get("uploader") or ""
        self.video_uploader_label.setText(f"Канал: {uploader}" if uploader else "")
        self.video_status_label.setText("Готово к добавлению в очередь")
        self.add_video_button.setEnabled(True)

        thumbnail_path = info.get("thumbnail_path")
        if thumbnail_path:
            pixmap = QPixmap(thumbnail_path)
            if not pixmap.isNull():
                self.thumbnail_label.setText("")
                self.thumbnail_label.setPixmap(pixmap.scaled(self.thumbnail_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def on_metadata_failed(self, request_id: int, message: str):
        if request_id != self.preview_request_id:
            return
        self.current_preview = {}
        self.add_video_button.setEnabled(self._looks_like_youtube_url(self.video_url_input.text().strip()))
        self.video_title_label.setText("Не удалось прочитать видео")
        self.video_status_label.setText(f"{message}\nМожно добавить ссылку в очередь без предпросмотра.")

    def add_video_to_queue(self):
        url = (self.current_preview.get("url") or self.video_url_input.text()).strip()
        if not self._looks_like_youtube_url(url):
            QMessageBox.warning(self, "Очередь", "Нужна ссылка на YouTube-видео")
            return

        video_id = (self.current_preview.get("video_id") or self.youtube_video_id_from_url(url)).strip()
        if video_id and self.archive_contains_video(video_id):
            QMessageBox.information(self, "Очередь", "Это видео уже есть в архиве")
            self.video_status_label.setText("Видео уже есть в архиве")
            return

        queued = self._read_queue()
        queued_ids = {self.youtube_video_id_from_url(item) for item in queued}
        if url in queued or (video_id and video_id in queued_ids):
            QMessageBox.information(self, "Очередь", "Это видео уже есть в очереди")
            return

        try:
            self.launcher.queue_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.launcher.queue_file, "a", encoding="utf-8") as f:
                f.write(url + "\n")
            self.video_status_label.setText("Добавлено в очередь")
            self.refresh_queue()
            self.refresh_overview()
        except Exception as e:
            QMessageBox.warning(self, "Очередь", str(e))

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
                for line in self.launcher.archive_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if video_id in line.split():
                        return True
        except Exception:
            pass
        try:
            if self.launcher.archive_details_file.exists():
                needle = f'"video_id":"{video_id}"'
                for line in self.launcher.archive_details_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if needle in line.replace(" ", ""):
                        return True
        except Exception:
            pass
        return False

    def _count_lines(self, path: Path, skip_comments: bool = False):
        if not path.exists():
            return 0
        count = 0
        for line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
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
        data = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(data[-lines:])

    def _last_interesting_line(self, path: Path):
        if not path or not path.exists():
            return "нет"
        interesting = ("Найдено", "Новых видео", "Отправлено", "Не отправлено", "Видео перемещено", "Жатва завершена")
        for line in reversed(path.read_text(encoding="utf-8", errors="ignore").splitlines()):
            if any(marker in line for marker in interesting):
                return line.strip()
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
                    reconfigure(errors="replace")
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
    if len(sys.argv) >= 2 and sys.argv[1] == "--run-yt-dlp":
        raise SystemExit(run_yt_dlp_helper(sys.argv[2:]))

    if len(sys.argv) >= 3 and sys.argv[1] == "--run-script":
        raise SystemExit(run_python_script_helper(sys.argv[2], sys.argv[3:]))

    launcher = TrayLauncher()
    launcher.run()
