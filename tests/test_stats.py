"""Tests for post-publish stats helpers."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import config as config_mod
from src import state as state_mod
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


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class GraphStatsTest(unittest.TestCase):
    """Stats via the Graph API — the Windows route (no facebook-cli)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self._orig_state = state_mod.STATE
        self._orig_published = state_mod.PUBLISHED
        self._orig_stats = stats.STATS
        self._orig_base = config_mod.BASE
        state_mod.STATE = base / "state"
        state_mod.PUBLISHED = base / "state" / "published.json"
        stats.STATS = base / "state" / "stats.json"
        config_mod.BASE = base
        self._orig_env = os.environ.get("FB_PAGE_ACCESS_TOKEN_111")
        os.environ["FB_PAGE_ACCESS_TOKEN_111"] = "FAKE-PAGE-TOKEN"
        config_mod._DOTENV_LOADED = True
        self.cfg = {"destinations": [
            {"name": "NewsDz9", "page_id": "111"},
            {"name": "Oussama — profile", "kind": "profile"},
        ]}
        state_mod.save_json(state_mod.STATE / "published.json", {
            "999": {"destinations": {
                "NewsDz9": {"id": "555"},
                "Oussama — profile": {"id": "666"},
            }},
        })

    def tearDown(self):
        state_mod.STATE = self._orig_state
        state_mod.PUBLISHED = self._orig_published
        stats.STATS = self._orig_stats
        config_mod.BASE = self._orig_base
        if self._orig_env is None:
            os.environ.pop("FB_PAGE_ACCESS_TOKEN_111", None)
        else:
            os.environ["FB_PAGE_ACCESS_TOKEN_111"] = self._orig_env
        config_mod._DOTENV_LOADED = False
        self.tmp.cleanup()

    def _urlopen(self, req, timeout=None):
        url = req.full_url
        if "video_insights" in url:
            return FakeResponse({"data": [{"values": [{"value": 1234}]}]})
        if "/555?" in url:
            return FakeResponse({
                "likes": {"summary": {"total_count": 42}},
                "comments": {"summary": {"total_count": 7}},
            })
        raise AssertionError(f"unexpected Graph URL: {url}")

    def test_read_post_graph_merges_likes_comments_views(self):
        eng = stats.read_post_graph("555", "TOKEN", urlopen=self._urlopen)
        self.assertEqual(eng, {"likes": 42, "comments": 7, "views": 1234})

    def test_refresh_stats_graph_skips_profile_without_token(self):
        out = stats.refresh_stats_graph(self.cfg, urlopen=self._urlopen)
        dests = out["999"]["destinations"]
        self.assertEqual(dests["NewsDz9"]["engagement"],
                         {"likes": 42, "comments": 7, "views": 1234})
        self.assertEqual(dests["NewsDz9"]["source"], "graph")
        self.assertNotIn("Oussama — profile", dests)

    def test_graph_failure_keeps_partial_engagement(self):
        def flaky(req, timeout=None):
            if "video_insights" in req.full_url:
                raise OSError("down")
            return self._urlopen(req, timeout)

        eng = stats.read_post_graph("555", "TOKEN", urlopen=flaky)
        self.assertEqual(eng, {"likes": 42, "comments": 7})


if __name__ == "__main__":
    unittest.main()
