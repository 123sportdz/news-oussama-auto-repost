"""Tests for the Facebook session check in diagnostics."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from src import diagnostics


class SessionCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig_auth = diagnostics.AUTH_FILE
        self.auth = Path(self.tmp.name) / "fb-auth.json"
        diagnostics.AUTH_FILE = self.auth
        # run_checks loads the real config; stub the heavy checks by
        # keeping the call but only asserting the session row.
        self._orig_run = diagnostics._run
        diagnostics._run = lambda cmd, timeout=25: (127, "stubbed")

    def tearDown(self):
        diagnostics.AUTH_FILE = self._orig_auth
        diagnostics._run = self._orig_run
        self.tmp.cleanup()

    def _session_row(self):
        rows = diagnostics.run_checks(
            {"sources": [{"enabled": True}], "destinations": []})
        return [r for r in rows
                if "جلسة فيسبوك" in r["name"]][0]

    def test_missing_session_is_not_ok(self):
        row = self._session_row()
        self.assertFalse(row["ok"])
        self.assertIn("--login", row["detail"])

    def test_fresh_session_is_ok_with_age(self):
        self.auth.write_text("{}")
        row = self._session_row()
        self.assertTrue(row["ok"])
        self.assertIn("منذ 0 يوم", row["detail"])

    def test_old_session_warns(self):
        self.auth.write_text("{}")
        old = datetime.now() - timedelta(days=90)
        stamp = old.timestamp()
        os.utime(self.auth, (stamp, stamp))
        row = self._session_row()
        self.assertFalse(row["ok"])
        self.assertIn("منذ 90 يوم", row["detail"])
        self.assertIn("--login", row["detail"])


if __name__ == "__main__":
    unittest.main()
