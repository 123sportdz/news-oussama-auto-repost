"""Tests for process_queue: incremental progress + failure isolation."""
import unittest

from src import monitor as mon
from src import state as state_mod
from src.monitor import QUEUE


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


if __name__ == "__main__":
    unittest.main()
