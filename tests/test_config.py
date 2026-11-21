"""Tests for config loading and validation."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import BASE, load_config, validate_config


class TestConfig(unittest.TestCase):
    def test_loads_real_config(self):
        cfg = load_config(BASE / "config.yaml")
        self.assertEqual(len(cfg["sources"]), 2)
        self.assertEqual(cfg["settings"]["check_every_minutes"], 30)
        self.assertEqual(cfg["settings"]["max_posts_per_check"], 3)
        self.assertEqual(cfg["settings"]["watermark"]["size_px"], 194)
        self.assertEqual(cfg["settings"]["watermark"]["margin_px"], 30)
        self.assertEqual(cfg["settings"]["caption"]["max_chars"], 1024)
        # Publish mode was switched to auto on 2026-11-20 (commit 2058f7b).
        self.assertEqual(cfg["settings"]["publish"]["mode"], "auto")

    def test_verified_page_ids(self):
        cfg = load_config(BASE / "config.yaml")
        dests = {d["name"]: d for d in cfg["destinations"]}
        self.assertEqual(dests["NewsDz9"]["page_id"], "147624121772177")
        self.assertEqual(dests["aljazaer07"]["page_id"], "107469321989814")

    def test_sources_are_the_two_known_pages(self):
        cfg = load_config(BASE / "config.yaml")
        urls = {s["url"] for s in cfg["sources"]}
        self.assertIn("https://www.facebook.com/goalalgeria16", urls)
        self.assertIn("https://www.facebook.com/mohrec1", urls)

    def test_valid_config_has_no_problems(self):
        cfg = load_config(BASE / "config.yaml")
        self.assertEqual(validate_config(cfg), [])

    def test_missing_page_id_is_flagged(self):
        cfg = load_config(BASE / "config.yaml")
        cfg["destinations"][0]["page_id"] = ""
        problems = validate_config(cfg)
        self.assertTrue(any("page_id missing" in p for p in problems))

    def test_defaults_fill_missing_settings(self):
        cfg = load_config(BASE / "config.yaml")
        del cfg["settings"]["editor"]
        from src.config import _deep_merge, DEFAULTS
        cfg = _deep_merge(DEFAULTS, cfg)
        self.assertIn("editor", cfg["settings"])


if __name__ == "__main__":
    unittest.main()
