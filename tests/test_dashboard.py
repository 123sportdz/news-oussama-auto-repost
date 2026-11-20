"""Tests for the dashboard: publish/download buttons and file serving."""
import json
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from src import dashboard, state as state_mod
from src.publisher import ConsentMissingError

BASE = Path(__file__).resolve().parent.parent


class DashboardButtonsTest(unittest.TestCase):
    def test_home_page_has_download_and_publish_buttons(self):
        page = dashboard.home_page()
        self.assertIn("سحب", page)
        self.assertIn("نشر", page)
        self.assertIn("/process", page)
        self.assertIn("/publish", page)
        self.assertIn("/queue-process", page)

    def test_resolve_download_rejects_traversal(self):
        self.assertIsNone(dashboard._resolve_download("../config"))
        self.assertIsNone(dashboard._resolve_download(".."))
        self.assertIsNone(dashboard._resolve_download("no-such-post-id"))

    def test_resolve_download_finds_watermarked_file(self):
        target = dashboard.DL / "test123-watermarked.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake")
        try:
            self.assertEqual(dashboard._resolve_download("test123"), target)
        finally:
            target.unlink(missing_ok=True)

    def test_publish_one_consent_error_leaves_post_queued(self):
        ready = state_mod.load_json(state_mod.READY, {})
        pid = "807380775688613"
        rec = ready.get(pid)
        self.assertIsNotNone(rec, "test fixture post missing from ready.json")
        cfg = {"settings": {"caption": {"template": "{caption}",
                                        "max_chars": 1024, "hashtags": []}},
               "destinations": [{"name": "NewsDz9", "page_id": "1",
                                 "enabled": True}]}
        calls = {"marked": False}
        orig_is_pub = state_mod.is_published
        orig_mark = state_mod.mark_published
        orig_publish = dashboard.publish
        state_mod.is_published = lambda *a: False
        state_mod.mark_published = lambda *a: calls.__setitem__("marked", True)

        def boom(*a, **k):
            raise ConsentMissingError("PROFESSIONAL_CONSENT_REQUIRED")
        dashboard.publish = boom
        try:
            ok, msg = dashboard._publish_one(cfg, pid, "NewsDz9")
        finally:
            state_mod.is_published = orig_is_pub
            state_mod.mark_published = orig_mark
            dashboard.publish = orig_publish
        self.assertFalse(ok)
        self.assertIn("Consent", msg)
        self.assertFalse(calls["marked"])


class DashboardServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), dashboard.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_unknown_post_route_is_404(self):
        req = urllib.request.Request(self._url("/no-such-route"),
                                     data=b"x=1", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 404)

    def test_file_route_rejects_traversal(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self._url("/file/..%2Fconfig"))
        self.assertEqual(ctx.exception.code, 404)

    def test_queue_post_adds_url(self):
        queue = BASE / "state" / "queue.txt"
        before = queue.read_text() if queue.exists() else ""
        test_url = "https://www.facebook.com/reel/test-dashboard-queue"
        data = urllib.parse.urlencode({"url": test_url}).encode()
        req = urllib.request.Request(self._url("/queue"), data=data,
                                     method="POST")
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as exc:
            # 303 redirect: urllib follows it; a failure here is real
            self.assertEqual(exc.code, 303)
        try:
            self.assertIn(test_url, queue.read_text())
        finally:
            lines = [l for l in queue.read_text().splitlines()
                     if l.strip() != test_url]
            queue.write_text("\n".join(lines) + ("\n" if lines else ""))


if __name__ == "__main__":
    unittest.main()
