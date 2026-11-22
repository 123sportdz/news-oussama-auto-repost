"""Tests for Telegram notifications (src/notify.py)."""
import io
import json
import os
import unittest
from unittest import mock

from src import config as config_mod
from src import notify


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class NotifyTest(unittest.TestCase):
    def setUp(self):
        self._orig = {k: os.environ.get(k) for k in
                      ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456:FAKE-TOKEN"
        os.environ["TELEGRAM_CHAT_ID"] = "987654321"
        # config.env reads os.environ directly; keep dotenv out of the way
        self._orig_loaded = config_mod._DOTENV_LOADED
        config_mod._DOTENV_LOADED = True

    def tearDown(self):
        for key, value in self._orig.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config_mod._DOTENV_LOADED = self._orig_loaded

    def test_configured_when_both_set(self):
        self.assertTrue(notify.configured())

    def test_not_configured_when_token_missing(self):
        os.environ.pop("TELEGRAM_BOT_TOKEN")
        self.assertFalse(notify.configured())
        self.assertFalse(notify.send_telegram("hi"))

    def test_send_posts_to_bot_api(self):
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            seen["body"] = req.data.decode("utf-8")
            return FakeResponse({"ok": True, "result": {}})

        self.assertTrue(notify.send_telegram("hello", urlopen=fake_urlopen))
        self.assertIn("api.telegram.org/bot123456:FAKE-TOKEN/sendMessage",
                      seen["url"])
        self.assertIn("chat_id=987654321", seen["body"])
        self.assertIn("text=hello", seen["body"])

    def test_send_returns_false_on_telegram_error(self):
        def fake_urlopen(req, timeout=None):
            return FakeResponse({"ok": False, "description": "bad token"})

        self.assertFalse(notify.send_telegram("hi", urlopen=fake_urlopen))

    def test_send_never_raises_on_network_error(self):
        def fake_urlopen(req, timeout=None):
            raise OSError("network down")

        self.assertFalse(notify.send_telegram("hi", urlopen=fake_urlopen))


if __name__ == "__main__":
    unittest.main()
