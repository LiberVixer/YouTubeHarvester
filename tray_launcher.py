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
from pathlib import Path
import urllib.request
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
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QFont, QPen, QDesktopServices, QTextCursor, QPalette
from PyQt5.QtCore import Qt, QTimer, QTime, QDate, QUrl, pyqtSignal
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
    ("shorts", "📱", "Шортсы"),
    ("streams", "🔴", "Стримы"),
)


class TrayLauncher:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.app_dir = Path(os.environ.get("YTD_APP_DIR", Path(__file__).resolve().parent))
        self.data_dir = Path(os.environ.get("YTD_DATA_DIR", self.app_dir))
        self.config_dir = Path(os.environ.get("YTD_CONFIG_DIR", self.data_dir))
        self.cache_dir = Path(os.environ.get("YTD_CACHE_DIR", Path.home() / ".cache" / "YTD"))

        self.script_path = Path(os.environ.get("YTD_SCRIPT_PATH", self.app_dir / "run_download.sh"))
        self.app_icon_path = Path(os.environ.get("YTD_APP_ICON", self.app_dir / "assets" / "yt-harvester.png"))
        self.channels_file = Path(os.environ.get("YTD_CHANNELS_FILE", self.data_dir / "channels.txt"))
        self.queue_file = Path(os.environ.get("YTD_QUEUE_FILE", self.data_dir / "queue.txt"))
        self.archive_file = Path(os.environ.get("YTD_ARCHIVE_FILE", self.data_dir / "yt_archive.txt"))
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

        self.schedules_file = Path(os.environ.get("YTD_SCHEDULES_FILE", Path.home() / ".config" / "YTD" / "schedules.json"))
        self.settings_file = Path(os.environ.get("YTD_SETTINGS_FILE", Path.home() / ".config" / "YTD" / "settings.json"))
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
        window_action = menu.addAction("Открыть окно")
        window_action.triggered.connect(self.open_main_window)
        run_action = menu.addAction("▶ Запустить загрузку")
        run_action.triggered.connect(self.run_script)
        exit_action = menu.addAction("✕ Выход")
        exit_action.triggered.connect(self.app.quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_clicked)

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

    def default_download_dir(self):
        return Path.home() / "Downloads" / "YouTubeHarvester"

    def default_temp_dir(self):
        return Path.home() / "temp" / "YTH"

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
        resolution = str(settings.get("max_resolution") or os.environ.get("YTD_MAX_RESOLUTION") or "1080").strip()
        self.max_resolution = resolution if resolution in {"480", "720", "1080", "1440", "2160", "best"} else "1080"

    def script_environment(self):
        env = os.environ.copy()
        env.update({
            "YTD_APP_DIR": str(self.app_dir),
            "YTD_DATA_DIR": str(self.data_dir),
            "YTD_CONFIG_DIR": str(self.config_dir),
            "YTD_CACHE_DIR": str(self.cache_dir),
            "YTD_ENV_FILE": str(self.env_file),
            "YTD_CHANNEL_RULES_FILE": str(self.channel_rules_file),
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
        })
        return env

    def run_script(self):
        if self.is_running:
            self.show_notification("⚠️", "Скрипт уже запущен", "Подождите завершения...")
            return

        try:
            self.stop_file.unlink(missing_ok=True)
        except Exception:
            pass

        self.is_running = True
        self.state = "running"
        self.update_icon()
        self.show_notification("▶️", "Загрузка началась", "Скрипт запущен...")

        thread = threading.Thread(target=self._execute_script, daemon=True)
        thread.start()

    def _execute_script(self):
        proc = None
        try:
            proc = subprocess.Popen(
                ["bash", str(self.script_path)],
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

    def request_stop(self):
        if not self.is_running:
            return
        try:
            self.stop_file.write_text(str(int(time.time())) + "\n", encoding="utf-8")
            self.state = "stopping"
            self.update_icon()
            self.show_notification("⏹", "Остановка", "Скрипт завершится после текущего безопасного шага")
        except Exception as e:
            self.show_notification("❌", "Не удалось остановить", str(e)[:200])

    def update_icon(self):
        # Проверка приоритетной иконки
        part_files = glob.glob(str(self.temp_dir / "*.part"))
        if part_files:
            icon = self.create_colored_icon((40, 180, 40), rect=True)  # зелёный круг с прямоугольником
            tooltip = "YT Harvester - есть загрузки .part"
        else:
            if self.state == "stopping":
                icon = self.create_colored_icon((230, 150, 40), rect=True)
                tooltip = "YT Harvester - останавливается"
            elif self.state == "running":
                icon = self.create_colored_icon((220, 53, 69), rect=True)  # красный круг с прямоугольником
                tooltip = "YT Harvester - РАБОТАЕТ"
            else:
                icon = self.create_colored_icon((120, 120, 120), rect=False)  # серый круг Zzz
                tooltip = "YT Harvester - спит"

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


class MainWindow(QMainWindow):
    metadata_loaded = pyqtSignal(dict)
    metadata_failed = pyqtSignal(int, str)
    channel_metadata_loaded = pyqtSignal(dict)

    def __init__(self, launcher: TrayLauncher):
        super().__init__()
        self.launcher = launcher
        self.setWindowTitle("YT Harvester")
        self.setFixedSize(900, 620)
        if self.launcher.app_icon_path.exists():
            self.setWindowIcon(QIcon(str(self.launcher.app_icon_path)))
        self.preview_request_id = 0
        self.current_preview = {}
        self.ui_settings = self.load_ui_settings()
        self.theme = self.ui_settings.get("theme", "dark")
        if self.theme not in {"dark", "light", "system"}:
            self.theme = "dark"
        self.channel_cards = {}
        self.channel_cache_dir = self.launcher.cache_dir / "channels"
        self.channel_rules = {}

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

        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.refresh_log_view)
        self.log_timer.start(5000)
        self.system_theme_timer = QTimer(self)
        self.system_theme_timer.timeout.connect(self.refresh_system_theme)
        self.system_theme_timer.start(30000)
        self.apply_theme()

    def _build_overview_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(8)

        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        self.overview_status_label = QLabel()
        self.overview_channels_label = QLabel()
        self.overview_queue_label = QLabel()
        self.overview_archive_label = QLabel()
        self.overview_last_download_label = QLabel()
        self.overview_temp_label = QLabel()
        for label in (
            self.overview_status_label,
            self.overview_channels_label,
            self.overview_queue_label,
            self.overview_archive_label,
            self.overview_last_download_label,
            self.overview_temp_label,
        ):
            label.setObjectName("overviewMetric")
            label.setTextFormat(Qt.RichText)
            label.setWordWrap(False)
            metrics.addWidget(label)
        metrics.addStretch()
        layout.addLayout(metrics)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.run_button = QPushButton("⏬ Скачать")
        self.run_button.setObjectName("overviewButton")
        self.run_button.setFixedHeight(32)
        self.run_button.clicked.connect(self.toggle_download)
        final_btn = QPushButton("📁 ПАПКА")
        final_btn.setObjectName("overviewButton")
        final_btn.setFixedHeight(32)
        final_btn.clicked.connect(lambda: self.open_folder(self.launcher.final_dir))
        temp_btn = QPushButton("⌛ TEMP")
        temp_btn.setObjectName("overviewButton")
        temp_btn.setFixedHeight(32)
        temp_btn.clicked.connect(lambda: self.open_folder(self.launcher.temp_dir))
        buttons.addWidget(self.run_button)
        buttons.addWidget(final_btn)
        buttons.addWidget(temp_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        content = QGridLayout()
        content.setHorizontalSpacing(14)
        content.setVerticalSpacing(8)
        self.overview_main_image = QLabel()
        self.overview_main_image.setObjectName("overviewMainImage")
        self.overview_main_image.setAlignment(Qt.AlignCenter)
        self.overview_main_image.setFixedSize(200, 200)

        self.overview_video_image = QLabel()
        self.overview_video_image.setObjectName("overviewVideoImage")
        self.overview_video_image.setAlignment(Qt.AlignCenter)
        self.overview_video_image.setFixedSize(200, 112)
        self.overview_video_image.hide()

        content.addWidget(self.overview_main_image, 0, 0, Qt.AlignTop)
        content.addWidget(self.overview_video_image, 1, 0, Qt.AlignTop)
        state_column = QVBoxLayout()
        state_column.setContentsMargins(0, 0, 0, 0)
        state_column.setSpacing(8)
        self.overview_activity_label = QLabel()
        self.overview_channel_label = QLabel()
        self.overview_video_status_label = QLabel()
        self.overview_shorts_status_label = QLabel()
        self.overview_streams_status_label = QLabel()
        self.overview_download_title_label = QLabel()
        self.overview_download_title_label.setWordWrap(True)
        for label in (
            self.overview_activity_label,
            self.overview_channel_label,
            self.overview_video_status_label,
            self.overview_shorts_status_label,
            self.overview_streams_status_label,
        ):
            label.setObjectName("overviewLine")
            label.setTextFormat(Qt.RichText)
            label.setMinimumHeight(22)
            state_column.addWidget(label)
        state_column.addStretch()
        content.addLayout(state_column, 0, 1)

        self.overview_download_title_label.setObjectName("overviewLine")
        self.overview_download_title_label.setTextFormat(Qt.RichText)
        self.overview_download_title_label.setMinimumHeight(22)
        content.addWidget(self.overview_download_title_label, 1, 1, Qt.AlignTop)
        content.setColumnStretch(1, 1)
        content.setRowStretch(2, 1)

        layout.addLayout(content, 1)

        self.tabs.addTab(tab, "Обзор")

    def _build_channels_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 10, 16, 16)

        self.channels_scroll = QScrollArea()
        self.channels_scroll.setWidgetResizable(True)
        self.channels_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.channels_scroll.setFrameShape(QScrollArea.NoFrame)
        self.channels_content = QWidget()
        self.channels_grid = QGridLayout(self.channels_content)
        self.channels_grid.setContentsMargins(0, 0, 0, 0)
        self.channels_grid.setHorizontalSpacing(12)
        self.channels_grid.setVerticalSpacing(18)
        self.channels_scroll.setWidget(self.channels_content)
        layout.addWidget(self.channels_scroll)

        self.tabs.addTab(tab, "Каналы")

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
        self.schedule_enabled_check.setChecked(True)
        add_btn = QPushButton("Добавить")
        add_btn.setFixedHeight(30)
        add_btn.clicked.connect(self.add_schedule)
        toggle_btn = QPushButton("Вкл / выкл")
        toggle_btn.setFixedHeight(30)
        toggle_btn.clicked.connect(self.toggle_selected_schedule)
        remove_btn = QPushButton("Удалить")
        remove_btn.setFixedHeight(30)
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
        remove_btn.clicked.connect(self.remove_selected_queued_video)
        reload_btn = QPushButton("Перечитать очередь")
        reload_btn.setFixedHeight(30)
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

        self.tabs.addTab(tab, "Очередь")

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
        download_layout.addLayout(self._path_setting_row(
            "📁 Папка",
            self.download_dir_input,
            lambda: self.choose_directory(self.download_dir_input),
        ))

        self.temp_dir_input = QLineEdit()
        download_layout.addLayout(self._path_setting_row(
            "⌛ TEMP",
            self.temp_dir_input,
            lambda: self.choose_directory(self.temp_dir_input),
        ))

        limits_row = QHBoxLayout()
        limits_row.setSpacing(6)
        self.videos_limit_spin = self._limit_spin()
        self.shorts_limit_spin = self._limit_spin()
        self.streams_limit_spin = self._limit_spin()
        for label_text, spin in (
            ("🎬", self.videos_limit_spin),
            ("📱", self.shorts_limit_spin),
            ("🔴", self.streams_limit_spin),
        ):
            limits_row.addWidget(QLabel(label_text))
            limits_row.addWidget(spin)
        limits_row.addStretch()
        download_layout.addLayout(limits_row)

        resolution_row = QHBoxLayout()
        resolution_row.setSpacing(8)
        self.resolution_combo = QComboBox()
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

        options_row = QHBoxLayout()
        options_row.setSpacing(8)
        self.cleanup_temp_check = QCheckBox("🧹 TEMP")
        self.retry_queue_check = QCheckBox("🔁 Очередь")
        self.autostart_check = QCheckBox("🚀 Старт")
        self.log_keep_spin = self._limit_spin(1, 50)
        options_row.addWidget(self.cleanup_temp_check)
        options_row.addWidget(self.retry_queue_check)
        options_row.addWidget(self.autostart_check)
        options_row.addWidget(QLabel("📝 Логов"))
        options_row.addWidget(self.log_keep_spin)
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
        self.telegram_enabled_check = QCheckBox("🔔 Включено")
        telegram_header.addWidget(telegram_title)
        telegram_header.addStretch()
        telegram_header.addWidget(self.telegram_enabled_check)
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
        save_btn.clicked.connect(self.save_settings_from_ui)
        open_env_btn = QPushButton("Открыть .env")
        open_env_btn.setFixedHeight(30)
        open_env_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.launcher.env_file))))
        save_row.addWidget(save_btn)
        save_row.addWidget(open_env_btn)
        save_row.addStretch()
        telegram_layout.addLayout(save_row)

        settings_row.addWidget(download_panel, 3)
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
        refresh_btn.clicked.connect(self.refresh_logs)
        reload_btn = QPushButton("Перечитать лог")
        reload_btn.setFixedHeight(30)
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

        self.tabs.addTab(tab, "Настройки")

    def _limit_spin(self, minimum: int = 1, maximum: int = 100):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setFixedWidth(62)
        return spin

    def _path_setting_row(self, label_text: str, line_edit: QLineEdit, callback):
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(label_text)
        label.setFixedWidth(82)
        button = QPushButton("...")
        button.setFixedSize(34, 30)
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
        button.setToolTip("Показать / скрыть")
        button.clicked.connect(lambda checked=False, field=line_edit: self.toggle_secret_visibility(field, checked))
        return line_edit, button

    def _secret_setting_row(self, label_text: str, line_edit: QLineEdit, eye_button: QPushButton):
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(label_text)
        label.setFixedWidth(104)
        row.addWidget(label)
        row.addWidget(line_edit, 1)
        row.addWidget(eye_button)
        return row

    def toggle_secret_visibility(self, field: QLineEdit, visible: bool):
        field.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)

    def choose_directory(self, field: QLineEdit):
        current = field.text().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Выбрать папку", current)
        if selected:
            field.setText(selected)

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
        self.telegram_enabled_check.setChecked(self.launcher.telegram_enabled)
        self.autostart_check.setChecked(self.is_autostart_enabled())

        resolution_index = self.resolution_combo.findData(self.launcher.max_resolution)
        self.resolution_combo.setCurrentIndex(resolution_index if resolution_index >= 0 else 2)

        self.bot_token_input.setText(env_values.get("BOT_TOKEN", ""))
        self.channel_id_input.setText(env_values.get("CHANNEL_ID", ""))
        self.proxy_url_input.setText(env_values.get("PROXY_URL", ""))

    def save_settings_from_ui(self):
        self.ui_settings.update({
            "download_dir": self.download_dir_input.text().strip() or str(self.launcher.default_download_dir()),
            "temp_dir": self.temp_dir_input.text().strip() or str(self.launcher.default_temp_dir()),
            "videos_limit": int(self.videos_limit_spin.value()),
            "shorts_limit": int(self.shorts_limit_spin.value()),
            "streams_limit": int(self.streams_limit_spin.value()),
            "max_resolution": self.resolution_combo.currentData() or "1080",
            "log_keep_count": int(self.log_keep_spin.value()),
            "cleanup_temp": self.cleanup_temp_check.isChecked(),
            "retry_failed_queue": self.retry_queue_check.isChecked(),
            "telegram_enabled": self.telegram_enabled_check.isChecked(),
        })
        self.save_ui_settings()
        self.launcher.app_settings = dict(self.ui_settings)
        self.launcher.apply_runtime_settings(self.launcher.app_settings)
        self.launcher.temp_dir.mkdir(parents=True, exist_ok=True)
        self.launcher.final_dir.mkdir(parents=True, exist_ok=True)
        self.write_env_values({
            "TELEGRAM_ENABLED": "1" if self.telegram_enabled_check.isChecked() else "0",
            "BOT_TOKEN": self.bot_token_input.text(),
            "CHANNEL_ID": self.channel_id_input.text(),
            "PROXY_URL": self.proxy_url_input.text(),
        })
        self.set_autostart_enabled(self.autostart_check.isChecked())
        self.refresh_overview()
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
                "# Telegram settings for YT Harvester.",
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
        return self.autostart_file().exists()

    def set_autostart_enabled(self, enabled: bool):
        path = self.autostart_file()
        try:
            if enabled:
                path.parent.mkdir(parents=True, exist_ok=True)
                exec_path = Path("/usr/bin/yt-harvester")
                exec_line = "yt-harvester" if exec_path.exists() else str(self.launcher.app_dir / "start_tray.sh")
                path.write_text(
                    "[Desktop Entry]\n"
                    "Type=Application\n"
                    "Name=YT Harvester\n"
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

    def refresh_all(self):
        self.refresh_overview()
        self.refresh_channels()
        self.refresh_schedules()
        self.refresh_queue()
        self.refresh_logs()

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
                QLabel#overviewMainImage, QLabel#overviewVideoImage {
                    background: #ffffff;
                    border: 1px solid #b9c3cc;
                }
                QLabel#queueArt {
                    background: transparent;
                    border: none;
                }
                QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QComboBox, QSpinBox {
                    background: #ffffff;
                    alternate-background-color: #f2f5f8;
                    color: #17202a;
                    border: 1px solid #b9c3cc;
                    selection-background-color: #2d7dd2;
                    selection-color: #ffffff;
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
                QLabel#overviewMainImage, QLabel#overviewVideoImage {
                    background: #101317;
                    border: 1px solid #3a4350;
                }
                QLabel#queueArt {
                    background: transparent;
                    border: none;
                }
                QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QComboBox, QSpinBox {
                    background: #101317;
                    alternate-background-color: #151a20;
                    color: #e8edf2;
                    border: 1px solid #3a4350;
                    selection-background-color: #2d7dd2;
                    selection-color: #ffffff;
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

    def effective_theme(self):
        if self.theme != "system":
            return self.theme
        detected = self.detect_system_theme()
        if detected:
            return detected
        window_color = QApplication.palette().color(QPalette.Window)
        return "dark" if window_color.lightness() < 128 else "light"

    def detect_system_theme(self):
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
        archive_count = self._count_lines(self.launcher.archive_file)

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
        self.overview_status_label.setText(f"Статус: {self._overview_header_state_text(state)}")
        self.overview_channels_label.setText(f"Каналов: {channels_count}")
        self.overview_queue_label.setText(f"В очереди: {queue_count}")
        self.overview_archive_label.setText(f"В архиве: {archive_count}")
        self.overview_last_download_label.setText(f"Скачивали: {self._last_download_text(status_info)}")
        self.overview_temp_label.setText(f"Временных: {temp_count}, Недокаченных: {part_count}")

        if self.launcher.is_running and stop_requested:
            self.run_button.setText("⏹ Останавливается")
            self.run_button.setEnabled(False)
        elif self.launcher.is_running:
            self.run_button.setText("⏹ Остановить")
            self.run_button.setEnabled(True)
        else:
            self.run_button.setText("⏬ Скачать")
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
            self.overview_channel_label.setText(f"{self._emoji_html('📺')} Канал: {self._html_text(channel_name)}")
        else:
            self.overview_channel_label.setText(f"{self._emoji_html('📺')} Канал: -")
        self.overview_video_status_label.setText(
            f"{self._emoji_html('🎬')} Видео: {self._type_status_text(status_info.get('videos_status'))}"
        )
        self.overview_shorts_status_label.setText(
            f"{self._emoji_html('📱')} Shorts: {self._type_status_text(status_info.get('shorts_status'))}"
        )
        self.overview_streams_status_label.setText(
            f"{self._emoji_html('🔴')} Stream: {self._type_status_text(status_info.get('streams_status'))}"
        )

        title = (status_info.get("video_title") or "").strip()
        if self.launcher.is_running and state == "downloading" and title:
            self.overview_download_title_label.show()
            self.overview_download_title_label.setText(f"Скачивается видео: {self._html_text(title)}")
        else:
            self.overview_download_title_label.setText("")
            self.overview_download_title_label.hide()

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

    def _last_download_text(self, status_info: dict):
        value = str(status_info.get("last_download_at") or "").strip()
        if not value and self.launcher.last_download_file.exists():
            try:
                value = self.launcher.last_download_file.read_text(encoding="utf-8").strip()
            except Exception:
                value = ""
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            timestamp = self._latest_final_video_timestamp()
        if not timestamp:
            return "нет"
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
            if os.environ.get("YTD_SKIP_CHANNEL_METADATA") != "1" and not self.channel_cache_complete(channel):
                thread = threading.Thread(target=self._channel_metadata_worker, args=(channel,), daemon=True)
                thread.start()

        plus_row = len(channels) // 4
        plus_col = len(channels) % 4
        self.channels_grid.addWidget(self.create_add_channel_card(), plus_row, plus_col)

        total_rows = ((len(channels) + 1) + 3) // 4
        for row in range(total_rows):
            self.channels_grid.setRowMinimumHeight(row, 276)
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

    def remove_channel(self, channel: str):
        channels = [item for item in self._read_channels() if item != channel]
        self.save_channel_urls(channels)
        key = self.normalize_channel_key(channel)
        if key in self.channel_rules:
            self.channel_rules.pop(key, None)
            self.save_channel_rules()
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

    def create_channel_card(self, channel: str):
        card = QWidget()
        card.setFixedSize(190, 264)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

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
        for idx, (type_name, emoji, label) in enumerate(CHANNEL_TYPE_BUTTONS):
            type_btn = QPushButton(emoji, image_box)
            type_btn.setCheckable(True)
            type_btn.setChecked(rules.get(type_name, True))
            type_btn.setGeometry(156, 38 + idx * 34, 30, 30)
            type_btn.setToolTip(f"{label}: включить / отключить скачивание")
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

        title = QLabel(self.channel_title_from_url(channel))
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setFixedHeight(58)
        font = QFont("Serif")
        font.setPointSize(12)
        font.setBold(True)
        title.setFont(font)

        layout.addWidget(image_box)
        layout.addWidget(title)

        card.image_label = image
        card.title_label = title
        return card

    def create_add_channel_card(self):
        card = QWidget()
        card.setFixedSize(190, 264)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

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
        title.setFixedHeight(58)
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
                card.title_label.setText(meta.get("title") or self.channel_title_from_url(channel))
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
                ["yt-dlp", "--dump-single-json", "--skip-download", "--flat-playlist", "--playlist-items", "1", metadata_url],
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
                ["yt-dlp", "--dump-single-json", "--no-playlist", "--skip-download", url],
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

        queued = self._read_queue()
        if url in queued:
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
        interesting = ("Найдено", "Новых видео", "Отправлено", "Не отправлено", "Видео перемещено", "ЖАТВА ЗАВЕРШЕНА")
        for line in reversed(path.read_text(encoding="utf-8", errors="ignore").splitlines()):
            if any(marker in line for marker in interesting):
                return line.strip()
        return "нет"


if __name__ == "__main__":
    launcher = TrayLauncher()
    launcher.run()
