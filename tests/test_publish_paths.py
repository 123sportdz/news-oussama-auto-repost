"""Regression tests: every publish path resolves the token PER DESTINATION.

Bug (2026-11-21): dashboard._publish_one and monitor.publish_ready
both read only the shared FB_PAGE_ACCESS_TOKEN and passed it along —
a token for NewsDz9 could be sent for aljazaer07, and a per-page
token added to .env after the process started was never picked up
(config._load_dotenv ran once). Both paths must now resolve through
publisher.token_for_destination, per destination, at publish time.
"""
import unittest
from pathlib import Path
from unittest import mock

from src import dashboard, monitor
from src import state as state_mod

NEWS_PAGE = "147624121772177"
DZ7_PAGE = "107469321989814"
FIXTURE_PID = "999999999999998"
FIXTURE_REC = {"post_id": FIXTURE_PID, "caption": "نص تجريبي",
               "owner": "Test", "created": "",
               "url": "https://example.invalid/reel/2",
               "media_type": "video",
               "watermarked": "/tmp/nope-watermarked.mp4",
               "publish": [{"destination": "NewsDz9"}]}

CFG = {"settings": {"caption": {"template": "{caption}", "max_chars": 1024,
                                "hashtags": []}},
       "destinations": [
           {"name": "NewsDz9", "page_id": NEWS_PAGE, "enabled": True},
           {"name": "aljazaer07", "page_id": DZ7_PAGE, "enabled": True},
       ]}


class _ReadyFixture(unittest.TestCase):
    def setUp(self):
        self._ready_before = state_mod.load_json(state_mod.READY, {})
        ready = dict(self._ready_before)
        ready[FIXTURE_PID] = dict(FIXTURE_REC)
        state_mod.save_json(state_mod.READY, ready)
        self._orig_is_pub = state_mod.is_published
        self._orig_mark = state_mod.mark_published
        state_mod.is_published = lambda *a: False
        state_mod.mark_published = lambda *a: None

    def tearDown(self):
        state_mod.save_json(state_mod.READY, self._ready_before)
        state_mod.is_published = self._orig_is_pub
        state_mod.mark_published = self._orig_mark


class DashboardPublishTokenTest(_ReadyFixture):
    def test_publish_one_uses_per_page_token_not_shared(self):
        calls = {}
        orig = dashboard.publish
        dashboard.publish = lambda dest, text, path, token="": calls.__setitem__(
            "token", token)
        try:
            with mock.patch.dict(
                    "os.environ",
                    {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": "token-news",
                     "FB_PAGE_ACCESS_TOKEN": "token-shared"},
                    clear=False):
                ok, _ = dashboard._publish_one(CFG, FIXTURE_PID, "NewsDz9")
        finally:
            dashboard.publish = orig
        self.assertTrue(ok)
        self.assertEqual(calls["token"], "token-news")

    def test_publish_one_gives_each_page_its_own_token(self):
        calls = {}
        orig = dashboard.publish

        def fake_publish(dest, text, path, token=""):
            calls[dest["name"]] = token
            return {"id": "v1"}
        dashboard.publish = fake_publish
        try:
            with mock.patch.dict(
                    "os.environ",
                    {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": "token-news",
                     f"FB_PAGE_ACCESS_TOKEN_{DZ7_PAGE}": "token-dz7"},
                    clear=False):
                dashboard._publish_one(CFG, FIXTURE_PID, "NewsDz9")
                dashboard._publish_one(CFG, FIXTURE_PID, "aljazaer07")
        finally:
            dashboard.publish = orig
        self.assertEqual(calls["NewsDz9"], "token-news")
        self.assertEqual(calls["aljazaer07"], "token-dz7")
        self.assertNotEqual(calls["NewsDz9"], calls["aljazaer07"])

    def test_publish_one_falls_back_to_shared_token(self):
        calls = {}
        orig = dashboard.publish
        dashboard.publish = lambda dest, text, path, token="": calls.__setitem__(
            "token", token)
        try:
            with mock.patch.dict(
                    "os.environ", {"FB_PAGE_ACCESS_TOKEN": "token-shared"},
                    clear=False):
                dashboard._publish_one(CFG, FIXTURE_PID, "NewsDz9")
        finally:
            dashboard.publish = orig
        self.assertEqual(calls["token"], "token-shared")


class MonitorPublishTokenTest(_ReadyFixture):
    def test_publish_ready_uses_per_page_token_per_destination(self):
        calls = {}
        orig = monitor.publish

        def fake_publish(dest, text, path, token=""):
            calls[dest["name"]] = token
            return {"id": "v1"}
        monitor.publish = fake_publish
        try:
            with mock.patch.dict(
                    "os.environ",
                    {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": "token-news",
                     f"FB_PAGE_ACCESS_TOKEN_{DZ7_PAGE}": "token-dz7",
                     "FB_PAGE_ACCESS_TOKEN": "token-shared"},
                    clear=False):
                monitor.publish_ready(CFG)
        finally:
            monitor.publish = orig
        self.assertEqual(calls["NewsDz9"], "token-news")
        self.assertEqual(calls["aljazaer07"], "token-dz7")

    def test_publish_ready_falls_back_to_shared_token(self):
        calls = {}
        orig = monitor.publish
        monitor.publish = lambda dest, text, path, token="": calls.__setitem__(
            dest["name"], token) or {"id": "v1"}
        try:
            with mock.patch.dict(
                    "os.environ", {"FB_PAGE_ACCESS_TOKEN": "token-shared"},
                    clear=False):
                monitor.publish_ready(CFG)
        finally:
            monitor.publish = orig
        self.assertEqual(calls["NewsDz9"], "token-shared")
        self.assertEqual(calls["aljazaer07"], "token-shared")


if __name__ == "__main__":
    unittest.main()
