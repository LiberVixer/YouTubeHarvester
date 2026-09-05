import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

try:
    from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow
except ImportError:
    MainWindow = None
else:
    from tray_launcher import MainWindow, ui_text


RUTUBE = "https://rutube.ru/channel/23704195"


@unittest.skipIf(MainWindow is None, "PyQt5 desktop dependencies unavailable")
class ChannelCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(["channel-tests", "-platform", "offscreen"])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.window = MainWindow.__new__(MainWindow)
        QMainWindow.__init__(self.window)
        w = self.window
        w.language = "en"
        w.launcher = SimpleNamespace(channels_file=root / "channels.txt", channel_rules_file=root / "rules.json")
        w.channel_rules = {}
        w.channel_cards = {}
        w.channel_section_results = {}
        w.channel_section_checks_pending = {}
        w.channel_section_checks_running = set()
        w.channel_paid_content_checks_running = set()
        w.active_channel_section_check = None
        w.channel_check_animation_step = 0
        w.channel_section_stop_event = threading.Event()
        w.pending_channel_additions = set()
        w.channel_sections_status_label = QLabel(w)
        w.refresh_channel_check_animation = Mock()
        w.channel_cache_dir = root / "cache"
        self.addCleanup(w.deleteLater)

    def test_rutube_card_capabilities_and_translations(self):
        w = self.window
        for language in ("en", "ru", "uk", "be", "fr", "es", "hi", "zh", "ja", "ar"):
            with self.subTest(language=language):
                w.language = language
                card = w.create_channel_card(RUTUBE)
                card.setParent(w)
                w.apply_channel_section_result(RUTUBE, card)
                self.assertTrue(card.type_buttons["videos"].isEnabled())
                self.assertTrue(card.type_buttons["shorts"].isEnabled())
                streams = card.type_buttons["streams"]
                self.assertFalse(streams.isEnabled())
                self.assertFalse(streams.isChecked())
                self.assertIn("Rutube", streams.toolTip())
                self.assertIn("Rutube", card.paid_content_button.toolTip())
                self.assertIn("Rutube", ui_text(language, "channels.add_prompt"))

    def test_youtube_card_keeps_all_three_sections_enabled(self):
        channel = "https://youtube.com/@example"
        card = self.window.create_channel_card(channel)
        card.setParent(self.window)
        self.assertTrue(all(button.isEnabled() and button.isChecked() for button in card.type_buttons.values()))

    def test_worker_never_animates_or_probes_unsupported_types(self):
        w = self.window
        w._run_channel_section_check = Mock(return_value=({"status": "available", "error": ""}, ""))
        w._run_channel_paid_content_check = Mock()
        events = []
        w.channel_sections_checked.connect(events.append)
        self.assertTrue(w._check_channel_sections_worker(RUTUBE, False, True))
        self.assertEqual([call.args[1] for call in w._run_channel_section_check.call_args_list], ["videos", "shorts"])
        w._run_channel_paid_content_check.assert_not_called()
        self.assertEqual([e["active_type"] for e in events if e.get("active_check")], ["videos", "shorts"])
        self.assertEqual(events[-1]["sections"]["streams"]["status"], "unsupported")
        self.assertFalse(events[-1]["paid_content_checked"])

    def test_waiting_state_excludes_unsupported_buttons(self):
        w = self.window
        card = w.create_channel_card(RUTUBE)
        card.setParent(w)
        w.channel_cards[RUTUBE] = card
        w.mark_channel_section_checking(RUTUBE, True)
        self.assertEqual(w.channel_section_checks_pending[RUTUBE], {"videos", "shorts"})
        self.assertNotIn(RUTUBE, w.channel_paid_content_checks_running)
        self.assertNotEqual(card.paid_content_button.text(), "...")

    @patch("tray_launcher.QMessageBox.information")
    def test_resolved_alias_and_numeric_url_are_saved_only_once(self, information):
        w = self.window
        w.refresh_channels = Mock()
        w.refresh_overview = Mock()
        w.check_channel_sections = Mock()
        w.pending_channel_additions = {"https://rutube.ru/u/rutube"}
        w.on_channel_add_resolved({"requested_channel": "https://rutube.ru/u/rutube", "channel": RUTUBE})
        w._add_resolved_channel(RUTUBE + "/videos/")
        self.assertEqual(w._read_channels(), [RUTUBE])
        self.assertEqual(w.check_channel_sections.call_count, 1)
        self.assertFalse(w.pending_channel_additions)
        information.assert_called_once()


if __name__ == "__main__":
    unittest.main()
