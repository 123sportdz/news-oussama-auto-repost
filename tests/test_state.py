"""Tests for dedup state: a post_id is never processed/published twice."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import state as state_mod


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.seen = Path(self.tmp.name) / "seen.json"
        self.published = Path(self.tmp.name) / "published.json"
        state_mod.SEEN = self.seen
        state_mod.PUBLISHED = self.published

    def tearDown(self):
        self.tmp.cleanup()

    def test_seen_roundtrip(self):
        self.assertFalse(state_mod.is_seen("123"))
        state_mod.mark_seen("123", {"caption": "goal"})
        self.assertTrue(state_mod.is_seen("123"))
        self.assertEqual(state_mod.load_json(self.seen, {})["123"]["caption"],
                         "goal")

    def test_published_per_destination(self):
        self.assertFalse(state_mod.is_published("123", "NewsDz9"))
        state_mod.mark_published("123", "NewsDz9", {"id": "x"})
        self.assertTrue(state_mod.is_published("123", "NewsDz9"))
        # a different destination is still unpublished
        self.assertFalse(state_mod.is_published("123", "aljazaer07"))

    def test_no_duplicate_publish(self):
        state_mod.mark_published("123", "NewsDz9", {"id": "x"})
        state_mod.mark_published("123", "NewsDz9", {"id": "y"})
        entry = state_mod.load_json(self.published, {})["123"]
        self.assertEqual(len(entry["destinations"]), 1)

    def test_load_json_missing_file(self):
        self.assertEqual(state_mod.load_json(Path("/nonexistent/x.json"), {}),
                         {})


if __name__ == "__main__":
    unittest.main()
