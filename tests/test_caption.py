"""Tests for caption building: template, hashtags, 1024-char limit."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.caption import build_caption, truncate


class TestCaption(unittest.TestCase):
    def test_template_preserves_original(self):
        self.assertEqual(
            build_caption("ثنائية مازة و حاج موسى 🎩🪄"),
            "ثنائية مازة و حاج موسى 🎩🪄")

    def test_custom_template(self):
        self.assertEqual(
            build_caption("goal", template="🎬 {caption} | NEWS OUSSAMA"),
            "🎬 goal | NEWS OUSSAMA")

    def test_hashtags_appended(self):
        out = build_caption("goal", hashtags=["dz", "#football"])
        self.assertIn("#dz", out)
        self.assertIn("#football", out)
        self.assertTrue(out.startswith("goal"))

    def test_hashtag_not_duplicated(self):
        out = build_caption("goal #dz", hashtags=["dz"])
        self.assertEqual(out.count("#dz"), 1)

    def test_truncate_page_limit(self):
        long_text = "x" * 2000
        out = build_caption(long_text, max_chars=1024)
        self.assertLessEqual(len(out), 1024)
        self.assertTrue(out.endswith("..."))

    def test_truncate_short_unchanged(self):
        self.assertEqual(truncate("short", 1024), "short")

    def test_empty_caption(self):
        self.assertEqual(build_caption(""), "")


if __name__ == "__main__":
    unittest.main()
