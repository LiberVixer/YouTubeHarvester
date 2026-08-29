import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from yth_common import download_preview_image


class PreviewHandler(BaseHTTPRequestHandler):
    payload = b"preview-image"

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, _format, *_args):
        return


class PreviewDownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PreviewHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/preview.jpg"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2)

    def test_downloads_http_image_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "preview.jpg"
            self.assertEqual(download_preview_image(self.url, target), str(target))
            self.assertEqual(target.read_bytes(), PreviewHandler.payload)
            self.assertEqual([path.name for path in target.parent.iterdir()], [target.name])

    def test_rejects_non_http_scheme(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "preview.jpg"
            with self.assertRaises(ValueError):
                download_preview_image("file:///etc/passwd", target)
            self.assertFalse(target.exists())

    def test_rejects_oversized_response(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "preview.jpg"
            with self.assertRaises(ValueError):
                download_preview_image(self.url, target, max_bytes=4)
            self.assertFalse(target.exists())
            self.assertEqual(list(target.parent.iterdir()), [])
