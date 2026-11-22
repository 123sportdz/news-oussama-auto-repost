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

FIXTURE_PID = "999999999999999"
FIXTURE_REC = {"post_id": FIXTURE_PID, "caption": "نص تجريبي",
               "owner": "Test", "created": "",
               "url": "https://example.invalid/reel/1",
               "media_type": "video",
               "watermarked": "/tmp/nope-watermarked.mp4",
               "publish": [{"destination": "NewsDz9"}]}


class DashboardButtonsTest(unittest.TestCase):
    def setUp(self):
        # Tests must not depend on the repo's live state: a fresh clone
        # has an empty ready.json, so create our own fixture post here.
        self._ready_before = state_mod.load_json(state_mod.READY, {})
        ready = dict(self._ready_before)
        ready[FIXTURE_PID] = FIXTURE_REC
        state_mod.save_json(state_mod.READY, ready)

    def tearDown(self):
        state_mod.save_json(state_mod.READY, self._ready_before)

    def test_home_page_has_download_and_publish_buttons(self):
        page = dashboard.home_page()
        self.assertIn("سحب", page)
        self.assertIn("نشر", page)
        self.assertIn("/process", page)
        self.assertIn("/publish", page)
        self.assertIn("/queue-process", page)
        self.assertIn("/settings", page)
        self.assertIn("/set-caption", page)
        self.assertIn("/refresh-stats", page)
        self.assertIn("status.json", page)

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
        pid = FIXTURE_PID
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

    def test_status_json(self):
        with urllib.request.urlopen(self._url("/status.json")) as resp:
            data = json.loads(resp.read())
        self.assertIn("queue", data)
        self.assertIn("ready", data)
        self.assertIn("busy", data)
        self.assertIn("last_action", data)

    def test_tokens_page_served(self):
        with urllib.request.urlopen(self._url("/tokens")) as resp:
            page = resp.read().decode("utf-8")
        self.assertEqual(resp.status, 200)
        self.assertIn("توكنات الصفحات", page)
        self.assertIn("token_147624121772177", page)
        self.assertIn("token_107469321989814", page)

    def test_home_page_links_tokens_page(self):
        with urllib.request.urlopen(self._url("/")) as resp:
            page = resp.read().decode("utf-8")
        self.assertIn("/tokens", page)
        self.assertIn("توكنات الصفحات", page)

    def test_home_page_has_telegram_card(self):
        with urllib.request.urlopen(self._url("/")) as resp:
            page = resp.read().decode("utf-8")
        self.assertIn("تنبيهات Telegram", page)
        self.assertIn("/telegram", page)
        self.assertIn("/telegram-test", page)

    def test_telegram_settings_saved_to_env(self):
        from src import tokens as tokens_mod
        from src.config import env as getenv
        data = urllib.parse.urlencode({
            "bot_token": "123456:TEST-BOT-TOKEN",
            "chat_id": "987654321"}).encode()
        req = urllib.request.Request(self._url("/telegram"), data=data,
                                     method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                page = resp.read().decode("utf-8")
            self.assertIn("تم حفظ إعدادات Telegram", page)
            self.assertEqual(getenv("TELEGRAM_BOT_TOKEN"),
                             "123456:TEST-BOT-TOKEN")
            self.assertEqual(getenv("TELEGRAM_CHAT_ID"), "987654321")
        finally:
            tokens_mod.write_env_tokens(
                {}, remove=("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"))

    def test_telegram_test_button_reports_result(self):
        from unittest import mock
        data = b""
        req = urllib.request.Request(self._url("/telegram-test"), data=data,
                                     method="POST")
        with mock.patch("src.notify.send_telegram",
                        return_value=True) as sent:
            with urllib.request.urlopen(req) as resp:
                page = resp.read().decode("utf-8")
        self.assertTrue(sent.called)
        self.assertIn("وصلت رسالة الاختبار", page)

    def test_queue_post_adds_url(self):
        queue = BASE / "state" / "queue.txt"
        before = queue.read_text() if queue.exists() else ""
        test_url = "https://www.facebook.com/reel/test-dashboard-queue"
        data = urllib.parse.urlencode({"url": test_url}).encode()
        req = urllib.request.Request(self._url("/queue"), data=data,
                                     method="POST")
        # urllib follows 303 by default — use a non-redirecting opener
        # so the redirect itself is asserted, not skipped silently
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers,
                                 newurl):
                raise urllib.error.HTTPError(newurl, code, msg, headers, fp)
        opener = urllib.request.build_opener(NoRedirect)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener.open(req)
        self.assertEqual(ctx.exception.code, 303)
        try:
            self.assertIn(test_url, queue.read_text())
        finally:
            lines = [l for l in queue.read_text().splitlines()
                     if l.strip() != test_url]
            queue.write_text("\n".join(lines) + ("\n" if lines else ""))

    def test_bad_index_returns_400(self):
        # i=-1 used to silently target the LAST source; i=999 and i=abc
        # used to drop the connection with no HTTP response at all.
        for bad in ("-1", "999", "abc", ""):
            data = urllib.parse.urlencode({"i": bad}).encode()
            req = urllib.request.Request(
                self._url("/toggle-source"), data=data, method="POST")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
