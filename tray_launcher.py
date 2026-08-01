#!/usr/bin/env python3
"""
Tray launcher для run_download.sh
- Спящий режим (серый круг Zzz) - скрипт не работает
- Красный круг с прямоугольником - скрипт работает
- Зелёный круг с прямоугольником - приоритетная загрузка (файлы .part в папке)
"""

import sys
import contextlib
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
import math
import random
from pathlib import Path
import urllib.request
import html
import tempfile
import platform
import zipfile
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
    QStackedWidget,
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QFont, QPen, QDesktopServices, QTextCursor, QPalette, QKeySequence, QPainterPath, QStandardItem, QStandardItemModel
from PyQt5.QtCore import Qt, QTimer, QTime, QDate, QUrl, QPoint, QSize, QLocale, pyqtSignal, QObject, QEvent, QAbstractNativeEventFilter
try:
    from PyQt5.QtMultimedia import QSoundEffect
except Exception:
    QSoundEffect = None
import json
import glob

from yth_common import (
    SingleInstanceLock,
    archive_entry_file_exists,
    archive_entry_matches_variant,
    extract_video_id,
    fix_mojibake,
    looks_like_youtube_url,
    media_resolution_from_path,
    normalize_text_value,
    read_text_for_display,
    yt_dlp_command as common_yt_dlp_command,
)
from i18n_locales import LOCALE_TRANSLATIONS


class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class EasterAssetBundle:
    MEMBERS = {
        "map": ("r/00", "u00.jpg"),
        "harvester": ("r/01", "u01.png"),
        "crystals": ("r/02", "u02.png"),
        "tree": ("r/03", "u03.png"),
        "victory_logo": ("r/04", "u04.png"),
        "reporting": (("r/10", "s10.wav"), ("r/11", "s11.wav")),
        "acknowledge": (("r/12", "s12.wav"), ("r/13", "s13.wav")),
        "victory_sound": (("r/14", "s14.wav"),),
    }

    def __init__(self, bundle_path, cache_dir):
        self.bundle_path = Path(bundle_path)
        self.cache_dir = Path(cache_dir)

    def file(self, key, fallback_path=None):
        fallback = Path(fallback_path) if fallback_path else None
        if fallback and fallback.is_file():
            return fallback

        record = self.MEMBERS.get(key)
        if isinstance(record, tuple) and record and isinstance(record[0], str):
            bundled = self._extract(record)
            if bundled and bundled.is_file():
                return bundled
        return fallback

    def files(self, key, fallback_paths=()):
        fallbacks = []
        for path in fallback_paths:
            path_obj = Path(path)
            if path_obj.is_file():
                fallbacks.append(path_obj)
        if fallbacks:
            return tuple(fallbacks)

        records = self.MEMBERS.get(key, ())
        resolved = []
        for record in records:
            bundled = self._extract(record)
            if bundled and bundled.is_file():
                resolved.append(bundled)
        return tuple(resolved)

    def _extract(self, record):
        if not self.bundle_path.is_file():
            return None
        member, output_name = record
        target = self.cache_dir / output_name
        tmp_target = target.with_name(f".{target.name}.tmp")
        try:
            bundle_mtime = self.bundle_path.stat().st_mtime
            with zipfile.ZipFile(self.bundle_path, "r") as bundle:
                info = bundle.getinfo(member)
                if (
                    target.is_file()
                    and target.stat().st_size == info.file_size
                    and target.stat().st_mtime >= bundle_mtime
                ):
                    return target
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp_target.write_bytes(bundle.read(member))
                os.replace(tmp_target, target)
                os.utime(target, (bundle_mtime, bundle_mtime))
                return target
        except Exception:
            with contextlib.suppress(Exception):
                tmp_target.unlink()
            return None


class HarvesterEasterEggGame(QWidget):
    finished = pyqtSignal(bool)

    def __init__(
        self,
        parent=None,
        map_path=None,
        harvester_path=None,
        crystal_path=None,
        tree_overlay_path=None,
        reporting_sound_paths=(),
        acknowledge_sound_paths=(),
        victory_sound_paths=(),
        language="en",
    ):
        super().__init__(parent)
        self.setObjectName("harvesterEasterEggGame")
        self.language = normalize_language(language)
        self.setFixedSize(232, 232)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.duration_ms = 15000
        self.archive_x = 25.0
        self.archive_y = 22.0
        self.archive_radius = 32.0
        self.capacity = 3
        self.required_delivered = 5
        self.harvester_x = 184.0
        self.harvester_y = 178.0
        self.destination = None
        self.direction = "NW"
        self.selected = False
        self.cargo = 0
        self.delivered = 0
        self.started_at = time.monotonic()
        self.last_tick = self.started_at
        self.completed = False
        self.game_over = False
        self.status_text = self.tr("easter.select_harvester")
        self.map_pixmap = self._load_pixmap(map_path)
        self.tree_overlay_pixmap = self._load_pixmap(tree_overlay_path)
        self.harvester_sheet = self._load_pixmap(harvester_path)
        self.harvester_frames = self._slice_harvester_frames()
        self.crystal_sheet = self._load_pixmap(crystal_path)
        self.crystal_frames = self._slice_crystal_frames()
        self.reporting_sound_paths = self._valid_sound_paths(reporting_sound_paths)
        self.acknowledge_sound_paths = self._valid_sound_paths(acknowledge_sound_paths)
        self.victory_sound_paths = self._valid_sound_paths(victory_sound_paths)
        self.reporting_sounds = self._load_sound_effects(self.reporting_sound_paths)
        self.acknowledge_sounds = self._load_sound_effects(self.acknowledge_sound_paths)
        self.victory_sounds = self._load_sound_effects(self.victory_sound_paths)
        self.resources = self._make_random_resources()
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def tr(self, key: str, **values) -> str:
        return ui_text(getattr(self, "language", "en"), key, **values)

    def _make_random_resources(self):
        resources = []
        attempts = 0
        while len(resources) < self.required_delivered and attempts < 400:
            attempts += 1
            x = random.uniform(42.0, self.width() - 28.0)
            y = random.uniform(42.0, self.height() - 42.0)
            if math.hypot(x - self.archive_x, y - self.archive_y) < self.archive_radius + 26:
                continue
            if math.hypot(x - self.harvester_x, y - self.harvester_y) < 42:
                continue
            if any(math.hypot(x - item["x"], y - item["y"]) < 33 for item in resources):
                continue
            resources.append({"x": round(x, 1), "y": round(y, 1), "taken": False})
        if len(resources) >= self.required_delivered:
            return resources

        fallback = [
            {"x": 92.0, "y": 58.0, "taken": False},
            {"x": 154.0, "y": 72.0, "taken": False},
            {"x": 195.0, "y": 123.0, "taken": False},
            {"x": 122.0, "y": 143.0, "taken": False},
            {"x": 70.0, "y": 171.0, "taken": False},
        ]
        random.shuffle(fallback)
        return (resources + fallback)[: self.required_delivered]

    def _valid_sound_paths(self, paths):
        valid_paths = []
        for path in paths:
            try:
                path_obj = Path(path)
                if path_obj.is_file():
                    valid_paths.append(path_obj)
            except Exception:
                continue
        return valid_paths

    def _load_pixmap(self, path):
        if not path:
            return QPixmap()
        try:
            pixmap = QPixmap(str(path))
            return pixmap if not pixmap.isNull() else QPixmap()
        except Exception:
            return QPixmap()

    def _load_sound_effects(self, paths):
        if QSoundEffect is None:
            return []
        effects = []
        for path in paths:
            try:
                path_obj = Path(path)
                if not path_obj.is_file():
                    continue
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(str(path_obj)))
                effect.setVolume(0.55)
                effects.append(effect)
            except Exception:
                continue
        return effects

    def _play_random_sound(self, effects, paths):
        sound_path = random.choice(paths) if paths else None
        if sound_path and self._play_sound_file(sound_path):
            return
        if effects:
            random.choice(effects).play()

    def _play_sound_file(self, path: Path):
        try:
            if os.name == "nt":
                import winsound

                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                return True
            players = (
                ("paplay", [str(path)]),
                ("pw-play", [str(path)]),
                ("aplay", [str(path)]),
                ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]),
            )
            for executable, args in players:
                player = shutil.which(executable)
                if not player:
                    continue
                subprocess.Popen(
                    [player, *args],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True
        except Exception:
            return False
        return False

    def _slice_harvester_frames(self):
        if self.harvester_sheet.isNull():
            return {}
        rects = {
            "N": (150, 9, 34, 51),
            "NE": (198, 42, 61, 48),
            "E": (228, 91, 65, 37),
            "SE": (198, 130, 60, 49),
            "S": (151, 161, 32, 52),
            "SW": (77, 129, 60, 50),
            "W": (43, 92, 66, 35),
            "NW": (78, 43, 60, 47),
        }
        frames = {}
        for direction, (x, y, width, height) in rects.items():
            frame = self.harvester_sheet.copy(x, y, width, height)
            if not frame.isNull():
                frames[direction] = frame
        return frames

    def _slice_crystal_frames(self):
        if self.crystal_sheet.isNull():
            return []
        frame_size = 38
        frames = []
        for x in range(0, self.crystal_sheet.width(), frame_size):
            frame = self.crystal_sheet.copy(x, 0, min(frame_size, self.crystal_sheet.width() - x), frame_size)
            if not frame.isNull():
                frames.append(frame)
        return frames

    def time_left_ms(self):
        elapsed = int((time.monotonic() - self.started_at) * 1000)
        return max(0, self.duration_ms - elapsed)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self.completed:
            return
        x = float(event.x())
        y = float(event.y())
        if self._hit_harvester(x, y):
            self.selected = True
            self.status_text = self.tr("easter.ready")
            self._play_random_sound(self.reporting_sounds, self.reporting_sound_paths)
            self.update()
            event.accept()
            return
        if self.selected:
            self.issue_move_order(x, y)
            event.accept()

    def issue_move_order(self, x: float, y: float):
        x = min(max(16.0, x), self.width() - 16.0)
        y = min(max(18.0, y), self.height() - 18.0)
        self.destination = (x, y)
        self.status_text = self.tr("easter.moving")
        self._play_random_sound(self.acknowledge_sounds, self.acknowledge_sound_paths)

    def _hit_harvester(self, x: float, y: float):
        dx = x - self.harvester_x
        dy = y - self.harvester_y
        return dx * dx + dy * dy <= 28 * 28

    def tick(self):
        if self.completed:
            return

        now = time.monotonic()
        dt = max(0.0, min(0.08, now - self.last_tick))
        self.last_tick = now

        if self.destination is not None:
            dx = self.destination[0] - self.harvester_x
            dy = self.destination[1] - self.harvester_y
            distance = math.hypot(dx, dy)
            speed = 64.0
            if distance <= max(2.0, speed * dt):
                self.harvester_x, self.harvester_y = self.destination
                self.destination = None
                self._resolve_arrival()
                if self.completed:
                    return
            else:
                self._set_direction(dx, dy)
                self.harvester_x += (dx / distance) * speed * dt
                self.harvester_y += (dy / distance) * speed * dt
                self._collect_nearby_resource()
                if self.completed:
                    return

        if self._inside_archive() and self.cargo:
            self._unload_archive()
            if self.completed:
                return

        if self.time_left_ms() <= 0:
            self.finish(False)
            return
        self.update()

    def _resolve_arrival(self):
        if self._inside_archive() and self.cargo:
            self._unload_archive()
        elif self._collect_nearby_resource():
            return
        elif self.cargo >= self.capacity:
            self.status_text = self.tr("easter.full")
        elif self.cargo and self._all_resources_taken():
            self.status_text = self.tr("easter.loaded_all")
        else:
            self.status_text = self.tr("easter.arrived")

    def _collect_nearby_resource(self):
        if self.cargo >= self.capacity:
            self.status_text = self.tr("easter.full")
            return False
        for resource in self.resources:
            if resource["taken"]:
                continue
            dx = resource["x"] - self.harvester_x
            dy = resource["y"] - self.harvester_y
            if dx * dx + dy * dy <= 24 * 24:
                resource["taken"] = True
                self.cargo += 1
                if self.cargo >= self.capacity:
                    self.status_text = self.tr("easter.full")
                elif self._all_resources_taken():
                    self.status_text = self.tr("easter.loaded_all")
                else:
                    self.status_text = self.tr("easter.loaded", cargo=self.cargo, capacity=self.capacity)
                return True
        return False

    def _all_resources_taken(self):
        return all(resource["taken"] for resource in self.resources)

    def _inside_archive(self):
        return math.hypot(self.harvester_x - self.archive_x, self.harvester_y - self.archive_y) <= self.archive_radius

    def _unload_archive(self):
        self.direction = "SE"
        self.delivered += self.cargo
        self.cargo = 0
        self.destination = None
        if self.delivered >= self.required_delivered:
            self.finish(True)
            return
        self.selected = True
        self.status_text = self.tr("easter.unloaded", delivered=self.delivered, total=self.required_delivered)

    def _set_direction(self, dx: float, dy: float):
        if abs(dx) < 0.01 and abs(dy) < 0.01:
            return
        angle = math.degrees(math.atan2(dy, dx))
        if -22.5 <= angle < 22.5:
            self.direction = "E"
        elif 22.5 <= angle < 67.5:
            self.direction = "SE"
        elif 67.5 <= angle < 112.5:
            self.direction = "S"
        elif 112.5 <= angle < 157.5:
            self.direction = "SW"
        elif angle >= 157.5 or angle < -157.5:
            self.direction = "W"
        elif -157.5 <= angle < -112.5:
            self.direction = "NW"
        elif -112.5 <= angle < -67.5:
            self.direction = "N"
        else:
            self.direction = "NE"

    def finish(self, won: bool):
        if self.completed:
            return
        self.completed = True
        self.timer.stop()
        if won:
            self._play_random_sound(self.victory_sounds, self.victory_sound_paths)
            self.finished.emit(True)
            return
        self.game_over = True
        self.status_text = self.tr("easter.game_over")
        self.update()
        QTimer.singleShot(900, lambda: self.finished.emit(False))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        width = self.width()
        height = self.height()

        if self.map_pixmap.isNull():
            painter.fillRect(0, 0, width, height, QColor("#273c24"))
        else:
            painter.drawPixmap(0, 0, self.map_pixmap.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        painter.fillRect(0, 0, width, height, QColor(0, 0, 0, 24))
        self._draw_archive_marker(painter)

        for index, resource in enumerate(self.resources):
            if not resource["taken"]:
                self._draw_resource(painter, resource["x"], resource["y"], index)

        if self.destination is not None and self.selected:
            self._draw_order_marker(painter)

        self._draw_harvester(painter, int(self.harvester_x), int(self.harvester_y))
        self._draw_tree_overlay(painter)
        self._draw_hud(painter)
        if self.game_over:
            self._draw_game_over(painter)
        painter.end()

    def _draw_tree_overlay(self, painter: QPainter):
        if self.tree_overlay_pixmap.isNull():
            return
        painter.save()
        painter.setOpacity(0.52)
        painter.drawPixmap(
            0,
            0,
            self.tree_overlay_pixmap.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation),
        )
        painter.restore()

    def _draw_archive_marker(self, painter: QPainter):
        return

    def _draw_order_marker(self, painter: QPainter):
        x, y = self.destination
        painter.setPen(QPen(QColor("#d7f0ff"), 1, Qt.DashLine))
        painter.drawLine(int(self.harvester_x), int(self.harvester_y), int(x), int(y))
        painter.setPen(QPen(QColor("#f0d269"), 2))
        painter.drawLine(int(x - 7), int(y), int(x + 7), int(y))
        painter.drawLine(int(x), int(y - 7), int(x), int(y + 7))

    def _draw_resource(self, painter: QPainter, x: float, y: float, index: int):
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 26, 42, 18))
        painter.drawEllipse(int(x - 18), int(y - 18), 36, 36)
        painter.setBrush(QColor(255, 92, 80, 8))
        painter.drawEllipse(int(x - 24), int(y - 24), 48, 48)
        painter.restore()

        if self.crystal_frames:
            frame = self.crystal_frames[index % len(self.crystal_frames)]
            size = 31
            frame = frame.scaled(QSize(size, size), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(int(x - frame.width() / 2), int(y - frame.height() / 2), frame)
            return

        painter.setPen(QPen(QColor("#ffb0a8"), 1))
        painter.setBrush(QColor("#9f1424"))
        painter.drawPolygon(
            QPoint(int(x - 4), int(y - 14)),
            QPoint(int(x + 11), int(y - 5)),
            QPoint(int(x + 9), int(y + 9)),
            QPoint(int(x - 2), int(y + 15)),
            QPoint(int(x - 13), int(y + 4)),
            QPoint(int(x - 10), int(y - 8)),
        )
        painter.setPen(QPen(QColor("#ff6b76"), 1))
        painter.drawLine(int(x - 4), int(y - 13), int(x - 2), int(y + 14))
        painter.drawLine(int(x - 12), int(y + 4), int(x + 10), int(y - 5))
        painter.setPen(QPen(QColor("#ffd7d0"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(int(x - 6), int(y - 9), int(x + 4), int(y - 4))
        painter.drawLine(int(x + 4), int(y - 4), int(x + 6), int(y + 5))

    def _draw_harvester(self, painter: QPainter, x: int, y: int):
        frame = self.harvester_frames.get(self.direction)
        if frame and not frame.isNull():
            frame = frame.scaled(QSize(58, 48), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(x - frame.width() // 2, y - frame.height() // 2, frame)
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#141414"))
            painter.drawRoundedRect(x - 21, y + 4, 42, 11, 4, 4)
            painter.setBrush(QColor("#746a35"))
            painter.drawRoundedRect(x - 18, y - 7, 36, 18, 4, 4)
            painter.setBrush(QColor("#d4ad45"))
            painter.drawRoundedRect(x - 12, y - 13, 24, 14, 4, 4)
            painter.setBrush(QColor("#d43b31"))
            painter.drawPolygon(QPoint(x - 9, y - 15), QPoint(x + 8, y - 18), QPoint(x + 4, y - 8))
        if self.cargo:
            painter.setPen(Qt.NoPen)
            for index in range(self.cargo):
                painter.setBrush(QColor("#d72d38"))
                crystal_x = x - 10 + index * 10
                painter.drawPolygon(
                    QPoint(crystal_x, y - 23),
                    QPoint(crystal_x + 5, y - 18),
                    QPoint(crystal_x, y - 13),
                    QPoint(crystal_x - 5, y - 18),
                )

    def _draw_hud(self, painter: QPainter):
        width = self.width()
        height = self.height()
        seconds_left = max(0, int((self.time_left_ms() + 999) / 1000))
        painter.setPen(Qt.NoPen)
        font = QFont("Arial")
        font.setBold(True)
        font.setPixelSize(10)
        painter.setFont(font)

        timer_size = 31
        timer_x = width - timer_size - 6
        timer_y = 6
        painter.setBrush(QColor(12, 18, 22, 185))
        painter.setPen(QPen(QColor(210, 226, 232, 95), 1))
        painter.drawRoundedRect(timer_x, timer_y, timer_size, timer_size, 3, 3)
        painter.setPen(QColor("#f2f4df"))
        painter.drawText(timer_x, timer_y, timer_size, timer_size, Qt.AlignCenter, f"{seconds_left}")

        panel_height = 34
        panel_y = height - panel_height
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(12, 18, 22, 210))
        painter.drawRect(0, panel_y, width, panel_height)
        painter.setPen(QColor("#f2f4df"))
        painter.drawText(
            7,
            panel_y + 2,
            width - 14,
            15,
            Qt.AlignLeft | Qt.AlignVCenter,
            self.tr("easter.resource", delivered=self.delivered, total=self.required_delivered),
        )
        painter.drawText(
            7,
            panel_y + 2,
            width - 14,
            15,
            Qt.AlignRight | Qt.AlignVCenter,
            self.tr("easter.cargo", cargo=self.cargo, capacity=self.capacity),
        )
        status_font = QFont("Arial")
        status_font.setPixelSize(9)
        painter.setFont(status_font)
        painter.setPen(QColor("#d7e3e9"))
        painter.drawText(7, panel_y + 17, width - 14, 15, Qt.AlignLeft | Qt.AlignVCenter, self.status_text)

    def _draw_game_over(self, painter: QPainter):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(8, 12, 14, 190))
        painter.drawRect(0, 0, self.width(), self.height())
        font = QFont("Arial")
        font.setBold(True)
        font.setPixelSize(25)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#2a0808"), 3))
        painter.drawText(self.rect(), Qt.AlignCenter, self.tr("easter.game_over"))
        painter.setPen(QColor("#ff4c4c"))
        painter.drawText(self.rect(), Qt.AlignCenter, self.tr("easter.game_over"))


CHANNEL_TYPE_DEFAULTS = {
    "videos": True,
    "shorts": True,
    "streams": True,
}

CHANNEL_TYPE_BUTTONS = (
    ("videos", "🎬", "overview.video"),
    ("shorts", "⚡", "overview.shorts"),
    ("streams", "🔴", "overview.stream"),
)

PAID_CONTENT_STATUS_KEY = "paid_content_status"
PAID_CONTENT_UNKNOWN = "unknown"
PAID_CONTENT_HAS = "has_paid"
PAID_CONTENT_FREE = "free_only"
PAID_CONTENT_STATUSES = {PAID_CONTENT_UNKNOWN, PAID_CONTENT_HAS, PAID_CONTENT_FREE}
PAID_CONTENT_EMOJIS = {
    PAID_CONTENT_UNKNOWN: "❔",
    PAID_CONTENT_HAS: "🪙",
    PAID_CONTENT_FREE: "🆓",
}

APP_NAME = "YouTube Harvester"
APP_VERSION = "1.1.2"
APP_TITLE = f"{APP_NAME} {APP_VERSION}"
USAGE_RULES_VERSION = "2026-06-13"
DEFAULT_QUICK_DOWNLOAD_HOTKEY = "Ctrl+Shift+Alt+Y"
QUICK_AUDIO_PLAYER_CLIENT = "tv_downgraded"
SUBTITLE_ICON = "🔤"
MIN_FREE_SPACE_MB = 1024
CACHE_PREVIEW_MAX_AGE_DAYS = 7
CACHE_CHANNEL_MAX_AGE_DAYS = 90

RESOLUTION_OPTIONS = (
    ("480p", "480"),
    ("720p", "720"),
    ("1080p", "1080"),
    ("1440p", "1440"),
    ("2160p", "2160"),
    ("Best", "best"),
)
VALID_RESOLUTIONS = {value for _label, value in RESOLUTION_OPTIONS}

STARTUP_DISPLAY_MODES = (
    ("System tray", "tray"),
    ("Taskbar", "taskbar"),
    ("Tray and taskbar", "both"),
)
VALID_STARTUP_DISPLAY_MODES = {value for _label, value in STARTUP_DISPLAY_MODES}

LANGUAGE_OPTIONS = (
    ("English", "en"),
    ("Русский", "ru"),
    ("Українська", "uk"),
    ("Français", "fr"),
    ("Español", "es"),
    ("हिन्दी", "hi"),
    ("中文", "zh"),
    ("日本語", "ja"),
    ("العربية", "ar"),
)
VALID_LANGUAGES = {value for _label, value in LANGUAGE_OPTIONS}
PRIORITY_LANGUAGE_CODES = (
    "ru",
    "en",
    "uk",
    *sorted(VALID_LANGUAGES - {"ru", "en", "uk"}),
)
PRIORITY_LANGUAGE_RANK = {language: index for index, language in enumerate(PRIORITY_LANGUAGE_CODES)}

I18N_EN = {
    "app.language": "Language",
    "tab.overview": "📊 Overview",
    "tab.channels": "📺 Channels",
    "tab.queue": "📥 Queue",
    "tab.settings": "⚙ Settings",
    "tab.diagnostics": "Diagnostics",
    "tray.status.idle": "😴 Status: idle",
    "tray.status.stopping": "⏹ Status: stopping",
    "tray.status.downloading": "⬇️ Status: downloading",
    "tray.status.partial": "🟢 Status: partial downloads",
    "tray.quick_download": "⚡ Quick download ({hotkey})",
    "tray.start": "⏬ Start",
    "tray.stop": "🛑 Stop",
    "tray.downloads": "📁 Downloads",
    "tray.temp": "⌛ Temp",
    "tray.exit": "🚪 Exit",
    "status.channels": "Channels",
    "status.queue": "Queue",
    "status.archive": "Archive",
    "status.files": "Files",
    "status.last_download": "Last downloaded video: {value}",
    "status.temp_files": "Temp files: {temp}\nPartial files: {part}",
    "button.archive": "🗃 Archive",
    "button.quick": "Quick download",
    "button.open_downloads": "Open downloads folder",
    "button.open_temp": "Open temp folder",
    "button.open_archive": "Open detailed download archive",
    "button.add_queue": "Add to queue",
    "button.queue_short": "Queue",
    "button.download": "Download",
    "button.cancel": "Cancel",
    "button.save_settings": "Save settings",
    "button.open_env": "Open .env",
    "button.refresh_list": "Refresh list",
    "button.reload_log": "Reload log",
    "button.refresh": "Refresh",
    "button.copy": "Copy",
    "overview.run": "Run queue and channel check",
    "overview.stop_requested": "Stop already requested; the script will finish at a safe step",
    "overview.stop_soft": "Soft-stop after the current safe step",
    "overview.add_queue_tip": "Add this YouTube video to the download queue",
    "overview.download_tip": "Download this YouTube video now",
    "overview.logo_tip": "YouTube Harvester logo",
    "overview.video_placeholder_tip": "Current video image or placeholder",
    "overview.channel": "Channel",
    "overview.video": "Video",
    "overview.shorts": "Shorts",
    "overview.stream": "Live",
    "state.sleep": "Sleep",
    "state.searching": "Searching",
    "state.downloading": "Downloading",
    "state.stopping": "Stopping",
    "state.stopped": "Stopped",
    "progress.checked_channels": "Checked channels: {checked} / {total}",
    "progress.waiting_data": "Waiting for progress data from yt-dlp",
    "stage.video": "Downloading video",
    "stage.audio": "Downloading audio",
    "stage.merge": "Merging video and audio",
    "stage.postprocess": "Processing file",
    "stage.download": "Downloading",
    "type.searching": "Search",
    "type.done": "Checked",
    "type.missing": "Page missing",
    "type.downloading": "Downloading",
    "type.disabled": "Disabled",
    "type.idle": "Waiting",
    "events.empty": "No events yet",
    "report.stopped": "Last check stopped",
    "report.finished": "Last check finished",
    "report.downloaded": "Downloaded",
    "report.no_new": "No new videos found",
    "report.today": "Downloaded today",
    "report.checked": "Checked channels",
    "report.errors": "Errors: {count}",
    "report.no_errors": "No errors",
    "download.current": "Downloading video: {title}",
    "download.waiting": "Waiting for download",
    "preview.loading": "Loading data...",
    "preview.thumbnail": "Thumbnail",
    "preview.quick_wait": "Waiting for a YouTube link",
    "preview.queue_wait": "Enter a YouTube video URL",
    "preview.error": "Error",
    "preview.need_youtube": "A valid YouTube link is required",
    "preview.reading": "Reading title and thumbnail...",
    "preview.ready_queue": "Ready to add to queue",
    "preview.channel": "Channel: {uploader}",
    "preview.no_title": "Untitled",
    "preview.failed": "Could not read video",
    "preview.failed_detail": "{message}\nYou can add the link to the queue without preview.",
    "preview.clipboard_error": "Clipboard does not contain a valid YouTube link",
    "preview.in_archive": "Video is already in archive",
    "preview.variant_in_archive": "This video with the selected quality, audio and subtitles is already in archive",
    "preview.in_queue": "Video is already in queue",
    "preview.added": "Added to queue",
    "preview.added_front": "Placed first in queue",
    "quick.title": "Quick download",
    "quick.resolution_tip": "Resolution for immediate download",
    "quick.audio_auto": "🎧 Audio: Auto",
    "quick.audio_tip": "Audio tracks for immediate download",
    "quick.audio_selected": "🎧 Audio: {count}",
    "quick.subtitles_none": "🔤 Subtitles: None",
    "quick.subtitles_tip": "Subtitles to embed in the downloaded video",
    "quick.subtitles_selected": "🔤 Subtitles: {count}",
    "quick.subtitles_auto_suffix": "auto",
    "quick.combined_audio_limit": "Select no more than one combined video/audio track",
    "quick.download_now": "Download immediately",
    "quick.close_tip": "Close quick download window",
    "quick.queue_easter": "To the queue, sons of cinema",
    "quick.already_running": "A download is already running. Add the link to the queue with the normal button.",
    "quick.accept_rules_first": "Usage rules must be accepted first",
    "settings.download": "Download",
    "settings.downloads": "📁 Downloads",
    "settings.temp": "⌛ Temp",
    "settings.downloads_tip": "Where finished videos are saved",
    "settings.temp_tip": "Where temporary files and partial downloads are stored",
    "settings.choose": "Choose: {label}",
    "settings.limits": "🔢 Limits",
    "settings.limits_tip": "How many recent items to check on each channel",
    "settings.videos_tip": "How many recent normal videos to check on each channel",
    "settings.shorts_tip": "How many recent Shorts to check on each channel",
    "settings.streams_tip": "How many recent live streams to check on each channel",
    "settings.resolution": "📺 Resolution",
    "settings.resolution_tip": "Maximum quality for yt-dlp; default is 1080p",
    "settings.behavior": "Behavior",
    "settings.quick_download": "📋 Quick download:",
    "settings.watch_clipboard": "Watch clipboard",
    "settings.watch_clipboard_tip": "Open quick download when a YouTube link appears in the clipboard",
    "settings.autostart": "🚀 Autostart",
    "settings.autostart_tip": "Start {app} when you sign in",
    "settings.startup_mode_tip": "How to show the app on autostart",
    "settings.misc": "⚙ Misc",
    "settings.cleanup_temp": "🧹 Temp",
    "settings.cleanup_temp_tip": "Clean the temp folder after successful processing",
    "settings.retry_queue": "🔁 Queue",
    "settings.retry_queue_tip": "Return failed links to the queue for retry",
    "settings.logs_count": "📝 Logs",
    "settings.logs_count_tip": "How many archived logs to keep",
    "settings.rules_tip": "Open usage rules and external component info",
    "settings.ytdlp_tip": "Check installed and latest yt-dlp version",
    "settings.ytdlp_checking": "Checking yt-dlp version...",
    "settings.hotkey_tip": "Quick download hotkey: {hotkey}",
    "settings.diagnostics_tip": "Diagnostics",
    "settings.saved": "Settings saved",
    "settings.select_folder": "Choose folder",
    "settings.theme_system": "Follow system: {mode}",
    "settings.theme_dark_mode": "dark",
    "settings.theme_light_mode": "light",
    "settings.theme_to_light": "Switch to day mode",
    "settings.theme_to_system": "Switch to system mode",
    "settings.theme_toggle": "Night / day mode",
    "startup.tray": "System tray",
    "startup.taskbar": "Taskbar",
    "startup.both": "Tray and taskbar",
    "resolution.best": "Best",
    "telegram.enabled": "🔔 Notifications enabled",
    "telegram.disabled": "🔕 Notifications disabled",
    "telegram.enabled_tip": "Telegram notifications are enabled. Click to disable.",
    "telegram.disabled_tip": "Telegram notifications are disabled. Click to enable.",
    "telegram.secret_tip": "{label}: value is hidden, click the eye to view",
    "telegram.eye_tip": "Show or hide field value",
    "telegram.save_tip": "Save all settings, including Telegram and folders",
    "telegram.open_env_tip": "Open Telegram settings file",
    "logs.title": "Logs",
    "logs.filter_tip": "Filter lines in the selected log",
    "logs.all": "All",
    "logs.important": "Important",
    "logs.errors": "Errors",
    "logs.refresh_tip": "Refresh available logs",
    "logs.reload_tip": "Read selected log again",
    "channels.check": "🔎 Check channels",
    "channels.stop_check": "Stop check",
    "channels.stopping": "Stopping...",
    "channels.check_paid": "Check paid content",
    "channels.check_paid_tip": "Also look for members-only content when checking channels",
    "channels.check_stop_tip": "Stop channel check after the current step",
    "channels.check_with_paid_tip": "Check Video, Shorts, Live and paid content",
    "channels.check_without_paid_tip": "Check Video, Shorts and Live without paid content search",
    "channels.none": "No channels",
    "channels.checking": "Checking: {done}/{total}",
    "channels.checked": "Checked channels: {total}",
    "channels.stopped_count": "Check stopped: {done}/{total}",
    "channels.checked_one": "Checked channels: 1",
    "channels.check_failed": "Check failed",
    "channels.stop_status": "Stopping check...",
    "channels.active": "{label}: checking now",
    "channels.waiting": "{label}: waiting for check",
    "channels.section_missing": "{label}: section not found; download setting was not changed",
    "channels.section_error": "{label}: could not check{error}",
    "channels.section_available": "{label}: section found; green means download, red means skip",
    "channels.section_toggle": "{label}: green means download, red means skip",
    "channels.paid_unknown": "Paid content: unknown",
    "channels.paid_has": "Paid content: members-only was seen",
    "channels.paid_free": "Paid content: checked, members-only not found",
    "channels.open": "Open channel",
    "channels.delete": "Delete channel",
    "channels.add": "Add channel",
    "channels.add_title": "Add channel",
    "channels.add_prompt": "YouTube channel link:",
    "channels.need_link": "A YouTube channel link is required",
    "channels.exists": "This channel already exists",
    "archive.title": "Archive",
    "archive.heading": "🗃 Download archive",
    "archive.type": "Type",
    "archive.channel": "Channel",
    "archive.name": "Title",
    "archive.date": "Date",
    "archive.quality": "Quality",
    "archive.refresh_tip": "Reload archive and check files",
    "archive.youtube_tip": "Open selected video on YouTube",
    "archive.file": "🎬 File",
    "archive.file_tip": "Open selected video from disk",
    "archive.folder": "📁 Folder",
    "archive.folder_tip": "Open selected video folder",
    "archive.delete": "🗑 Delete",
    "archive.delete_tip": "Delete selected entry from detailed and service archives",
    "archive.file_exists": "File exists on disk",
    "archive.file_missing": "File not found on disk",
    "archive.select_entry": "Select a table entry",
    "archive.no_youtube": "This entry has no YouTube link",
    "archive.no_channel": "This entry has no channel link",
    "archive.no_path": "This entry has no file path",
    "archive.not_found": "File not found on disk",
    "archive.stop_first": "Stop downloading first so the archive is not written from two places at once.",
    "archive.mark_tip": "Mark latest Video, Shorts and Live section items as already downloaded",
    "archive.mark_question": "Mark the latest Video, Shorts and Live items from channel \"{title}\" as already downloaded?\n\nDownloading will not start. Found items will be added to the archive.",
    "archive.mark_found": "Found",
    "archive.mark_added": "Added to archive",
    "queue.planner": "Scheduler",
    "queue.enabled": "Enabled",
    "queue.add": "Add",
    "queue.toggle": "On / off",
    "queue.remove": "Remove",
    "queue.run_at": "Run at",
    "queue.new_enabled_tip": "New schedule entry will be active",
    "queue.add_tip": "Add run at the selected hour",
    "queue.toggle_tip": "Enable or disable selected schedule",
    "queue.remove_tip": "Delete selected schedule entry",
    "queue.video_queue": "Video queue",
    "queue.remove_selected": "Remove selected",
    "queue.remove_selected_tip": "Remove selected link from queue",
    "queue.reload": "Reload queue",
    "queue.reload_tip": "Reload queue list from file",
    "queue.not_selected": "No video selected",
    "queue.schedule_not_selected": "No schedule entry selected",
    "queue.enabled_summary": "{enabled} enabled / {total} total",
    "queue.on": "ON",
    "queue.off": "OFF",
    "queue.never_run": "never run",
    "queue.one_video": "1 video",
    "queue.many_videos": "{count} videos",
    "dialog.hotkey": "Hotkey",
    "dialog.hotkey_title": "Quick download",
    "dialog.hotkey_tip": "Quick download key combination",
    "dialog.default": "Default",
    "dialog.system": "Install in system",
    "dialog.usage_rules": "Usage rules",
    "dialog.accept": "Accept",
    "dialog.decline": "Decline",
    "dialog.close": "Close",
    "usage.check_1": "I have read the rules and understand that I am responsible for using the app.",
    "usage.check_2": "I will follow YouTube rules, copyright law, and the laws of my country.",
    "usage.check_3": "I understand that external tools have their own licenses and no warranty.",
    "diagnostics.title": "Diagnostics",
    "diagnostics.copied": "Report copied",
    "yt_dlp.current": "Current version: {value}",
    "yt_dlp.latest": "Latest version: {value}",
    "yt_dlp.unknown_current": "could not detect",
    "yt_dlp.unknown_latest": "could not check",
    "yt_dlp.new_available": "A new yt-dlp version is available.",
    "yt_dlp.frozen_update": "In Windows/PyInstaller builds, yt-dlp is updated together with a new app version.",
    "yt_dlp.source_update": "For source installs, update yt-dlp in Python or through your system package manager.",
    "yt_dlp.current_ok": "yt-dlp looks up to date.",
    "time.none": "none",
    "time.just_now": "just now",
    "time.day": "d",
    "time.hour": "h",
    "time.minute": "m",
    "time.ago": "{value} ago",
    "disk.temp_folder": "Temp folder",
    "disk.download_folder": "Downloads folder",
    "disk.low_space": "Low disk space",
    "disk.free_needed": "{label}: {free} free, at least {required} needed",
    "notify.settings": "Settings",
    "notify.rules_not_accepted": "Rules not accepted",
    "notify.app_will_close": "The app will close",
    "notify.python_engine": "Python engine",
    "notify.file_not_found": "File not found: {path}",
    "notify.ffmpeg_missing": "ffmpeg not found",
    "notify.ffmpeg_needed": "Windows build needs bundled ffmpeg.exe and ffprobe.exe",
    "notify.deno_missing": "Deno not found",
    "notify.deno_needed": "Windows build needs bundled deno.exe for YouTube JS",
    "notify.ytdlp_missing": "yt-dlp not found",
    "notify.ytdlp_install": "Install yt-dlp and check PATH",
    "notify.already_running": "Script is already running",
    "notify.wait_finish": "Wait for it to finish...",
    "notify.download_not_started": "Download not started",
    "notify.apply_settings_failed": "Could not apply settings: {error}",
    "notify.download_started": "Download started",
    "notify.script_started": "Script started...",
    "notify.error": "Error",
    "notify.stopping": "Stopping",
    "notify.stop_after_safe": "The script will stop after the current safe step",
    "notify.stop_failed": "Could not stop",
    "tray.tip.partial": "{app} - partial .part downloads",
    "tray.tip.stopping": "{app} - stopping",
    "tray.tip.running": "{app} - running",
    "tray.tip.sleep": "{app} - idle",
    "easter.select_harvester": "Select the harvester",
    "easter.ready": "Harvester ready",
    "easter.moving": "Heading for YouTubium",
    "easter.full": "Cargo full. Back to base!",
    "easter.loaded_all": "YouTubium loaded. Back to base!",
    "easter.arrived": "Arrived",
    "easter.loaded": "YouTubium loaded: {cargo}/{capacity}",
    "easter.unloaded": "YouTubium unloaded: {delivered}/{total}",
    "easter.resource": "YouTubium {delivered}/{total}",
    "easter.cargo": "Cargo {cargo}/{capacity}",
    "easter.victory_ready": "YTuHa is ready to harvest",
}

I18N_EN.update({
    "placeholder.youtube_url": "YouTube URL",
    "placeholder.video_url": "https://www.youtube.com/watch?v=...",
    "generic.script_not_found": "Script not found:\n{path}",
    "archive.migration_not_found": "Migration script not found:\n{path}",
    "archive.migration_run_failed": "Could not run migration:\n{error}",
    "archive.migration_failed": "Migration script failed",
    "archive.migration_complete": "Migration complete.",
    "archive.migration_old_ids": "IDs in old archive: {count}",
    "archive.migration_scanned": "Files checked: {count}",
    "archive.migration_matched": "Files matching the YTH pattern: {count}",
    "archive.migration_with_file": "Added with file: {count}",
    "archive.migration_missing_file": "Added without file: {count}",
    "archive.migration_total": "Total added: {count}",
    "archive.selected_entry": "selected entry",
    "archive.delete_question": "Delete archive entry \"{title}\"?",
    "archive.delete_note": "The file on disk will not be deleted. Only the selected variant is removed; the service ID remains while other variants exist.",
    "archive.deleted": "Entry deleted.",
    "archive.deleted_details": "Detailed archive: removed {count}",
    "archive.deleted_service": "Service archive: removed {count}",
    "archive.update_failed": "Could not update archive",
    "hotkey.assign_failed": "Could not assign: {hotkey}",
    "hotkey.wayland_only": "System installation is only needed for Linux Wayland",
    "hotkey.gsettings_missing": "gsettings was not found",
    "hotkey.convert_failed": "Could not convert the key combination",
    "hotkey.add_failed": "Could not add the system key combination",
    "hotkey.cinnamon_schema": "Cinnamon keybindings schema is unavailable",
    "hotkey.cinnamon_list": "Could not update the Cinnamon custom-list",
    "hotkey.cinnamon_write": "Could not save the Cinnamon shortcut",
    "hotkey.cinnamon_done": "Cinnamon system shortcut installed: {binding}",
    "hotkey.gnome_schema": "GNOME media-keys schema is unavailable",
    "hotkey.gnome_list": "Could not update GNOME custom-keybindings",
    "hotkey.gnome_write": "Could not save the GNOME shortcut",
    "hotkey.gnome_done": "GNOME system shortcut installed: {binding}",
    "hotkey.wayland_status": "Wayland: the internal global hotkey is disabled; use a system shortcut",
    "hotkey.not_initialized": "not initialized",
    "hotkey.registered": "registered",
    "hotkey.not_registered": "not registered",
    "hotkey.running": "running",
    "hotkey.not_running": "not running: {error}",
    "diagnostics.date": "Date: {value}",
    "diagnostics.system": "System",
    "diagnostics.os": "OS: {value}",
    "diagnostics.python": "Python: {value}",
    "diagnostics.qt": "Qt: {value}",
    "diagnostics.frozen": "Frozen/PyInstaller: {value}",
    "diagnostics.session": "Session: {value}",
    "diagnostics.desktop": "Desktop: {value}",
    "diagnostics.tray": "Tray available: {value}",
    "diagnostics.startup": "Startup mode: {value}",
    "diagnostics.hotkey_clipboard": "Hotkey and clipboard",
    "diagnostics.hotkey": "Hotkey: {value}",
    "diagnostics.hotkey_status": "Hotkey status: {value}",
    "diagnostics.clipboard_watch": "Clipboard watch: {value}",
    "diagnostics.wayland_paste": "Wayland wl-paste: {value}",
    "diagnostics.tools": "Tools",
    "diagnostics.paths": "Paths",
    "diagnostics.cache_size": "Cache size: {value}",
    "diagnostics.cache_cleanup": "Cache cleanup: previews {preview_days}d, channel logos {channel_days}d",
    "diagnostics.data": "Data",
    "diagnostics.channels": "Channels: {count}",
    "diagnostics.queue": "Queue: {count}",
    "diagnostics.archive_lines": "Archive txt lines: {count}",
    "diagnostics.archive_details": "Archive details lines: {count}",
    "diagnostics.telegram": "Telegram",
    "diagnostics.enabled": "Enabled: {value}",
    "diagnostics.configured": "configured",
    "diagnostics.not_configured": "not configured",
    "diagnostics.yes": "yes",
    "diagnostics.no": "no",
    "diagnostics.writable": "writable: {value}",
    "diagnostics.path_error": "{label}: {path} | error: {error} | writable: {writable}",
    "diagnostics.path_space": "{label}: {path} | free {free} of {total} | writable: {writable}",
    "diagnostics.command_error": "error: {error}",
    "diagnostics.command_exit": "exit code {code}: {detail}",
    "diagnostics.command_ok": "ok",
    "diagnostics.tool_missing": "{label}: not found",
    "easter.game_over": "GAME OVER",
})

I18N = {
    "en": I18N_EN,
    "ru": {
        "app.language": "Язык",
        "tab.overview": "📊 Обзор", "tab.channels": "📺 Каналы", "tab.queue": "📥 Очередь", "tab.settings": "⚙ Настройки", "tab.diagnostics": "Диагностика",
        "tray.status.idle": "😴 Статус: сон", "tray.status.stopping": "⏹ Статус: останавливается", "tray.status.downloading": "⬇️ Статус: скачивание", "tray.status.partial": "🟢 Статус: есть недокачанные",
        "tray.quick_download": "⚡ Быстрое скачивание ({hotkey})", "tray.start": "⏬ Старт", "tray.stop": "🛑 Стоп", "tray.downloads": "📁 Загрузки", "tray.temp": "⌛ Врем.", "tray.exit": "🚪 Выход",
        "status.channels": "Каналов", "status.queue": "Очередь", "status.archive": "Архив", "status.files": "Файлы", "status.last_download": "Последнее скаченное видео: {value}", "status.temp_files": "Временных файлов: {temp}\nНедокачанных файлов: {part}",
        "button.archive": "🗃 Архив", "button.quick": "Быстрое скачивание", "button.open_downloads": "Открыть папку загрузок", "button.open_temp": "Открыть временную папку", "button.open_archive": "Открыть подробный архив скачиваний", "button.add_queue": "Добавить в очередь", "button.queue_short": "В очередь", "button.download": "Скачать", "button.cancel": "Отмена", "button.save_settings": "Сохранить настройки", "button.open_env": "Открыть .env", "button.refresh_list": "Обновить список", "button.reload_log": "Перечитать лог", "button.refresh": "Обновить", "button.copy": "Скопировать",
        "overview.run": "Запустить проверку очереди и каналов", "overview.stop_requested": "Остановка уже запрошена; скрипт завершится на безопасном шаге", "overview.stop_soft": "Мягко остановить скачивание после текущего безопасного шага", "overview.add_queue_tip": "Добавить указанное YouTube-видео в очередь скачивания", "overview.download_tip": "Скачать указанное YouTube-видео сразу", "overview.logo_tip": "Логотип YouTube Harvester", "overview.video_placeholder_tip": "Заставка текущего видео или заглушка", "overview.channel": "Канал", "overview.video": "Видео", "overview.shorts": "Shorts", "overview.stream": "Трансляция",
        "state.sleep": "Сон", "state.searching": "Идет поиск", "state.downloading": "Идет скачивание", "state.stopping": "Остановка", "state.stopped": "Остановлено", "progress.checked_channels": "Проверено каналов: {checked} / {total}", "progress.waiting_data": "Ожидаю данные прогресса от yt-dlp", "stage.video": "Скачивается видео", "stage.audio": "Скачивается аудио", "stage.merge": "Объединение видео и аудио", "stage.postprocess": "Обработка файла", "stage.download": "Скачивание", "type.searching": "Поиск", "type.done": "Проверено", "type.missing": "Страница отсутствует", "type.downloading": "Скачивание", "type.disabled": "Отключено", "type.idle": "Ожидание",
        "events.empty": "Событий пока нет", "report.stopped": "Последняя проверка остановлена", "report.finished": "Последняя проверка завершена", "report.downloaded": "Скачано", "report.no_new": "Новых видео не найдено", "report.today": "Скачано за сегодня", "report.checked": "Проверено каналов", "report.errors": "Ошибок: {count}", "report.no_errors": "Без ошибок",
        "download.current": "Скачивается видео: {title}", "download.waiting": "Ожидаем скачивания",
        "preview.loading": "Загрузка данных...", "preview.thumbnail": "Обложка", "preview.quick_wait": "Ожидаю ссылку YouTube", "preview.queue_wait": "Введите адрес YouTube-видео", "preview.error": "Ошибка", "preview.need_youtube": "Нужна корректная ссылка YouTube", "preview.reading": "Читаю название и обложку...", "preview.ready_queue": "Готово к добавлению в очередь", "preview.channel": "Канал: {uploader}", "preview.no_title": "Без названия", "preview.failed": "Не удалось прочитать видео", "preview.failed_detail": "{message}\nМожно добавить ссылку в очередь без предпросмотра.", "preview.clipboard_error": "В буфере обмена нет корректной ссылки YouTube", "preview.in_archive": "Видео уже есть в архиве", "preview.in_queue": "Видео уже есть в очереди", "preview.added": "Добавлено в очередь", "preview.added_front": "Поставлено первым в очередь",
        "quick.title": "Быстрое скачивание", "quick.resolution_tip": "Разрешение для немедленного скачивания", "quick.download_now": "Скачать немедленно", "quick.close_tip": "Закрыть окно быстрого скачивания", "quick.queue_easter": "В очередь, сукины дети", "quick.already_running": "Скачивание уже идёт. Ссылка добавится в очередь обычной кнопкой.", "quick.accept_rules_first": "Сначала нужно принять правила использования",
        "settings.download": "Загрузка", "settings.downloads": "📁 Загрузки", "settings.temp": "⌛ Врем.", "settings.downloads_tip": "Куда складывать готовые скачанные видео", "settings.temp_tip": "Где хранить временные файлы и недокачанные части", "settings.choose": "Выбрать: {label}", "settings.limits": "🔢 Лимиты", "settings.limits_tip": "Сколько последних элементов проверять на каждом канале", "settings.videos_tip": "Сколько последних обычных видео проверять на каждом канале", "settings.shorts_tip": "Сколько последних Shorts проверять на каждом канале", "settings.streams_tip": "Сколько последних трансляций проверять на каждом канале", "settings.resolution": "📺 Разрешение", "settings.resolution_tip": "Максимальное качество для yt-dlp; по умолчанию 1080p", "settings.behavior": "Поведение", "settings.quick_download": "📋 Быстрое скачивание:", "settings.watch_clipboard": "Следить за буфером", "settings.watch_clipboard_tip": "Открывать окно быстрого скачивания, когда в буфере появляется ссылка YouTube", "settings.autostart": "🚀 Автозагрузка", "settings.autostart_tip": "Запускать {app} при входе в систему", "settings.startup_mode_tip": "Как показывать программу при автозагрузке", "settings.misc": "⚙ Прочее", "settings.cleanup_temp": "🧹 Врем.", "settings.cleanup_temp_tip": "Очищать временную папку после успешной обработки", "settings.retry_queue": "🔁 Очередь", "settings.retry_queue_tip": "Возвращать неудачные ссылки обратно в очередь для повтора", "settings.logs_count": "📝 Логов", "settings.logs_count_tip": "Сколько архивных логов хранить", "settings.rules_tip": "Открыть правила использования и сведения о внешних компонентах", "settings.ytdlp_tip": "Проверить установленную и последнюю версию yt-dlp", "settings.ytdlp_checking": "Проверяю версию yt-dlp...", "settings.hotkey_tip": "Горячая клавиша быстрого скачивания: {hotkey}", "settings.diagnostics_tip": "Диагностика", "settings.saved": "Настройки сохранены", "settings.select_folder": "Выбрать папку", "settings.theme_system": "Как в системе: {mode}", "settings.theme_dark_mode": "темный", "settings.theme_light_mode": "светлый", "settings.theme_to_light": "Включить дневной режим", "settings.theme_to_system": "Включить режим как в системе", "settings.theme_toggle": "Ночной / дневной режим",
        "startup.tray": "Системный трей", "startup.taskbar": "Панель задач", "startup.both": "Трей и панель задач", "resolution.best": "Лучшее",
        "telegram.enabled": "🔔 Уведомления включены", "telegram.disabled": "🔕 Уведомления выключены", "telegram.enabled_tip": "Telegram-уведомления включены. Нажмите, чтобы выключить.", "telegram.disabled_tip": "Telegram-уведомления выключены. Нажмите, чтобы включить.", "telegram.secret_tip": "{label}: значение скрыто, нажмите глаз для просмотра", "telegram.eye_tip": "Показать или скрыть значение поля", "telegram.save_tip": "Сохранить все настройки, включая Telegram и папки", "telegram.open_env_tip": "Открыть файл Telegram-настроек",
        "logs.title": "Логи", "logs.filter_tip": "Фильтр строк выбранного лога", "logs.all": "Всё", "logs.important": "Важное", "logs.errors": "Ошибки", "logs.refresh_tip": "Обновить список доступных логов", "logs.reload_tip": "Заново прочитать выбранный лог",
        "channels.check": "🔎 Проверить каналы", "channels.stop_check": "Остановить проверку", "channels.stopping": "Останавливается...", "channels.check_paid": "Проверять наличие платного контента", "channels.check_paid_tip": "При проверке каналов дополнительно искать members-only", "channels.check_stop_tip": "Остановить проверку каналов после текущего шага", "channels.check_with_paid_tip": "Проверить Видео, Shorts, Трансляции и платный контент", "channels.check_without_paid_tip": "Проверить Видео, Shorts и Трансляции без поиска платного контента", "channels.none": "Каналов нет", "channels.checking": "Проверка: {done}/{total}", "channels.checked": "Проверено каналов: {total}", "channels.stopped_count": "Проверка остановлена: {done}/{total}", "channels.checked_one": "Проверено каналов: 1", "channels.check_failed": "Проверка не удалась", "channels.stop_status": "Остановка проверки...", "channels.active": "{label}: проверяется сейчас", "channels.waiting": "{label}: ожидает проверки", "channels.section_missing": "{label}: раздел не найден; настройка скачивания не изменена", "channels.section_error": "{label}: не удалось проверить{error}", "channels.section_available": "{label}: раздел найден; зелёный - скачивать, красный - пропускать", "channels.section_toggle": "{label}: зелёный - скачивать, красный - пропускать", "channels.paid_unknown": "Платный контент: неизвестно", "channels.paid_has": "Платный контент: встречалось members-only", "channels.paid_free": "Платный контент: проверили, members-only не нашли", "channels.open": "Открыть канал", "channels.delete": "Удалить канал", "channels.add": "Добавить канал", "channels.add_title": "Добавить канал", "channels.add_prompt": "Ссылка на YouTube-канал:", "channels.need_link": "Нужна ссылка на YouTube-канал", "channels.exists": "Такой канал уже есть",
        "archive.title": "Архив", "archive.heading": "🗃 Архив скачиваний", "archive.type": "Тип", "archive.channel": "Канал", "archive.name": "Название", "archive.date": "Дата", "archive.refresh_tip": "Перечитать архив и проверить наличие файлов", "archive.youtube_tip": "Открыть выбранное видео на YouTube", "archive.file": "🎬 Файл", "archive.file_tip": "Открыть выбранное видео с диска", "archive.folder": "📁 Папка", "archive.folder_tip": "Открыть папку выбранного видео", "archive.delete": "🗑 Удалить", "archive.delete_tip": "Удалить выбранную запись из подробного и служебного архивов", "archive.file_exists": "Файл есть на диске", "archive.file_missing": "Файл не найден на диске", "archive.select_entry": "Выберите запись в таблице", "archive.no_youtube": "В этой записи нет ссылки на YouTube", "archive.no_channel": "В этой записи нет ссылки на канал", "archive.no_path": "В этой записи нет пути к файлу", "archive.not_found": "Файл не найден на диске", "archive.stop_first": "Сначала остановите скачивание, чтобы архив не записывался одновременно из двух мест.", "archive.mark_tip": "Пометить последние элементы разделов Видео, Shorts и Трансляция как уже скачанные", "archive.mark_question": "Пометить последние элементы разделов Видео, Shorts и Трансляция канала «{title}» как уже скачанные?\n\nСкачивание не запустится. Найденные ролики будут добавлены в архив.", "archive.mark_found": "Найдено", "archive.mark_added": "Добавлено в архив",
        "queue.planner": "Планировщик", "queue.enabled": "Включено", "queue.add": "Добавить", "queue.toggle": "Вкл / выкл", "queue.remove": "Удалить", "queue.run_at": "Запуск в", "queue.new_enabled_tip": "Новая запись расписания будет активной", "queue.add_tip": "Добавить запуск в выбранный час", "queue.toggle_tip": "Включить или выключить выбранное расписание", "queue.remove_tip": "Удалить выбранную запись расписания", "queue.video_queue": "Очередь видео", "queue.remove_selected": "Удалить выбранное", "queue.remove_selected_tip": "Удалить выбранную ссылку из очереди", "queue.reload": "Перечитать очередь", "queue.reload_tip": "Перечитать список очереди из файла", "queue.not_selected": "Не выбрано видео", "queue.schedule_not_selected": "Не выбрана запись", "queue.enabled_summary": "{enabled} включено / {total} всего", "queue.on": "ВКЛ", "queue.off": "ВЫКЛ", "queue.never_run": "не запускался", "queue.one_video": "1 видео", "queue.many_videos": "{count} видео",
        "dialog.hotkey": "Горячая клавиша", "dialog.hotkey_title": "Быстрое скачивание", "dialog.hotkey_tip": "Комбинация для быстрого скачивания", "dialog.default": "По умолчанию", "dialog.system": "В систему", "dialog.usage_rules": "Правила использования", "dialog.accept": "Принимаю", "dialog.decline": "Не принимаю", "dialog.close": "Закрыть", "usage.check_1": "Я прочитал(а) правила и понимаю, что отвечаю за использование программы.", "usage.check_2": "Я буду соблюдать правила YouTube, авторское право и законы своей страны.", "usage.check_3": "Я понимаю, что внешние инструменты поставляются со своими лицензиями и без гарантий.", "diagnostics.title": "Диагностика", "diagnostics.copied": "Отчёт скопирован",
        "yt_dlp.current": "Текущая версия: {value}", "yt_dlp.latest": "Последняя версия: {value}", "yt_dlp.unknown_current": "не удалось определить", "yt_dlp.unknown_latest": "не удалось проверить", "yt_dlp.new_available": "Доступна новая версия yt-dlp.", "yt_dlp.frozen_update": "В Windows/PyInstaller-сборке yt-dlp обновляется вместе с новой версией программы.", "yt_dlp.source_update": "Для исходников обновите yt-dlp в окружении Python или через пакетный менеджер системы.", "yt_dlp.current_ok": "yt-dlp выглядит актуальным.",
        "time.none": "нет", "time.just_now": "только что", "time.day": "д", "time.hour": "ч", "time.minute": "м", "time.ago": "{value} назад",
        "disk.temp_folder": "Временная папка", "disk.download_folder": "Папка загрузок", "disk.low_space": "Мало места на диске", "disk.free_needed": "{label}: свободно {free}, нужно хотя бы {required}", "notify.settings": "Настройки", "notify.rules_not_accepted": "Правила не приняты", "notify.app_will_close": "Программа будет закрыта", "notify.python_engine": "Python-движок", "notify.file_not_found": "Не найден файл: {path}", "notify.ffmpeg_missing": "ffmpeg не найден", "notify.ffmpeg_needed": "Windows-сборке нужны bundled ffmpeg.exe и ffprobe.exe", "notify.deno_missing": "Deno не найден", "notify.deno_needed": "Windows-сборке нужен bundled deno.exe для YouTube JS", "notify.ytdlp_missing": "yt-dlp не найден", "notify.ytdlp_install": "Установите yt-dlp и проверьте PATH", "notify.already_running": "Скрипт уже запущен", "notify.wait_finish": "Подождите завершения...", "notify.download_not_started": "Скачивание не запущено", "notify.apply_settings_failed": "Не удалось применить настройки: {error}", "notify.download_started": "Загрузка началась", "notify.script_started": "Скрипт запущен...", "notify.error": "Ошибка", "notify.stopping": "Остановка", "notify.stop_after_safe": "Скрипт завершится после текущего безопасного шага", "notify.stop_failed": "Не удалось остановить", "tray.tip.partial": "{app} - есть загрузки .part", "tray.tip.stopping": "{app} - останавливается", "tray.tip.running": "{app} - работает", "tray.tip.sleep": "{app} - спит",
        "easter.select_harvester": "Выбери харвестер", "easter.ready": "Харвестер готов", "easter.moving": "Еду за Ютубиумом", "easter.full": "Груз полный. На базу!", "easter.loaded_all": "Ютубиум в кузове. На базу!", "easter.arrived": "Прибыл", "easter.loaded": "Ютубиум загружен: {cargo}/{capacity}", "easter.unloaded": "Ютубиум разгружен: {delivered}/{total}", "easter.resource": "Ютубиум {delivered}/{total}", "easter.cargo": "Груз {cargo}/{capacity}", "easter.victory_ready": "ЮТуХа готова к сбору",
    },
}

I18N_COMMON = {
    "fr": {
        "app.language": "Langue", "tab.overview": "📊 Aperçu", "tab.channels": "📺 Chaînes", "tab.queue": "📥 File", "tab.settings": "⚙ Réglages", "tab.diagnostics": "Diagnostic",
        "status.channels": "Chaînes", "status.queue": "File", "status.archive": "Archive", "button.add_queue": "Ajouter à la file", "button.queue_short": "File", "button.download": "Télécharger", "button.cancel": "Annuler", "button.refresh": "Actualiser", "settings.download": "Téléchargement", "settings.behavior": "Comportement", "settings.watch_clipboard": "Surveiller le presse-papiers", "settings.autostart": "🚀 Démarrage auto", "settings.misc": "⚙ Divers", "logs.title": "Journaux", "logs.all": "Tout", "logs.important": "Important", "logs.errors": "Erreurs", "channels.check": "🔎 Vérifier les chaînes", "channels.check_paid": "Vérifier le contenu payant", "queue.planner": "Planificateur", "queue.video_queue": "File vidéo", "telegram.enabled": "🔔 Notifications activées", "telegram.disabled": "🔕 Notifications désactivées", "quick.title": "Téléchargement rapide", "quick.download_now": "Télécharger maintenant", "archive.title": "Archive", "archive.heading": "🗃 Archive des téléchargements", "archive.type": "Type", "archive.channel": "Chaîne", "archive.name": "Titre", "archive.date": "Date", "archive.file": "🎬 Fichier", "archive.folder": "📁 Dossier", "archive.delete": "🗑 Supprimer", "preview.thumbnail": "Miniature", "preview.quick_wait": "En attente d'un lien YouTube", "preview.queue_wait": "Entrez une URL vidéo YouTube", "preview.ready_queue": "Prêt à ajouter à la file", "preview.channel": "Chaîne : {uploader}", "resolution.best": "Meilleur", "startup.tray": "Zone de notification", "startup.taskbar": "Barre des tâches", "startup.both": "Zone et barre", "time.none": "aucun", "time.just_now": "à l'instant", "time.ago": "il y a {value}", "easter.select_harvester": "Sélectionne le harvester", "easter.ready": "Harvester prêt", "easter.moving": "En route vers le YouTubium", "easter.full": "Cargaison pleine. Retour à la base !", "easter.loaded_all": "YouTubium chargé. Retour à la base !", "easter.arrived": "Arrivé", "easter.loaded": "YouTubium chargé : {cargo}/{capacity}", "easter.unloaded": "YouTubium déchargé : {delivered}/{total}", "easter.resource": "YouTubium {delivered}/{total}", "easter.cargo": "Cargaison {cargo}/{capacity}", "easter.victory_ready": "YTuHa est prêt à récolter",
    },
    "es": {
        "app.language": "Idioma", "tab.overview": "📊 Resumen", "tab.channels": "📺 Canales", "tab.queue": "📥 Cola", "tab.settings": "⚙ Ajustes", "tab.diagnostics": "Diagnóstico",
        "status.channels": "Canales", "status.queue": "Cola", "status.archive": "Archivo", "button.add_queue": "Agregar a la cola", "button.queue_short": "Cola", "button.download": "Descargar", "button.cancel": "Cancelar", "button.refresh": "Actualizar", "settings.download": "Descarga", "settings.behavior": "Comportamiento", "settings.watch_clipboard": "Vigilar portapapeles", "settings.autostart": "🚀 Inicio automático", "settings.misc": "⚙ Otros", "logs.title": "Registros", "logs.all": "Todo", "logs.important": "Importante", "logs.errors": "Errores", "channels.check": "🔎 Comprobar canales", "channels.check_paid": "Comprobar contenido de pago", "queue.planner": "Programador", "queue.video_queue": "Cola de vídeos", "telegram.enabled": "🔔 Notificaciones activadas", "telegram.disabled": "🔕 Notificaciones desactivadas", "quick.title": "Descarga rápida", "quick.download_now": "Descargar ahora", "archive.title": "Archivo", "archive.heading": "🗃 Archivo de descargas", "archive.type": "Tipo", "archive.channel": "Canal", "archive.name": "Título", "archive.date": "Fecha", "archive.file": "🎬 Archivo", "archive.folder": "📁 Carpeta", "archive.delete": "🗑 Eliminar", "preview.thumbnail": "Miniatura", "preview.quick_wait": "Esperando enlace de YouTube", "preview.queue_wait": "Introduce una URL de vídeo de YouTube", "preview.ready_queue": "Listo para agregar a la cola", "preview.channel": "Canal: {uploader}", "resolution.best": "Mejor", "startup.tray": "Bandeja del sistema", "startup.taskbar": "Barra de tareas", "startup.both": "Bandeja y barra", "time.none": "ninguno", "time.just_now": "ahora mismo", "time.ago": "hace {value}", "easter.select_harvester": "Selecciona el harvester", "easter.ready": "Harvester listo", "easter.moving": "Rumbo al YouTubium", "easter.full": "Carga llena. ¡A la base!", "easter.loaded_all": "YouTubium cargado. ¡A la base!", "easter.arrived": "Llegó", "easter.loaded": "YouTubium cargado: {cargo}/{capacity}", "easter.unloaded": "YouTubium descargado: {delivered}/{total}", "easter.resource": "YouTubium {delivered}/{total}", "easter.cargo": "Carga {cargo}/{capacity}", "easter.victory_ready": "YTuHa está listo para cosechar",
    },
    "hi": {
        "app.language": "भाषा", "tab.overview": "📊 अवलोकन", "tab.channels": "📺 चैनल", "tab.queue": "📥 कतार", "tab.settings": "⚙ सेटिंग्स", "tab.diagnostics": "डायग्नोस्टिक्स",
        "status.channels": "चैनल", "status.queue": "कतार", "status.archive": "आर्काइव", "button.add_queue": "कतार में जोड़ें", "button.queue_short": "कतार", "button.download": "डाउनलोड", "button.cancel": "रद्द करें", "button.refresh": "रीफ्रेश", "settings.download": "डाउनलोड", "settings.behavior": "व्यवहार", "settings.watch_clipboard": "क्लिपबोर्ड देखें", "settings.autostart": "🚀 ऑटोस्टार्ट", "settings.misc": "⚙ अन्य", "logs.title": "लॉग", "logs.all": "सभी", "logs.important": "महत्वपूर्ण", "logs.errors": "त्रुटियां", "channels.check": "🔎 चैनल जांचें", "channels.check_paid": "पेड कंटेंट जांचें", "queue.planner": "शेड्यूलर", "queue.video_queue": "वीडियो कतार", "telegram.enabled": "🔔 सूचनाएं चालू", "telegram.disabled": "🔕 सूचनाएं बंद", "quick.title": "त्वरित डाउनलोड", "quick.download_now": "अभी डाउनलोड करें", "archive.title": "आर्काइव", "archive.heading": "🗃 डाउनलोड आर्काइव", "archive.type": "प्रकार", "archive.channel": "चैनल", "archive.name": "शीर्षक", "archive.date": "तारीख", "archive.file": "🎬 फ़ाइल", "archive.folder": "📁 फ़ोल्डर", "archive.delete": "🗑 हटाएं", "preview.thumbnail": "थंबनेल", "preview.quick_wait": "YouTube लिंक की प्रतीक्षा", "preview.queue_wait": "YouTube वीडियो URL दर्ज करें", "preview.ready_queue": "कतार में जोड़ने के लिए तैयार", "preview.channel": "चैनल: {uploader}", "resolution.best": "सर्वश्रेष्ठ", "startup.tray": "सिस्टम ट्रे", "startup.taskbar": "टास्कबार", "startup.both": "ट्रे और टास्कबार", "time.none": "नहीं", "time.just_now": "अभी", "time.ago": "{value} पहले", "easter.select_harvester": "हार्वेस्टर चुनें", "easter.ready": "हार्वेस्टर तैयार", "easter.moving": "YouTubium की ओर जा रहा है", "easter.full": "कार्गो पूरा। बेस पर लौटें!", "easter.loaded_all": "YouTubium लोड हो गया। बेस पर लौटें!", "easter.arrived": "पहुंच गया", "easter.loaded": "YouTubium लोड: {cargo}/{capacity}", "easter.unloaded": "YouTubium उतारा: {delivered}/{total}", "easter.resource": "YouTubium {delivered}/{total}", "easter.cargo": "कार्गो {cargo}/{capacity}", "easter.victory_ready": "YTuHa कटाई के लिए तैयार है",
    },
    "zh": {
        "app.language": "语言", "tab.overview": "📊 概览", "tab.channels": "📺 频道", "tab.queue": "📥 队列", "tab.settings": "⚙ 设置", "tab.diagnostics": "诊断",
        "status.channels": "频道", "status.queue": "队列", "status.archive": "归档", "button.add_queue": "加入队列", "button.queue_short": "队列", "button.download": "下载", "button.cancel": "取消", "button.refresh": "刷新", "settings.download": "下载", "settings.behavior": "行为", "settings.watch_clipboard": "监视剪贴板", "settings.autostart": "🚀 自动启动", "settings.misc": "⚙ 其他", "logs.title": "日志", "logs.all": "全部", "logs.important": "重要", "logs.errors": "错误", "channels.check": "🔎 检查频道", "channels.check_paid": "检查付费内容", "queue.planner": "计划任务", "queue.video_queue": "视频队列", "telegram.enabled": "🔔 通知已开启", "telegram.disabled": "🔕 通知已关闭", "quick.title": "快速下载", "quick.download_now": "立即下载", "archive.title": "归档", "archive.heading": "🗃 下载归档", "archive.type": "类型", "archive.channel": "频道", "archive.name": "标题", "archive.date": "日期", "archive.file": "🎬 文件", "archive.folder": "📁 文件夹", "archive.delete": "🗑 删除", "preview.thumbnail": "缩略图", "preview.quick_wait": "等待 YouTube 链接", "preview.queue_wait": "输入 YouTube 视频 URL", "preview.ready_queue": "可以加入队列", "preview.channel": "频道：{uploader}", "resolution.best": "最佳", "startup.tray": "系统托盘", "startup.taskbar": "任务栏", "startup.both": "托盘和任务栏", "time.none": "无", "time.just_now": "刚刚", "time.ago": "{value}前", "easter.select_harvester": "选择采矿车", "easter.ready": "采矿车就绪", "easter.moving": "前往 YouTubium", "easter.full": "货仓已满，返回基地！", "easter.loaded_all": "YouTubium 已装载，返回基地！", "easter.arrived": "已到达", "easter.loaded": "YouTubium 已装载：{cargo}/{capacity}", "easter.unloaded": "YouTubium 已卸载：{delivered}/{total}", "easter.resource": "YouTubium {delivered}/{total}", "easter.cargo": "货物 {cargo}/{capacity}", "easter.victory_ready": "YTuHa 已准备好收割",
    },
    "ar": {
        "app.language": "اللغة", "tab.overview": "📊 نظرة عامة", "tab.channels": "📺 القنوات", "tab.queue": "📥 قائمة الانتظار", "tab.settings": "⚙ الإعدادات", "tab.diagnostics": "التشخيص",
        "status.channels": "القنوات", "status.queue": "الانتظار", "status.archive": "الأرشيف", "button.add_queue": "إضافة إلى الانتظار", "button.queue_short": "إلى الانتظار", "button.download": "تنزيل", "button.cancel": "إلغاء", "button.refresh": "تحديث", "settings.download": "التنزيل", "settings.behavior": "السلوك", "settings.watch_clipboard": "مراقبة الحافظة", "settings.autostart": "🚀 تشغيل تلقائي", "settings.misc": "⚙ أخرى", "logs.title": "السجلات", "logs.all": "الكل", "logs.important": "المهم", "logs.errors": "الأخطاء", "channels.check": "🔎 فحص القنوات", "channels.check_paid": "فحص المحتوى المدفوع", "queue.planner": "المجدول", "queue.video_queue": "قائمة الفيديو", "telegram.enabled": "🔔 الإشعارات مفعلة", "telegram.disabled": "🔕 الإشعارات معطلة", "quick.title": "تنزيل سريع", "quick.download_now": "تنزيل الآن", "archive.title": "الأرشيف", "archive.heading": "🗃 أرشيف التنزيلات", "archive.type": "النوع", "archive.channel": "القناة", "archive.name": "العنوان", "archive.date": "التاريخ", "archive.file": "🎬 الملف", "archive.folder": "📁 المجلد", "archive.delete": "🗑 حذف", "preview.thumbnail": "الصورة المصغرة", "preview.quick_wait": "بانتظار رابط YouTube", "preview.queue_wait": "أدخل رابط فيديو YouTube", "preview.ready_queue": "جاهز للإضافة إلى الانتظار", "preview.channel": "القناة: {uploader}", "resolution.best": "الأفضل", "startup.tray": "علبة النظام", "startup.taskbar": "شريط المهام", "startup.both": "العلبة وشريط المهام", "time.none": "لا يوجد", "time.just_now": "الآن", "time.ago": "منذ {value}", "easter.select_harvester": "اختر الحاصدة", "easter.ready": "الحاصدة جاهزة", "easter.moving": "متجه إلى YouTubium", "easter.full": "الحمولة ممتلئة. عودة إلى القاعدة!", "easter.loaded_all": "تم تحميل YouTubium. عودة إلى القاعدة!", "easter.arrived": "وصل", "easter.loaded": "تم تحميل YouTubium: {cargo}/{capacity}", "easter.unloaded": "تم تفريغ YouTubium: {delivered}/{total}", "easter.resource": "YouTubium {delivered}/{total}", "easter.cargo": "الحمولة {cargo}/{capacity}", "easter.victory_ready": "YTuHa جاهز للحصاد",
    },
}
for _language_code, _translations in LOCALE_TRANSLATIONS.items():
    I18N_COMMON[_language_code] = {**I18N_COMMON.get(_language_code, {}), **_translations}
for _language_code, _overrides in I18N_COMMON.items():
    I18N[_language_code] = {**I18N_EN, **I18N.get(_language_code, {}), **_overrides}
for _language_code, _translations in LOCALE_TRANSLATIONS.items():
    I18N.setdefault(_language_code, {**I18N_EN}).update(_translations)


def normalize_language(value) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    if text.startswith("zh"):
        return "zh"
    if text.startswith("ja"):
        return "ja"
    if text.startswith("ar"):
        return "ar"
    if text.startswith("hi"):
        return "hi"
    if text.startswith("es"):
        return "es"
    if text.startswith("fr"):
        return "fr"
    if text.startswith("ru"):
        return "ru"
    if text.startswith("uk"):
        return "uk"
    return text if text in VALID_LANGUAGES else "en"


def ui_text(language: str, key: str, **values) -> str:
    text = I18N.get(normalize_language(language), I18N_EN).get(key, I18N_EN.get(key, key))
    try:
        return text.format(**values)
    except Exception:
        return text


def localized_resolution_options(language: str):
    return tuple((ui_text(language, "resolution.best") if value == "best" else label, value) for label, value in RESOLUTION_OPTIONS)


def media_audio_track_name(media_format: dict) -> str:
    audio_track = media_format.get("audio_track") if isinstance(media_format.get("audio_track"), dict) else {}
    name = str(audio_track.get("display_name") or audio_track.get("name") or "").strip()
    if name:
        return fix_mojibake(name)
    note_parts = [part.strip() for part in str(media_format.get("format_note") or "").split(",")]
    descriptive = [
        part
        for part in note_parts
        if part.casefold() not in {"low", "medium", "high", "default"}
        and not re.fullmatch(r"\d{3,4}p(?:\d+)?", part, re.IGNORECASE)
    ]
    return fix_mojibake(descriptive[0] if descriptive else "")


def media_language_root(value: str) -> str:
    return str(value or "und").strip().casefold().replace("_", "-").split("-", 1)[0]


def media_option_sort_key(option: dict) -> tuple:
    language = str(option.get("language") or "und").strip()
    root = media_language_root(language)
    if root in {"ru", "en", "uk"}:
        priority = ("ru", "en", "uk").index(root)
    elif root in PRIORITY_LANGUAGE_RANK:
        priority = 3
    else:
        priority = 4
    display_name = str(option.get("name") or language).casefold()
    return (priority, display_name, language.casefold())


def prioritized_media_sections(options: list[dict]) -> tuple[list[dict], list[dict]]:
    original = []
    preferred = []
    remaining = []
    for option in options:
        if option.get("is_original") or option.get("mode") == "manual":
            original.append(option)
        elif media_language_root(option.get("language")) in PRIORITY_LANGUAGE_RANK:
            preferred.append(option)
        else:
            remaining.append(option)
    first_section = sorted(original, key=media_option_sort_key) + sorted(preferred, key=media_option_sort_key)
    return first_section, sorted(remaining, key=media_option_sort_key)


def subtitle_media_sections(options: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    manual = sorted(
        (option for option in options if option.get("mode") == "manual"),
        key=media_option_sort_key,
    )
    automatic = [option for option in options if option.get("mode") != "manual"]
    preferred_automatic, other_automatic = prioritized_media_sections(automatic)
    return manual, preferred_automatic, other_automatic


def audio_track_options(metadata: dict) -> list[dict]:
    selected: dict[tuple[str, str], tuple[tuple[int, int, float, int], dict]] = {}
    for media_format in metadata.get("formats") or []:
        if not isinstance(media_format, dict):
            continue
        if media_format.get("vcodec") != "none" or media_format.get("acodec") in {None, "none"}:
            continue
        format_id = str(media_format.get("format_id") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]+", format_id):
            continue
        language = str(media_format.get("language") or "und").strip()
        name = media_audio_track_name(media_format)
        format_note = str(media_format.get("format_note") or "")
        try:
            language_preference = float(media_format.get("language_preference") or 0)
        except (TypeError, ValueError):
            language_preference = 0.0
        key = (language.casefold(), name.casefold())
        try:
            abr = float(media_format.get("abr") or media_format.get("tbr") or 0)
        except (TypeError, ValueError):
            abr = 0.0
        try:
            sample_rate = int(float(media_format.get("asr") or 0))
        except (TypeError, ValueError):
            sample_rate = 0
        score = (
            0 if re.search(r"\bDRC\b", str(media_format.get("format_note") or ""), re.IGNORECASE) else 1,
            1 if str(media_format.get("ext") or "").lower() == "m4a" else 0,
            abr,
            sample_rate,
        )
        option = {
            "format_id": format_id,
            "format_kind": "audio",
            "language": language,
            "name": name,
            "is_original": bool(
                re.search(r"\boriginal\b|\(default\)", format_note, re.IGNORECASE)
                or language_preference > 0
            ),
        }
        if key not in selected or score > selected[key][0]:
            selected[key] = (score, option)

    audio_language_roots = {key[0].split("-", 1)[0] for key in selected}
    combined: dict[tuple[str, str], dict] = {}
    for media_format in metadata.get("formats") or []:
        if not isinstance(media_format, dict):
            continue
        if media_format.get("vcodec") in {None, "none"} or media_format.get("acodec") in {None, "none"}:
            continue
        format_id = str(media_format.get("format_id") or "").strip()
        language = str(media_format.get("language") or "").strip()
        if not language or not re.fullmatch(r"[A-Za-z0-9._-]+", format_id):
            continue
        name = media_audio_track_name(media_format)
        format_note = str(media_format.get("format_note") or "")
        try:
            language_preference = float(media_format.get("language_preference") or 0)
        except (TypeError, ValueError):
            language_preference = 0.0
        if not name and language.casefold().split("-", 1)[0] in audio_language_roots:
            continue
        try:
            height = int(media_format.get("height") or 0)
        except (TypeError, ValueError):
            height = 0
        try:
            bitrate = float(media_format.get("tbr") or 0)
        except (TypeError, ValueError):
            bitrate = 0.0
        key = (language.casefold(), name.casefold())
        option = combined.setdefault(key, {
            "format_id": "",
            "format_kind": "combined",
            "language": language,
            "name": name,
            "is_original": bool(
                re.search(r"\boriginal\b|\(default\)", format_note, re.IGNORECASE)
                or language_preference > 0
            ),
            "formats": [],
        })
        option["formats"].append({
            "format_id": format_id,
            "height": height,
            "ext": str(media_format.get("ext") or ""),
            "tbr": bitrate,
        })

    options = [item[1] for item in selected.values()] + list(combined.values())
    first_section, remaining = prioritized_media_sections(options)
    return first_section + remaining


def resolve_audio_track_option(track: dict, resolution: str) -> dict:
    option = dict(track or {})
    if option.get("format_kind") != "combined":
        return option
    formats = [item for item in option.get("formats") or [] if isinstance(item, dict) and item.get("format_id")]
    if not formats:
        return {}
    try:
        target_height = int(resolution)
    except (TypeError, ValueError):
        target_height = 0
    eligible = [item for item in formats if not target_height or 0 < int(item.get("height") or 0) <= target_height]
    if target_height and not eligible:
        selected_format = min(formats, key=lambda item: int(item.get("height") or 0) or sys.maxsize)
    else:
        selected_format = max(
            eligible or formats,
            key=lambda item: (
                int(item.get("height") or 0),
                1 if str(item.get("ext") or "").casefold() == "mp4" else 0,
                float(item.get("tbr") or 0),
            ),
        )
    option["format_id"] = str(selected_format.get("format_id") or "")
    option["selected_height"] = int(selected_format.get("height") or 0)
    return option


def subtitle_track_options(metadata: dict) -> list[dict]:
    options: list[dict] = []
    for mode, key in (("manual", "subtitles"), ("auto", "automatic_captions")):
        tracks = metadata.get(key) or {}
        if not isinstance(tracks, dict):
            continue
        for language, formats in tracks.items():
            language = str(language or "").strip()
            if not language or language == "live_chat":
                continue
            name = ""
            if isinstance(formats, list):
                first = next((item for item in formats if isinstance(item, dict)), {})
                name = str(first.get("name") or "").strip()
            options.append({
                "selection": f"{mode}:{language}",
                "language": language,
                "name": fix_mojibake(name),
                "mode": mode,
                "is_original": mode == "manual",
            })
    first_section, remaining = prioritized_media_sections(options)
    return first_section + remaining


def localized_startup_display_modes(language: str):
    return (
        (ui_text(language, "startup.tray"), "tray"),
        (ui_text(language, "startup.taskbar"), "taskbar"),
        (ui_text(language, "startup.both"), "both"),
    )

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


def script_check_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setPen(QPen(QColor("#1f6fb2"), 3))
    painter.setBrush(QColor("#eef7ff"))
    page = QPainterPath()
    page.moveTo(17, 8)
    page.lineTo(41, 8)
    page.lineTo(51, 18)
    page.lineTo(51, 56)
    page.lineTo(17, 56)
    page.closeSubpath()
    painter.drawPath(page)

    painter.setBrush(QColor("#d4ecff"))
    painter.drawPolygon(QPoint(41, 8), QPoint(51, 18), QPoint(41, 18))

    painter.setPen(QPen(QColor("#21445f"), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawLine(24, 29, 31, 36)
    painter.drawLine(31, 36, 24, 43)
    painter.drawLine(36, 43, 44, 43)

    painter.setPen(QPen(QColor("#2a9d62"), 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawLine(43, 50, 49, 56)
    painter.drawLine(49, 56, 61, 42)
    painter.end()
    return QIcon(pixmap)


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
        with contextlib.suppress(Exception):
            ctypes.windll.user32.UnregisterHotKey(self.hwnd, self.hotkey_id)
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
            self.last_error = "hotkey.convert_failed"
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
        with contextlib.suppress(Exception):
            self.listener.stop()
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

    def eventFilter(self, _obj, event):
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


class LauncherSignals(QObject):
    script_error = pyqtSignal(str)
    script_finished = pyqtSignal()


USAGE_RULES_HTML_EN = f"""
<h2>{APP_NAME}: usage rules</h2>
<p><b>Important:</b> this app is not affiliated with YouTube, Google, Telegram, or yt-dlp.
It is a local wrapper that launches external tools on your computer.</p>

<h3>What you need to understand</h3>
<ul>
  <li>Download only materials for which you have rights, permission from the author,
      or a lawful basis for personal use.</li>
  <li>Follow YouTube Terms of Service, copyright law, and the laws of your country.</li>
  <li>Do not use the app to bypass access restrictions, mass-copy content, distribute piracy,
      sell downloaded materials, or publicly rebroadcast someone else's content.</li>
  <li>Telegram notifications may send titles, links, and files to the selected channel.
      Keep BOT_TOKEN and CHANNEL_ID private.</li>
  <li>You are responsible for selected channels, the queue, downloaded files, and further use.</li>
</ul>

<h3>External components</h3>
<ul>
  <li><b>yt-dlp</b> reads pages and downloads media files.</li>
  <li><b>PyQt5/Qt</b> powers the graphical interface.</li>
  <li><b>curl</b> is used for Telegram notifications with SOCKS proxy mode.</li>
  <li><b>pynput</b> is used for the global hotkey on Linux/X11.</li>
  <li><b>Bash engine</b> remains in the source tree as legacy code, but is disabled in the UI and not used.</li>
</ul>

<p>Every external component has its own license and documentation.
README contains links to the main rules and projects.</p>
"""

USAGE_RULES_HTML_RU = f"""
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


USAGE_RULES_HTML = {
    "en": USAGE_RULES_HTML_EN,
    "ru": USAGE_RULES_HTML_RU,
    "uk": f"""
<h2>{APP_NAME}: правила використання</h2>
<p><b>Важливо:</b> програма не пов'язана з YouTube, Google, Telegram або yt-dlp. Це локальна оболонка, що запускає зовнішні інструменти на вашому комп'ютері.</p>
<h3>Що варто розуміти</h3><ul><li>Завантажуйте лише матеріали, на які маєте права, дозвіл автора або законні підстави для особистого використання.</li><li>Дотримуйтеся правил YouTube, авторського права та законів своєї країни.</li><li>Не використовуйте програму для обходу обмежень доступу, масового копіювання, піратства, продажу чи публічної трансляції чужого контенту.</li><li>Telegram-сповіщення можуть надсилати назви, посилання та файли. Бережіть BOT_TOKEN і CHANNEL_ID.</li><li>Ви самостійно відповідаєте за канали, чергу, файли та їх використання.</li></ul>
<h3>Зовнішні компоненти</h3><ul><li><b>yt-dlp</b> читає сторінки та завантажує медіа.</li><li><b>PyQt5/Qt</b> забезпечує графічний інтерфейс.</li><li><b>curl</b> використовується для Telegram через SOCKS-проксі.</li><li><b>pynput</b> використовується для глобальної гарячої клавіші у Linux/X11.</li><li><b>Bash-рушій</b> залишено як застарілий код, але вимкнено в інтерфейсі.</li></ul><p>Кожен компонент має власну ліцензію та документацію. Посилання є в README.</p>""",
    "fr": f"""
<h2>{APP_NAME} : règles d'utilisation</h2>
<p><b>Important :</b> cette application n'est affiliée ni à YouTube, ni à Google, Telegram ou yt-dlp. C'est une interface locale qui lance des outils externes sur votre ordinateur.</p>
<h3>À comprendre</h3><ul><li>Téléchargez uniquement les contenus pour lesquels vous avez les droits, l'autorisation de l'auteur ou une base légale d'usage personnel.</li><li>Respectez les règles de YouTube, le droit d'auteur et les lois de votre pays.</li><li>N'utilisez pas l'application pour contourner des restrictions, copier massivement, diffuser illégalement, vendre ou rediffuser le contenu d'autrui.</li><li>Les notifications Telegram peuvent envoyer titres, liens et fichiers. Gardez BOT_TOKEN et CHANNEL_ID privés.</li><li>Vous êtes responsable des chaînes, de la file, des fichiers téléchargés et de leur utilisation.</li></ul>
<h3>Composants externes</h3><ul><li><b>yt-dlp</b> lit les pages et télécharge les médias.</li><li><b>PyQt5/Qt</b> fournit l'interface graphique.</li><li><b>curl</b> sert aux notifications Telegram avec proxy SOCKS.</li><li><b>pynput</b> sert au raccourci global sous Linux/X11.</li><li>Le <b>moteur Bash</b> reste dans les sources comme code historique, mais est désactivé.</li></ul><p>Chaque composant a sa licence et sa documentation. Les liens figurent dans le README.</p>""",
    "es": f"""
<h2>{APP_NAME}: reglas de uso</h2>
<p><b>Importante:</b> esta aplicación no está afiliada a YouTube, Google, Telegram ni yt-dlp. Es una interfaz local que ejecuta herramientas externas en tu equipo.</p>
<h3>Lo que debes saber</h3><ul><li>Descarga solo materiales para los que tengas derechos, permiso del autor o una base legal de uso personal.</li><li>Respeta las reglas de YouTube, los derechos de autor y las leyes de tu país.</li><li>No uses la aplicación para eludir restricciones, copiar masivamente, distribuir piratería, vender o retransmitir contenido ajeno.</li><li>Las notificaciones de Telegram pueden enviar títulos, enlaces y archivos. Mantén privados BOT_TOKEN y CHANNEL_ID.</li><li>Eres responsable de los canales, la cola, los archivos descargados y su uso posterior.</li></ul>
<h3>Componentes externos</h3><ul><li><b>yt-dlp</b> lee páginas y descarga medios.</li><li><b>PyQt5/Qt</b> proporciona la interfaz gráfica.</li><li><b>curl</b> se usa para Telegram con proxy SOCKS.</li><li><b>pynput</b> se usa para el atajo global en Linux/X11.</li><li>El <b>motor Bash</b> queda como código heredado, pero está desactivado.</li></ul><p>Cada componente tiene su licencia y documentación. Los enlaces están en el README.</p>""",
    "hi": f"""
<h2>{APP_NAME}: उपयोग के नियम</h2>
<p><b>महत्वपूर्ण:</b> यह ऐप YouTube, Google, Telegram या yt-dlp से संबद्ध नहीं है। यह आपके कंप्यूटर पर बाहरी उपकरण चलाने वाला स्थानीय इंटरफ़ेस है।</p>
<h3>ध्यान रखने योग्य बातें</h3><ul><li>केवल वही सामग्री डाउनलोड करें जिसके लिए आपके पास अधिकार, लेखक की अनुमति या निजी उपयोग का कानूनी आधार हो।</li><li>YouTube के नियम, कॉपीराइट कानून और अपने देश के कानूनों का पालन करें।</li><li>ऐप का उपयोग पहुँच प्रतिबंधों को दरकिनार करने, बड़े पैमाने पर कॉपी करने, पायरेसी फैलाने, बेचने या दूसरे के कंटेंट के सार्वजनिक प्रसारण के लिए न करें।</li><li>Telegram सूचनाएँ शीर्षक, लिंक और फ़ाइलें भेज सकती हैं। BOT_TOKEN और CHANNEL_ID को निजी रखें।</li><li>चैनलों, कतार, डाउनलोड की गई फ़ाइलों और उनके उपयोग के लिए आप जिम्मेदार हैं।</li></ul>
<h3>बाहरी घटक</h3><ul><li><b>yt-dlp</b> पेज पढ़ता है और मीडिया डाउनलोड करता है।</li><li><b>PyQt5/Qt</b> ग्राफिकल इंटरफ़ेस देता है।</li><li><b>curl</b> SOCKS प्रॉक्सी के साथ Telegram के लिए उपयोग होता है।</li><li><b>pynput</b> Linux/X11 में ग्लोबल हॉटकी के लिए उपयोग होता है।</li><li><b>Bash इंजन</b> पुराने कोड के रूप में है, लेकिन बंद है।</li></ul><p>हर घटक का अपना लाइसेंस और दस्तावेज़ है। लिंक README में हैं।</p>""",
    "zh": f"""
<h2>{APP_NAME}：使用规则</h2>
<p><b>重要：</b>本应用与 YouTube、Google、Telegram 或 yt-dlp 没有隶属关系。它是在您的电脑上运行外部工具的本地界面。</p>
<h3>需要了解的事项</h3><ul><li>仅下载您拥有权利、获得作者许可或有合法个人使用依据的内容。</li><li>请遵守 YouTube 规则、版权法和您所在国家/地区的法律。</li><li>请勿用本应用绕过访问限制、大规模复制、传播盗版、出售或公开转播他人的内容。</li><li>Telegram 通知可能发送标题、链接和文件。请妥善保管 BOT_TOKEN 和 CHANNEL_ID。</li><li>您需要自行负责频道、队列、下载文件及其后续使用。</li></ul>
<h3>外部组件</h3><ul><li><b>yt-dlp</b> 读取页面并下载媒体。</li><li><b>PyQt5/Qt</b> 提供图形界面。</li><li><b>curl</b> 用于通过 SOCKS 代理发送 Telegram 通知。</li><li><b>pynput</b> 用于 Linux/X11 的全局快捷键。</li><li><b>Bash 引擎</b> 作为旧代码保留，但已禁用。</li></ul><p>每个组件都有自己的许可证和文档。README 中包含相关链接。</p>""",
    "ja": f"""
<h2>{APP_NAME}: 利用規約</h2>
<p><b>重要:</b> 本アプリは YouTube、Google、Telegram、yt-dlp のいずれとも提携していません。お使いのコンピューター上で外部ツールを実行するローカルインターフェースです。</p>
<h3>ご理解いただきたいこと</h3><ul><li>権利を所有している、作者の許可を得ている、または個人利用の法的根拠がある素材のみをダウンロードしてください。</li><li>YouTube の利用規約、著作権法、お住まいの国の法律を遵守してください。</li><li>アクセス制限の回避、大量複製、海賊版の配布、他者のコンテンツの販売や公開再配信に本アプリを使用しないでください。</li><li>Telegram 通知はタイトル、リンク、ファイルを送信する場合があります。BOT_TOKEN と CHANNEL_ID は公開しないでください。</li><li>選択したチャンネル、キュー、ダウンロードしたファイル、およびその利用については利用者が責任を負います。</li></ul>
<h3>外部コンポーネント</h3><ul><li><b>yt-dlp</b> はページを読み取り、メディアをダウンロードします。</li><li><b>PyQt5/Qt</b> はグラフィカルインターフェースを提供します。</li><li><b>curl</b> は SOCKS プロキシ経由の Telegram 通知に使用されます。</li><li><b>pynput</b> は Linux/X11 のグローバルホットキーに使用されます。</li><li><b>Bash エンジン</b> は旧コードとして残されていますが、無効化され使用されません。</li></ul><p>各外部コンポーネントには独自のライセンスとドキュメントがあります。主な規約とプロジェクトへのリンクは README にあります。</p>""",
    "ar": f"""
<h2>{APP_NAME}: قواعد الاستخدام</h2>
<p><b>مهم:</b> هذا التطبيق غير تابع لـ YouTube أو Google أو Telegram أو yt-dlp. إنه واجهة محلية تشغّل أدوات خارجية على جهازك.</p>
<h3>ما يجب معرفته</h3><ul><li>نزّل فقط المواد التي تملك حقوقها أو إذن المؤلف أو أساسًا قانونيًا لاستخدامها الشخصي.</li><li>التزم بقواعد YouTube وقانون حقوق النشر وقوانين بلدك.</li><li>لا تستخدم التطبيق لتجاوز القيود أو النسخ الجماعي أو القرصنة أو البيع أو البث العلني لمحتوى الآخرين.</li><li>قد ترسل إشعارات Telegram العناوين والروابط والملفات. حافظ على خصوصية BOT_TOKEN و CHANNEL_ID.</li><li>أنت مسؤول عن القنوات وقائمة الانتظار والملفات المنزّلة واستخدامها لاحقًا.</li></ul>
<h3>المكونات الخارجية</h3><ul><li><b>yt-dlp</b> يقرأ الصفحات وينزّل الوسائط.</li><li><b>PyQt5/Qt</b> يوفر الواجهة الرسومية.</li><li><b>curl</b> يستخدم لـ Telegram عبر وكيل SOCKS.</li><li><b>pynput</b> يستخدم للاختصار العام في Linux/X11.</li><li>يبقى <b>محرك Bash</b> ككود قديم، لكنه معطل.</li></ul><p>لكل مكون ترخيصه ووثائقه. توجد الروابط في README.</p>""",
}


def usage_rules_html(language: str) -> str:
    return USAGE_RULES_HTML.get(normalize_language(language), USAGE_RULES_HTML_EN)


class UsageRulesDialog(QDialog):
    def __init__(self, required: bool, parent=None, language: str = "en"):
        super().__init__(parent)
        self.language = normalize_language(language)
        self.setWindowTitle(ui_text(self.language, "dialog.usage_rules"))
        self.setModal(True)
        self.setMinimumSize(620, 500)
        self.required = required

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(usage_rules_html(self.language))
        layout.addWidget(text, 1)

        self.checkboxes = []
        if required:
            for label in (
                ui_text(self.language, "usage.check_1"),
                ui_text(self.language, "usage.check_2"),
                ui_text(self.language, "usage.check_3"),
            ):
                checkbox = QCheckBox(label)
                checkbox.stateChanged.connect(self.update_accept_button)
                self.checkboxes.append(checkbox)
                layout.addWidget(checkbox)

        buttons = QDialogButtonBox(
            (QDialogButtonBox.Ok | QDialogButtonBox.Cancel) if required else QDialogButtonBox.Close
        )
        if required:
            buttons.button(QDialogButtonBox.Ok).setText(ui_text(self.language, "dialog.accept"))
            buttons.button(QDialogButtonBox.Cancel).setText(ui_text(self.language, "dialog.decline"))
            buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        else:
            buttons.button(QDialogButtonBox.Close).setText(ui_text(self.language, "dialog.close"))
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
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
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
        self.easter_assets = EasterAssetBundle(
            Path(os.environ.get("YTD_EASTER_BUNDLE", self.app_dir / "assets" / "ui.dat")),
            self.cache_dir / ".ui",
        )
        self.easter_map_path = self.easter_assets.file(
            "map",
            os.environ.get("YTD_EASTER_MAP", self.app_dir / "assets" / "ui-00.jpg"),
        )
        self.easter_harvester_path = self.easter_assets.file(
            "harvester",
            os.environ.get("YTD_EASTER_HARVESTER", self.app_dir / "assets" / "ui-01.png"),
        )
        self.easter_crystal_path = self.easter_assets.file(
            "crystals",
            os.environ.get("YTD_EASTER_CRYSTALS", self.app_dir / "assets" / "ui-02.png"),
        )
        self.easter_tree_overlay_path = self.easter_assets.file(
            "tree",
            os.environ.get("YTD_EASTER_TREE", self.app_dir / "assets" / "ui-03.png"),
        )
        self.easter_victory_logo_path = self.easter_assets.file(
            "victory_logo",
            os.environ.get("YTD_EASTER_VICTORY_LOGO", self.app_dir / "assets" / "ui-04.png"),
        )
        self.easter_reporting_sound_paths = self.easter_assets.files(
            "reporting",
            (
                self.app_dir / "assets" / "ui-10.wav",
                self.app_dir / "assets" / "ui-11.wav",
            ),
        )
        self.easter_acknowledge_sound_paths = self.easter_assets.files(
            "acknowledge",
            (
                self.app_dir / "assets" / "ui-12.wav",
                self.app_dir / "assets" / "ui-13.wav",
            ),
        )
        self.easter_victory_sound_paths = self.easter_assets.files(
            "victory_sound",
            (
                Path(os.environ.get("YTD_EASTER_VICTORY_SOUND", self.app_dir / "assets" / "ui-14.wav")),
            ),
        )
        self.ffmpeg_dir = self.detect_ffmpeg_dir()
        self.deno_path = self.detect_deno_path()
        self.is_running = False
        self.state = "idle"
        self.current_process = None
        self.signals = LauncherSignals()
        self.signals.script_error.connect(self.on_script_error)
        self.signals.script_finished.connect(self.on_script_finished)

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
        self.quick_resolution_override = ""
        self.quick_audio_overrides = []
        self.quick_subtitle_overrides = []
        self.clipboard_last_url = ""
        self.clipboard_last_trigger_at = 0.0
        self.clipboard_check_pending = False
        with contextlib.suppress(Exception):
            self.app.clipboard().dataChanged.connect(self.on_clipboard_changed)
        self.last_tray_trigger_at = 0.0
        if self.app_icon_path.exists():
            self.app.setWindowIcon(QIcon(str(self.app_icon_path)))

        self.tray = QSystemTrayIcon(self.app)
        self.create_menu()
        self.update_icon()
        if self.tray_available:
            self.tray.show()

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_process_status)
        self.timer.start(1000)

        self.schedule_timer = QTimer()
        self.schedule_timer.timeout.connect(self.check_schedules)
        self.schedule_timer.start(15000)

        self.clipboard_timer = QTimer()
        self.clipboard_timer.setInterval(1200)
        self.clipboard_timer.timeout.connect(self.check_clipboard_for_quick_download)
        self.refresh_clipboard_watch_timer()

        self.load_schedules()
        self.setup_global_hotkey()
        self.app.aboutToQuit.connect(self.cleanup_global_hotkey)
        QTimer.singleShot(1500, self.cleanup_cache)
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
        self.tray_status_action = menu.addAction(self.tr("tray.status.idle"))
        self.tray_status_action.setEnabled(False)
        menu.addSeparator()

        self.tray_overview_action = menu.addAction(self.tr("tab.overview"))
        self.tray_overview_action.triggered.connect(lambda checked=False: self.open_main_window(0))
        self.tray_channels_action = menu.addAction(self.tr("tab.channels"))
        self.tray_channels_action.triggered.connect(lambda checked=False: self.open_main_window(1))
        self.tray_queue_action = menu.addAction(self.tr("tab.queue"))
        self.tray_queue_action.triggered.connect(lambda checked=False: self.open_main_window(2))
        self.tray_settings_action = menu.addAction(self.tr("tab.settings"))
        self.tray_settings_action.triggered.connect(lambda checked=False: self.open_main_window(3))
        menu.addSeparator()

        self.quick_download_action = menu.addAction(self.tr("tray.quick_download", hotkey=self.quick_download_hotkey))
        self.quick_download_action.triggered.connect(lambda checked=False: self.open_quick_download_window())
        self.tray_start_action = menu.addAction(self.tr("tray.start"))
        self.tray_start_action.triggered.connect(self.run_script)
        self.tray_stop_action = menu.addAction(self.tr("tray.stop"))
        self.tray_stop_action.triggered.connect(self.request_stop)
        menu.addSeparator()

        self.tray_downloads_action = menu.addAction(self.tr("tray.downloads"))
        self.tray_downloads_action.triggered.connect(lambda checked=False: self.open_path(self.final_dir))
        self.tray_temp_action = menu.addAction(self.tr("tray.temp"))
        self.tray_temp_action.triggered.connect(lambda checked=False: self.open_path(self.temp_dir))
        menu.addSeparator()

        self.tray_exit_action = menu.addAction(self.tr("tray.exit"))
        self.tray_exit_action.triggered.connect(self.app.quit)

        self.tray_menu = menu
        menu.aboutToShow.connect(self.update_tray_menu)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_clicked)
        self.update_tray_menu()

    def update_tray_menu(self):
        if not hasattr(self, "tray_status_action"):
            return
        if self.state == "stopping":
            status_text = self.tr("tray.status.stopping")
        elif self.is_running:
            status_text = self.tr("tray.status.downloading")
        elif glob.glob(str(self.temp_dir / "*.part")):
            status_text = self.tr("tray.status.partial")
        else:
            status_text = self.tr("tray.status.idle")

        self.tray_status_action.setText(status_text)
        self.tray_overview_action.setText(self.tr("tab.overview"))
        self.tray_channels_action.setText(self.tr("tab.channels"))
        self.tray_queue_action.setText(self.tr("tab.queue"))
        self.tray_settings_action.setText(self.tr("tab.settings"))
        self.quick_download_action.setText(self.tr("tray.quick_download", hotkey=self.quick_download_hotkey))
        self.tray_start_action.setText(self.tr("tray.start"))
        self.tray_stop_action.setText(self.tr("tray.stop"))
        self.tray_downloads_action.setText(self.tr("tray.downloads"))
        self.tray_temp_action.setText(self.tr("tray.temp"))
        self.tray_exit_action.setText(self.tr("tray.exit"))
        self.tray_start_action.setEnabled(not self.is_running)
        self.tray_stop_action.setEnabled(self.is_running)

    def tr(self, key: str, **values) -> str:
        return ui_text(getattr(self, "language", "en"), key, **values)

    def open_path(self, path: Path):
        with contextlib.suppress(Exception):
            path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def human_size(self, size: int) -> str:
        value = float(max(0, int(size or 0)))
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if value < 1024 or unit == "TiB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
            value /= 1024
        return f"{value:.1f} TiB"

    def minimum_free_space_bytes(self) -> int:
        try:
            mb = int(os.environ.get("YTD_MIN_FREE_SPACE_MB", MIN_FREE_SPACE_MB))
        except (TypeError, ValueError):
            mb = MIN_FREE_SPACE_MB
        return max(128, mb) * 1024 * 1024

    def free_space_for_path(self, path: Path):
        try:
            path.mkdir(parents=True, exist_ok=True)
            usage = shutil.disk_usage(path)
            return usage.free, usage.total, ""
        except OSError as exc:
            return 0, 0, str(exc)

    def validate_free_space(self) -> bool:
        required = self.minimum_free_space_bytes()
        problems = []
        for label, path in ((self.tr("disk.temp_folder"), self.temp_dir), (self.tr("disk.download_folder"), self.final_dir)):
            free, _total, error = self.free_space_for_path(path)
            if error:
                problems.append(f"{label}: {error}")
            elif free < required:
                problems.append(self.tr("disk.free_needed", label=label, free=self.human_size(free), required=self.human_size(required)))
        if problems:
            self.show_notification("❌", self.tr("disk.low_space"), "\n".join(problems)[:220])
            return False
        return True

    def cleanup_cache(self):
        now = time.time()
        targets = (
            (self.cache_dir / "previews", CACHE_PREVIEW_MAX_AGE_DAYS),
            (self.cache_dir / "channels", CACHE_CHANNEL_MAX_AGE_DAYS),
        )
        for directory, max_age_days in targets:
            if not directory.exists():
                continue
            cutoff = now - max_age_days * 24 * 60 * 60
            with contextlib.suppress(OSError):
                for item in directory.iterdir():
                    try:
                        if item.is_file() and item.stat().st_mtime < cutoff:
                            item.unlink()
                    except OSError:
                        pass

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
        self.apply_taskbar_mode_to_window(self.main_window)
        self.main_window.showNormal()
        self.main_window.setWindowState(self.main_window.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.main_window.raise_()
        self.main_window.activateWindow()

    def open_quick_download_window(self, initial_url: str = ""):
        if not self.ensure_usage_rules_accepted(self.main_window):
            self.show_notification("⚖️", self.tr("quick.title"), self.tr("quick.accept_rules_first"))
            return
        if self.main_window is None:
            self.main_window = MainWindow(self)
        self.main_window.open_quick_download_window(initial_url)

    def hide_windows_from_taskbar(self):
        return self.tray_available and self.startup_display_mode == "tray"

    def apply_taskbar_mode_to_window(self, window):
        if window is None:
            return
        base_type = getattr(window, "_yth_base_window_type", None)
        if base_type is None:
            base_type = Qt.Dialog if isinstance(window, QDialog) else Qt.Window
            window._yth_base_window_type = base_type

        target_type = Qt.Tool if self.hide_windows_from_taskbar() else base_type
        current_flags = window.windowFlags()
        new_flags = (current_flags & ~Qt.WindowType_Mask) | target_type
        if new_flags == current_flags:
            return

        was_visible = window.isVisible()
        geometry = window.geometry()
        state = window.windowState()
        window.setWindowFlags(new_flags)
        window.setGeometry(geometry)
        window.setWindowState(state)
        if was_visible:
            window.show()

    def refresh_window_taskbar_mode(self):
        if self.main_window is None:
            return
        windows = [self.main_window]
        if getattr(self.main_window, "archive_window", None) is not None:
            windows.append(self.main_window.archive_window)
        if getattr(self.main_window, "quick_download_dialog", None) is not None:
            windows.append(self.main_window.quick_download_dialog)
        for window in windows:
            self.apply_taskbar_mode_to_window(window)

    def extract_youtube_url_from_text(self, text: str):
        for match in re.finditer(r"https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/[^\s<>'\"]+", str(text or "")):
            candidate = match.group(0).rstrip(").,;]")
            if candidate.startswith("http://"):
                candidate = "https://" + candidate[7:]
            if candidate.startswith(("https://www.youtube.com/", "https://youtube.com/", "https://m.youtube.com/", "https://youtu.be/")):
                return candidate
        return ""

    def on_clipboard_changed(self):
        if not getattr(self, "clipboard_watch_enabled", False):
            return
        if self.clipboard_check_pending:
            return
        self.clipboard_check_pending = True
        QTimer.singleShot(120, self.check_clipboard_for_quick_download)

    def refresh_clipboard_watch_timer(self):
        timer = getattr(self, "clipboard_timer", None)
        if timer is None:
            return
        if getattr(self, "clipboard_watch_enabled", False):
            if not timer.isActive():
                timer.start()
            QTimer.singleShot(250, self.check_clipboard_for_quick_download)
        elif timer.isActive():
            timer.stop()

    def clipboard_text(self):
        text = ""
        try:
            text = QApplication.clipboard().text()
        except Exception:
            text = ""
        if text:
            return text
        if self.is_wayland_session() and shutil.which("wl-paste"):
            try:
                result = subprocess.run(
                    ["wl-paste", "--no-newline", "--type", "text", "--paste-once"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=1,
                    check=False,
                )
                if result.returncode == 0:
                    return result.stdout
            except Exception:
                return ""
        return ""

    def check_clipboard_for_quick_download(self):
        self.clipboard_check_pending = False
        if not getattr(self, "clipboard_watch_enabled", False):
            return
        text = self.clipboard_text()
        url = self.extract_youtube_url_from_text(text)
        if not url:
            self.clipboard_last_url = ""
            return
        if self.is_running:
            self.clipboard_last_url = url
            return
        now = time.monotonic()
        if url == self.clipboard_last_url:
            return
        if self.main_window is not None and self.main_window.quick_download_dialog is not None:
            dialog = self.main_window.quick_download_dialog
            if dialog.isVisible() and dialog.url_input.text().strip() == url:
                return
        self.clipboard_last_url = url
        self.clipboard_last_trigger_at = now
        self.open_quick_download_window(url)

    def is_wayland_session(self):
        return not self.is_windows and os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"

    def setup_global_hotkey(self):
        if self.is_windows:
            self.hotkey_window = QWidget()
            self.hotkey_window.setWindowTitle(f"{APP_NAME} {self.tr('dialog.hotkey')}")
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
            if detail == "hotkey.convert_failed":
                detail = self.tr(detail)
            message = self.tr("hotkey.assign_failed", hotkey=self.quick_download_hotkey)
            if detail:
                message += f"\n{detail[:160]}"
            self.show_notification("⚠️", self.tr("dialog.hotkey"), message)

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
            return False, self.tr("hotkey.wayland_only")
        if not shutil.which("gsettings"):
            return False, self.tr("hotkey.gsettings_missing")
        binding = self.quick_hotkey_desktop_binding(sequence)
        if not binding:
            return False, self.tr("hotkey.convert_failed")
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
        return False, "; ".join(error for error in errors if error) or self.tr("hotkey.add_failed")

    def install_cinnamon_quick_hotkey(self, binding: str, command: str):
        list_schema = "org.cinnamon.desktop.keybindings"
        item_schema = "org.cinnamon.desktop.keybindings.custom-keybinding"
        current = self.gsettings_get(list_schema, "custom-list")
        if current is None:
            return False, self.tr("hotkey.cinnamon_schema")
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
                return False, self.tr("hotkey.cinnamon_list")
        path = f"/org/cinnamon/desktop/keybindings/custom-keybindings/{target}/"
        ok = (
            self.gsettings_set(item_schema, "name", self.gsettings_string(target_name), path)
            and self.gsettings_set(item_schema, "command", self.gsettings_string(command), path)
            and self.gsettings_set(item_schema, "binding", self.gsettings_strv([binding]), path)
        )
        if not ok:
            return False, self.tr("hotkey.cinnamon_write")
        return True, self.tr("hotkey.cinnamon_done", binding=binding)

    def install_gnome_quick_hotkey(self, binding: str, command: str):
        list_schema = "org.gnome.settings-daemon.plugins.media-keys"
        item_schema = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
        current = self.gsettings_get(list_schema, "custom-keybindings")
        if current is None:
            return False, self.tr("hotkey.gnome_schema")
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
                return False, self.tr("hotkey.gnome_list")
        ok = (
            self.gsettings_set(item_schema, "name", self.gsettings_string(target_name), target_path)
            and self.gsettings_set(item_schema, "command", self.gsettings_string(command), target_path)
            and self.gsettings_set(item_schema, "binding", self.gsettings_string(binding), target_path)
        )
        if not ok:
            return False, self.tr("hotkey.gnome_write")
        return True, self.tr("hotkey.gnome_done", binding=binding)

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
            self.show_notification("⚠️", self.tr("notify.settings"), str(e)[:200])

    def usage_rules_accepted(self):
        if os.environ.get("YTD_SKIP_USAGE_RULES") == "1":
            return True
        return self.app_settings.get("usage_rules_accepted_version") == USAGE_RULES_VERSION

    def show_initial_usage_rules(self):
        if self.usage_rules_accepted():
            return
        if not self.ensure_usage_rules_accepted():
            self.show_notification("⚖️", self.tr("notify.rules_not_accepted"), self.tr("notify.app_will_close"))
            self.app.quit()

    def ensure_usage_rules_accepted(self, parent=None):
        if self.usage_rules_accepted():
            return True
        dialog = UsageRulesDialog(required=True, parent=parent, language=getattr(self, "language", "en"))
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
        # An explicitly selected configuration directory must contain every
        # user-specific file. This keeps portable/test instances isolated
        # from settings left by another installation.
        if os.environ.get("YTD_CONFIG_DIR", "").strip():
            return self.config_dir
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
        if os.environ.get("YTD_YT_DLP_COMMAND_JSON") or os.environ.get("YTD_YT_DLP_COMMAND"):
            return common_yt_dlp_command()
        if getattr(sys, "frozen", False):
            return [sys.executable, "--run-yt-dlp"]
        return common_yt_dlp_command()

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
            capture_output=True,
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
        self.language = normalize_language(settings.get("language") or os.environ.get("YTD_LANGUAGE") or "en")
        self.temp_dir = self._setting_path(settings, "temp_dir", "YTD_TEMP_DIR", self.default_temp_dir())
        self.final_dir = self._setting_path(settings, "download_dir", "YTD_FINAL_DIR", self.default_download_dir())
        self.videos_limit = self._setting_int(settings, "videos_limit", 5, 1, 100)
        self.shorts_limit = self._setting_int(settings, "shorts_limit", 5, 1, 100)
        self.streams_limit = self._setting_int(settings, "streams_limit", 5, 1, 100)
        self.log_keep_count = self._setting_int(settings, "log_keep_count", 3, 1, 50)
        self.cleanup_temp = self._setting_bool(settings, "cleanup_temp", True)
        self.retry_failed_queue = self._setting_bool(settings, "retry_failed_queue", True)
        self.clipboard_watch_enabled = self._setting_bool(settings, "clipboard_watch_enabled", False)
        startup_mode = str(settings.get("startup_display_mode") or os.environ.get("YTD_STARTUP_DISPLAY_MODE") or "tray").strip()
        self.startup_display_mode = startup_mode if startup_mode in VALID_STARTUP_DISPLAY_MODES else "tray"
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
        self.max_resolution = resolution if resolution in VALID_RESOLUTIONS else "1080"
        quick_resolution = str(
            settings.get("quick_download_resolution")
            or os.environ.get("YTD_QUICK_DOWNLOAD_RESOLUTION")
            or self.max_resolution
        ).strip()
        self.quick_download_resolution = quick_resolution if quick_resolution in VALID_RESOLUTIONS else self.max_resolution

    def validate_download_environment(self):
        if not self.python_downloader_path.exists():
            self.show_notification("❌", self.tr("notify.python_engine"), self.tr("notify.file_not_found", path=self.python_downloader_path))
            return False
        if self.is_windows and not self.ffmpeg_dir:
            self.show_notification(
                "❌",
                self.tr("notify.ffmpeg_missing"),
                self.tr("notify.ffmpeg_needed"),
            )
            return False
        if self.is_windows and not self.deno_path:
            self.show_notification(
                "❌",
                self.tr("notify.deno_missing"),
                self.tr("notify.deno_needed"),
            )
            return False
        if (
            not getattr(sys, "frozen", False)
            and not os.environ.get("YTD_YT_DLP_COMMAND")
            and not os.environ.get("YTD_YT_DLP_COMMAND_JSON")
            and not self.command_exists("yt-dlp")
        ):
            self.show_notification("❌", self.tr("notify.ytdlp_missing"), self.tr("notify.ytdlp_install"))
            return False
        if not self.validate_free_space():
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
            "YTD_MAX_RESOLUTION": str(self.quick_resolution_override or self.max_resolution),
            "YTD_LOG_KEEP_COUNT": str(self.log_keep_count),
            "YTD_CLEANUP_TEMP": "1" if self.cleanup_temp else "0",
            "YTD_RETRY_FAILED_QUEUE": "1" if self.retry_failed_queue else "0",
            "YTD_TELEGRAM_ENABLED": "1" if telegram_enabled else "0",
            "YTD_DOWNLOAD_ENGINE": self.download_engine,
            "YTD_QUICK_DOWNLOAD_HOTKEY": self.quick_download_hotkey,
            "YTD_QUICK_DOWNLOAD_TELEGRAM_NOTIFY": "1" if self.quick_download_telegram_notify else "0",
            "YTD_QUICK_DOWNLOAD_RESOLUTION": str(self.quick_download_resolution),
            "YTD_STARTUP_DISPLAY_MODE": str(self.startup_display_mode),
            "YTD_CLIPBOARD_WATCH_ENABLED": "1" if self.clipboard_watch_enabled else "0",
            "YTD_YT_DLP_COMMAND": subprocess.list2cmdline(yt_dlp_command),
            "YTD_YT_DLP_COMMAND_JSON": json.dumps(yt_dlp_command, ensure_ascii=False),
        })
        if self.quick_single_url:
            env["YTD_SINGLE_QUEUE_URL"] = self.quick_single_url
        if self.quick_audio_overrides:
            env["YTD_AUDIO_TRACKS_JSON"] = json.dumps(self.quick_audio_overrides, ensure_ascii=False)
            first_audio = self.quick_audio_overrides[0]
            env["YTD_AUDIO_FORMAT_ID"] = str(first_audio.get("format_id") or "")
            env["YTD_AUDIO_FORMAT_KIND"] = str(first_audio.get("format_kind") or "audio")
            env["YTD_AUDIO_LANGUAGE"] = str(first_audio.get("language") or "")
            env["YTD_AUDIO_TRACK_NAME"] = str(first_audio.get("name") or "")
            if first_audio.get("player_client"):
                env["YTD_YOUTUBE_AUDIO_PLAYER_CLIENT"] = str(first_audio["player_client"])
        if self.quick_subtitle_overrides:
            env["YTD_SUBTITLE_SELECTIONS_JSON"] = json.dumps(self.quick_subtitle_overrides, ensure_ascii=False)
            env["YTD_SUBTITLE_SELECTION"] = self.quick_subtitle_overrides[0]
        if self.ffmpeg_dir:
            env["YTD_FFMPEG_DIR"] = str(self.ffmpeg_dir)
        if self.deno_path:
            env["YTD_DENO_PATH"] = str(self.deno_path)
        return env

    def run_script(
        self,
        telegram_override=None,
        single_queue_url: str = "",
        max_resolution_override: str = "",
        audio_track_overrides: list[dict] | None = None,
        subtitle_overrides: list[str] | None = None,
    ):
        if self.is_running:
            self.show_notification("⚠️", self.tr("notify.already_running"), self.tr("notify.wait_finish"))
            return
        if not self.ensure_usage_rules_accepted(self.main_window):
            self.show_notification("⚖️", self.tr("notify.download_not_started"), self.tr("quick.accept_rules_first"))
            return
        if self.main_window is not None:
            try:
                self.main_window.save_settings_from_ui(show_message=False)
            except Exception as e:
                self.show_notification("⚠️", self.tr("notify.settings"), self.tr("notify.apply_settings_failed", error=str(e)[:160]))
        if not self.validate_download_environment():
            return

        with contextlib.suppress(Exception):
            self.stop_file.unlink(missing_ok=True)

        self.reset_status_for_new_run()
        self.is_running = True
        self.state = "running"
        self.quick_telegram_override = telegram_override
        self.quick_single_url = str(single_queue_url or "").strip()
        resolution_override = str(max_resolution_override or "").strip()
        self.quick_resolution_override = resolution_override if resolution_override in VALID_RESOLUTIONS else ""
        self.quick_audio_overrides = [dict(track) for track in (audio_track_overrides or [])]
        self.quick_subtitle_overrides = [str(value).strip() for value in (subtitle_overrides or []) if str(value).strip()]
        self.update_icon()
        self.update_tray_menu()
        self.show_notification("▶️", self.tr("notify.download_started"), self.tr("notify.script_started"))

        thread = threading.Thread(target=self._execute_script, daemon=True)
        thread.start()

    def reset_status_for_new_run(self):
        previous = {}
        try:
            if self.status_file.exists():
                previous = json.loads(self.status_file.read_text(encoding="utf-8"))
        except Exception:
            previous = {}

        channels_total = 0
        try:
            channels_total = sum(
                1
                for line in self.channels_file.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
                if line.strip() and not line.strip().startswith("#")
            )
        except Exception:
            channels_total = 0

        status = {
            "state": "searching",
            "channel_url": "",
            "channel_name": "",
            "current_type": "",
            "videos_status": "idle",
            "shorts_status": "idle",
            "streams_status": "idle",
            "channels_total": channels_total,
            "channels_checked": 0,
            "video_title": "",
            "video_thumbnail": "",
            "download_percent": "",
            "download_speed": "",
            "download_eta": "",
            "download_size": "",
            "download_stage": "",
            "progress_bucket": "",
            "last_run_completed_at": previous.get("last_run_completed_at", 0),
            "last_run_stopped": previous.get("last_run_stopped", False),
            "last_run_new_count": previous.get("last_run_new_count", 0),
            "last_run_failed_count": previous.get("last_run_failed_count", 0),
            "last_run_videos": previous.get("last_run_videos", 0),
            "last_run_shorts": previous.get("last_run_shorts", 0),
            "last_run_streams": previous.get("last_run_streams", 0),
            "last_run_queue": previous.get("last_run_queue", 0),
            "last_run_channels_total": previous.get("last_run_channels_total", 0),
            "last_run_channels_checked": previous.get("last_run_channels_checked", 0),
            "last_download_at": previous.get("last_download_at", ""),
        }
        try:
            self.status_file.parent.mkdir(parents=True, exist_ok=True)
            self.status_file.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass

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
            self.signals.script_error.emit(str(e)[:200])
        finally:
            self.signals.script_finished.emit()

    def on_script_error(self, message: str):
        self.show_notification("❌", self.tr("notify.error"), str(message or "")[:200])

    def on_script_finished(self):
        self.current_process = None
        self.is_running = False
        self.state = "idle"
        self.quick_telegram_override = None
        self.quick_single_url = ""
        self.quick_resolution_override = ""
        self.quick_audio_overrides = []
        self.quick_subtitle_overrides = []
        self.update_icon()
        self.update_tray_menu()
        if self.main_window is not None and self.main_window.isVisible():
            self.main_window.refresh_overview()

    def request_stop(self):
        if not self.is_running:
            return
        try:
            self.stop_file.write_text(str(int(time.time())) + "\n", encoding="utf-8")
            self.state = "stopping"
            self.update_icon()
            self.update_tray_menu()
            self.show_notification("⏹", self.tr("notify.stopping"), self.tr("notify.stop_after_safe"))
        except Exception as e:
            self.show_notification("❌", self.tr("notify.stop_failed"), str(e)[:200])

    def update_icon(self):
        # Проверка приоритетной иконки
        part_files = glob.glob(str(self.temp_dir / "*.part"))
        if part_files:
            icon = self.create_colored_icon((40, 180, 40), rect=True)  # зелёный круг с прямоугольником
            tooltip = self.tr("tray.tip.partial", app=APP_NAME)
        else:
            if self.state == "stopping":
                icon = self.create_colored_icon((230, 150, 40), rect=True)
                tooltip = self.tr("tray.tip.stopping", app=APP_NAME)
            elif self.state == "running":
                icon = self.create_colored_icon((220, 53, 69), rect=True)  # красный круг с прямоугольником
                tooltip = self.tr("tray.tip.running", app=APP_NAME)
            else:
                icon = self.create_colored_icon((120, 120, 120), rect=False)  # серый круг Zzz
                tooltip = self.tr("tray.tip.sleep", app=APP_NAME)

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

    def startup_mode_arg(self, mode: str | None = None):
        value = mode or self.startup_display_mode
        if value == "taskbar":
            return "--start-window"
        if value == "both":
            return "--start-both"
        return "--start-tray"

    def handle_startup_mode(self, args):
        args = set(args or [])
        if "--start-window" in args:
            mode = "taskbar"
        elif "--start-both" in args:
            mode = "both"
        elif "--start-tray" in args:
            mode = "tray"
        else:
            if not self.tray_available:
                self.tray.hide()
                self.app.setQuitOnLastWindowClosed(True)
                QTimer.singleShot(0, lambda: self.open_main_window(0))
            return

        if not self.tray_available and mode in {"tray", "both"}:
            mode = "taskbar"

        if mode == "taskbar":
            self.tray.hide()
            self.app.setQuitOnLastWindowClosed(True)
            QTimer.singleShot(0, lambda: self.open_main_window(0))
        elif mode == "both":
            self.tray.show()
            self.app.setQuitOnLastWindowClosed(False)
            QTimer.singleShot(0, lambda: self.open_main_window(0))
        else:
            self.tray.show()
            self.app.setQuitOnLastWindowClosed(False)

    def show_notification(self, icon: str, title: str, message: str):
        if not self.tray_available:
            return
        with contextlib.suppress(Exception):
            self.tray.showMessage(f"{icon} {title}", message, QSystemTrayIcon.Information, 5000)

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
                with open(self.schedules_file, encoding="utf-8") as f:
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
        return self.app.exec_()


class ArchiveWindow(QMainWindow):
    TYPE_EMOJIS = {
        "videos": "🎬",
        "shorts": "⚡",
        "streams": "●",
        "queue": "📥",
    }

    def __init__(self, launcher: TrayLauncher, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.setWindowTitle(self.tr("archive.title"))
        self.resize(980, 560)
        self.setMinimumSize(760, 420)
        self.launcher.apply_taskbar_mode_to_window(self)
        if self.launcher.app_icon_path.exists():
            self.setWindowIcon(QIcon(str(self.launcher.app_icon_path)))

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        title = QLabel(self.tr("archive.heading"))
        title.setObjectName("sectionTitle")
        self.archive_title_label = title
        self.refresh_button = QPushButton("🔄 " + self.tr("button.refresh"))
        self.refresh_button.setToolTip(self.tr("archive.refresh_tip"))
        self.refresh_button.clicked.connect(self.refresh)
        self.youtube_button = QPushButton("▶ YouTube")
        self.youtube_button.setToolTip(self.tr("archive.youtube_tip"))
        self.youtube_button.clicked.connect(self.open_selected_youtube)
        self.file_button = QPushButton(self.tr("archive.file"))
        self.file_button.setToolTip(self.tr("archive.file_tip"))
        self.file_button.clicked.connect(self.open_selected_file)
        self.folder_button = QPushButton(self.tr("archive.folder"))
        self.folder_button.setToolTip(self.tr("archive.folder_tip"))
        self.folder_button.clicked.connect(self.open_selected_folder)
        self.delete_button = QPushButton(self.tr("archive.delete"))
        self.delete_button.setToolTip(self.tr("archive.delete_tip"))
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

        self.table = QTableWidget(0, 7)
        self.apply_language()
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
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.setCentralWidget(central)

    def tr(self, key: str, **values) -> str:
        return ui_text(getattr(self.launcher, "language", "en"), key, **values)

    def apply_language(self):
        self.setWindowTitle(self.tr("archive.title"))
        self.setLayoutDirection(Qt.RightToLeft if normalize_language(getattr(self.launcher, "language", "en")) == "ar" else Qt.LeftToRight)
        if hasattr(self, "archive_title_label"):
            self.archive_title_label.setText(self.tr("archive.heading"))
            self.refresh_button.setText("🔄 " + self.tr("button.refresh"))
            self.refresh_button.setToolTip(self.tr("archive.refresh_tip"))
            self.youtube_button.setToolTip(self.tr("archive.youtube_tip"))
            self.file_button.setText(self.tr("archive.file"))
            self.file_button.setToolTip(self.tr("archive.file_tip"))
            self.folder_button.setText(self.tr("archive.folder"))
            self.folder_button.setToolTip(self.tr("archive.folder_tip"))
            self.delete_button.setText(self.tr("archive.delete"))
            self.delete_button.setToolTip(self.tr("archive.delete_tip"))
        if hasattr(self, "table"):
            self.table.setHorizontalHeaderLabels([
                "",
                self.tr("archive.type"),
                self.tr("archive.channel"),
                self.tr("archive.name"),
                self.tr("archive.quality"),
                "ID",
                self.tr("archive.date"),
            ])

    def type_label(self, type_name: str) -> str:
        labels = {
            "videos": "🎬 " + self.tr("overview.video"),
            "shorts": "⚡ " + self.tr("overview.shorts"),
            "streams": "🔴 " + self.tr("overview.stream"),
            "queue": "📥 " + self.tr("status.queue"),
        }
        return labels.get(type_name, type_name)

    def quality_tooltip(self, entry: dict) -> str:
        lines: list[str] = []
        entry_audio_tracks = entry.get("audio_tracks")
        if isinstance(entry_audio_tracks, list):
            for track in entry_audio_tracks:
                if not isinstance(track, dict):
                    continue
                name = fix_mojibake(str(track.get("name") or "").strip())
                language = str(track.get("language") or "").strip()
                label = name or language
                if name and language and not name.casefold().endswith(f"({language})".casefold()):
                    label = f"{name} ({language})"
                if label:
                    lines.append(f"🎧 {label}")
        else:
            legacy_audio = fix_mojibake(str(entry.get("audio_track_name") or entry.get("audio_language") or "").strip())
            if legacy_audio and legacy_audio.casefold() != "auto":
                lines.append(f"🎧 {legacy_audio}")
        if not lines:
            lines.append(self.tr("quick.audio_auto"))

        entry_subtitles = entry.get("subtitle_selections")
        if not isinstance(entry_subtitles, list):
            legacy_subtitle = str(entry.get("subtitle_selection") or "none").strip()
            entry_subtitles = [] if legacy_subtitle.casefold() in {"", "none"} else [legacy_subtitle]
        subtitle_lines = []
        for subtitle_selection in entry_subtitles:
            mode, _separator, language = str(subtitle_selection).partition(":")
            language = language.strip()
            if not language:
                continue
            suffix = f" ({self.tr('quick.subtitles_auto_suffix')})" if mode == "auto" else ""
            subtitle_lines.append(f"{SUBTITLE_ICON} {language}{suffix}")
        lines.extend(subtitle_lines or [self.tr("quick.subtitles_none")])
        return "\n".join(lines)

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
        status_item.setToolTip(self.tr("archive.file_exists") if exists else self.tr("archive.file_missing"))
        status_item.setTextAlignment(Qt.AlignCenter)
        status_item.setData(Qt.UserRole, entry)
        status_item.setForeground(QBrush(QColor("#2abf68" if exists else "#e54b4b")))
        self.table.setItem(row, 0, status_item)

        type_name = str(entry.get("type") or "").strip()
        type_emoji = self.TYPE_EMOJIS.get(type_name, type_name)
        video_id = str(entry.get("video_id") or "").strip()
        resolution = str(entry.get("resolution") or media_resolution_from_path(entry.get("filename") or entry.get("file_path"))).strip()
        quality_text = f"{resolution}p" if resolution.isdigit() else (resolution or "-")
        quality_tooltip = self.quality_tooltip(entry)
        values = [
            type_emoji,
            fix_mojibake(str(entry.get("channel_name") or "")),
            fix_mojibake(str(entry.get("title") or "")),
            quality_text,
            video_id,
            fix_mojibake(str(entry.get("downloaded_at") or "")),
        ]
        for col, value in enumerate(values, start=1):
            display_value = value.strip() or "-"
            item = QTableWidgetItem(display_value)
            if col == 1:
                item.setToolTip(self.type_label(type_name))
            elif col == 4:
                item.setToolTip(quality_tooltip)
            else:
                item.setToolTip(value.strip())
            if col in (1, 4, 5, 6):
                item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, col, item)

        self.table.setRowHeight(row, 28)

    def run_migration(self):
        script = self.launcher.migrate_script_path
        if not script.exists():
            QMessageBox.warning(self, self.tr("archive.title"), self.tr("archive.migration_not_found", path=script))
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
            QMessageBox.warning(self, self.tr("archive.title"), self.tr("archive.migration_run_failed", error=exc))
            return

        if result.returncode != 0:
            message = (result.stderr or result.stdout or self.tr("archive.migration_failed")).strip()
            QMessageBox.warning(self, self.tr("archive.title"), message)
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
                self.tr("archive.title"),
            "\n\n".join((
                self.tr("archive.migration_complete"),
                "\n".join((
                    self.tr("archive.migration_old_ids", count=summary.get("archive_ids", 0)),
                    self.tr("archive.migration_scanned", count=summary.get("scanned_files", 0)),
                    self.tr("archive.migration_matched", count=summary.get("matched_files", 0)),
                    self.tr("archive.migration_with_file", count=summary.get("file_records_added", 0)),
                    self.tr("archive.migration_missing_file", count=summary.get("missing_records_added", 0)),
                    self.tr("archive.migration_total", count=summary.get("total_added", 0)),
                )),
            )),
        )

    def delete_selected_entry(self):
        entry = self.selected_entry()
        if not entry:
            return

        video_id = str(entry.get("video_id") or "").strip()
        title = str(entry.get("title") or video_id or self.tr("archive.selected_entry")).strip()
        answer = QMessageBox.question(
            self,
            self.tr("archive.title"),
            self.tr("archive.delete_question", title=title) + "\n\n" + self.tr("archive.delete_note"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        details_removed = self.remove_from_details_archive(entry)
        service_removed = 0 if self.details_archive_contains_video(video_id) else self.remove_from_service_archive(video_id)
        self.refresh()
        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh_overview"):
            parent.refresh_overview()

        QMessageBox.information(
            self,
            self.tr("archive.title"),
            "\n\n".join((
                self.tr("archive.deleted"),
                "\n".join((
                    self.tr("archive.deleted_details", count=details_removed),
                    self.tr("archive.deleted_service", count=service_removed),
                )),
            )),
        )

    def remove_from_details_archive(self, entry: dict) -> int:
        path = self.launcher.archive_details_file
        if not path.exists():
            return 0

        selected_index = entry.get("_index")
        removed = 0
        kept_lines = []
        for index, raw_line in enumerate(read_text_for_display(path).splitlines()):
            if selected_index == index:
                removed += 1
            else:
                kept_lines.append(raw_line)

        path.write_text("\n".join(kept_lines).rstrip() + ("\n" if kept_lines else ""), encoding="utf-8")
        return removed

    def details_archive_contains_video(self, video_id: str) -> bool:
        if not video_id or not self.launcher.archive_details_file.exists():
            return False
        for raw_line in read_text_for_display(self.launcher.archive_details_file).splitlines():
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict) and str(entry.get("video_id") or "").strip() == video_id:
                return True
        return False

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
            if video_id in raw_line.split():
                removed += 1
            else:
                kept_lines.append(raw_line)

        path.write_text("\n".join(kept_lines).rstrip() + ("\n" if kept_lines else ""), encoding="utf-8")
        return removed

    def selected_entry(self, warn: bool = True):
        row = self.table.currentRow()
        if row < 0:
            if warn:
                QMessageBox.information(self, self.tr("archive.title"), self.tr("archive.select_entry"))
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
            QMessageBox.information(self, self.tr("archive.title"), self.tr("archive.no_youtube"))
            return
        QDesktopServices.openUrl(QUrl(url))

    def open_selected_channel(self):
        entry = self.selected_entry()
        if not entry:
            return
        url = self.channel_url_from_entry(entry)
        if not url:
            QMessageBox.information(self, self.tr("archive.title"), self.tr("archive.no_channel"))
            return
        QDesktopServices.openUrl(QUrl(url))

    def open_selected_channel_section(self):
        entry = self.selected_entry()
        if not entry:
            return
        url = self.channel_url_from_entry(entry)
        if not url:
            QMessageBox.information(self, self.tr("archive.title"), self.tr("archive.no_channel"))
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
            QMessageBox.information(self, self.tr("archive.title"), self.tr("archive.no_path"))
            return
        path = self.resolve_existing_path(Path(path_text))
        if path is None:
            QMessageBox.information(self, self.tr("archive.title"), self.tr("archive.not_found"))
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


class CheckableComboBox(QComboBox):
    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().installEventFilter(self)
        self.setModel(QStandardItemModel(self))
        self.view().pressed.connect(self.toggle_item)
        self.model().dataChanged.connect(self.update_summary)
        self._skip_next_hide = False
        self.empty_text = ""
        self.count_template = "{count}"

    def eventFilter(self, watched, event):
        if watched is self.lineEdit() and event.type() == QEvent.MouseButtonRelease and self.isEnabled():
            self.showPopup()
            return True
        return super().eventFilter(watched, event)

    def hidePopup(self):
        if self._skip_next_hide:
            self._skip_next_hide = False
            return
        super().hidePopup()

    def toggle_item(self, index):
        item = self.model().itemFromIndex(index)
        if item is None or not item.isEnabled() or item.data(Qt.UserRole) is None:
            return
        item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
        self._skip_next_hide = True
        self.update_summary()
        self.selectionChanged.emit()

    def set_display_texts(self, empty_text: str, count_template: str):
        self.empty_text = empty_text
        self.count_template = count_template
        self.update_summary()

    def add_check_item(self, text: str, data, *, checked: bool = False):
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsEnabled)
        item.setData(data, Qt.UserRole)
        item.setData(Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
        item.setToolTip(text)
        self.model().appendRow(item)
        self.update_summary()

    def add_separator(self):
        self.insertSeparator(self.count())

    def checked_data(self) -> list:
        return [
            self.model().item(index).data(Qt.UserRole)
            for index in range(self.model().rowCount())
            if self.model().item(index).checkState() == Qt.Checked
        ]

    def checked_keys(self, key_function) -> set:
        return {key_function(value) for value in self.checked_data()}

    def update_summary(self, *_args):
        labels = [
            self.model().item(index).text()
            for index in range(self.model().rowCount())
            if self.model().item(index).checkState() == Qt.Checked
        ]
        if not labels:
            text = self.empty_text
        elif len(labels) == 1:
            text = labels[0]
        else:
            text = self.count_template.format(count=len(labels))
        self.lineEdit().setText(text)
        self.lineEdit().setToolTip("\n".join(labels) if labels else self.toolTip())


class QuickDownloadDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.launcher = main_window.launcher
        self.setWindowTitle(self.main_window.tr("quick.title"))
        self.setModal(False)
        self.setFixedSize(900, 270)
        self.launcher.apply_taskbar_mode_to_window(self)
        self._position_ready = False
        self.position_save_timer = QTimer(self)
        self.position_save_timer.setSingleShot(True)
        self.position_save_timer.setInterval(600)
        self.position_save_timer.timeout.connect(self.save_position)
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
        self.url_input.setPlaceholderText(self.main_window.tr("placeholder.youtube_url"))
        self.url_input.setFixedHeight(32)
        self.url_input.textChanged.connect(self.on_url_changed)
        self.url_input.returnPressed.connect(self.download_now)
        self.resolution_combo = QComboBox()
        self.resolution_combo.setToolTip(self.main_window.tr("quick.resolution_tip"))
        self.resolution_combo.setFixedWidth(104)
        self.resolution_combo.setFixedHeight(32)
        for label, value in localized_resolution_options(self.main_window.language):
            self.resolution_combo.addItem(label, value)
        self.select_resolution(self.launcher.quick_download_resolution)
        self.resolution_combo.currentIndexChanged.connect(self.save_resolution_setting)
        self.download_button = QPushButton()
        self.download_button.setObjectName("quickRunButton")
        self.download_button.setFixedSize(46, 46)
        self.download_button.setIconSize(QSize(44, 44))
        self.download_button.setIcon(self.main_window._run_button_icon(False))
        self.download_button.setToolTip(self.main_window.tr("quick.download_now"))
        self.download_button.setFlat(True)
        self.download_button.setAutoDefault(False)
        self.download_button.clicked.connect(self.download_now)
        self.add_queue_button = QPushButton(self.main_window.tr("button.queue_short"))
        self.add_queue_button.setFixedHeight(32)
        self.add_queue_button.setToolTip(self.main_window.tr("quick.queue_easter"))
        self.add_queue_button.clicked.connect(self.add_to_queue)
        self.cancel_button = QPushButton(self.main_window.tr("button.cancel"))
        self.cancel_button.setFixedHeight(32)
        self.cancel_button.setToolTip(self.main_window.tr("quick.close_tip"))
        self.cancel_button.clicked.connect(self.reject)
        top_row.addWidget(self.url_input, 1)
        top_row.addWidget(self.resolution_combo)
        top_row.addWidget(self.download_button)
        right_layout.addLayout(top_row)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(10)
        self.thumbnail_label = QLabel(self.main_window.tr("preview.thumbnail"))
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setFixedSize(285, 165)
        self.thumbnail_label.setObjectName("quickThumbnail")
        preview_row.addWidget(self.thumbnail_label, 0, Qt.AlignTop)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)
        self.video_title_label = QLabel(self.main_window.tr("preview.quick_wait"))
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

        media_row = QHBoxLayout()
        media_row.setSpacing(8)
        self.audio_combo = CheckableComboBox()
        self.audio_combo.setFixedHeight(28)
        self.audio_combo.view().setMinimumWidth(300)
        self.audio_combo.setToolTip(self.main_window.tr("quick.audio_tip"))
        self.subtitle_combo = CheckableComboBox()
        self.subtitle_combo.setFixedHeight(28)
        self.subtitle_combo.view().setMinimumWidth(300)
        self.subtitle_combo.setToolTip(self.main_window.tr("quick.subtitles_tip"))
        media_row.addWidget(self.audio_combo, 1)
        media_row.addWidget(self.subtitle_combo, 1)
        info_layout.addLayout(media_row)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        bottom_row.addStretch()
        self.telegram_check = QCheckBox("Telegram")
        self.telegram_check.setObjectName("quickTelegramCheck")
        self.telegram_check.setChecked(self.launcher.quick_download_telegram_notify)
        self.telegram_check.toggled.connect(self.save_telegram_setting)
        bottom_row.addWidget(self.telegram_check)
        bottom_row.addWidget(self.add_queue_button)
        bottom_row.addWidget(self.cancel_button)
        info_layout.addLayout(bottom_row)
        preview_row.addLayout(info_layout, 1)
        right_layout.addLayout(preview_row, 1)

        self.reset_media_options()
        self.update_actions(False)

    def apply_language(self):
        self.setWindowTitle(self.main_window.tr("quick.title"))
        self.setLayoutDirection(Qt.RightToLeft if self.main_window.language == "ar" else Qt.LeftToRight)
        self.url_input.setPlaceholderText(self.main_window.tr("placeholder.youtube_url"))
        self.resolution_combo.setToolTip(self.main_window.tr("quick.resolution_tip"))
        self.audio_combo.setToolTip(self.main_window.tr("quick.audio_tip"))
        self.subtitle_combo.setToolTip(self.main_window.tr("quick.subtitles_tip"))
        self.audio_combo.set_display_texts(
            self.main_window.tr("quick.audio_auto"),
            self.main_window.tr("quick.audio_selected"),
        )
        self.subtitle_combo.set_display_texts(
            self.main_window.tr("quick.subtitles_none"),
            self.main_window.tr("quick.subtitles_selected"),
        )
        self.main_window._replace_combo_items(
            self.resolution_combo,
            localized_resolution_options(self.main_window.language),
            self.selected_resolution(),
        )
        self.download_button.setToolTip(self.main_window.tr("quick.download_now"))
        self.add_queue_button.setText(self.main_window.tr("button.queue_short"))
        self.add_queue_button.setToolTip(self.main_window.tr("quick.queue_easter"))
        self.cancel_button.setText(self.main_window.tr("button.cancel"))
        self.cancel_button.setToolTip(self.main_window.tr("quick.close_tip"))
        self.set_media_options(self.main_window.current_previews.get("quick", {}))
        if self.thumbnail_label.text():
            self.thumbnail_label.setText(self.main_window.tr("preview.thumbnail"))
        if not self.url_input.text().strip() and not self.main_window.current_previews.get("quick"):
            self.video_title_label.setText(self.main_window.tr("preview.quick_wait"))

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
        if self._position_ready:
            self.position_save_timer.start()

    def save_position_now(self):
        self.position_save_timer.stop()
        self.save_position()

    def closeEvent(self, event):
        self.save_position_now()
        super().closeEvent(event)

    def accept(self):
        self.save_position_now()
        super().accept()

    def reject(self):
        self.save_position_now()
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

    def select_resolution(self, value: str):
        index = self.resolution_combo.findData(value if value in VALID_RESOLUTIONS else self.launcher.quick_download_resolution)
        self.resolution_combo.blockSignals(True)
        self.resolution_combo.setCurrentIndex(index if index >= 0 else 2)
        self.resolution_combo.blockSignals(False)

    def selected_resolution(self):
        value = str(self.resolution_combo.currentData() or self.launcher.quick_download_resolution or "1080")
        return value if value in VALID_RESOLUTIONS else "1080"

    def language_label(self, language: str, name: str = "") -> str:
        language = str(language or "und").strip()
        name = fix_mojibake(str(name or "").strip())
        if name:
            suffix = f"({language})".casefold()
            return name if name.casefold().endswith(suffix) else f"{name} ({language})"
        locale_name = QLocale(language.replace("-", "_")).nativeLanguageName().strip()
        return f"{locale_name} ({language})" if locale_name else language

    def reset_media_options(self):
        self.audio_combo.clear()
        self.audio_combo.set_display_texts(
            self.main_window.tr("quick.audio_auto"),
            self.main_window.tr("quick.audio_selected"),
        )
        self.audio_combo.setEnabled(False)
        self.subtitle_combo.clear()
        self.subtitle_combo.set_display_texts(
            self.main_window.tr("quick.subtitles_none"),
            self.main_window.tr("quick.subtitles_selected"),
        )
        self.subtitle_combo.setEnabled(False)

    @staticmethod
    def audio_option_key(option: dict) -> tuple[str, str, str]:
        return (
            str(option.get("format_kind") or ""),
            str(option.get("language") or "").casefold(),
            str(option.get("name") or "").casefold(),
        )

    def set_media_options(self, info: dict):
        selected_audio_keys = self.audio_combo.checked_keys(self.audio_option_key)
        selected_subtitles = {str(value) for value in self.subtitle_combo.checked_data()}
        audio_options = info.get("audio_tracks") or []
        subtitle_options = info.get("subtitle_tracks") or []

        self.audio_combo.clear()
        self.audio_combo.set_display_texts(
            self.main_window.tr("quick.audio_auto"),
            self.main_window.tr("quick.audio_selected"),
        )
        preferred_audio, other_audio = prioritized_media_sections(audio_options)
        for option in preferred_audio:
            label = self.language_label(option.get("language"), option.get("name"))
            self.audio_combo.add_check_item(
                f"🎧 {label}",
                option,
                checked=self.audio_option_key(option) in selected_audio_keys,
            )
        if preferred_audio and other_audio:
            self.audio_combo.add_separator()
        for option in other_audio:
            label = self.language_label(option.get("language"), option.get("name"))
            self.audio_combo.add_check_item(
                f"🎧 {label}",
                option,
                checked=self.audio_option_key(option) in selected_audio_keys,
            )
        self.audio_combo.setEnabled(bool(audio_options))
        self.audio_combo.update_summary()

        self.subtitle_combo.clear()
        self.subtitle_combo.set_display_texts(
            self.main_window.tr("quick.subtitles_none"),
            self.main_window.tr("quick.subtitles_selected"),
        )
        subtitle_sections = [
            section
            for section in subtitle_media_sections(subtitle_options)
            if section
        ]
        for section_index, section in enumerate(subtitle_sections):
            if section_index:
                self.subtitle_combo.add_separator()
            for option in section:
                label = self.language_label(option.get("language"), option.get("name"))
                if option.get("mode") == "auto":
                    label = f"{label} ({self.main_window.tr('quick.subtitles_auto_suffix')})"
                selection = str(option.get("selection") or "")
                self.subtitle_combo.add_check_item(
                    f"{SUBTITLE_ICON} {label}",
                    selection,
                    checked=selection in selected_subtitles,
                )
        self.subtitle_combo.setEnabled(bool(subtitle_options))
        self.subtitle_combo.update_summary()

    def selected_audio_tracks(self) -> list[dict]:
        return [dict(value) for value in self.audio_combo.checked_data() if isinstance(value, dict)]

    def selected_subtitles(self) -> list[str]:
        return [str(value) for value in self.subtitle_combo.checked_data() if value]

    def selected_audio_track(self) -> dict:
        tracks = self.selected_audio_tracks()
        return tracks[0] if tracks else {}

    def selected_subtitle(self) -> str:
        subtitles = self.selected_subtitles()
        return subtitles[0] if subtitles else "none"

    def open_from_clipboard(self, initial_url: str = ""):
        self._position_ready = False
        self.position_save_timer.stop()
        clipboard_text = (initial_url or self.launcher.clipboard_text()).strip()
        clipboard_url = self.launcher.extract_youtube_url_from_text(clipboard_text) or clipboard_text
        self.main_window.current_previews["quick"] = {}
        self.thumbnail_label.setPixmap(QPixmap())
        self.thumbnail_label.setText(self.main_window.tr("preview.thumbnail"))
        self._load_logo()
        self.video_uploader_label.setText("")
        self.video_status_label.setText("")
        self.reset_media_options()
        self.select_resolution(self.launcher.quick_download_resolution)
        if self.main_window._looks_like_youtube_url(clipboard_url):
            self.url_input.setText(clipboard_url)
            self.url_input.selectAll()
            self.main_window.schedule_video_preview("quick")
        else:
            self.url_input.clear()
            self.video_title_label.setText(self.main_window.tr("preview.error"))
            self.video_status_label.setText(self.main_window.tr("preview.clipboard_error"))
            self.update_actions(False)
        self.telegram_check.setChecked(self.launcher.quick_download_telegram_notify)
        self.restore_position()
        self.launcher.apply_taskbar_mode_to_window(self)
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

    def save_resolution_setting(self, *_args):
        self.main_window.ui_settings["quick_download_resolution"] = self.selected_resolution()
        self.main_window.save_ui_settings()
        self.launcher.app_settings = dict(self.main_window.ui_settings)
        self.launcher.apply_runtime_settings(self.launcher.app_settings)

    def add_to_queue(self):
        if self.main_window.add_video_to_queue("quick"):
            self.accept()

    def download_now(self):
        if not self.download_button.isEnabled():
            return
        self.save_resolution_setting()
        if self.main_window.quick_download_now():
            self.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.download_now()
            event.accept()
            return
        if event.key() == Qt.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    metadata_loaded = pyqtSignal(dict)
    metadata_failed = pyqtSignal(int, str)
    quick_channel_logo_loaded = pyqtSignal(dict)
    channel_metadata_loaded = pyqtSignal(dict)
    channel_marked_archived = pyqtSignal(dict)
    channel_mark_archive_failed = pyqtSignal(str)
    channel_sections_checked = pyqtSignal(dict)
    yt_dlp_version_checked = pyqtSignal(dict)

    def __init__(self, launcher: TrayLauncher):
        super().__init__()
        self.launcher = launcher
        self.setWindowTitle(APP_TITLE)
        self.setFixedSize(900, 620)
        self.launcher.apply_taskbar_mode_to_window(self)
        if self.launcher.app_icon_path.exists():
            self.setWindowIcon(QIcon(str(self.launcher.app_icon_path)))
        self.preview_request_id = 0
        self.preview_request_context = "queue"
        self.pending_preview_context = "queue"
        self.current_preview = {}
        self.current_previews = {"overview": {}, "queue": {}, "quick": {}}
        self.ui_settings = self.load_ui_settings()
        self.language = normalize_language(self.ui_settings.get("language") or getattr(self.launcher, "language", "en"))
        self.i18n_entries = []
        self._window_position_ready = False
        self.theme = self.ui_settings.get("theme", "dark")
        if self.theme not in {"dark", "light", "system"}:
            self.theme = "dark"
        self.channel_cards = {}
        self.channel_cache_dir = self.launcher.cache_dir / "channels"
        self.channel_rules = {}
        self.channel_section_results = {}
        self.channel_section_checks_running = set()
        self.channel_section_checks_pending = {}
        self.channel_paid_content_checks_running = set()
        self.active_channel_section_check = None
        self.channel_section_checks_active = False
        self.channel_section_stop_event = threading.Event()
        self.channel_check_animation_step = 0
        self.archive_window = None
        self.quick_download_dialog = None
        self.diagnostics_tab = None
        self.diagnostics_text = None
        self.diagnostics_revealed = False
        self.overview_logo_clicks = 0
        self.overview_easter_game = None
        self.overview_easter_unlocked = False
        self.overview_easter_victory_pixmap = QPixmap()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.theme_corner = QWidget()
        self.theme_corner.setObjectName("themeCorner")
        self.theme_corner.setFixedSize(32, 32)
        theme_corner_layout = QVBoxLayout(self.theme_corner)
        theme_corner_layout.setContentsMargins(0, 1, 0, 0)
        theme_corner_layout.setSpacing(0)
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("themeButton")
        self.theme_button.setFixedSize(32, 32)
        self._set_i18n(self.theme_button, "settings.theme_toggle", "toolTip")
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
        self.yt_dlp_version_checked.connect(self.on_yt_dlp_version_checked)

        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.refresh_log_view)
        self.log_timer.start(5000)
        self.channel_check_animation_timer = QTimer(self)
        self.channel_check_animation_timer.setInterval(350)
        self.channel_check_animation_timer.timeout.connect(self.animate_channel_checks)
        self.system_theme_timer = QTimer(self)
        self.system_theme_timer.timeout.connect(self.refresh_system_theme)
        self.system_theme_timer.start(30000)
        self.window_position_timer = QTimer(self)
        self.window_position_timer.setSingleShot(True)
        self.window_position_timer.timeout.connect(self.save_window_position)
        self.apply_theme()
        self.apply_language()
        self.restore_window_position()
        self._window_position_ready = True

    def tr(self, key: str, **values) -> str:
        return ui_text(getattr(self, "language", "en"), key, **values)

    def _set_i18n(self, widget, key: str, prop: str = "text", **values):
        self.i18n_entries.append((widget, key, prop, dict(values)))
        self._apply_i18n_entry(widget, key, prop, values)
        return widget

    def _apply_i18n_entry(self, widget, key: str, prop: str, values: dict):
        if widget is None:
            return
        text = self.tr(key, **values)
        if prop == "text":
            widget.setText(text)
        elif prop == "toolTip":
            widget.setToolTip(text)
        elif prop == "placeholderText":
            widget.setPlaceholderText(text)
        elif prop == "windowTitle":
            widget.setWindowTitle(text)

    def _replace_combo_items(self, combo: QComboBox, items, selected=None):
        if combo is None:
            return
        selected = combo.currentData() if selected is None else selected
        combo.blockSignals(True)
        combo.clear()
        for label, value in items:
            combo.addItem(label, value)
        index = combo.findData(selected)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _update_tab_titles(self):
        for tab, key in (
            (getattr(self, "overview_tab", None), "tab.overview"),
            (getattr(self, "channels_tab", None), "tab.channels"),
            (getattr(self, "queue_tab", None), "tab.queue"),
            (getattr(self, "settings_tab", None), "tab.settings"),
            (getattr(self, "diagnostics_tab", None), "tab.diagnostics"),
        ):
            if tab is None:
                continue
            index = self.tabs.indexOf(tab)
            if index >= 0:
                self.tabs.setTabText(index, self.tr(key if key != "tab.diagnostics" else "tab.diagnostics"))
                if key == "tab.diagnostics":
                    self.tabs.setTabText(index, "🩺")
                    self.tabs.setTabToolTip(index, self.tr("tab.diagnostics"))

    def _refresh_localized_combos(self):
        if hasattr(self, "resolution_combo"):
            self._replace_combo_items(
                self.resolution_combo,
                localized_resolution_options(self.language),
                self.resolution_combo.currentData() or self.launcher.max_resolution,
            )
        if hasattr(self, "startup_mode_combo"):
            self._replace_combo_items(
                self.startup_mode_combo,
                localized_startup_display_modes(self.language),
                self.startup_mode_combo.currentData() or self.launcher.startup_display_mode,
            )
        if hasattr(self, "log_filter_combo"):
            self._replace_combo_items(
                self.log_filter_combo,
                (
                    (self.tr("logs.all"), "all"),
                    (self.tr("logs.important"), "important"),
                    (self.tr("logs.errors"), "errors"),
                ),
                self.log_filter_combo.currentData() or "all",
            )
        if hasattr(self, "language_combo"):
            self._replace_combo_items(self.language_combo, LANGUAGE_OPTIONS, self.language)

    def apply_language(self):
        self.language = normalize_language(self.ui_settings.get("language") or getattr(self.launcher, "language", "en"))
        self.launcher.language = self.language
        direction = Qt.RightToLeft if self.language == "ar" else Qt.LeftToRight
        QApplication.instance().setLayoutDirection(direction)
        self.setLayoutDirection(direction)
        self.tabs.setLayoutDirection(direction)
        self.theme_corner.setLayoutDirection(Qt.LeftToRight)
        for widget, key, prop, values in list(self.i18n_entries):
            self._apply_i18n_entry(widget, key, prop, values)
        self._refresh_static_texts()
        self._update_tab_titles()
        self._refresh_localized_combos()
        self.update_telegram_enabled_button()
        self.update_quick_hotkey_button()
        self.update_check_channel_sections_tooltip()
        self.set_channel_section_check_button_running(getattr(self, "channel_section_checks_active", False))
        self.apply_theme()
        if getattr(self, "quick_download_dialog", None) is not None:
            self.quick_download_dialog.apply_language()
        if getattr(self, "archive_window", None) is not None:
            self.archive_window.apply_language()
        self.launcher.update_tray_menu()

    def _refresh_static_texts(self):
        if hasattr(self, "overview_quick_button"):
            self.overview_quick_button.setToolTip(self.tr("button.quick"))
            self.overview_final_button.setToolTip(self.tr("button.open_downloads"))
            self.overview_temp_button.setToolTip(self.tr("button.open_temp"))
            self.overview_archive_button.setText(self.tr("button.archive"))
            self.overview_archive_button.setToolTip(self.tr("button.open_archive"))
            self.overview_archive_button.setFixedWidth(max(34, self.overview_archive_button.fontMetrics().horizontalAdvance(self.overview_archive_button.text()) + 18))
            self.overview_add_video_button.setText(self.tr("button.add_queue"))
            self.overview_add_video_button.setToolTip(self.tr("overview.add_queue_tip"))
            self.overview_download_video_button.setText(self.tr("button.download"))
            self.overview_download_video_button.setToolTip(self.tr("overview.download_tip"))
            self.overview_main_image.setToolTip(self.tr("overview.logo_tip"))
            self.overview_video_image.setToolTip(self.tr("overview.video_placeholder_tip"))
            for key, (label, emoji) in getattr(self, "overview_type_name_labels", {}).items():
                label.setText(f"{emoji} {self.tr(key)}")
        if hasattr(self, "check_paid_content_check"):
            self.check_paid_content_check.setText(self.tr("channels.check_paid"))
            self.check_paid_content_check.setToolTip(self.tr("channels.check_paid_tip"))
        if hasattr(self, "schedule_title_label"):
            self.schedule_title_label.setText(self.tr("queue.planner"))
            self.schedule_enabled_check.setText(self.tr("queue.enabled"))
            self.schedule_enabled_check.setToolTip(self.tr("queue.new_enabled_tip"))
            self.schedule_add_button.setText(self.tr("queue.add"))
            self.schedule_add_button.setToolTip(self.tr("queue.add_tip"))
            self.schedule_toggle_button.setText(self.tr("queue.toggle"))
            self.schedule_toggle_button.setToolTip(self.tr("queue.toggle_tip"))
            self.schedule_remove_button.setText(self.tr("queue.remove"))
            self.schedule_remove_button.setToolTip(self.tr("queue.remove_tip"))
            self.schedule_run_at_label.setText(self.tr("queue.run_at"))
            self.queue_title_label.setText(self.tr("queue.video_queue"))
            self.add_video_button.setText(self.tr("button.add_queue"))
            self.add_video_button.setToolTip(self.tr("overview.add_queue_tip"))
            self.queue_remove_button.setText(self.tr("queue.remove_selected"))
            self.queue_remove_button.setToolTip(self.tr("queue.remove_selected_tip"))
            self.queue_reload_button.setText(self.tr("queue.reload"))
            self.queue_reload_button.setToolTip(self.tr("queue.reload_tip"))
            if not self.video_url_input.text().strip() and not self.current_previews.get("queue"):
                self.video_title_label.setText(self.tr("preview.queue_wait"))
            if self.thumbnail_label.text():
                self.thumbnail_label.setText(self.tr("preview.thumbnail"))
        if hasattr(self, "settings_download_title_label"):
            self.settings_download_title_label.setText(self.tr("settings.download"))
            self.download_dir_input.setToolTip(self.tr("settings.downloads_tip"))
            self.temp_dir_input.setToolTip(self.tr("settings.temp_tip"))
            for label, button, key in getattr(self, "path_setting_rows", []):
                label_text = self.tr(key)
                label.setText(label_text)
                button.setToolTip(self.tr("settings.choose", label=label_text))
            self.videos_limit_spin.setToolTip(self.tr("settings.videos_tip"))
            self.shorts_limit_spin.setToolTip(self.tr("settings.shorts_tip"))
            self.streams_limit_spin.setToolTip(self.tr("settings.streams_tip"))
            self.settings_limits_label.setText(self.tr("settings.limits"))
            self.settings_limits_label.setToolTip(self.tr("settings.limits_tip"))
            for (label, spin), text in zip(
                getattr(self, "limit_labels", []),
                ("🎬 " + self.tr("overview.video"), "  ⚡ " + self.tr("overview.shorts"), "  🔴 " + self.tr("overview.stream")),
            ):
                label.setText(text)
                label.setToolTip(spin.toolTip())
            self.resolution_combo.setToolTip(self.tr("settings.resolution_tip"))
            self.settings_resolution_label.setText(self.tr("settings.resolution"))
            self.settings_behavior_title_label.setText(self.tr("settings.behavior"))
            self.language_label.setText("🌐 " + self.tr("app.language"))
            self.clipboard_label.setText(self.tr("settings.quick_download"))
            self.clipboard_watch_check.setText(self.tr("settings.watch_clipboard"))
            self.clipboard_watch_check.setToolTip(self.tr("settings.watch_clipboard_tip"))
            self.autostart_check.setText(self.tr("settings.autostart"))
            self.autostart_check.setToolTip(self.tr("settings.autostart_tip", app=APP_NAME))
            self.startup_mode_combo.setToolTip(self.tr("settings.startup_mode_tip"))
            self.options_label.setText(self.tr("settings.misc"))
            self.cleanup_temp_check.setText(self.tr("settings.cleanup_temp"))
            self.cleanup_temp_check.setToolTip(self.tr("settings.cleanup_temp_tip"))
            self.retry_queue_check.setText(self.tr("settings.retry_queue"))
            self.retry_queue_check.setToolTip(self.tr("settings.retry_queue_tip"))
            self.log_keep_label.setText(self.tr("settings.logs_count"))
            self.log_keep_spin.setToolTip(self.tr("settings.logs_count_tip"))
            self.rules_button.setToolTip(self.tr("settings.rules_tip"))
            self.ytdlp_version_button.setToolTip(self.tr("settings.ytdlp_tip"))
            self.diagnostics_secret_button.setToolTip(self.tr("settings.diagnostics_tip"))
            self.settings_save_button.setText(self.tr("button.save_settings"))
            self.settings_save_button.setToolTip(self.tr("telegram.save_tip"))
            self.settings_open_env_button.setText(self.tr("button.open_env"))
            self.settings_open_env_button.setToolTip(self.tr("telegram.open_env_tip"))
            self.logs_title_label.setText(self.tr("logs.title"))
            self.log_filter_combo.setToolTip(self.tr("logs.filter_tip"))
            self.logs_refresh_button.setText(self.tr("button.refresh_list"))
            self.logs_refresh_button.setToolTip(self.tr("logs.refresh_tip"))
            self.logs_reload_button.setText(self.tr("button.reload_log"))
            self.logs_reload_button.setToolTip(self.tr("logs.reload_tip"))
        if hasattr(self, "diagnostics_title_label"):
            self.diagnostics_title_label.setText(self.tr("diagnostics.title"))
            self.diagnostics_refresh_button.setText(self.tr("button.refresh"))
            self.diagnostics_copy_button.setText(self.tr("button.copy"))

    def on_language_changed(self, *_args):
        if not hasattr(self, "language_combo"):
            return
        language = normalize_language(self.language_combo.currentData())
        if language == self.language:
            return
        self.language = language
        self.ui_settings["language"] = language
        self.save_ui_settings()
        self.launcher.app_settings = dict(self.ui_settings)
        self.launcher.apply_runtime_settings(self.launcher.app_settings)
        self.apply_language()
        self.refresh_all()

    def _build_overview_tab(self):
        tab = QWidget()
        self.overview_tab = tab
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
        self.run_button.setToolTip(self.tr("overview.run"))
        self.run_button.clicked.connect(self.toggle_download)

        overview_toolbar_font = QFont(self.font())
        overview_toolbar_font.setPixelSize(12)
        overview_toolbar_font.setBold(True)

        def setup_overview_toolbar_button(button: QPushButton, min_width: int = 30, extra_width: int = 0):
            button.setObjectName("overviewToolbarButton")
            button.setFont(overview_toolbar_font)
            width = max(min_width, button.fontMetrics().horizontalAdvance(button.text()) + 14 + extra_width)
            button.setFixedSize(width, 28)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        quick_btn = QPushButton("🚀")
        setup_overview_toolbar_button(quick_btn)
        quick_btn.setToolTip(self.tr("button.quick"))
        quick_btn.clicked.connect(lambda checked=False: self.open_quick_download_window())
        final_btn = QPushButton("📁")
        setup_overview_toolbar_button(final_btn)
        final_btn.setToolTip(self.tr("button.open_downloads"))
        final_btn.clicked.connect(lambda: self.open_folder(self.launcher.final_dir))
        temp_btn = QPushButton("⌛")
        setup_overview_toolbar_button(temp_btn)
        temp_btn.setToolTip(self.tr("button.open_temp"))
        temp_btn.clicked.connect(lambda: self.open_folder(self.launcher.temp_dir))
        archive_btn = QPushButton(self.tr("button.archive"))
        setup_overview_toolbar_button(archive_btn, extra_width=4)
        archive_btn.setToolTip(self.tr("button.open_archive"))
        archive_btn.clicked.connect(self.open_archive_window)
        self.overview_quick_button = quick_btn
        self.overview_final_button = final_btn
        self.overview_temp_button = temp_btn
        self.overview_archive_button = archive_btn
        top_row.addWidget(self.run_button, 0, Qt.AlignLeft | Qt.AlignTop)
        for button in (quick_btn, final_btn, temp_btn, archive_btn):
            top_row.addWidget(button, 0, Qt.AlignLeft | Qt.AlignVCenter)
        top_row.addStretch(1)
        top_row.addLayout(metrics_row)
        header_layout.addLayout(top_row)

        overview_queue_row = QHBoxLayout()
        overview_queue_row.setSpacing(8)
        self.overview_video_url_input = QLineEdit()
        self.overview_video_url_input.setPlaceholderText(self.tr("placeholder.youtube_url"))
        self.overview_video_url_input.textChanged.connect(lambda: self.schedule_video_preview("overview"))
        self.overview_add_video_button = QPushButton(self.tr("button.add_queue"))
        self.overview_add_video_button.setFixedHeight(30)
        self.overview_add_video_button.setToolTip(self.tr("overview.add_queue_tip"))
        self.overview_add_video_button.setEnabled(False)
        self.overview_add_video_button.clicked.connect(lambda: self.add_video_to_queue("overview"))
        self.overview_download_video_button = QPushButton(self.tr("button.download"))
        self.overview_download_video_button.setFixedHeight(30)
        self.overview_download_video_button.setToolTip(self.tr("overview.download_tip"))
        self.overview_download_video_button.setEnabled(False)
        self.overview_download_video_button.clicked.connect(self.download_overview_video_now)
        overview_queue_row.addWidget(self.overview_video_url_input, 1)
        overview_queue_row.addWidget(self.overview_download_video_button, 0)
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
        self.overview_logo_stack = QStackedWidget()
        self.overview_logo_stack.setFixedSize(232, 232)
        self.overview_main_image = ClickableLabel()
        self.overview_main_image.setObjectName("overviewMainImage")
        self.overview_main_image.setAlignment(Qt.AlignCenter)
        self.overview_main_image.setFixedSize(232, 232)
        self.overview_main_image.setToolTip(self.tr("overview.logo_tip"))
        self.overview_main_image.clicked.connect(self.on_overview_logo_clicked)

        self.overview_logo_stack.addWidget(self.overview_main_image)
        media_layout.addWidget(self.overview_logo_stack, 0, Qt.AlignHCenter | Qt.AlignVCenter)
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
        self.overview_type_name_labels = {}
        self.overview_channel_label = self._overview_type_status_row(status_grid, 0, "📺", "overview.channel")
        self.overview_video_status_label = self._overview_type_status_row(status_grid, 1, "🎬", "overview.video")
        self.overview_shorts_status_label = self._overview_type_status_row(status_grid, 2, "⚡", "overview.shorts")
        self.overview_streams_status_label = self._overview_type_status_row(status_grid, 3, "🔴", "overview.stream")
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
        self.overview_video_image.setToolTip(self.tr("overview.video_placeholder_tip"))
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

        self.tabs.addTab(tab, self.tr("tab.overview"))

    def _overview_type_status_row(self, grid: QGridLayout, row: int, emoji: str, title_key: str):
        name = QLabel(f"{emoji} {self.tr(title_key)}")
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
        self.overview_type_name_labels[title_key] = (name, emoji)
        return status

    def _build_channels_tab(self):
        tab = QWidget()
        self.channels_tab = tab
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 10, 16, 16)
        layout.setSpacing(8)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.check_channel_sections_button = QPushButton(self.tr("channels.check"))
        self.check_channel_sections_button.setObjectName("checkChannelsButton")
        self.check_channel_sections_button.setLayoutDirection(Qt.LeftToRight)
        self.check_channel_sections_button.setFixedSize(220, 32)
        self.check_channel_sections_button.clicked.connect(self.toggle_channel_section_checks)
        self.check_paid_content_check = QCheckBox(self.tr("channels.check_paid"))
        self.check_paid_content_check.setChecked(self.check_paid_content_enabled())
        self.check_paid_content_check.setToolTip(self.tr("channels.check_paid_tip"))
        self.check_paid_content_check.toggled.connect(self.set_check_paid_content_enabled)
        self.channel_sections_status_label = QLabel("")
        self.channel_sections_status_label.setObjectName("subtleText")
        self.channel_sections_status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tools.addSpacing(11)
        tools.addWidget(self.check_channel_sections_button)
        tools.addWidget(self.check_paid_content_check)
        tools.addStretch()
        tools.addWidget(self.channel_sections_status_label, 0, Qt.AlignRight | Qt.AlignVCenter)
        layout.addLayout(tools)
        self.update_check_channel_sections_tooltip()

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

        self.tabs.addTab(tab, self.tr("tab.channels"))

    def _build_queue_tab(self):
        tab = QWidget()
        self.queue_tab = tab
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
        schedule_title = QLabel(self.tr("queue.planner"))
        schedule_title.setObjectName("sectionTitle")
        self.schedule_title_label = schedule_title
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
        self.schedule_enabled_check = QCheckBox(self.tr("queue.enabled"))
        self.schedule_enabled_check.setToolTip(self.tr("queue.new_enabled_tip"))
        self.schedule_enabled_check.setChecked(True)
        add_btn = QPushButton(self.tr("queue.add"))
        add_btn.setFixedHeight(30)
        add_btn.setToolTip(self.tr("queue.add_tip"))
        add_btn.clicked.connect(self.add_schedule)
        toggle_btn = QPushButton(self.tr("queue.toggle"))
        toggle_btn.setFixedHeight(30)
        toggle_btn.setToolTip(self.tr("queue.toggle_tip"))
        toggle_btn.clicked.connect(self.toggle_selected_schedule)
        remove_btn = QPushButton(self.tr("queue.remove"))
        remove_btn.setFixedHeight(30)
        remove_btn.setToolTip(self.tr("queue.remove_tip"))
        remove_btn.clicked.connect(self.remove_selected_schedule)
        self.schedule_run_at_label = QLabel(self.tr("queue.run_at"))
        top.addWidget(self.schedule_run_at_label, 0, 0)
        top.addWidget(self.schedule_hour_spin, 0, 1)
        top.addWidget(self.schedule_enabled_check, 0, 2)
        top.addWidget(add_btn, 1, 0, 1, 3)
        top.addWidget(toggle_btn, 2, 0, 1, 2)
        top.addWidget(remove_btn, 2, 2)
        self.schedule_add_button = add_btn
        self.schedule_toggle_button = toggle_btn
        self.schedule_remove_button = remove_btn
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
        queue_title = QLabel(self.tr("queue.video_queue"))
        queue_title.setObjectName("sectionTitle")
        self.queue_title_label = queue_title
        self.queue_summary_label = QLabel("")
        self.queue_summary_label.setObjectName("subtleText")
        queue_header.addWidget(queue_title)
        queue_header.addStretch()
        queue_header.addWidget(self.queue_summary_label)
        queue_layout.addLayout(queue_header)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.video_url_input = QLineEdit()
        self.video_url_input.setPlaceholderText(self.tr("placeholder.video_url"))
        self.video_url_input.textChanged.connect(lambda: self.schedule_video_preview("queue"))
        self.add_video_button = QPushButton(self.tr("button.add_queue"))
        self.add_video_button.setFixedHeight(30)
        self.add_video_button.setToolTip(self.tr("overview.add_queue_tip"))
        self.add_video_button.setEnabled(False)
        self.add_video_button.clicked.connect(lambda: self.add_video_to_queue("queue"))
        input_row.addWidget(self.video_url_input)
        input_row.addWidget(self.add_video_button)
        queue_layout.addLayout(input_row)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(12)
        self.thumbnail_label = QLabel(self.tr("preview.thumbnail"))
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setFixedSize(220, 124)
        self.thumbnail_label.setStyleSheet("border: 1px solid #555; background: #202020; color: #bbb;")
        preview_row.addWidget(self.thumbnail_label, 0, Qt.AlignTop)

        preview_info = QVBoxLayout()
        self.video_title_label = QLabel(self.tr("preview.queue_wait"))
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
        remove_btn = QPushButton(self.tr("queue.remove_selected"))
        remove_btn.setFixedHeight(30)
        remove_btn.setToolTip(self.tr("queue.remove_selected_tip"))
        remove_btn.clicked.connect(self.remove_selected_queued_video)
        reload_btn = QPushButton(self.tr("queue.reload"))
        reload_btn.setFixedHeight(30)
        reload_btn.setToolTip(self.tr("queue.reload_tip"))
        reload_btn.clicked.connect(self.refresh_queue)
        self.queue_remove_button = remove_btn
        self.queue_reload_button = reload_btn
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

        self.tabs.addTab(tab, self.tr("tab.queue"))

    def _build_logs_tab(self):
        tab = QWidget()
        self.settings_tab = tab
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

        download_title = QLabel(self.tr("settings.download"))
        download_title.setObjectName("sectionTitle")
        self.settings_download_title_label = download_title
        download_layout.addWidget(download_title)

        self.download_dir_input = QLineEdit()
        self.download_dir_input.setToolTip(self.tr("settings.downloads_tip"))
        download_layout.addLayout(self._path_setting_row(
            "settings.downloads",
            self.download_dir_input,
            lambda: self.choose_directory(self.download_dir_input),
        ))

        self.temp_dir_input = QLineEdit()
        self.temp_dir_input.setToolTip(self.tr("settings.temp_tip"))
        download_layout.addLayout(self._path_setting_row(
            "settings.temp",
            self.temp_dir_input,
            lambda: self.choose_directory(self.temp_dir_input),
        ))

        self.videos_limit_spin = self._limit_spin()
        self.videos_limit_spin.setToolTip(self.tr("settings.videos_tip"))
        self.shorts_limit_spin = self._limit_spin()
        self.shorts_limit_spin.setToolTip(self.tr("settings.shorts_tip"))
        self.streams_limit_spin = self._limit_spin()
        self.streams_limit_spin.setToolTip(self.tr("settings.streams_tip"))
        limits_row = QHBoxLayout()
        limits_row.setSpacing(0)
        limits_font = QFont(self.font())
        limits_font.setPointSize(max(8, limits_font.pointSize() - 2))
        limits_title = QLabel(self.tr("settings.limits"))
        limits_title.setFixedWidth(96)
        limits_title.setFont(limits_font)
        limits_title.setToolTip(self.tr("settings.limits_tip"))
        self.settings_limits_label = limits_title
        limits_row.addWidget(limits_title)
        limits_row.addSpacing(8)
        for label_text, spin in (
            ("🎬 " + self.tr("overview.video"), self.videos_limit_spin),
            ("  ⚡ " + self.tr("overview.shorts"), self.shorts_limit_spin),
            ("  🔴 " + self.tr("overview.stream"), self.streams_limit_spin),
        ):
            spin.setButtonSymbols(QSpinBox.NoButtons)
            spin.setAlignment(Qt.AlignCenter)
            spin.setFixedSize(36, 18)
            spin.setFont(limits_font)
            label = QLabel(label_text)
            label.setFixedSize(92, 18)
            label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            label.setFont(limits_font)
            label.setToolTip(spin.toolTip())
            if not hasattr(self, "limit_labels"):
                self.limit_labels = []
            self.limit_labels.append((label, spin))
            limit_group = QHBoxLayout()
            limit_group.setContentsMargins(0, 0, 0, 0)
            limit_group.setSpacing(0)
            limit_group.addWidget(label)
            limit_group.addWidget(spin)
            limits_row.addLayout(limit_group)
        limits_row.addStretch()
        download_layout.addLayout(limits_row)

        resolution_row = QHBoxLayout()
        resolution_row.setSpacing(8)
        self.resolution_combo = QComboBox()
        self.resolution_combo.setToolTip(self.tr("settings.resolution_tip"))
        self.resolution_combo.setFixedSize(128, 18)
        for label, value in localized_resolution_options(self.language):
            self.resolution_combo.addItem(label, value)
        resolution_label = QLabel(self.tr("settings.resolution"))
        resolution_label.setFixedWidth(96)
        resolution_font = QFont(limits_font)
        resolution_font.setPointSize(max(8, resolution_font.pointSize() - 1))
        resolution_label.setFont(resolution_font)
        self.settings_resolution_label = resolution_label
        resolution_row.addWidget(resolution_label)
        resolution_row.addWidget(self.resolution_combo, 0)
        resolution_row.addStretch(1)
        download_layout.addLayout(resolution_row)

        behavior_panel = QWidget()
        behavior_panel.setObjectName("toolPanel")
        behavior_layout = QVBoxLayout(behavior_panel)
        behavior_layout.setContentsMargins(10, 8, 10, 10)
        behavior_layout.setSpacing(8)
        behavior_title = QLabel(self.tr("settings.behavior"))
        behavior_title.setObjectName("sectionTitle")
        self.settings_behavior_title_label = behavior_title
        behavior_layout.addWidget(behavior_title)

        language_row = QHBoxLayout()
        language_row.setSpacing(8)
        self.language_label = QLabel("🌐 " + self.tr("app.language"))
        self.language_label.setFixedWidth(210)
        self.language_combo = QComboBox()
        self.language_combo.setFixedHeight(26)
        for label, value in LANGUAGE_OPTIONS:
            self.language_combo.addItem(label, value)
        language_row.addWidget(self.language_label)
        language_row.addWidget(self.language_combo, 1)
        behavior_layout.addLayout(language_row)
        self.language_combo.currentIndexChanged.connect(self.on_language_changed)

        clipboard_row = QHBoxLayout()
        clipboard_row.setSpacing(8)
        clipboard_label = QLabel(self.tr("settings.quick_download"))
        clipboard_label.setFixedWidth(210)
        self.clipboard_label = clipboard_label
        self.clipboard_watch_check = QCheckBox(self.tr("settings.watch_clipboard"))
        self.clipboard_watch_check.setToolTip(self.tr("settings.watch_clipboard_tip"))
        clipboard_row.addWidget(clipboard_label)
        clipboard_row.addWidget(self.clipboard_watch_check, 1)
        behavior_layout.addLayout(clipboard_row)

        startup_row = QHBoxLayout()
        startup_row.setSpacing(8)
        self.autostart_check = QCheckBox(self.tr("settings.autostart"))
        self.autostart_check.setToolTip(self.tr("settings.autostart_tip", app=APP_NAME))
        self.startup_mode_combo = QComboBox()
        self.startup_mode_combo.setToolTip(self.tr("settings.startup_mode_tip"))
        for label, value in localized_startup_display_modes(self.language):
            self.startup_mode_combo.addItem(label, value)
        startup_row.addWidget(self.autostart_check)
        startup_row.addWidget(self.startup_mode_combo, 1)
        behavior_layout.addLayout(startup_row)

        options_row = QHBoxLayout()
        options_row.setSpacing(6)
        options_font = QFont(self.font())
        options_font.setPointSize(max(8, options_font.pointSize() - 2))
        options_label = QLabel(self.tr("settings.misc"))
        options_label.setFixedWidth(82)
        options_label.setFont(options_font)
        self.options_label = options_label
        self.cleanup_temp_check = QCheckBox(self.tr("settings.cleanup_temp"))
        self.cleanup_temp_check.setToolTip(self.tr("settings.cleanup_temp_tip"))
        self.retry_queue_check = QCheckBox(self.tr("settings.retry_queue"))
        self.retry_queue_check.setToolTip(self.tr("settings.retry_queue_tip"))
        self.cleanup_temp_check.setFont(options_font)
        self.retry_queue_check.setFont(options_font)
        self.log_keep_spin = self._limit_spin(1, 50)
        self.log_keep_spin.setFixedWidth(38)
        self.log_keep_spin.setToolTip(self.tr("settings.logs_count_tip"))
        log_keep_label = QLabel(self.tr("settings.logs_count"))
        log_keep_label.setFont(options_font)
        self.log_keep_label = log_keep_label
        options_row.addWidget(options_label)
        options_row.addWidget(self.cleanup_temp_check)
        options_row.addWidget(self.retry_queue_check)
        options_row.addWidget(log_keep_label)
        options_row.addWidget(self.log_keep_spin)
        rules_btn = QPushButton("⚖")
        rules_btn.setFixedSize(30, 28)
        rules_btn.setToolTip(self.tr("settings.rules_tip"))
        rules_btn.clicked.connect(self.open_usage_rules)
        self.rules_button = rules_btn
        options_row.addWidget(rules_btn)
        self.ytdlp_version_button = QPushButton()
        self.ytdlp_version_button.setIcon(script_check_icon())
        self.ytdlp_version_button.setIconSize(QSize(22, 22))
        self.ytdlp_version_button.setFixedSize(34, 28)
        self.ytdlp_version_button.setToolTip(self.tr("settings.ytdlp_tip"))
        self.ytdlp_version_button.clicked.connect(self.check_yt_dlp_version)
        options_row.addWidget(self.ytdlp_version_button)
        self.quick_hotkey_button = QPushButton()
        self.quick_hotkey_button.setIcon(quick_hotkey_icon())
        self.quick_hotkey_button.setIconSize(QSize(20, 20))
        self.quick_hotkey_button.setFixedSize(30, 28)
        self.quick_hotkey_button.clicked.connect(self.open_quick_hotkey_dialog)
        options_row.addWidget(self.quick_hotkey_button)
        self.diagnostics_secret_button = QPushButton("·")
        self.diagnostics_secret_button.setFixedSize(14, 28)
        self.diagnostics_secret_button.setToolTip(self.tr("settings.diagnostics_tip"))
        self.diagnostics_secret_button.clicked.connect(self.open_diagnostics_tab)
        options_row.addWidget(self.diagnostics_secret_button)
        options_row.addStretch()
        behavior_layout.addLayout(options_row)

        telegram_panel = QWidget()
        telegram_panel.setObjectName("toolPanel")
        telegram_panel.setFixedWidth(306)
        telegram_layout = QVBoxLayout(telegram_panel)
        telegram_layout.setContentsMargins(10, 10, 10, 10)
        telegram_layout.setSpacing(10)

        telegram_header = QHBoxLayout()
        telegram_title = QLabel("Telegram")
        telegram_title.setObjectName("sectionTitle")
        telegram_header.addWidget(telegram_title)
        telegram_header.addStretch()
        telegram_layout.addLayout(telegram_header)

        self.telegram_enabled_button = QPushButton()
        self.telegram_enabled_button.setObjectName("telegramToggleButton")
        self.telegram_enabled_button.setCheckable(True)
        self.telegram_enabled_button.setFixedHeight(30)
        self.telegram_enabled_button.clicked.connect(self.on_telegram_enabled_clicked)
        telegram_layout.addWidget(self.telegram_enabled_button)

        self.bot_token_input, self.bot_token_eye = self._secret_input()
        self.channel_id_input, self.channel_id_eye = self._secret_input()
        self.proxy_url_input, self.proxy_url_eye = self._secret_input()
        telegram_form = QGridLayout()
        telegram_form.setContentsMargins(0, 12, 0, 0)
        telegram_form.setHorizontalSpacing(8)
        telegram_form.setVerticalSpacing(10)
        for row, (label_text, line_edit, eye_button) in enumerate((
            ("BOT_TOKEN", self.bot_token_input, self.bot_token_eye),
            ("CHANNEL_ID", self.channel_id_input, self.channel_id_eye),
            ("PROXY_URL", self.proxy_url_input, self.proxy_url_eye),
        )):
            label = QLabel(label_text)
            label.setFixedWidth(104)
            line_edit.setToolTip(self.tr("telegram.secret_tip", label=label_text))
            line_edit.setFixedHeight(30)
            line_edit.setFixedWidth(132)
            telegram_form.addWidget(label, row, 0)
            telegram_form.addWidget(line_edit, row, 1)
            telegram_form.addWidget(eye_button, row, 2)
        telegram_layout.addLayout(telegram_form)
        telegram_layout.addStretch(1)

        save_row = QHBoxLayout()
        save_row.setSpacing(8)
        save_font = QFont(self.font())
        save_font.setPointSize(max(8, save_font.pointSize() - 4))
        save_btn = QPushButton(self.tr("button.save_settings"))
        save_btn.setFont(save_font)
        save_btn.setFixedHeight(30)
        save_btn.setFixedWidth(166)
        save_btn.setToolTip(self.tr("telegram.save_tip"))
        save_btn.clicked.connect(lambda: self.save_settings_from_ui(show_message=True))
        self.settings_save_button = save_btn
        open_env_btn = QPushButton(self.tr("button.open_env"))
        open_env_btn.setFont(save_font)
        open_env_btn.setFixedHeight(30)
        open_env_btn.setFixedWidth(112)
        open_env_btn.setToolTip(self.tr("telegram.open_env_tip"))
        open_env_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.launcher.env_file))))
        self.settings_open_env_button = open_env_btn
        save_row.addWidget(save_btn)
        save_row.addStretch(1)
        save_row.addWidget(open_env_btn)
        telegram_layout.addLayout(save_row)

        left_settings = QVBoxLayout()
        left_settings.setContentsMargins(0, 0, 0, 0)
        left_settings.setSpacing(10)
        left_settings.addWidget(download_panel)
        left_settings.addWidget(behavior_panel)
        settings_row.addLayout(left_settings, 1)
        settings_row.addWidget(telegram_panel, 0)
        layout.addLayout(settings_row)

        logs_panel = QWidget()
        logs_panel.setObjectName("toolPanel")
        logs_layout = QVBoxLayout(logs_panel)
        logs_layout.setContentsMargins(10, 8, 10, 10)
        logs_layout.setSpacing(8)

        top = QHBoxLayout()
        logs_title = QLabel(self.tr("logs.title"))
        logs_title.setObjectName("sectionTitle")
        self.logs_title_label = logs_title
        self.log_combo = QComboBox()
        self.log_combo.setMinimumWidth(340)
        self.log_filter_combo = QComboBox()
        self.log_filter_combo.setFixedWidth(120)
        self.log_filter_combo.setToolTip(self.tr("logs.filter_tip"))
        for label, value in ((self.tr("logs.all"), "all"), (self.tr("logs.important"), "important"), (self.tr("logs.errors"), "errors")):
            self.log_filter_combo.addItem(label, value)
        self.log_filter_combo.currentIndexChanged.connect(lambda *_: self.refresh_log_view())
        log_control_height = 26
        self.log_combo.setFixedHeight(log_control_height)
        self.log_filter_combo.setFixedHeight(log_control_height)
        refresh_btn = QPushButton(self.tr("button.refresh_list"))
        refresh_btn.setFixedHeight(log_control_height)
        refresh_btn.setToolTip(self.tr("logs.refresh_tip"))
        refresh_btn.clicked.connect(self.refresh_logs)
        reload_btn = QPushButton(self.tr("button.reload_log"))
        reload_btn.setFixedHeight(log_control_height)
        reload_btn.setToolTip(self.tr("logs.reload_tip"))
        reload_btn.clicked.connect(self.refresh_log_view)
        self.logs_refresh_button = refresh_btn
        self.logs_reload_button = reload_btn
        top.addWidget(logs_title)
        top.addWidget(self.log_combo, 1)
        top.addWidget(refresh_btn)
        top.addWidget(reload_btn)
        top.addWidget(self.log_filter_combo)
        logs_layout.addLayout(top)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        logs_layout.addWidget(self.log_view, 1)
        layout.addWidget(logs_panel, 1)

        self.refresh_settings_controls()

        self.tabs.addTab(tab, self.tr("tab.settings"))

    def _limit_spin(self, minimum: int = 1, maximum: int = 100):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setFixedWidth(46)
        return spin

    def _path_setting_row(self, label_key: str, line_edit: QLineEdit, callback):
        row = QHBoxLayout()
        row.setSpacing(8)
        label_text = self.tr(label_key)
        label = QLabel(label_text)
        label.setFixedWidth(96)
        button = QPushButton("...")
        button.setFixedSize(34, 30)
        button.setToolTip(self.tr("settings.choose", label=label_text))
        button.clicked.connect(callback)
        if not hasattr(self, "path_setting_rows"):
            self.path_setting_rows = []
        self.path_setting_rows.append((label, button, label_key))
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
        self._set_i18n(button, "telegram.eye_tip", "toolTip")
        button.clicked.connect(lambda checked=False, field=line_edit: self.toggle_secret_visibility(field, checked))
        return line_edit, button

    def _secret_setting_row(self, label_text: str, line_edit: QLineEdit, eye_button: QPushButton):
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(label_text)
        label.setFixedWidth(104)
        line_edit.setToolTip(self.tr("telegram.secret_tip", label=label_text))
        row.addWidget(label)
        row.addWidget(line_edit, 1)
        row.addWidget(eye_button)
        return row

    def toggle_secret_visibility(self, field: QLineEdit, visible: bool):
        field.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)

    def update_telegram_enabled_button(self):
        enabled = self.telegram_enabled_button.isChecked()
        if enabled:
            self.telegram_enabled_button.setText(self.tr("telegram.enabled"))
            self.telegram_enabled_button.setToolTip(self.tr("telegram.enabled_tip"))
        else:
            self.telegram_enabled_button.setText(self.tr("telegram.disabled"))
            self.telegram_enabled_button.setToolTip(self.tr("telegram.disabled_tip"))

    def on_telegram_enabled_clicked(self, checked: bool):
        self.update_telegram_enabled_button()
        self.save_settings_from_ui(show_message=False)

    def update_quick_hotkey_button(self):
        hotkey = self.launcher.quick_download_hotkey or DEFAULT_QUICK_DOWNLOAD_HOTKEY
        self.quick_hotkey_button.setToolTip(self.tr("settings.hotkey_tip", hotkey=hotkey))

    def install_current_system_hotkey(self, editor: QKeySequenceEdit):
        sequence = editor.keySequence().toString(QKeySequence.NativeText).strip() or DEFAULT_QUICK_DOWNLOAD_HOTKEY
        self.ui_settings["quick_download_hotkey"] = sequence
        self.save_settings_from_ui(show_message=False)
        self.launcher.quick_download_hotkey = sequence
        self.launcher.refresh_global_hotkey()
        self.update_quick_hotkey_button()
        ok, message = self.launcher.install_system_quick_hotkey(sequence)
        if ok:
            QMessageBox.information(self, self.tr("dialog.hotkey"), message)
        else:
            QMessageBox.warning(self, self.tr("dialog.hotkey"), message)

    def open_quick_hotkey_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("dialog.hotkey_title"))
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        label = QLabel(self.tr("dialog.hotkey"))
        label.setObjectName("sectionTitle")
        layout.addWidget(label)

        editor = QKeySequenceEdit(QKeySequence(self.launcher.quick_download_hotkey or DEFAULT_QUICK_DOWNLOAD_HOTKEY))
        editor.setToolTip(self.tr("dialog.hotkey_tip"))
        layout.addWidget(editor)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        default_button = buttons.addButton(self.tr("dialog.default"), QDialogButtonBox.ResetRole)
        system_button = buttons.addButton(self.tr("dialog.system"), QDialogButtonBox.ActionRole)
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
                self.launcher.show_notification(icon, self.tr("dialog.hotkey"), message)

    def open_usage_rules(self):
        required = not self.launcher.usage_rules_accepted()
        dialog = UsageRulesDialog(required=required, parent=self, language=self.language)
        if dialog.exec_() == QDialog.Accepted and required:
            self.ui_settings["usage_rules_accepted_version"] = USAGE_RULES_VERSION
            self.save_ui_settings()
            self.launcher.app_settings = dict(self.ui_settings)
            self.launcher.apply_runtime_settings(self.launcher.app_settings)

    def check_yt_dlp_version(self):
        if hasattr(self, "ytdlp_version_button"):
            self.ytdlp_version_button.setEnabled(False)
            self.ytdlp_version_button.setToolTip(self.tr("settings.ytdlp_checking"))
        thread = threading.Thread(target=self._yt_dlp_version_worker, daemon=True)
        thread.start()

    def _yt_dlp_version_worker(self):
        info = {
            "current": "",
            "latest": "",
            "error": "",
            "command": " ".join(self.launcher.yt_dlp_command()),
            "frozen": bool(getattr(sys, "frozen", False)),
        }
        try:
            result = subprocess.run(
                self.launcher.yt_dlp_command() + ["--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self.launcher.script_environment(),
                timeout=12,
                check=False,
            )
            if result.returncode == 0:
                info["current"] = (result.stdout or "").strip().splitlines()[0] if (result.stdout or "").strip() else ""
            else:
                info["error"] = (result.stderr or result.stdout or self.tr("yt_dlp.unknown_current")).strip()
        except Exception as exc:
            info["error"] = str(exc)

        try:
            request = urllib.request.Request(
                "https://pypi.org/pypi/yt-dlp/json",
                headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            info["latest"] = str((payload.get("info") or {}).get("version") or "").strip()
        except Exception as exc:
            if info["error"]:
                info["error"] += f"\nPyPI: {exc}"
            else:
                info["error"] = f"{self.tr('yt_dlp.unknown_latest')}: {exc}"
        self.yt_dlp_version_checked.emit(info)

    def yt_dlp_version_key(self, version: str):
        return tuple(int(part) for part in re.findall(r"\d+", str(version or "")))

    def on_yt_dlp_version_checked(self, info: dict):
        current = str(info.get("current") or "").strip()
        latest = str(info.get("latest") or "").strip()
        error = str(info.get("error") or "").strip()
        if hasattr(self, "ytdlp_version_button"):
            self.ytdlp_version_button.setEnabled(True)
            tooltip = f"yt-dlp: {current or self.tr('yt_dlp.unknown_current')}"
            if latest:
                tooltip += f" / latest {latest}"
            self.ytdlp_version_button.setToolTip(tooltip)

        lines = [
            self.tr("yt_dlp.current", value=current or self.tr("yt_dlp.unknown_current")),
            self.tr("yt_dlp.latest", value=latest or self.tr("yt_dlp.unknown_latest")),
        ]
        current_key = self.yt_dlp_version_key(current)
        latest_key = self.yt_dlp_version_key(latest)
        if current_key and latest_key:
            if latest_key > current_key:
                lines.append(self.tr("yt_dlp.new_available"))
                if info.get("frozen"):
                    lines.append(self.tr("yt_dlp.frozen_update"))
                else:
                    lines.append(self.tr("yt_dlp.source_update"))
            else:
                lines.append(self.tr("yt_dlp.current_ok"))
        if error:
            lines.append("")
            lines.append(error[:600])
        QMessageBox.information(self, "yt-dlp", "\n".join(lines))
        if self.diagnostics_tab is not None:
            self.refresh_diagnostics()

    def open_diagnostics_tab(self):
        self.diagnostics_revealed = True
        self.ensure_diagnostics_tab()
        index = self.tabs.indexOf(self.diagnostics_tab)
        if index >= 0:
            self.tabs.setCurrentIndex(index)
        self.refresh_diagnostics()

    def ensure_diagnostics_tab(self):
        if not self.diagnostics_revealed:
            return
        if self.diagnostics_tab is None:
            self.diagnostics_tab = self._build_diagnostics_tab()
        if self.tabs.indexOf(self.diagnostics_tab) < 0:
            self.tabs.addTab(self.diagnostics_tab, "🩺")
            self.tabs.setTabToolTip(self.tabs.indexOf(self.diagnostics_tab), self.tr("tab.diagnostics"))

    def on_tab_changed(self, _index: int):
        if self.diagnostics_revealed:
            self.ensure_diagnostics_tab()
        index = self.tabs.indexOf(self.diagnostics_tab)
        if index >= 0 and self.tabs.currentIndex() == index:
            self.refresh_diagnostics()

    def _build_diagnostics_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel(self.tr("diagnostics.title"))
        title.setObjectName("sectionTitle")
        self.diagnostics_title_label = title
        refresh_btn = QPushButton(self.tr("button.refresh"))
        refresh_btn.setFixedHeight(28)
        refresh_btn.clicked.connect(self.refresh_diagnostics)
        copy_btn = QPushButton(self.tr("button.copy"))
        copy_btn.setFixedHeight(28)
        copy_btn.clicked.connect(self.copy_diagnostics_report)
        self.diagnostics_refresh_button = refresh_btn
        self.diagnostics_copy_button = copy_btn
        top.addWidget(title)
        top.addStretch()
        top.addWidget(refresh_btn)
        top.addWidget(copy_btn)
        layout.addLayout(top)

        self.diagnostics_text = QTextEdit()
        self.diagnostics_text.setReadOnly(True)
        self.diagnostics_text.setObjectName("diagnosticsText")
        layout.addWidget(self.diagnostics_text, 1)
        return tab

    def refresh_diagnostics(self):
        if self.diagnostics_text is not None:
            self.diagnostics_text.setPlainText(self.collect_diagnostics_report())

    def copy_diagnostics_report(self):
        report = self.collect_diagnostics_report()
        QApplication.clipboard().setText(report)
        self.launcher.show_notification("🩺", self.tr("diagnostics.title"), self.tr("diagnostics.copied"))

    def command_version_line(self, command: list[str], timeout: int = 4) -> str:
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=self.launcher.script_environment(),
                check=False,
            )
        except Exception as exc:
            return self.tr("diagnostics.command_error", error=exc)
        output = (result.stdout or "").strip().splitlines()
        first = output[0].strip() if output else ""
        if result.returncode != 0:
            return self.tr("diagnostics.command_exit", code=result.returncode, detail=first[:160])
        return first[:180] if first else self.tr("diagnostics.command_ok")

    def tool_report_line(self, label: str, command: str, args: list[str] | None = None, path: Path | None = None) -> str:
        resolved = str(path) if path else (shutil.which(command) or "")
        if not resolved:
            return self.tr("diagnostics.tool_missing", label=label)
        version = self.command_version_line([resolved] + list(args or ["--version"]))
        return f"{label}: {resolved} | {version}"

    def path_writable(self, path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / ".yth-write-test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            return True
        except OSError:
            return False

    def path_size(self, path: Path) -> int:
        total = 0
        try:
            if path.is_file():
                return path.stat().st_size
            if not path.exists():
                return 0
            for item in path.rglob("*"):
                with contextlib.suppress(OSError):
                    if item.is_file():
                        total += item.stat().st_size
        except OSError:
            return total
        return total

    def path_report_line(self, label: str, path: Path) -> str:
        free, total, error = self.launcher.free_space_for_path(path)
        writable = self.tr("diagnostics.yes") if self.path_writable(path) else self.tr("diagnostics.no")
        if error:
            return self.tr("diagnostics.path_error", label=label, path=path, error=error, writable=writable)
        return self.tr(
            "diagnostics.path_space",
            label=label,
            path=path,
            free=self.launcher.human_size(free),
            total=self.launcher.human_size(total),
            writable=writable,
        )

    def file_count(self, path: Path) -> int:
        try:
            return len([line for line in read_text_for_display(path).splitlines() if line.strip() and not line.strip().startswith("#")])
        except Exception:
            return 0

    def current_hotkey_status(self) -> str:
        if self.launcher.is_wayland_session():
            return self.tr("hotkey.wayland_status")
        hotkey_filter = self.launcher.hotkey_filter
        if hotkey_filter is None:
            return self.tr("hotkey.not_initialized")
        if self.launcher.is_windows:
            return self.tr("hotkey.registered") if getattr(hotkey_filter, "registered", False) else self.tr("hotkey.not_registered")
        return self.tr("hotkey.running") if getattr(hotkey_filter, "listener", None) is not None else self.tr("hotkey.not_running", error=getattr(hotkey_filter, "last_error", ""))

    def collect_diagnostics_report(self) -> str:
        env_values = self.read_env_values()
        lines = [
            f"{APP_NAME} {APP_VERSION}",
            self.tr("diagnostics.date", value=time.strftime("%Y-%m-%d %H:%M:%S")),
            "",
            f"[{self.tr('diagnostics.system')}]",
            self.tr("diagnostics.os", value=platform.platform()),
            self.tr("diagnostics.python", value=f"{sys.version.split()[0]} ({sys.executable})"),
            self.tr("diagnostics.qt", value=QApplication.instance().applicationName() or "PyQt5"),
            self.tr("diagnostics.frozen", value=self.tr("diagnostics.yes") if getattr(sys, "frozen", False) else self.tr("diagnostics.no")),
            self.tr("diagnostics.session", value=os.environ.get("XDG_SESSION_TYPE", "") or "n/a"),
            self.tr("diagnostics.desktop", value=os.environ.get("XDG_CURRENT_DESKTOP", "") or "n/a"),
            self.tr("diagnostics.tray", value=self.tr("diagnostics.yes") if self.launcher.tray_available else self.tr("diagnostics.no")),
            self.tr("diagnostics.startup", value=self.launcher.startup_display_mode),
            "",
            f"[{self.tr('diagnostics.hotkey_clipboard')}]",
            self.tr("diagnostics.hotkey", value=self.launcher.quick_download_hotkey),
            self.tr("diagnostics.hotkey_status", value=self.current_hotkey_status()),
            self.tr("diagnostics.clipboard_watch", value=self.tr("diagnostics.yes") if self.launcher.clipboard_watch_enabled else self.tr("diagnostics.no")),
            self.tr("diagnostics.wayland_paste", value=shutil.which("wl-paste") or self.tr("diagnostics.tool_missing", label="wl-paste")),
            "",
            f"[{self.tr('diagnostics.tools')}]",
            f"yt-dlp: {' '.join(self.launcher.yt_dlp_command())} | {self.command_version_line(self.launcher.yt_dlp_command() + ['--version'])}",
            self.tool_report_line("ffmpeg", "ffmpeg", ["-version"], self.launcher.ffmpeg_dir / ("ffmpeg.exe" if self.launcher.is_windows else "ffmpeg") if self.launcher.ffmpeg_dir else None),
            self.tool_report_line("ffprobe", "ffprobe", ["-version"], self.launcher.ffmpeg_dir / ("ffprobe.exe" if self.launcher.is_windows else "ffprobe") if self.launcher.ffmpeg_dir else None),
            self.tool_report_line("deno", "deno", ["--version"], self.launcher.deno_path),
            self.tool_report_line("curl", "curl", ["--version"]),
            self.tool_report_line("gsettings", "gsettings", ["--version"]),
            "",
            f"[{self.tr('diagnostics.paths')}]",
            self.path_report_line("App", self.launcher.app_dir),
            self.path_report_line("Data", self.launcher.data_dir),
            self.path_report_line("Config", self.launcher.config_dir),
            self.path_report_line("Cache", self.launcher.cache_dir),
            self.path_report_line(self.tr("disk.temp_folder"), self.launcher.temp_dir),
            self.path_report_line(self.tr("disk.download_folder"), self.launcher.final_dir),
            self.tr("diagnostics.cache_size", value=self.launcher.human_size(self.path_size(self.launcher.cache_dir))),
            self.tr("diagnostics.cache_cleanup", preview_days=CACHE_PREVIEW_MAX_AGE_DAYS, channel_days=CACHE_CHANNEL_MAX_AGE_DAYS),
            "",
            f"[{self.tr('diagnostics.data')}]",
            self.tr("diagnostics.channels", count=self.file_count(self.launcher.channels_file)),
            self.tr("diagnostics.queue", count=self.file_count(self.launcher.queue_file)),
            self.tr("diagnostics.archive_lines", count=self.file_count(self.launcher.archive_file)),
            self.tr("diagnostics.archive_details", count=self.file_count(self.launcher.archive_details_file)),
            "",
            f"[{self.tr('diagnostics.telegram')}]",
            self.tr("diagnostics.enabled", value=self.tr("diagnostics.yes") if self.launcher.telegram_enabled else self.tr("diagnostics.no")),
            f"BOT_TOKEN: {self.tr('diagnostics.configured') if env_values.get('BOT_TOKEN') else self.tr('diagnostics.not_configured')}",
            f"CHANNEL_ID: {self.tr('diagnostics.configured') if env_values.get('CHANNEL_ID') else self.tr('diagnostics.not_configured')}",
            f"PROXY_URL: {self.tr('diagnostics.configured') if env_values.get('PROXY_URL') else self.tr('diagnostics.not_configured')}",
        ]
        return "\n".join(lines)

    def choose_directory(self, field: QLineEdit):
        current = field.text().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, self.tr("settings.select_folder"), current)
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
        self.clipboard_watch_check.setChecked(self.launcher.clipboard_watch_enabled)
        if hasattr(self, "language_combo"):
            language_index = self.language_combo.findData(self.language)
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(language_index if language_index >= 0 else 0)
            self.language_combo.blockSignals(False)
        self.telegram_enabled_button.setChecked(self.launcher.telegram_enabled)
        self.update_telegram_enabled_button()
        self.update_quick_hotkey_button()
        self.autostart_check.setChecked(self.is_autostart_enabled())
        startup_index = self.startup_mode_combo.findData(self.launcher.startup_display_mode)
        self.startup_mode_combo.blockSignals(True)
        self.startup_mode_combo.setCurrentIndex(startup_index if startup_index >= 0 else 0)
        self.startup_mode_combo.blockSignals(False)

        resolution_index = self.resolution_combo.findData(self.launcher.max_resolution)
        self.resolution_combo.blockSignals(True)
        self.resolution_combo.setCurrentIndex(resolution_index if resolution_index >= 0 else 2)
        self.resolution_combo.blockSignals(False)

        self.bot_token_input.setText(env_values.get("BOT_TOKEN", ""))
        self.channel_id_input.setText(env_values.get("CHANNEL_ID", ""))
        self.proxy_url_input.setText(env_values.get("PROXY_URL", ""))

    def save_settings_from_ui(self, show_message: bool = True):
        self.language = normalize_language(self.language_combo.currentData()) if hasattr(self, "language_combo") else self.language
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
            "clipboard_watch_enabled": self.clipboard_watch_check.isChecked(),
            "language": self.language_combo.currentData() if hasattr(self, "language_combo") else self.language,
            "startup_display_mode": self.startup_mode_combo.currentData() or "tray",
            "telegram_enabled": self.telegram_enabled_button.isChecked(),
            "quick_download_hotkey": self.ui_settings.get("quick_download_hotkey") or self.launcher.quick_download_hotkey or DEFAULT_QUICK_DOWNLOAD_HOTKEY,
            "quick_download_telegram_notify": self.ui_settings.get("quick_download_telegram_notify", self.launcher.quick_download_telegram_notify),
            "quick_download_resolution": self.ui_settings.get("quick_download_resolution") or self.launcher.quick_download_resolution,
        })
        self.save_ui_settings()
        self.launcher.app_settings = dict(self.ui_settings)
        self.launcher.apply_runtime_settings(self.launcher.app_settings)
        self.launcher.refresh_global_hotkey()
        self.launcher.refresh_clipboard_watch_timer()
        self.launcher.refresh_window_taskbar_mode()
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
            QMessageBox.information(self, self.tr("tab.settings"), self.tr("settings.saved"))

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
                exec_command = f"{shlex.quote(exec_line)} {self.launcher.startup_mode_arg()}"
                path.write_text(
                    "[Desktop Entry]\n"
                    "Type=Application\n"
                    f"Name={APP_NAME}\n"
                    f"Exec={exec_command}\n"
                    "Icon=yt-harvester\n"
                    "Terminal=false\n"
                    "X-GNOME-Autostart-enabled=true\n",
                    encoding="utf-8",
                )
            elif path.exists():
                path.unlink()
        except Exception as e:
            QMessageBox.warning(self, self.tr("settings.autostart"), str(e))

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
        command.append(self.launcher.startup_mode_arg())
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
                with contextlib.suppress(FileNotFoundError):
                    winreg.DeleteValue(key, self.windows_autostart_value_name())

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
            QMessageBox.warning(self, self.tr("tab.settings"), str(e))

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
            mode = self.tr("settings.theme_dark_mode") if effective_theme == "dark" else self.tr("settings.theme_light_mode")
            self.theme_button.setToolTip(self.tr("settings.theme_system", mode=mode))
        elif self.theme == "dark":
            self.theme_button.setText("☀")
            self.theme_button.setToolTip(self.tr("settings.theme_to_light"))
        else:
            self.theme_button.setText("☾")
            self.theme_button.setToolTip(self.tr("settings.theme_to_system"))

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
                QCheckBox {
                    spacing: 8px;
                }
                QCheckBox#quickTelegramCheck {
                    spacing: 8px;
                    font-size: 15px;
                    font-weight: bold;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    border: 1px solid #7f93a8;
                    border-radius: 3px;
                    background: #f7fafc;
                }
                QCheckBox::indicator:checked {
                    background: #2d3540;
                    border: 1px solid #7f93a8;
                    border-radius: 8px;
                }
                QCheckBox::indicator:unchecked:hover {
                    background: #edf3f8;
                    border: 1px solid #6fb8ef;
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
                QWidget#toolPanel QCheckBox {
                    spacing: 8px;
                }
                QWidget#toolPanel QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    border: 1px solid #7f93a8;
                    border-radius: 3px;
                    background: #f7fafc;
                }
                QWidget#toolPanel QCheckBox::indicator:checked {
                    background: #2d3540;
                    border: 1px solid #7f93a8;
                    border-radius: 8px;
                }
                QWidget#toolPanel QCheckBox::indicator:unchecked:hover {
                    background: #edf3f8;
                    border: 1px solid #6fb8ef;
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
                QPushButton#checkChannelsButton {
                    font-family: "Noto Sans", "DejaVu Sans", "Segoe UI Emoji", "Noto Color Emoji", sans-serif;
                    font-size: 15px;
                    font-weight: bold;
                    padding: 0 12px;
                    text-align: center;
                }
                QPushButton#overviewToolbarButton {
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 12px;
                    font-weight: bold;
                    padding: 0 7px;
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
                QPushButton#quickRunButton {
                    background: transparent;
                    border: none;
                    border-radius: 23px;
                    min-width: 46px;
                    max-width: 46px;
                    min-height: 46px;
                    max-height: 46px;
                    padding: 0;
                    margin: 0;
                }
                QPushButton#quickRunButton:hover {
                    background: rgba(50, 190, 108, 58);
                    border-radius: 23px;
                }
                QPushButton#quickRunButton:pressed {
                    background: rgba(50, 190, 108, 92);
                    border-radius: 23px;
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
                QCheckBox {
                    spacing: 8px;
                }
                QCheckBox#quickTelegramCheck {
                    spacing: 8px;
                    font-size: 15px;
                    font-weight: bold;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    border: 1px solid #7f93a8;
                    border-radius: 3px;
                    background: #0f151d;
                }
                QCheckBox::indicator:checked {
                    background: #f4f6f8;
                    border: 1px solid #ffffff;
                    border-radius: 8px;
                }
                QCheckBox::indicator:unchecked:hover {
                    background: #172232;
                    border: 1px solid #9ed4ff;
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
                QWidget#toolPanel QCheckBox {
                    spacing: 8px;
                }
                QWidget#toolPanel QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    border: 1px solid #7f93a8;
                    border-radius: 3px;
                    background: #0f151d;
                }
                QWidget#toolPanel QCheckBox::indicator:checked {
                    background: #f4f6f8;
                    border: 1px solid #ffffff;
                    border-radius: 8px;
                }
                QWidget#toolPanel QCheckBox::indicator:unchecked:hover {
                    background: #172232;
                    border: 1px solid #9ed4ff;
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
                QPushButton#checkChannelsButton {
                    font-family: "Noto Sans", "DejaVu Sans", "Segoe UI Emoji", "Noto Color Emoji", sans-serif;
                    font-size: 15px;
                    font-weight: bold;
                    padding: 0 12px;
                    text-align: center;
                }
                QPushButton#overviewToolbarButton {
                    font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                    font-size: 12px;
                    font-weight: bold;
                    padding: 0 7px;
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
                QPushButton#quickRunButton {
                    background: transparent;
                    border: none;
                    border-radius: 23px;
                    min-width: 46px;
                    max-width: 46px;
                    min-height: 46px;
                    max-height: 46px;
                    padding: 0;
                    margin: 0;
                }
                QPushButton#quickRunButton:hover {
                    background: rgba(54, 210, 122, 58);
                    border-radius: 23px;
                }
                QPushButton#quickRunButton:pressed {
                    background: rgba(54, 210, 122, 98);
                    border-radius: 23px;
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
                check=False,
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
        self.archive_window.apply_language()
        self.archive_window.refresh()
        self.launcher.apply_taskbar_mode_to_window(self.archive_window)
        self.archive_window.show()
        self.archive_window.raise_()
        self.archive_window.activateWindow()

    def open_quick_download_window(self, initial_url: str = ""):
        if self.quick_download_dialog is None:
            self.quick_download_dialog = QuickDownloadDialog(self)
            self.quick_download_dialog.setStyleSheet(self.styleSheet())
        self.quick_download_dialog.apply_language()
        self.launcher.apply_taskbar_mode_to_window(self.quick_download_dialog)
        self.quick_download_dialog.open_from_clipboard(initial_url)

    def quick_download_now(self):
        if self.launcher.is_running:
            QMessageBox.information(self, self.tr("quick.title"), self.tr("quick.already_running"))
            return False
        widgets = self._preview_widgets("quick")
        preview = self.current_previews.get("quick", {})
        url = (preview.get("url") or widgets["input"].text()).strip()
        if not self._looks_like_youtube_url(url):
            QMessageBox.warning(self, self.tr("quick.title"), self.tr("preview.need_youtube"))
            return False
        video_id = (preview.get("video_id") or self.youtube_video_id_from_url(url)).strip()
        telegram_notify = False
        resolution = self.launcher.quick_download_resolution
        audio_tracks = []
        subtitle_selections = []
        if self.quick_download_dialog is not None:
            telegram_notify = self.quick_download_dialog.telegram_check.isChecked()
            resolution = self.quick_download_dialog.selected_resolution()
            audio_tracks = [
                resolve_audio_track_option(track, resolution)
                for track in self.quick_download_dialog.selected_audio_tracks()
            ]
            audio_tracks = [track for track in audio_tracks if track.get("format_id")]
            subtitle_selections = self.quick_download_dialog.selected_subtitles()
        if sum(track.get("format_kind") == "combined" for track in audio_tracks) > 1:
            message = self.tr("quick.combined_audio_limit")
            QMessageBox.warning(self, self.tr("quick.title"), message)
            widgets["status"].setText(message)
            return False
        if video_id and self.archive_contains_variant(
            video_id,
            resolution=resolution,
            audio_tracks=audio_tracks,
            subtitle_selections=subtitle_selections,
        ):
            QMessageBox.information(self, self.tr("quick.title"), self.tr("preview.variant_in_archive"))
            widgets["status"].setText(self.tr("preview.variant_in_archive"))
            return False
        self.launcher.run_script(
            telegram_override=telegram_notify,
            single_queue_url=url,
            max_resolution_override=resolution,
            audio_track_overrides=audio_tracks,
            subtitle_overrides=subtitle_selections,
        )
        self.refresh_overview()
        return True

    def download_overview_video_now(self):
        widgets = self._preview_widgets("overview")
        preview = self.current_previews.get("overview", {})
        url = (preview.get("url") or widgets["input"].text()).strip()
        if not self._looks_like_youtube_url(url):
            QMessageBox.warning(self, self.tr("button.download"), self.tr("preview.need_youtube"))
            return False

        if self.launcher.is_running:
            return self.add_video_to_queue("overview", front=True)

        video_id = (preview.get("video_id") or self.youtube_video_id_from_url(url)).strip()
        if video_id and self.archive_contains_variant(video_id, resolution=self.launcher.max_resolution):
            QMessageBox.information(self, self.tr("button.download"), self.tr("preview.variant_in_archive"))
            widgets["status"].setText(self.tr("preview.variant_in_archive"))
            return False

        widgets["input"].clear()
        self._clear_video_preview("overview")
        self.launcher.run_script(
            single_queue_url=url,
            max_resolution_override=self.launcher.max_resolution,
        )
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

    def on_overview_logo_clicked(self):
        if self.overview_easter_game is not None:
            return
        self.overview_logo_clicks += 1
        if self.overview_logo_clicks >= 10:
            self.start_overview_easter_game()

    def start_overview_easter_game(self):
        if self.overview_easter_game is not None:
            return
        self.overview_logo_clicks = 0
        game = HarvesterEasterEggGame(
            self.overview_logo_stack,
            map_path=self.launcher.easter_map_path,
            harvester_path=self.launcher.easter_harvester_path,
            crystal_path=self.launcher.easter_crystal_path,
            tree_overlay_path=self.launcher.easter_tree_overlay_path,
            reporting_sound_paths=self.launcher.easter_reporting_sound_paths,
            acknowledge_sound_paths=self.launcher.easter_acknowledge_sound_paths,
            victory_sound_paths=self.launcher.easter_victory_sound_paths,
            language=self.language,
        )
        game.finished.connect(self.finish_overview_easter_game)
        self.overview_easter_game = game
        self.overview_logo_stack.addWidget(game)
        self.overview_logo_stack.setCurrentWidget(game)
        game.setFocus()

    def finish_overview_easter_game(self, won: bool):
        game = self.overview_easter_game
        self.overview_easter_game = None
        self.overview_logo_stack.setCurrentWidget(self.overview_main_image)
        if game is not None:
            self.overview_logo_stack.removeWidget(game)
            game.deleteLater()
        if won:
            self.overview_easter_unlocked = True
            self.set_overview_easter_logo()
            self.overview_idle_status_label.setText(self.tr("easter.victory_ready"))
        else:
            self.overview_easter_unlocked = False
            self.overview_logo_clicks = 0
            self.refresh_overview()

    def set_overview_easter_logo(self):
        if self.overview_easter_victory_pixmap.isNull():
            self.overview_easter_victory_pixmap = self.make_overview_easter_logo()
        self.overview_main_image.setText("")
        self.overview_main_image.setPixmap(
            self.overview_easter_victory_pixmap.scaled(
                self.overview_main_image.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def make_overview_easter_logo(self):
        if self.launcher.easter_victory_logo_path.is_file():
            pixmap = QPixmap(str(self.launcher.easter_victory_logo_path))
            if not pixmap.isNull():
                return pixmap

        pixmap = QPixmap(232, 232)
        pixmap.fill(QColor("#12171b"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)

        painter.fillRect(0, 0, 232, 232, QColor("#1a2229"))
        painter.setPen(QPen(QColor("#303c47"), 1))
        for y in range(18, 232, 24):
            painter.drawLine(0, y, 232, y - 42)
            painter.drawLine(0, y + 8, 232, y - 34)
        for x in range(0, 232, 18):
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#7d1f24") if (x // 18) % 2 == 0 else QColor("#c8a13a"))
            painter.drawPolygon(QPoint(x, 0), QPoint(min(232, x + 12), 0), QPoint(min(232, x + 4), 24), QPoint(max(0, x - 8), 24))
            painter.drawPolygon(QPoint(x, 208), QPoint(min(232, x + 12), 208), QPoint(min(232, x + 4), 232), QPoint(max(0, x - 8), 232))

        painter.setPen(QPen(QColor("#b24b4b"), 2))
        painter.setBrush(QColor("#202a31"))
        painter.drawRoundedRect(10, 28, 212, 174, 7, 7)

        painter.setPen(QPen(QColor("#eac85b"), 2))
        painter.setBrush(QColor("#5b2025"))
        painter.drawEllipse(49, 54, 134, 134)
        painter.setBrush(QColor("#2d3430"))
        painter.drawEllipse(61, 66, 110, 110)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1b1b1b"))
        painter.drawRoundedRect(65, 140, 102, 24, 8, 8)
        painter.setBrush(QColor("#807039"))
        painter.drawRoundedRect(72, 113, 88, 38, 7, 7)
        painter.setBrush(QColor("#cda047"))
        painter.drawRoundedRect(86, 96, 60, 30, 8, 8)
        painter.setBrush(QColor("#f47b35"))
        painter.drawEllipse(91, 66, 50, 50)
        painter.setBrush(QColor("#ffd2aa"))
        painter.drawEllipse(98, 78, 36, 34)
        painter.setPen(QPen(QColor("#301d18"), 2))
        painter.drawArc(103, 90, 24, 16, 205 * 16, 130 * 16)

        painter.setBrush(QColor("#ef3f32"))
        painter.setPen(QPen(QColor("#131820"), 3))
        painter.drawRoundedRect(31, 100, 58, 43, 10, 10)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawPolygon(QPoint(53, 110), QPoint(53, 134), QPoint(74, 122))

        painter.setPen(QPen(QColor("#e6d56d"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(43, 157, 72, 146)
        painter.drawLine(189, 157, 160, 146)
        painter.drawLine(70, 154, 90, 164)
        painter.drawLine(162, 154, 142, 164)

        title_font = QFont("Arial")
        title_font.setBold(True)
        title_font.setPixelSize(24)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor("#0a0d10"), 3))
        painter.drawText(13, 31, 206, 32, Qt.AlignCenter, "ЮТУХА")
        painter.setPen(QColor("#f3e8b0"))
        painter.drawText(13, 31, 206, 32, Qt.AlignCenter, "ЮТУХА")

        small_font = QFont("Arial")
        small_font.setBold(True)
        small_font.setPixelSize(11)
        painter.setFont(small_font)
        painter.setPen(QColor("#d7e0c7"))
        painter.drawText(12, 197, 208, 24, Qt.AlignCenter, "HARVESTER ONLINE")
        painter.end()
        return pixmap

    def refresh_overview(self):
        self.sync_channel_paid_content_from_disk()
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

        self.overview_channels_label.setText(f"{self._emoji_html('📺')} {self.tr('status.channels')}: {channels_count}")
        self.overview_queue_label.setText(f"{self._emoji_html('📥')} {self.tr('status.queue')}: {queue_count}")
        self.overview_archive_label.setText(f"{self._emoji_html('🗃')} {self.tr('status.archive')}: {archive_count}")
        last_download_text = self._last_download_text(status_info)
        self.overview_last_download_label.setText(
            f"{self._emoji_html('⏱️')}: {self._html_text(last_download_text)}"
        )
        self.overview_last_download_label.setToolTip(
            self.tr("status.last_download", value=last_download_text)
        )
        self.overview_temp_label.setText(
            f"{self.tr('status.files')}{self._emoji_html('⌛')}:{temp_count}  {self._emoji_html('⚠')}:{part_count}"
        )
        self.overview_temp_label.setToolTip(
            self.tr("status.temp_files", temp=temp_count, part=part_count)
        )

        if self.launcher.is_running and stop_requested:
            self._set_run_button_state(
                True,
                False,
                self.tr("overview.stop_requested"),
            )
        elif self.launcher.is_running:
            self._set_run_button_state(
                True,
                True,
                self.tr("overview.stop_soft"),
            )
        else:
            self._set_run_button_state(False, True, self.tr("overview.run"))

        channel_url = status_info.get("channel_url") or ""
        channel_name = self._channel_display_name(channel_url, status_info.get("channel_name") or "")
        if self.launcher.is_running and channel_url:
            channel_image = self.channel_cache_path(channel_url).with_suffix(".jpg")
            main_image = channel_image if channel_image.exists() else self.launcher.overview_logo_path
            self._set_label_image(self.overview_main_image, main_image, channel_name or "YT")
        elif self.overview_easter_unlocked:
            self.set_overview_easter_logo()
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
            self.overview_download_title_label.setText(self.tr("download.current", title=self._html_text(title)))
            self.overview_download_title_label.setToolTip(title)
            self.overview_idle_uploader_label.clear()
            self.overview_idle_status_label.clear()
        elif overview_url or overview_preview:
            preview_title = overview_preview.get("title") or self.overview_download_title_label.text() or self.tr("preview.loading")
            self.overview_download_title_label.show()
            self.overview_download_title_label.setText(self._html_text(preview_title))
            self.overview_download_title_label.setToolTip(preview_title)
            uploader = overview_preview.get("uploader") or ""
            self.overview_idle_uploader_label.setText(self.tr("preview.channel", uploader=self._html_text(uploader)) if uploader else "")
            if not self.overview_idle_status_label.text():
                self.overview_idle_status_label.setText(self.tr("preview.ready_queue") if overview_preview else self.tr("preview.reading"))
        else:
            self.overview_download_title_label.show()
            self.overview_download_title_label.setText(self.tr("download.waiting"))
            self.overview_download_title_label.setToolTip("")
            self.overview_idle_uploader_label.clear()
            if self.overview_idle_status_label.text() != self.tr("preview.added"):
                self.overview_idle_status_label.clear()

        self._refresh_overview_progress(status_info, state)
        self.overview_events_label.setText(self._recent_events_html(status_info, state))

    def _overview_state_text(self, state: str):
        return {
            "sleep": f"{self._emoji_html('😴')} {self.tr('state.sleep')}",
            "searching": f"{self._emoji_html('🔎')} {self.tr('state.searching')}",
            "downloading": f"{self._emoji_html('⬇️')} {self.tr('state.downloading')}",
            "stopping": f"{self._emoji_html('⏹')} {self.tr('state.stopping')}",
            "stopped": f"{self._emoji_html('⏹')} {self.tr('state.stopped')}",
        }.get(state, f"{self._emoji_html('😴')} {self.tr('state.sleep')}")

    def _refresh_overview_activity(self, status_info: dict, state: str, channels_count: int):
        if state in {"searching", "downloading"}:
            try:
                total = max(0, int(status_info.get("channels_total") or channels_count))
                checked = max(0, min(total, int(status_info.get("channels_checked") or 0)))
            except (TypeError, ValueError):
                total, checked = channels_count, 0
            self.overview_activity_bar.setRange(0, max(1, total))
            self.overview_activity_bar.setValue(checked)
            self.overview_activity_bar.setFormat(self.tr("progress.checked_channels", checked=checked, total=total))
            return

        self.overview_activity_bar.setRange(0, 100)
        if state == "stopping":
            self.overview_activity_bar.setValue(100)
            self.overview_activity_bar.setFormat(self.tr("state.stopping"))
        elif state == "stopped":
            self.overview_activity_bar.setValue(0)
            self.overview_activity_bar.setFormat(self.tr("state.stopped"))
        else:
            self.overview_activity_bar.setValue(0)
            self.overview_activity_bar.setFormat(self.tr("state.sleep"))

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
            "searching": ("🔎", self.tr("type.searching")),
            "done": ("✅", self.tr("type.done")),
            "missing": ("❌", self.tr("type.missing")),
            "downloading": ("⬇️", self.tr("type.downloading")),
            "disabled": ("🚫", self.tr("type.disabled")),
            "idle": ("😴", self.tr("type.idle")),
        }.get(status or "idle", ("😴", self.tr("type.idle")))
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
            "video": self.tr("stage.video"),
            "audio": self.tr("stage.audio"),
            "merge": self.tr("stage.merge"),
            "postprocess": self.tr("stage.postprocess"),
            "download": self.tr("stage.download"),
        }.get(stage, self.tr("stage.download"))
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
            self.overview_progress_detail_label.setText(self.tr("progress.waiting_data"))

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
            return self._html_text(self.tr("events.empty"))
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
        title = self.tr("report.stopped") if stopped else self.tr("report.finished")
        finished = time.strftime("%Y-%m-%d %H:%M", time.localtime(completed_at))
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
            lines.append(f"{self._emoji_html('📦')} {self.tr('report.downloaded')}: <b>{total}</b> &nbsp; {media_counts}")
        else:
            lines.append(f"{self._emoji_html('📭')} {self.tr('report.no_new')}")

        today = self._today_download_summary()
        today_counts = (
            f"{self._emoji_html('🎬')} {today['videos']}"
            f" &nbsp; {self._emoji_html('⚡')} {today['shorts']}"
            f" &nbsp; {self._emoji_html('🔴')} {today['streams']}"
        )
        if today["queue"]:
            today_counts += f" &nbsp; {self._emoji_html('📥')} {today['queue']}"
        lines.append(f"{self._emoji_html('📅')} {self.tr('report.today')}: <b>{today['total']}</b> &nbsp; {today_counts}")

        checked = count("last_run_channels_checked")
        channels_total = count("last_run_channels_total")
        failed = count("last_run_failed_count")
        lines.append(
            f"{self._emoji_html('📺')} {self.tr('report.checked')}: {checked} / {channels_total}"
            f" &nbsp; {self._emoji_html('⚠️' if failed else '✨')} "
            f"{self._html_text(self.tr('report.errors', count=failed) if failed else self.tr('report.no_errors'))}"
        )
        return "<br>".join(lines)

    def _today_download_summary(self) -> dict[str, int]:
        today = time.strftime("%Y-%m-%d", time.localtime())
        seen: set[str] = set()
        counts = {"total": 0, "videos": 0, "shorts": 0, "streams": 0, "queue": 0}
        try:
            lines = read_text_for_display(self.launcher.archive_details_file).splitlines()
        except Exception:
            return counts
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            downloaded_at = str(entry.get("downloaded_at") or "").strip()
            timestamp = self._valid_timestamp(entry.get("downloaded_at_ts"))
            if timestamp:
                entry_day = time.strftime("%Y-%m-%d", time.localtime(timestamp))
            else:
                entry_day = downloaded_at[:10]
            if entry_day != today:
                continue
            video_id = str(entry.get("video_id") or "").strip()
            unique_key = video_id or str(entry.get("file_path") or entry.get("youtube_url") or line)
            if unique_key in seen:
                continue
            seen.add(unique_key)
            counts["total"] += 1
            type_name = str(entry.get("type") or "").strip().lower()
            if type_name in {"videos", "shorts", "streams", "queue"}:
                counts[type_name] += 1
        return counts

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
            return self.tr("time.none")
        timestamp = max(timestamps)
        elapsed = max(0, int(time.time() - timestamp))
        if elapsed < 60:
            return self.tr("time.just_now")
        days, rem = divmod(elapsed, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        parts = []
        if days:
            parts.append(f"{days}{self.tr('time.day')}")
        if hours or days:
            parts.append(f"{hours}{self.tr('time.hour')}")
        parts.append(f"{minutes}{self.tr('time.minute')}")
        return self.tr("time.ago", value=" ".join(parts[:3]))

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
            return sum(
                1
                for item in path.rglob(pattern)
                if item.is_file() and not (path == self.launcher.temp_dir and item == self.launcher.temp_marker_file)
            )
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
        text, ok = QInputDialog.getText(self, self.tr("channels.add_title"), self.tr("channels.add_prompt"))
        if not ok:
            return
        text = text.strip()
        if not text:
            return
        if not self._looks_like_youtube_channel_url(text):
            QMessageBox.warning(self, self.tr("tab.channels"), self.tr("channels.need_link"))
            return
        text = text.rstrip("/")
        existing = self._read_channels()
        if text in existing:
            QMessageBox.information(self, self.tr("tab.channels"), self.tr("channels.exists"))
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
        self.channel_section_checks_pending.pop(key, None)
        self.channel_paid_content_checks_running.discard(key)
        self.refresh_channel_check_animation()
        self.refresh_channels()
        self.refresh_overview()

    def save_channel_urls(self, channels):
        channels = [c.strip().rstrip("/") for c in channels if c.strip()]
        try:
            self.launcher.channels_file.write_text("\n".join(channels) + "\n", encoding="utf-8-sig")
        except Exception as e:
            QMessageBox.warning(self, self.tr("tab.channels"), str(e))

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
                    value = values.get(type_name, default)
                    if bool(value) != default:
                        channel_rules[type_name] = bool(value)
                paid_status = str(values.get(PAID_CONTENT_STATUS_KEY) or PAID_CONTENT_UNKNOWN).strip()
                if paid_status in PAID_CONTENT_STATUSES and paid_status != PAID_CONTENT_UNKNOWN:
                    channel_rules[PAID_CONTENT_STATUS_KEY] = paid_status
                if channel_rules:
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
            QMessageBox.warning(self, self.tr("tab.channels"), str(e))

    def sync_channel_paid_content_from_disk(self):
        if not self.channel_cards:
            return
        latest_rules = self.load_channel_rules()
        changed_channels = []
        for channel in self.channel_cards:
            key = self.normalize_channel_key(channel)
            current_status = str(
                (self.channel_rules.get(key) or {}).get(PAID_CONTENT_STATUS_KEY) or PAID_CONTENT_UNKNOWN
            ).strip()
            latest_status = str(
                (latest_rules.get(key) or {}).get(PAID_CONTENT_STATUS_KEY) or PAID_CONTENT_UNKNOWN
            ).strip()
            if current_status not in PAID_CONTENT_STATUSES:
                current_status = PAID_CONTENT_UNKNOWN
            if latest_status not in PAID_CONTENT_STATUSES:
                latest_status = PAID_CONTENT_UNKNOWN
            if current_status != latest_status:
                changed_channels.append(channel)
        if not changed_channels:
            return
        self.channel_rules = latest_rules
        for channel in changed_channels:
            if self.normalize_channel_key(channel) in self.channel_section_checks_running:
                continue
            self.apply_channel_paid_content_status(channel, self.channel_cards.get(channel))

    def channel_rule(self, channel: str):
        key = self.normalize_channel_key(channel)
        rules = dict(CHANNEL_TYPE_DEFAULTS)
        rules[PAID_CONTENT_STATUS_KEY] = PAID_CONTENT_UNKNOWN
        rules.update(self.channel_rules.get(key, {}))
        return rules

    def compact_channel_rules(self, rules: dict) -> dict:
        compact = {}
        for type_name, default in CHANNEL_TYPE_DEFAULTS.items():
            if bool(rules.get(type_name, default)) != default:
                compact[type_name] = bool(rules.get(type_name))
        paid_status = str(rules.get(PAID_CONTENT_STATUS_KEY) or PAID_CONTENT_UNKNOWN).strip()
        if paid_status in PAID_CONTENT_STATUSES and paid_status != PAID_CONTENT_UNKNOWN:
            compact[PAID_CONTENT_STATUS_KEY] = paid_status
        return compact

    def set_channel_type_enabled(self, channel: str, type_name: str, enabled: bool):
        if type_name not in CHANNEL_TYPE_DEFAULTS:
            return
        key = self.normalize_channel_key(channel)
        rules = self.channel_rule(channel)
        rules[type_name] = bool(enabled)
        compact = self.compact_channel_rules(rules)
        if compact:
            self.channel_rules[key] = compact
        else:
            self.channel_rules.pop(key, None)
        self.save_channel_rules()

    def channel_paid_content_status(self, channel: str) -> str:
        status = str(self.channel_rule(channel).get(PAID_CONTENT_STATUS_KEY) or PAID_CONTENT_UNKNOWN).strip()
        return status if status in PAID_CONTENT_STATUSES else PAID_CONTENT_UNKNOWN

    def set_channel_paid_content_status(self, channel: str, status: str):
        if status not in PAID_CONTENT_STATUSES:
            return
        key = self.normalize_channel_key(channel)
        rules = self.channel_rule(channel)
        rules[PAID_CONTENT_STATUS_KEY] = status
        compact = self.compact_channel_rules(rules)
        if compact:
            self.channel_rules[key] = compact
        else:
            self.channel_rules.pop(key, None)
        self.save_channel_rules()
        card = self.channel_cards.get(channel)
        if card:
            self.apply_channel_paid_content_status(channel, card)

    def check_paid_content_enabled(self) -> bool:
        return bool(self.ui_settings.get("check_paid_content_enabled", True))

    def set_check_paid_content_enabled(self, enabled: bool):
        self.ui_settings["check_paid_content_enabled"] = bool(enabled)
        self.save_ui_settings()
        self.launcher.app_settings = dict(self.ui_settings)
        self.update_check_channel_sections_tooltip()

    def update_check_channel_sections_tooltip(self):
        if not hasattr(self, "check_channel_sections_button"):
            return
        if getattr(self, "channel_section_checks_active", False):
            self.check_channel_sections_button.setToolTip(self.tr("channels.check_stop_tip"))
            return
        if self.check_paid_content_enabled():
            tooltip = self.tr("channels.check_with_paid_tip")
        else:
            tooltip = self.tr("channels.check_without_paid_tip")
        self.check_channel_sections_button.setToolTip(tooltip)

    def set_channel_section_check_button_running(self, running: bool):
        if not hasattr(self, "check_channel_sections_button"):
            return
        self.channel_section_checks_active = bool(running)
        if running:
            self.check_channel_sections_button.setEnabled(True)
            self.check_channel_sections_button.setText(self.tr("channels.stop_check"))
        else:
            self.check_channel_sections_button.setEnabled(True)
            self.check_channel_sections_button.setText(self.tr("channels.check"))
        self.update_check_channel_sections_tooltip()

    def toggle_channel_section_checks(self):
        if getattr(self, "channel_section_checks_active", False):
            self.stop_channel_section_checks()
            return
        self.check_all_channel_sections()

    def stop_channel_section_checks(self):
        self.channel_section_stop_event.set()
        if hasattr(self, "check_channel_sections_button"):
            self.check_channel_sections_button.setEnabled(False)
            self.check_channel_sections_button.setText(self.tr("channels.stopping"))
        self.channel_sections_status_label.setText(self.tr("channels.stop_status"))

    def channel_check_animation_text(self) -> str:
        return "." * ((self.channel_check_animation_step % 3) + 1)

    def channel_check_waiting_text(self) -> str:
        return "..."

    def refresh_channel_check_animation(self):
        has_active_checks = bool(self.channel_section_checks_running or self.channel_paid_content_checks_running)
        if has_active_checks:
            if not self.channel_check_animation_timer.isActive():
                self.channel_check_animation_timer.start()
            self.animate_channel_checks(advance=False)
            return
        if self.channel_check_animation_timer.isActive():
            self.channel_check_animation_timer.stop()
        self.channel_check_animation_step = 0
        self.active_channel_section_check = None

    def animate_channel_checks(self, advance: bool = True):
        if advance:
            self.channel_check_animation_step = (self.channel_check_animation_step + 1) % 3
        dots = self.channel_check_animation_text()
        waiting = self.channel_check_waiting_text()
        active_key = active_type = None
        if self.active_channel_section_check:
            active_key, active_type = self.active_channel_section_check
        for channel, card in self.channel_cards.items():
            key = self.normalize_channel_key(channel)
            if key not in self.channel_section_checks_running:
                continue
            pending_sections = self.channel_section_checks_pending.get(key) or set()
            for type_name, button in getattr(card, "type_buttons", {}).items():
                if type_name not in pending_sections:
                    continue
                is_active = key == active_key and type_name == active_type
                button.setText(dots if is_active else waiting)
                label = self.channel_type_label(type_name)
                if is_active:
                    button.setToolTip(self.tr("channels.active", label=label))
                else:
                    button.setToolTip(self.tr("channels.waiting", label=label))
            paid_button = getattr(card, "paid_content_button", None)
            if paid_button is not None and key in self.channel_paid_content_checks_running:
                is_active = key == active_key and active_type == PAID_CONTENT_STATUS_KEY
                paid_button.setText(dots if is_active else waiting)
                if is_active:
                    paid_button.setToolTip(self.tr("channels.active", label=self.tr("channels.paid_unknown").split(":", 1)[0]))
                else:
                    paid_button.setToolTip(self.tr("channels.waiting", label=self.tr("channels.paid_unknown").split(":", 1)[0]))

    def check_all_channel_sections(self):
        channels = self._read_channels()
        if not channels:
            self.channel_sections_status_label.setText(self.tr("channels.none"))
            return
        if not self.launcher.check_sections_script_path.exists():
            QMessageBox.warning(self, self.tr("tab.channels"), self.tr("generic.script_not_found", path=self.launcher.check_sections_script_path))
            return

        check_paid_content = self.check_paid_content_enabled()
        self.channel_section_stop_event.clear()
        self.set_channel_section_check_button_running(True)
        self.channel_sections_status_label.setText(self.tr("channels.checking", done=0, total=len(channels)))
        for channel in channels:
            self.mark_channel_section_checking(channel, check_paid_content)
        thread = threading.Thread(
            target=self._check_channel_sections_many_worker,
            args=(channels, check_paid_content),
            daemon=True,
        )
        thread.start()

    def check_channel_sections(self, channel: str):
        if not self.launcher.check_sections_script_path.exists():
            return
        check_paid_content = self.check_paid_content_enabled()
        self.channel_section_stop_event.clear()
        self.set_channel_section_check_button_running(True)
        self.channel_sections_status_label.setText(self.tr("channels.checking", done=0, total=1))
        self.mark_channel_section_checking(channel, check_paid_content)
        thread = threading.Thread(
            target=self._check_channel_sections_worker,
            args=(channel, False, check_paid_content),
            daemon=True,
        )
        thread.start()

    def mark_channel_section_checking(self, channel: str, check_paid_content: bool = True):
        key = self.normalize_channel_key(channel)
        self.channel_section_checks_running.add(key)
        self.channel_section_checks_pending[key] = {type_name for type_name, _emoji, _label in CHANNEL_TYPE_BUTTONS}
        if check_paid_content:
            self.channel_paid_content_checks_running.add(key)
        else:
            self.channel_paid_content_checks_running.discard(key)
        card = self.channel_cards.get(channel)
        if not card:
            self.refresh_channel_check_animation()
            return
        waiting = self.channel_check_waiting_text()
        for type_name, button in getattr(card, "type_buttons", {}).items():
            button.setText(waiting)
            button.setToolTip(self.tr("channels.waiting", label=self.channel_type_label(type_name)))
        paid_button = getattr(card, "paid_content_button", None)
        if paid_button is not None and check_paid_content:
            paid_button.setText(waiting)
            paid_button.setToolTip(self.tr("channels.waiting", label=self.tr("channels.paid_unknown").split(":", 1)[0]))
        self.refresh_channel_check_animation()

    def _check_channel_sections_many_worker(self, channels: list, check_paid_content: bool = True):
        total = len(channels)
        done = 0
        stopped = False
        for channel in channels:
            if self.channel_section_stop_event.is_set():
                stopped = True
                break
            completed = self._check_channel_sections_worker(channel, True, check_paid_content)
            if completed:
                done += 1
            self.channel_sections_checked.emit({"progress_done": done, "progress_total": total})
            if self.channel_section_stop_event.is_set():
                stopped = True
                break
        self.channel_sections_checked.emit({
            "batch_finished": True,
            "progress_done": done,
            "progress_total": total,
            "stopped": stopped,
        })

    def _check_channel_sections_worker(self, channel: str, called_from_batch: bool, check_paid_content: bool = True):
        payload = {"channel": channel, "sections": {}, "error": "", "paid_content_checked": check_paid_content}
        completed = True
        for type_name, _emoji, _label in CHANNEL_TYPE_BUTTONS:
            if self.channel_section_stop_event.is_set():
                completed = False
                payload["cancelled"] = True
                break
            self.channel_sections_checked.emit({
                "active_check": True,
                "channel": channel,
                "active_type": type_name,
                "called_from_batch": called_from_batch,
            })
            section_info, error = self._run_channel_section_check(channel, type_name)
            payload["sections"][type_name] = section_info
            if error and not payload["error"]:
                payload["error"] = error
            self.channel_sections_checked.emit({
                "partial_result": True,
                "channel": channel,
                "sections": {type_name: section_info},
                "called_from_batch": called_from_batch,
            })

        if completed and check_paid_content and not self.channel_section_stop_event.is_set():
            self.channel_sections_checked.emit({
                "active_check": True,
                "channel": channel,
                "active_type": PAID_CONTENT_STATUS_KEY,
                "called_from_batch": called_from_batch,
            })
            paid_status, error = self._run_channel_paid_content_check(channel, payload["sections"])
            payload[PAID_CONTENT_STATUS_KEY] = paid_status
            if error and not payload["error"]:
                payload["error"] = error
            self.channel_sections_checked.emit({
                "partial_result": True,
                "channel": channel,
                PAID_CONTENT_STATUS_KEY: paid_status,
                "called_from_batch": called_from_batch,
            })

        payload["called_from_batch"] = called_from_batch
        self.channel_sections_checked.emit(payload)
        return completed

    def _run_channel_section_check(self, channel: str, type_name: str):
        args = [
            "--channel",
            channel,
            "--section",
            type_name,
            "--skip-paid-content",
        ]
        try:
            result = self.launcher.run_python_script_capture(self.launcher.check_sections_script_path, args, timeout=75)
            if result.returncode != 0:
                error = (result.stderr or result.stdout or self.tr("channels.check_failed")).strip()
                return {"status": "error", "url": f"{channel.rstrip('/')}/{type_name}", "error": error}, error
            payload = json.loads(result.stdout.strip() or "{}")
            sections = payload.get("sections") or {}
            section_info = sections.get(type_name) or {}
            if not isinstance(section_info, dict):
                section_info = {"status": "error", "url": f"{channel.rstrip('/')}/{type_name}", "error": self.tr("channels.check_failed")}
            return section_info, ""
        except Exception as e:
            error = str(e)
            return {"status": "error", "url": f"{channel.rstrip('/')}/{type_name}", "error": error}, error

    def _run_channel_paid_content_check(self, channel: str, sections: dict):
        available_sections = []
        for type_name, section in (sections or {}).items():
            if isinstance(section, dict) and section.get("status") != "missing":
                available_sections.append(type_name)
        args = [
            "--channel",
            channel,
            "--paid-content-only",
            "--available-sections",
            ",".join(available_sections),
        ]
        try:
            result = self.launcher.run_python_script_capture(self.launcher.check_sections_script_path, args, timeout=120)
            if result.returncode != 0:
                return PAID_CONTENT_UNKNOWN, (result.stderr or result.stdout or self.tr("channels.paid_unknown")).strip()
            payload = json.loads(result.stdout.strip() or "{}")
            status = str(payload.get(PAID_CONTENT_STATUS_KEY) or PAID_CONTENT_UNKNOWN).strip()
            if status not in PAID_CONTENT_STATUSES:
                status = PAID_CONTENT_UNKNOWN
            return status, ""
        except Exception as e:
            return PAID_CONTENT_UNKNOWN, str(e)

    def on_channel_sections_checked(self, info: dict):
        if info.get("active_check"):
            channel = info.get("channel")
            active_type = info.get("active_type")
            if channel and active_type:
                self.active_channel_section_check = (self.normalize_channel_key(channel), active_type)
                card = self.channel_cards.get(channel)
                if card:
                    self.apply_channel_section_result(channel, card)
            self.refresh_channel_check_animation()
            return

        if info.get("partial_result"):
            channel = info.get("channel")
            if not channel:
                return
            key = self.normalize_channel_key(channel)
            sections = info.get("sections") or {}
            if isinstance(sections, dict) and sections:
                self.channel_section_results.setdefault(key, {}).update(sections)
                pending_sections = self.channel_section_checks_pending.setdefault(key, set())
                for type_name in sections:
                    pending_sections.discard(type_name)
            paid_status = str(info.get(PAID_CONTENT_STATUS_KEY) or "").strip()
            current_paid_status = self.channel_paid_content_status(channel)
            if paid_status == PAID_CONTENT_HAS or (paid_status == PAID_CONTENT_FREE and current_paid_status != PAID_CONTENT_HAS):
                self.set_channel_paid_content_status(channel, paid_status)
            card = self.channel_cards.get(channel)
            if card:
                self.apply_channel_section_result(channel, card)
            self.refresh_channel_check_animation()
            return

        if info.get("batch_finished"):
            self.channel_section_checks_running.clear()
            self.channel_section_checks_pending.clear()
            self.channel_paid_content_checks_running.clear()
            self.active_channel_section_check = None
            self.channel_section_stop_event.clear()
            self.set_channel_section_check_button_running(False)
            done = info.get("progress_done")
            total = info.get("progress_total", 0)
            if info.get("stopped"):
                self.channel_sections_status_label.setText(self.tr("channels.stopped_count", done=done, total=total))
            else:
                self.channel_sections_status_label.setText(self.tr("channels.checked", total=total))
            for channel, card in self.channel_cards.items():
                self.apply_channel_section_result(channel, card)
            self.refresh_channel_check_animation()
            return
        if info.get("progress_done") is not None:
            self.channel_sections_status_label.setText(
                self.tr("channels.checking", done=info.get("progress_done"), total=info.get("progress_total"))
            )
            return

        channel = info.get("channel")
        if not channel:
            return
        key = self.normalize_channel_key(channel)
        self.channel_section_checks_running.discard(key)
        self.channel_section_checks_pending.pop(key, None)
        self.channel_paid_content_checks_running.discard(key)
        sections = info.get("sections") or {}
        if isinstance(sections, dict) and sections:
            self.channel_section_results[key] = sections
        paid_status = str(info.get(PAID_CONTENT_STATUS_KEY) or "").strip()
        current_paid_status = self.channel_paid_content_status(channel)
        if paid_status == PAID_CONTENT_HAS or (paid_status == PAID_CONTENT_FREE and current_paid_status != PAID_CONTENT_HAS):
            self.set_channel_paid_content_status(channel, paid_status)
        card = self.channel_cards.get(channel)
        if card:
            self.apply_channel_section_result(channel, card)
        if self.active_channel_section_check and self.active_channel_section_check[0] == key:
            self.active_channel_section_check = None
        if not info.get("called_from_batch"):
            self.channel_section_stop_event.clear()
            self.set_channel_section_check_button_running(False)
            if info.get("cancelled"):
                self.channel_sections_status_label.setText(self.tr("state.stopped"))
            elif not (info.get("error") or "").strip():
                self.channel_sections_status_label.setText(self.tr("channels.checked_one"))
        self.refresh_channel_check_animation()
        error = (info.get("error") or "").strip()
        if error and not info.get("called_from_batch"):
            self.channel_sections_status_label.setText(self.tr("channels.check_failed"))

    def apply_channel_section_result(self, channel: str, card=None):
        card = card or self.channel_cards.get(channel)
        if not card:
            return
        key = self.normalize_channel_key(channel)
        sections = self.channel_section_results.get(key) or {}
        pending_sections = self.channel_section_checks_pending.get(key) or set()
        is_running = key in self.channel_section_checks_running
        active_key = active_type = None
        if self.active_channel_section_check:
            active_key, active_type = self.active_channel_section_check
        dots = self.channel_check_animation_text()
        waiting = self.channel_check_waiting_text()
        for type_name, button in getattr(card, "type_buttons", {}).items():
            base_emoji = self.channel_type_emoji(type_name)
            section = sections.get(type_name) or {}
            if is_running and type_name in pending_sections:
                is_active = key == active_key and type_name == active_type
                button.setText(dots if is_active else waiting)
                label = self.channel_type_label(type_name)
                if is_active:
                    button.setToolTip(self.tr("channels.active", label=label))
                else:
                    button.setToolTip(self.tr("channels.waiting", label=label))
                continue
            status = section.get("status") if isinstance(section, dict) else ""
            if status == "missing":
                button.setText("❌")
                button.setToolTip(self.tr("channels.section_missing", label=self.channel_type_label(type_name)))
            elif status == "error":
                button.setText(base_emoji)
                error = (section.get("error") or "").strip() if isinstance(section, dict) else ""
                button.setToolTip(self.tr("channels.section_error", label=self.channel_type_label(type_name), error=(f" ({error[:120]})" if error else "")))
            else:
                button.setText(base_emoji)
                if status == "available":
                    button.setToolTip(self.tr("channels.section_available", label=self.channel_type_label(type_name)))
                else:
                    button.setToolTip(self.tr("channels.section_toggle", label=self.channel_type_label(type_name)))
        paid_button = getattr(card, "paid_content_button", None)
        if paid_button is not None and key in self.channel_paid_content_checks_running:
            is_active = key == active_key and active_type == PAID_CONTENT_STATUS_KEY
            paid_button.setText(dots if is_active else waiting)
            if is_active:
                paid_button.setToolTip(self.tr("channels.active", label=self.tr("channels.paid_unknown").split(":", 1)[0]))
            else:
                paid_button.setToolTip(self.tr("channels.waiting", label=self.tr("channels.paid_unknown").split(":", 1)[0]))
            return
        self.apply_channel_paid_content_status(channel, card)

    def apply_channel_paid_content_status(self, channel: str, card=None):
        card = card or self.channel_cards.get(channel)
        if not card:
            return
        button = getattr(card, "paid_content_button", None)
        if button is None:
            return
        status = self.channel_paid_content_status(channel)
        button.setText(PAID_CONTENT_EMOJIS.get(status, PAID_CONTENT_EMOJIS[PAID_CONTENT_UNKNOWN]))
        tooltip_key = {
            PAID_CONTENT_UNKNOWN: "channels.paid_unknown",
            PAID_CONTENT_HAS: "channels.paid_has",
            PAID_CONTENT_FREE: "channels.paid_free",
        }.get(status, "channels.paid_unknown")
        button.setToolTip(self.tr(tooltip_key))

    def channel_type_emoji(self, type_name: str):
        for item_type, emoji, _label in CHANNEL_TYPE_BUTTONS:
            if item_type == type_name:
                return emoji
        return "?"

    def channel_type_label(self, type_name: str):
        labels = {
            "videos": self.tr("overview.video"),
            "shorts": self.tr("overview.shorts"),
            "streams": self.tr("overview.stream"),
        }
        if type_name in labels:
            return labels[type_name]
        return type_name

    def mark_channel_archived(self, channel: str):
        if self.launcher.is_running:
            QMessageBox.warning(
                self,
                self.tr("archive.title"),
                self.tr("archive.stop_first"),
            )
            return
        if not self.launcher.mark_script_path.exists():
            QMessageBox.warning(self, self.tr("archive.title"), self.tr("generic.script_not_found", path=self.launcher.mark_script_path))
            return

        title = self._channel_display_name(channel, self.channel_title_from_url(channel)) or channel
        answer = QMessageBox.question(
            self,
            self.tr("archive.title"),
            self.tr("archive.mark_question", title=title),
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
                message = (result.stderr or result.stdout or self.tr("archive.update_failed")).strip()
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
            "videos": self.tr("overview.video"),
            "shorts": "Shorts",
            "streams": self.tr("overview.stream"),
        }
        lines = [
            f"{self.tr('archive.mark_found')}: {summary.get('total_found', 0)}",
            f"{self.tr('archive.mark_added')}: {summary.get('total_added', 0)}",
        ]
        for type_name in ("videos", "shorts", "streams"):
            details = type_info.get(type_name) or {}
            line = f"{labels[type_name]}: {self.tr('archive.mark_found').lower()} {details.get('found', 0)}, {self.tr('archive.mark_added').lower()} {details.get('added', 0)}"
            error = (details.get("error") or "").strip()
            if error:
                line += f", error: {error}"
            lines.append(line)
        QMessageBox.information(self, self.tr("archive.title"), "\n".join(lines))
        self.refresh_overview()

    def on_channel_mark_archive_failed(self, message: str):
        QMessageBox.warning(self, self.tr("archive.title"), message or self.tr("archive.update_failed"))

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
        image.setToolTip(self.tr("channels.open"))
        image.clicked.connect(lambda c=channel: self.open_channel(c))

        side_button_x = 158
        side_button_size = 28

        delete_btn = QPushButton("X", image_box)
        delete_btn.setGeometry(side_button_x, 4, side_button_size, side_button_size)
        delete_btn.setToolTip(self.tr("channels.delete"))
        delete_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 0, 0, 110);
                color: white;
                border: none;
                font-size: 22px;
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
        paid_btn = QPushButton(image_box)
        paid_btn.setEnabled(False)
        paid_btn.setGeometry(side_button_x, 128, side_button_size, side_button_size)
        paid_btn.setStyleSheet("""
            QPushButton:disabled {
                background: rgba(0, 0, 0, 135);
                color: white;
                border: none;
                font-family: "Noto Sans", "DejaVu Sans", "Noto Color Emoji", sans-serif;
                font-size: 18px;
                font-weight: bold;
                padding: 0;
                text-align: center;
            }
        """)
        paid_btn.raise_()
        card.paid_content_button = paid_btn
        self.apply_channel_paid_content_status(channel, card)

        type_buttons = {}
        for idx, (type_name, emoji, label) in enumerate(CHANNEL_TYPE_BUTTONS):
            type_btn = QPushButton(emoji, image_box)
            type_btn.setCheckable(True)
            type_btn.setChecked(rules.get(type_name, True))
            type_btn.setGeometry(side_button_x, 35 + idx * 31, side_button_size, side_button_size)
            type_btn.setToolTip(self.tr("channels.section_toggle", label=self.channel_type_label(type_name)))
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
        archive_btn.setGeometry(side_button_x, 159, side_button_size, side_button_size)
        archive_btn.setToolTip(self.tr("archive.mark_tip"))
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
        button.setToolTip(self.tr("channels.add"))
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
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self.launcher.script_environment(),
                timeout=45,
                check=False,
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
            enabled = self.tr("queue.on") if is_enabled else self.tr("queue.off")
            hour = int(sched.get("hour", 0))
            marker = sched.get("last_run_marker", "")
            last_run = marker if marker else self.tr("queue.never_run")
            item = QListWidgetItem(f"{hour:02d}:00    {enabled}    {last_run}")
            item.setData(Qt.UserRole, idx)
            self.schedule_list.addItem(item)
        if hasattr(self, "schedule_summary_label"):
            total = len(self.launcher.schedules)
            self.schedule_summary_label.setText(self.tr("queue.enabled_summary", enabled=enabled_count, total=total))

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
                "download_button": self.overview_download_video_button,
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
        if self.pending_preview_context == context or self.preview_request_context == context:
            self.preview_timer.stop()
            self.preview_request_id += 1
        widgets["status"].setText("")
        widgets["uploader"].setText("")
        widgets["thumbnail"].setPixmap(QPixmap())
        widgets["thumbnail"].setText(self.tr("preview.thumbnail"))
        widgets["button"].setEnabled(False)
        download_button = widgets.get("download_button")
        if download_button is not None:
            download_button.setEnabled(False)
        widgets["title"].setText(self.tr("preview.quick_wait") if context == "quick" else self.tr("preview.queue_wait"))
        if context == "quick" and self.quick_download_dialog is not None:
            self.quick_download_dialog.update_actions(False)
            self.quick_download_dialog.set_channel_logo("")
            self.quick_download_dialog.reset_media_options()

    def schedule_video_preview(self, context: str = "queue"):
        widgets = self._preview_widgets(context)
        self.current_previews[context] = {}
        if context == "queue":
            self.current_preview = {}
        widgets["status"].setText("")
        widgets["uploader"].setText("")
        widgets["thumbnail"].setPixmap(QPixmap())
        widgets["thumbnail"].setText(self.tr("preview.thumbnail"))
        text = widgets["input"].text().strip()
        valid = self._looks_like_youtube_url(text)
        widgets["button"].setEnabled(valid)
        download_button = widgets.get("download_button")
        if download_button is not None:
            download_button.setEnabled(valid)
        if context == "quick" and self.quick_download_dialog is not None:
            self.quick_download_dialog.update_actions(valid)
            self.quick_download_dialog.reset_media_options()
        if not text:
            self.preview_timer.stop()
            self.preview_request_id += 1
            widgets["title"].setText(self.tr("preview.quick_wait") if context == "quick" else self.tr("preview.queue_wait"))
            return
        if not self._looks_like_youtube_url(text):
            self.preview_timer.stop()
            self.preview_request_id += 1
            widgets["title"].setText(self.tr("preview.error") if context == "quick" else self.tr("preview.need_youtube"))
            if context == "quick":
                widgets["status"].setText(self.tr("preview.need_youtube"))
            return
        widgets["title"].setText(self.tr("preview.loading"))
        self.pending_preview_context = context
        self.preview_timer.start(800)

    def fetch_video_preview(self):
        context = self.pending_preview_context
        widgets = self._preview_widgets(context)
        url = widgets["input"].text().strip()
        if not self._looks_like_youtube_url(url):
            widgets["title"].setText(self.tr("preview.need_youtube"))
            widgets["status"].setText("")
            return

        self.preview_request_id += 1
        request_id = self.preview_request_id
        self.preview_request_context = context
        widgets["status"].setText(self.tr("preview.reading"))

        thread = threading.Thread(target=self._metadata_worker, args=(request_id, context, url), daemon=True)
        thread.start()

    def _metadata_worker(self, request_id: int, context: str, url: str):
        try:
            attempts = [("", [])]
            if context == "quick":
                attempts.insert(0, (
                    QUICK_AUDIO_PLAYER_CLIENT,
                    ["--extractor-args", f"youtube:player_client={QUICK_AUDIO_PLAYER_CLIENT}"],
                ))
            data = None
            metadata_player_client = ""
            last_error = self.tr("preview.failed")
            for player_client, extractor_args in attempts:
                try:
                    result = subprocess.run(
                        self.launcher.yt_dlp_command()
                        + self.launcher.yt_dlp_js_runtime_args()
                        + extractor_args
                        + ["--dump-single-json", "--no-playlist", "--skip-download", url],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        env=self.launcher.script_environment(),
                        timeout=45,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    last_error = self.tr("preview.failed")
                    continue
                if result.returncode != 0:
                    last_error = result.stderr.strip() or self.tr("preview.failed")
                    continue
                try:
                    candidate = json.loads(result.stdout)
                except json.JSONDecodeError:
                    last_error = self.tr("preview.failed")
                    continue
                if isinstance(candidate, dict):
                    data = candidate
                    metadata_player_client = player_client
                    break
            if data is None:
                self.metadata_failed.emit(request_id, last_error[-300:])
                return
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

            audio_tracks = audio_track_options(data)
            if metadata_player_client:
                for audio_track in audio_tracks:
                    audio_track["player_client"] = metadata_player_client
            self.metadata_loaded.emit({
                "request_id": request_id,
                "context": context,
                "url": data.get("webpage_url") or url,
                "video_id": data.get("id") or self.youtube_video_id_from_url(url),
                "title": data.get("title") or self.tr("preview.no_title"),
                "uploader": data.get("uploader") or "",
                "thumbnail_path": thumbnail_path,
                "channel_thumbnail_path": channel_thumbnail_path,
                "channel_url": channel_url,
                "audio_tracks": audio_tracks,
                "subtitle_tracks": subtitle_track_options(data),
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
                check=False,
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
        current_url = widgets["input"].text().strip()
        current_id = self.youtube_video_id_from_url(current_url)
        info_id = str(info.get("video_id") or self.youtube_video_id_from_url(info.get("url") or "")).strip()
        if not current_url or (current_id and info_id and current_id != info_id):
            return
        self.current_previews[context] = info
        if context == "queue":
            self.current_preview = info
        widgets["title"].setText(info.get("title", self.tr("preview.no_title")))
        uploader = info.get("uploader") or ""
        widgets["uploader"].setText(self.tr("preview.channel", uploader=uploader) if uploader else "")
        widgets["status"].setText(self.tr("preview.ready_queue"))
        widgets["button"].setEnabled(True)
        download_button = widgets.get("download_button")
        if download_button is not None:
            download_button.setEnabled(True)
        if context == "quick" and self.quick_download_dialog is not None:
            self.quick_download_dialog.update_actions(True)
            self.quick_download_dialog.set_channel_logo(info.get("channel_thumbnail_path") or "")
            self.quick_download_dialog.set_media_options(info)

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
        download_button = widgets.get("download_button")
        if download_button is not None:
            download_button.setEnabled(widgets["button"].isEnabled())
        if context == "quick" and self.quick_download_dialog is not None:
            self.quick_download_dialog.update_actions(self._looks_like_youtube_url(widgets["input"].text().strip()))
            self.quick_download_dialog.set_channel_logo("")
            self.quick_download_dialog.reset_media_options()
        widgets["title"].setText(self.tr("preview.failed"))
        widgets["status"].setText(self.tr("preview.failed_detail", message=message))

    def add_video_to_queue(self, context: str = "queue", *, front: bool = False, clear_after: bool = True, quiet: bool = False):
        widgets = self._preview_widgets(context)
        preview = self.current_previews.get(context, {})
        url = (preview.get("url") or widgets["input"].text()).strip()
        if not self._looks_like_youtube_url(url):
            if not quiet:
                QMessageBox.warning(self, self.tr("tab.queue"), self.tr("preview.need_youtube"))
            return False

        video_id = (preview.get("video_id") or self.youtube_video_id_from_url(url)).strip()
        if video_id and self.archive_contains_video(video_id):
            if not quiet:
                QMessageBox.information(self, self.tr("tab.queue"), self.tr("preview.in_archive"))
            widgets["status"].setText(self.tr("preview.in_archive"))
            return False

        queued = self._read_queue()
        queued_ids = {self.youtube_video_id_from_url(item) for item in queued}
        if url in queued or (video_id and video_id in queued_ids):
            if not front:
                if not quiet:
                    QMessageBox.information(self, self.tr("tab.queue"), self.tr("preview.in_queue"))
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
            if clear_after:
                widgets["input"].clear()
                self._clear_video_preview(context)
            widgets["status"].setText(self.tr("preview.added_front") if front else self.tr("preview.added"))
            self.refresh_queue()
            self.refresh_overview()
            return True
        except Exception as e:
            if not quiet:
                QMessageBox.warning(self, self.tr("tab.queue"), str(e))
            return False

    def refresh_queue(self):
        self.queue_list.clear()
        for url in self._read_queue():
            self.queue_list.addItem(url)
        if hasattr(self, "queue_summary_label"):
            count = self.queue_list.count()
            if count == 1:
                text = self.tr("queue.one_video")
            else:
                text = self.tr("queue.many_videos", count=count)
            self.queue_summary_label.setText(text)

    def remove_selected_queued_video(self):
        row = self.queue_list.currentRow()
        if row < 0:
            QMessageBox.information(self, self.tr("tab.queue"), self.tr("queue.not_selected"))
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
        self.log_view.setPlainText(self._filtered_log_text(self._tail_text(path, 500)))
        self.log_view.moveCursor(QTextCursor.End)

    def _filtered_log_text(self, text: str) -> str:
        mode = self.log_filter_combo.currentData() if hasattr(self, "log_filter_combo") else "all"
        if mode == "all":
            return text
        lines = text.splitlines()
        if mode == "errors":
            filtered = [line for line in lines if self._is_error_log_line(line)]
        else:
            filtered = [line for line in lines if self._is_important_log_line(line)]
        return "\n".join(filtered)

    def _is_error_log_line(self, line: str) -> bool:
        text = fix_mojibake(line).lower()
        if self._is_members_only_log_line(text):
            return False
        return any(marker in text for marker in (
            "❌",
            "⚠",
            "error",
            "failed",
            "failure",
            "traceback",
            "exception",
            "ошиб",
            "не найден",
            "не удалось",
            "таймаут",
            "timeout",
            "could not",
            "cannot",
        ))

    def _is_important_log_line(self, line: str) -> bool:
        text = fix_mojibake(line).lower()
        if self._is_members_only_log_line(text):
            return True
        return any(marker in text for marker in (
            "🔔 найдено новое видео",
            "⏬ видео скач",
            "⚓ видео перемещено",
            "видео скач",
            "скачано:",
            "download complete",
            "has already been downloaded",
            "merging formats",
            "destination:",
        ))

    def _is_members_only_log_line(self, text: str) -> bool:
        return any(marker in text for marker in (
            "🔒",
            "members-only",
            "join this channel",
            "exclusive perks",
            "закрыто для участников",
        ))

    def open_folder(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _selected_schedule_index(self):
        item = self.schedule_list.currentItem()
        if not item:
            QMessageBox.information(self, self.tr("queue.planner"), self.tr("queue.schedule_not_selected"))
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
        return looks_like_youtube_url(url)

    def _looks_like_youtube_channel_url(self, url: str):
        if not url.startswith(("https://www.youtube.com/", "https://youtube.com/")):
            return False
        return "/@" in url or "/channel/" in url or "/c/" in url or "/user/" in url

    def youtube_video_id_from_url(self, url: str):
        return extract_video_id(url)

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

    def archive_contains_variant(
        self,
        video_id: str,
        *,
        resolution: str,
        audio_tracks: list[dict] | None = None,
        subtitle_selections: list[str] | None = None,
    ) -> bool:
        video_id = str(video_id or "").strip()
        if not video_id or not self.launcher.archive_details_file.exists():
            return False
        audio_tracks = audio_tracks or []
        subtitle_selections = subtitle_selections or []
        for line in read_text_for_display(self.launcher.archive_details_file).splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict) or str(entry.get("video_id") or "").strip() != video_id:
                continue
            if archive_entry_file_exists(entry) and archive_entry_matches_variant(
                entry,
                resolution=resolution,
                audio_format_ids=[str(track.get("format_id") or "") for track in audio_tracks],
                audio_languages=[str(track.get("language") or "") for track in audio_tracks],
                subtitle_selections=subtitle_selections,
            ):
                return True
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
    old_sys_path = sys.path[:]
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    fallback_stdout = None
    fallback_stderr = None
    try:
        if sys.stdout is None:
            fallback_stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
            sys.stdout = fallback_stdout
        if sys.stderr is None:
            fallback_stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
            sys.stderr = fallback_stderr
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                with contextlib.suppress(OSError, ValueError):
                    reconfigure(encoding="utf-8", errors="replace")
        for import_path in (str(base_dir), str(script_path.parent)):
            if import_path not in sys.path:
                sys.path.insert(0, import_path)
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
        sys.path = old_sys_path
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
            with contextlib.suppress(OSError, ValueError):
                reconfigure(encoding="utf-8", errors="replace")
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


def run_launcher(args: list[str], *, open_quick: bool = False) -> int:
    lock = SingleInstanceLock("yt_harvester_launcher.lock")
    if not lock.acquire():
        return write_quick_download_request() if open_quick else 0
    try:
        launcher = TrayLauncher()
        launcher.app.aboutToQuit.connect(lock.release)
        if open_quick:
            QTimer.singleShot(250, launcher.open_quick_download_window)
        else:
            launcher.handle_startup_mode(args)
        return int(launcher.run() or 0)
    finally:
        lock.release()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--quick-download":
        raise SystemExit(run_launcher(sys.argv[2:], open_quick=True))

    if len(sys.argv) >= 2 and sys.argv[1] == "--run-yt-dlp":
        raise SystemExit(run_yt_dlp_helper(sys.argv[2:]))

    if len(sys.argv) >= 3 and sys.argv[1] == "--run-script":
        raise SystemExit(run_python_script_helper(sys.argv[2], sys.argv[3:]))

    raise SystemExit(run_launcher(sys.argv[1:]))
