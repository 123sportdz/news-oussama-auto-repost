"""Tests for post-publish stats helpers."""
import unittest

from src import stats


class StatsTest(unittest.TestCase):
    def test_extract_engagement(self):
        post = {
            "post_id": "1",
            "post_caption": "hello",
            "likes": 120,
            "comments_count": 5,
            "shares": 2,
            "insights": {"views": 900, "plays": 800},
            "random_number": 42,
        }
        eng = stats.extract_engagement(post)
        self.assertEqual(eng.get("likes"), 120)
        self.assertEqual(eng.get("comments_count"), 5)
        self.assertEqual(eng.get("shares"), 2)
        self.assertEqual(eng.get("views"), 900)
        self.assertNotIn("random_number", eng)

    def test_stats_url(self):
        self.assertEqual(
            stats.stats_url({"url": "https://www.facebook.com/reel/1"}),
            "https://www.facebook.com/reel/1")
        self.assertEqual(stats.stats_url({"id": "123"}),
                         "https://www.facebook.com/reel/123")
        self.assertIsNone(stats.stats_url({"note": "no id here"}))
        self.assertIsNone(stats.stats_url("not a dict"))


if __name__ == "__main__":
    unittest.main()
