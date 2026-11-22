"""Tests for automatic state backups (src/backup.py)."""
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from src import backup


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self._orig_state = backup.STATE_DIR
        self._orig_backups = backup.BACKUP_DIR
        backup.STATE_DIR = base / "state"
        backup.BACKUP_DIR = base / "backups"
        backup.STATE_DIR.mkdir(parents=True)
        (backup.STATE_DIR / "published.json").write_text('{"1": {}}')
        (backup.STATE_DIR / "seen.json").write_text('{}')
        (backup.STATE_DIR / "monitor.lock").write_text("123")
        (backup.STATE_DIR / ".seen.json.tmp").write_text("partial")

    def tearDown(self):
        backup.STATE_DIR = self._orig_state
        backup.BACKUP_DIR = self._orig_backups
        self.tmp.cleanup()

    def test_backup_contains_state_without_lock_and_tmps(self):
        dest = backup.backup_state(now=datetime(2026, 11, 22, 12, 0, 0))
        self.assertEqual(dest.name, "state-20261122-120000.zip")
        with zipfile.ZipFile(dest) as zf:
            names = zf.namelist()
        self.assertIn("published.json", names)
        self.assertIn("seen.json", names)
        self.assertNotIn("monitor.lock", names)
        self.assertNotIn(".seen.json.tmp", names)

    def test_if_due_skips_when_fresh(self):
        now = datetime(2026, 11, 22, 12, 0, 0)
        backup.backup_state(now=now)
        self.assertIsNone(
            backup.backup_state_if_due(now=now + timedelta(hours=1)))

    def test_if_due_runs_when_stale(self):
        old = datetime(2026, 11, 20, 12, 0, 0)
        backup.backup_state(now=old)
        dest = backup.backup_state_if_due(
            now=old + timedelta(hours=25))
        self.assertIsNotNone(dest)

    def test_prunes_to_keep_newest(self):
        base = datetime(2026, 11, 22, 12, 0, 0)
        for i in range(5):
            backup.backup_state(now=base + timedelta(hours=i), keep=3)
        self.assertEqual(len(backup.list_backups()), 3)

    def test_restore_round_trip(self):
        dest = backup.backup_state(now=datetime(2026, 11, 22, 12, 0, 0))
        (backup.STATE_DIR / "monitor.lock").unlink()
        (backup.STATE_DIR / "published.json").unlink()
        backup.restore_state(dest)
        self.assertTrue((backup.STATE_DIR / "published.json").exists())

    def test_restore_refuses_while_locked(self):
        dest = backup.backup_state(now=datetime(2026, 11, 22, 12, 0, 0))
        with self.assertRaises(SystemExit):
            backup.restore_state(dest)


if __name__ == "__main__":
    unittest.main()
