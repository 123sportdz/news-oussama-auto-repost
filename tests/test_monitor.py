"""Tests for monitor helpers: content-hash dedup and publish windows."""
import hashlib
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from src import monitor
from src import state as state_mod
from src.monitor import (clear_publish_failure, file_sha256,
                         find_duplicate_by_hash, in_publish_window,
                         is_publish_abandoned, load_publish_failures,
                         next_window_start, record_publish_failure)
from src.publisher import (AuthPublishError, ConsentMissingError,
                           PublishError, TransientPublishError)

BASE = Path(__file__).resolve().parent.parent

FIXTURE_PID = "999999999999998"
FIXTURE_CFG = {
    "settings": {"caption": {"template": "{caption}", "max_chars": 1024,
                             "hashtags": []},
                 "publish": {"windows": []}},
    "destinations": [{"name": "NewsDz9", "page_id": "1", "enabled": True}],
}
FIXTURE_REC = {"post_id": FIXTURE_PID, "caption": "نص تجريبي",
               "owner": "Test", "created": "",
               "url": "https://example.invalid/reel/1",
               "media_type": "video",
               "watermarked": "/tmp/nope-watermarked.mp4",
               "publish": [{"destination": "NewsDz9"}]}


class DedupTest(unittest.TestCase):
    def test_file_sha256(self):
        target = BASE / "state" / "downloads" / "hash-test.bin"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"news-oussama")
        try:
            self.assertEqual(file_sha256(target),
                             hashlib.sha256(b"news-oussama").hexdigest())
        finally:
            target.unlink(missing_ok=True)

    def test_find_duplicate_by_hash(self):
        seen = {
            "111": {"content_hash": "aaa"},
            "222": {"content_hash": "bbb"},
            "333": {},
        }
        self.assertEqual(find_duplicate_by_hash(seen, "bbb"), "222")
        self.assertEqual(
            find_duplicate_by_hash(seen, "bbb", exclude_pid="222"), None)
        self.assertIsNone(find_duplicate_by_hash(seen, "zzz"))
        self.assertIsNone(find_duplicate_by_hash(seen, "aaa",
                                                  exclude_pid="111"))


class PublishWindowTest(unittest.TestCase):
    def test_empty_windows_always_open(self):
        self.assertTrue(in_publish_window([]))
        self.assertTrue(in_publish_window(None))
        self.assertIsNone(next_window_start([]))

    def test_simple_window(self):
        self.assertTrue(in_publish_window(["18:00-23:00"],
                                          datetime(2026, 11, 20, 19, 30)))
        self.assertFalse(in_publish_window(["18:00-23:00"],
                                           datetime(2026, 11, 20, 12, 0)))
        self.assertEqual(next_window_start(["18:00-23:00"],
                                           datetime(2026, 11, 20, 12, 0)),
                         "18:00")
        self.assertEqual(next_window_start(["18:00-23:00"],
                                           datetime(2026, 11, 20, 23, 30)),
                         "18:00")

    def test_overnight_window(self):
        self.assertTrue(in_publish_window(["22:00-01:00"],
                                          datetime(2026, 11, 20, 23, 30)))
        self.assertTrue(in_publish_window(["22:00-01:00"],
                                          datetime(2026, 11, 21, 0, 30)))
        self.assertFalse(in_publish_window(["22:00-01:00"],
                                           datetime(2026, 11, 20, 12, 0)))

    def test_invalid_window_ignored(self):
        self.assertFalse(in_publish_window(["not-a-window"],
                                           datetime(2026, 11, 20, 12, 0)))
        self.assertIsNone(next_window_start(["not-a-window"]))


class PublishFailureTrackingTest(unittest.TestCase):
    """A permanently failing (post, destination) gives up after 3
    attempts and alerts once; auth, network and consent problems
    never abandon a post."""

    def setUp(self):
        self._ready_before = state_mod.load_json(state_mod.READY, {})
        self._failed_before = load_publish_failures()
        self._published_before = state_mod.load_json(state_mod.PUBLISHED, {})
        ready = dict(self._ready_before)
        ready[FIXTURE_PID] = FIXTURE_REC
        state_mod.save_json(state_mod.READY, ready)
        state_mod.save_json(monitor.PUBLISH_FAILED, {})

    def tearDown(self):
        state_mod.save_json(state_mod.READY, self._ready_before)
        state_mod.save_json(monitor.PUBLISH_FAILED, self._failed_before)
        state_mod.save_json(state_mod.PUBLISHED, self._published_before)

    def _run_publish_ready(self, effect):
        calls = {"n": 0}

        def fake_publish(*a, **k):
            calls["n"] += 1
            if isinstance(effect, Exception):
                raise effect
            return {"id": "v1"}

        orig_publish = monitor.publish
        orig_is_pub = state_mod.is_published
        orig_mark = state_mod.mark_published
        monitor.publish = fake_publish
        state_mod.is_published = lambda *a: False
        state_mod.mark_published = lambda *a: None
        try:
            with mock.patch("src.notify.notify") as notify:
                monitor.publish_ready(FIXTURE_CFG)
                return calls["n"], notify.call_count
        finally:
            monitor.publish = orig_publish
            state_mod.is_published = orig_is_pub
            state_mod.mark_published = orig_mark

    def test_permanent_failures_abandon_after_three_attempts(self):
        err = PublishError("Graph API publish failed (400): bad video")
        for _ in range(3):
            self._run_publish_ready(err)
        self.assertTrue(is_publish_abandoned(FIXTURE_PID, "NewsDz9"))
        calls, _ = self._run_publish_ready(err)
        self.assertEqual(calls, 0)  # abandoned: never retried

    def test_auth_transient_and_consent_never_abandon(self):
        for err in (AuthPublishError("401 bad token"),
                    TransientPublishError("500 boom"),
                    ConsentMissingError("consent")):
            state_mod.save_json(monitor.PUBLISH_FAILED, {})
            for _ in range(5):
                self._run_publish_ready(err)
            self.assertFalse(is_publish_abandoned(FIXTURE_PID, "NewsDz9"))

    def test_alert_only_once_for_repeated_failures(self):
        err = TransientPublishError("Graph API publish failed (500): boom")
        _, notify_calls_1 = self._run_publish_ready(err)
        _, notify_calls_2 = self._run_publish_ready(err)
        self.assertEqual(notify_calls_1, 1)
        self.assertEqual(notify_calls_2, 0)

    def test_success_clears_failure_record(self):
        err = PublishError("Graph API publish failed (400): bad video")
        self._run_publish_ready(err)
        self.assertEqual(
            load_publish_failures()[FIXTURE_PID]["NewsDz9"]["attempts"], 1)
        self._run_publish_ready(None)
        self.assertNotIn(FIXTURE_PID, load_publish_failures())

    def test_record_counts_only_permanent_errors(self):
        attempts, just_abandoned, first = record_publish_failure(
            FIXTURE_PID, "NewsDz9", "401 bad token", permanent=False)
        self.assertEqual((attempts, just_abandoned, first), (0, False, True))
        attempts, just_abandoned, first = record_publish_failure(
            FIXTURE_PID, "NewsDz9", "401 bad token", permanent=False)
        self.assertEqual((attempts, just_abandoned, first), (0, False, False))
        clear_publish_failure(FIXTURE_PID, "NewsDz9")
        self.assertNotIn(FIXTURE_PID, load_publish_failures())


if __name__ == "__main__":
    unittest.main()
