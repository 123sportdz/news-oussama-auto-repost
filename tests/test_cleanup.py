"""Tests for download retention (src/cleanup.py)."""
import os
import tempfile
import unittest
from pathlib import Path

from src import cleanup
from src import state as state_mod

OLD = 40 * 86400  # 40 days ago
NEW = 1 * 86400   # 1 day ago


class CleanupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self._orig_dl = cleanup.DL
        self._orig_published = state_mod.PUBLISHED
        self._orig_ready = state_mod.READY
        cleanup.DL = base / "downloads"
        state_mod.PUBLISHED = base / "state" / "published.json"
        state_mod.READY = base / "state" / "ready.json"
        cleanup.DL.mkdir(parents=True)
        self.cfg = {"destinations": [
            {"name": "NewsDz9", "enabled": True},
            {"name": "aljazaer07", "enabled": True},
        ], "settings": {"cleanup": {"keep_days": 30}}}
        state_mod.save_json(state_mod.PUBLISHED, {
            "111": {"destinations": {"NewsDz9": {}, "aljazaer07": {}}},
            "222": {"destinations": {"NewsDz9": {}}},
            "333": {"destinations": {"NewsDz9": {}, "aljazaer07": {}}},
        })
        state_mod.save_json(state_mod.READY, {
            "333": {"caption": "still waiting"},
        })
        self.now = 1795400000.0

    def tearDown(self):
        cleanup.DL = self._orig_dl
        state_mod.PUBLISHED = self._orig_published
        state_mod.READY = self._orig_ready
        self.tmp.cleanup()

    def _file(self, name: str, age: float) -> Path:
        path = cleanup.DL / name
        path.write_bytes(b"x" * 100)
        os.utime(path, (self.now - age, self.now - age))
        return path

    def test_deletes_old_fully_published(self):
        old = self._file("111-watermarked.mp4", OLD)
        old_raw = self._file("111.mp4", OLD)
        result = cleanup.cleanup_downloads(self.cfg, now=self.now)
        self.assertEqual(result["deleted"],
                         ["111-watermarked.mp4", "111.mp4"])
        self.assertEqual(result["freed_bytes"], 200)
        self.assertFalse(old.exists())
        self.assertFalse(old_raw.exists())

    def test_keeps_new_files(self):
        new = self._file("111.mp4", NEW)
        result = cleanup.cleanup_downloads(self.cfg, now=self.now)
        self.assertEqual(result["deleted"], [])
        self.assertTrue(new.exists())

    def test_keeps_partially_published(self):
        partial = self._file("222.mp4", OLD)
        result = cleanup.cleanup_downloads(self.cfg, now=self.now)
        self.assertEqual(result["deleted"], [])
        self.assertTrue(partial.exists())

    def test_keeps_ready_posts(self):
        ready = self._file("333.mp4", OLD)
        result = cleanup.cleanup_downloads(self.cfg, now=self.now)
        self.assertEqual(result["deleted"], [])
        self.assertTrue(ready.exists())

    def test_keeps_unknown_posts(self):
        unknown = self._file("999.mp4", OLD)
        result = cleanup.cleanup_downloads(self.cfg, now=self.now)
        self.assertEqual(result["deleted"], [])
        self.assertTrue(unknown.exists())

    def test_keep_days_zero_disables(self):
        self.cfg["settings"]["cleanup"]["keep_days"] = 0
        old = self._file("111.mp4", OLD)
        result = cleanup.cleanup_downloads(self.cfg, now=self.now)
        self.assertEqual(result["deleted"], [])
        self.assertTrue(old.exists())

    def test_dry_run_deletes_nothing(self):
        old = self._file("111.mp4", OLD)
        result = cleanup.cleanup_downloads(self.cfg, now=self.now,
                                           dry_run=True)
        self.assertEqual(result["deleted"], ["111.mp4"])
        self.assertTrue(old.exists())


if __name__ == "__main__":
    unittest.main()
