"""Tests for the fixes from the 2026-11-20 independent code review.

Each test names the finding it covers (C1, M3, M4, M5, M6, M7, M8, C5).
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import caption as caption_mod
from src import monitor as monitor_mod
from src import state as state_mod
from src.config import load_config, validate_config
from src.downloader import post_info, video_info


class MissingCliTest(unittest.TestCase):
    """C1: a missing facebook-cli must fall back to yt-dlp, not crash."""

    def test_post_info_falls_back_when_cli_missing(self):
        ytdlp_json = json.dumps({
            "id": "123456789012345", "description": "test caption",
            "uploader": "Goal Algeria", "upload_date": "20261120",
            "ext": "mp4", "title": "test",
        })
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd[0])
            if "facebook-cli" in cmd[0]:
                raise FileNotFoundError("no such file")
            result = mock.Mock()
            result.stdout = ytdlp_json
            result.stderr = ""
            result.returncode = 0
            return result

        with mock.patch("src.downloader.subprocess.run", fake_run):
            info = post_info("https://www.facebook.com/reel/123456789012345")
        self.assertEqual(info["post_id"], "123456789012345")
        self.assertEqual(info["caption"], "test caption")

    def test_video_info_missing_ytdlp_raises_system_exit(self):
        def fake_run(cmd, **kwargs):
            raise FileNotFoundError("no such file")

        with mock.patch("src.downloader.subprocess.run", fake_run):
            with self.assertRaises(SystemExit):
                video_info("https://www.facebook.com/reel/123456789012345")

    def test_post_info_missing_id_raises_not_none(self):
        # a CLI reply with no post_id used to become the post "None"
        from src.downloader import _post_info_cli

        def fake_run(cmd, **kwargs):
            result = mock.Mock()
            result.stdout = json.dumps({"posts": [{"caption": "x"}]})
            result.stderr = ""
            return result

        with mock.patch("src.downloader.subprocess.run", fake_run):
            with self.assertRaises(SystemExit):
                _post_info_cli("https://www.facebook.com/reel/123456789012345")


class CaptionSafetyTest(unittest.TestCase):
    """M6: a bad caption template must not crash the whole run."""

    def test_unknown_placeholder_stays_literal(self):
        text = caption_mod.build_caption("hello", "{title} — {caption}")
        self.assertEqual(text, "{title} — hello")

    def test_truncate_clamps_tiny_max_chars(self):
        self.assertEqual(caption_mod.truncate("hello world", 2), "h...")
        # 0 / None means "default" (1024) — no truncation
        self.assertEqual(caption_mod.truncate("hello world", 0),
                         "hello world")


class ConfigFixesTest(unittest.TestCase):
    """M5 (.env) and M8 (publish windows as a string)."""

    def test_windows_string_normalised_to_list(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.yaml"
            path.write_text("settings:\n  publish:\n"
                            "    mode: auto\n"
                            "    windows: '18:00-23:00'\n")
            cfg = load_config(path)
            windows = cfg["settings"]["publish"]["windows"]
            self.assertEqual(windows, ["18:00-23:00"])

    def test_validate_config_flags_bad_window(self):
        problems = validate_config({
            "sources": [{"url": "https://example.invalid", "name": "s"}],
            "destinations": [{"url": "https://example.invalid",
                              "name": "d", "page_id": "1"}],
            "settings": {"check_every_minutes": 30,
                         "max_posts_per_check": 3,
                         "publish": {"windows": ["not-a-window"]}},
        })
        self.assertTrue(any("window" in p for p in problems))

    def test_dotenv_is_loaded(self):
        import os
        from src import config as config_mod
        with tempfile.TemporaryDirectory() as td:
            dotenv = Path(td) / ".env"
            dotenv.write_text("FB_PAGE_ACCESS_TOKEN=test-token-123\n")
            config_mod._DOTENV_LOADED = False
            old_base = config_mod.BASE
            config_mod.BASE = Path(td)
            try:
                os.environ.pop("FB_PAGE_ACCESS_TOKEN", None)
                self.assertEqual(
                    config_mod.env("FB_PAGE_ACCESS_TOKEN"), "test-token-123")
            finally:
                config_mod.BASE = old_base
                config_mod._DOTENV_LOADED = False
                os.environ.pop("FB_PAGE_ACCESS_TOKEN", None)


class FailedRetryTest(unittest.TestCase):
    """C5: failed URLs are retried (up to 3 attempts), not lost forever."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig_failed = monitor_mod.FAILED
        monitor_mod.FAILED = Path(self.tmp.name) / "failed.txt"

    def tearDown(self):
        monitor_mod.FAILED = self._orig_failed
        self.tmp.cleanup()

    def test_failed_roundtrip_and_requeue(self):
        monitor_mod.save_failed({
            "https://example.invalid/a": {"error": "boom", "attempts": 1},
            "https://example.invalid/b": {"error": "boom", "attempts": 3},
        })
        failed = monitor_mod.load_failed()
        self.assertEqual(failed["https://example.invalid/a"]["attempts"], 1)
        # only the 1-attempt URL is retried; the 3-attempt one is done
        urls = monitor_mod.requeue_failed(["https://example.invalid/c"])
        self.assertEqual(urls, ["https://example.invalid/a",
                                "https://example.invalid/c"])
        # the requeued entry stays in failed.txt with its attempts count,
        # so the next failure increments it instead of resetting to 1
        self.assertEqual(
            monitor_mod.load_failed()["https://example.invalid/a"]
            ["attempts"], 1)

    def test_old_format_without_attempts_defaults_to_one(self):
        monitor_mod.FAILED.write_text(
            "https://example.invalid/a | download failed\n")
        failed = monitor_mod.load_failed()
        self.assertEqual(failed["https://example.invalid/a"]["attempts"], 1)


class DedupIdentityTest(unittest.TestCase):
    """M7: the /reel/ id and the CLI post id are different namespaces."""

    def test_known_post_ids_includes_url_id(self):
        seen = {
            "122150043855008839": {
                "post_id": "122150043855008839",
                "url_id": "2332956744217094",
            },
        }
        ids = monitor_mod.known_post_ids(seen)
        self.assertIn("122150043855008839", ids)
        self.assertIn("2332956744217094", ids)


class AtomicSaveTest(unittest.TestCase):
    """M1: save_json must always leave valid JSON on disk."""

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.json"
            state_mod.save_json(path, {"a": 1})
            state_mod.save_json(path, {"a": 2, "b": [1, 2, 3]})
            self.assertEqual(state_mod.load_json(path, {}),
                             {"a": 2, "b": [1, 2, 3]})
            self.assertFalse(path.with_name(".x.json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
