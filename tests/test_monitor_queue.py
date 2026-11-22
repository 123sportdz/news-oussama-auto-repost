"""Tests for process_queue: incremental progress + failure isolation."""
import unittest
from unittest import mock

from src import monitor as mon
from src import state as state_mod
from src.monitor import QUEUE


class MediaOkTest(unittest.TestCase):
    def test_valid_duration_is_ok(self):
        import subprocess as sp
        import tempfile
        from pathlib import Path
        path = Path(tempfile.mkdtemp()) / "v.mp4"
        path.write_bytes(b"fake")
        ok = sp.CompletedProcess(args=["ffprobe"], returncode=0,
                                 stdout="185.13\n", stderr="")
        with mock.patch.object(mon.subprocess, "run", return_value=ok):
            self.assertTrue(mon.media_ok(path))
        with mock.patch.object(mon.subprocess, "run",
                               return_value=sp.CompletedProcess(
                                   args=["ffprobe"], returncode=0,
                                   stdout="", stderr="moov atom not found")):
            self.assertFalse(mon.media_ok(path))

    def test_missing_or_empty_is_not_ok(self):
        import tempfile
        from pathlib import Path
        d = Path(tempfile.mkdtemp())
        self.assertFalse(mon.media_ok(d / "nope.mp4"))
        empty = d / "empty.mp4"
        empty.write_bytes(b"")
        self.assertFalse(mon.media_ok(empty))


class RunLockTest(unittest.TestCase):
    def test_second_run_is_refused_while_first_holds_lock(self):
        import tempfile
        from pathlib import Path
        path = Path(tempfile.mkdtemp()) / "monitor.lock"
        with mon.RunLock(path) as first:
            self.assertTrue(first)
            with mon.RunLock(path) as second:
                self.assertFalse(second)
            self.assertTrue(path.exists())
        self.assertFalse(path.exists())

    def test_stale_lock_is_taken_over(self):
        import tempfile
        from pathlib import Path
        path = Path(tempfile.mkdtemp()) / "monitor.lock"
        path.write_text("999999")  # a PID that does not exist
        with mon.RunLock(path) as locked:
            self.assertTrue(locked)


class ProcessQueueTest(unittest.TestCase):
    def test_failure_isolated_and_progress_saved(self):
        ready_before = state_mod.load_json(state_mod.READY, {})
        queue_before = QUEUE.read_text() if QUEUE.exists() else ""
        failed_before = (mon.FAILED.read_text()
                         if mon.FAILED.exists() else None)
        cfg = {"settings": {
                   "caption": {"template": "{caption}", "max_chars": 1024,
                               "hashtags": []},
                   "watermark": {}, "editor": {}},
               "destinations": []}

        def fake_process_url(url, cfg):
            if "bad" in url:
                raise SystemExit("boom")
            return {"post_id": "999001", "caption": "ok", "owner": "t",
                    "watermarked": "/tmp/x.mp4"}

        orig = mon.process_url
        mon.process_url = fake_process_url
        try:
            done, remaining = mon.process_queue(
                cfg,
                ["https://www.facebook.com/reel/999001",
                 "https://www.facebook.com/reel/bad"], 2)
            ready_now = state_mod.load_json(state_mod.READY, {})
            failed_now = (mon.FAILED.read_text()
                          if mon.FAILED.exists() else "")
            queue_now = QUEUE.read_text() if QUEUE.exists() else ""
        finally:
            mon.process_url = orig
            state_mod.save_json(state_mod.READY, ready_before)
            QUEUE.write_text(queue_before)
            if failed_before is None:
                if mon.FAILED.exists():
                    mon.FAILED.unlink()
            else:
                mon.FAILED.write_text(failed_before)
        self.assertEqual(
            done, ["https://www.facebook.com/reel/999001"])
        self.assertEqual(remaining, [])
        self.assertIn("999001", ready_now)
        self.assertIn("bad", failed_now)
        self.assertNotIn("999001", queue_now)


class RequeueFailedTest(unittest.TestCase):
    """A failed URL retried forever must reach MAX_FAILED_ATTEMPTS.

    Regression: requeue_failed used to drop the failed.txt entry when
    requeuing, so the next failure recorded attempt 1 again and the
    URL was retried on every run instead of being given up on.
    """
    def test_attempts_counter_survives_requeue(self):
        ready_before = state_mod.load_json(state_mod.READY, {})
        queue_before = QUEUE.read_text() if QUEUE.exists() else ""
        failed_before = (mon.FAILED.read_text()
                         if mon.FAILED.exists() else None)
        cfg = {"settings": {
                   "caption": {"template": "{caption}", "max_chars": 1024,
                               "hashtags": []},
                   "watermark": {}, "editor": {}},
               "destinations": []}
        url = "https://www.facebook.com/reel/2152493808690039"

        def always_fail(url, cfg):
            raise SystemExit("boom")

        orig = mon.process_url
        mon.process_url = always_fail
        try:
            mon.save_failed({url: {"error": "Cannot parse data",
                                   "attempts": 1}})
            # cycle 1: requeue keeps the entry, retry fails -> attempt 2
            self.assertEqual(mon.requeue_failed([]), [url])
            self.assertEqual(mon.load_failed()[url]["attempts"], 1)
            mon.process_queue(cfg, [url], 1)
            self.assertEqual(mon.load_failed()[url]["attempts"], 2)
            # cycle 2: same again -> attempt 3, then it is given up on
            self.assertEqual(mon.requeue_failed([]), [url])
            mon.process_queue(cfg, [url], 1)
            self.assertEqual(mon.load_failed()[url]["attempts"], 3)
            self.assertEqual(mon.requeue_failed([]), [])
        finally:
            mon.process_url = orig
            state_mod.save_json(state_mod.READY, ready_before)
            QUEUE.write_text(queue_before)
            if failed_before is None:
                if mon.FAILED.exists():
                    mon.FAILED.unlink()
            else:
                mon.FAILED.write_text(failed_before)


class QualityFilterTest(unittest.TestCase):
    """Clips shorter than editor.min_duration_seconds are skipped."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        self._orig_dl = mon.DL
        mon.DL = Path(self.tmp.name)
        self.seen_before = state_mod.load_json(state_mod.SEEN, {})
        self.cfg = {"settings": {
                        "watermark": {"enabled": False},
                        "editor": {"min_duration_seconds": 5},
                        "caption": {}},
                    "destinations": []}
        self._orig = {}
        for name in ("post_info", "download_video", "media_ok",
                     "media_duration", "file_sha256",
                     "find_duplicate_by_hash"):
            self._orig[name] = getattr(mon, name)
        mon.post_info = lambda url: {
            "post_id": "123", "caption": "x", "owner": "o",
            "created": "c", "media_type": "video"}
        mon.download_video = lambda url, path: path.write_bytes(b"fake")
        mon.media_ok = lambda path, is_photo=False: True
        mon.file_sha256 = lambda path: "abc"
        mon.find_duplicate_by_hash = lambda seen, h, exclude_pid=None: None

    def tearDown(self):
        for name, fn in self._orig.items():
            setattr(mon, name, fn)
        mon.DL = self._orig_dl
        state_mod.save_json(state_mod.SEEN, self.seen_before)
        self.tmp.cleanup()

    def test_short_clip_is_skipped(self):
        mon.media_duration = lambda path: 2.0
        with self.assertRaises(SystemExit) as ctx:
            mon.process_url("https://www.facebook.com/reel/123", self.cfg)
        self.assertIn("too short", str(ctx.exception))

    def test_long_clip_passes(self):
        mon.media_duration = lambda path: 10.0
        rec = mon.process_url("https://www.facebook.com/reel/123",
                              self.cfg)
        self.assertEqual(rec["post_id"], "123")

    def test_filter_off_when_min_is_zero(self):
        mon.media_duration = lambda path: 2.0
        self.cfg["settings"]["editor"]["min_duration_seconds"] = 0
        rec = mon.process_url("https://www.facebook.com/reel/123",
                              self.cfg)
        self.assertEqual(rec["post_id"], "123")


if __name__ == "__main__":
    unittest.main()
