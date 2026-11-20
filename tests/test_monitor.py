"""Tests for monitor helpers: content-hash dedup and publish windows."""
import hashlib
import unittest
from datetime import datetime
from pathlib import Path

from src.monitor import (file_sha256, find_duplicate_by_hash,
                         in_publish_window, next_window_start)

BASE = Path(__file__).resolve().parent.parent


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


if __name__ == "__main__":
    unittest.main()
