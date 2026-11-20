"""Tests for discovery (URL extraction from page HTML) and diagnostics."""
import unittest

from src import diagnostics
from src.discover import _post_id_from_url, extract_post_urls


class ExtractUrlsTest(unittest.TestCase):
    def test_reel_and_watch_links(self):
        html = """
        <a href="/reel/1668308364143510/">x</a>
        <a href="/reel/980161941419171/">y</a>
        <a href="/watch/?v=123456789012345">z</a>
        <a href="/reel/1668308364143510/">dup</a>
        <a href="/photo/999/">not a video</a>
        """
        urls = extract_post_urls(html)
        self.assertEqual(urls, [
            "https://www.facebook.com/reel/1668308364143510",
            "https://www.facebook.com/reel/980161941419171",
            "https://www.facebook.com/reel/123456789012345",
        ])

    def test_empty_html(self):
        self.assertEqual(extract_post_urls(""), [])
        self.assertEqual(extract_post_urls(None), [])

    def test_post_id_from_url(self):
        self.assertEqual(
            _post_id_from_url("https://www.facebook.com/reel/123456"),
            "123456")


class DiagnosticsTest(unittest.TestCase):
    def test_run_checks_shape(self):
        checks = diagnostics.run_checks()
        names = [c["name"] for c in checks]
        self.assertIn("ffmpeg", names)
        self.assertIn("yt-dlp", names)
        self.assertIn("Playwright (اكتشاف المنشورات)", names)
        self.assertIn("جلسة فيسبوك (اكتشاف المنشورات)", names)
        self.assertIn("الإعدادات", names)
        for c in checks:
            self.assertIn("ok", c)
            self.assertIn("detail", c)

    def test_playwright_missing_reported_honestly(self):
        checks = diagnostics.run_checks()
        pw = next(c for c in checks
                  if c["name"].startswith("Playwright"))
        # On this machine Playwright is not installed — the check must say so.
        self.assertFalse(pw["ok"])
        self.assertIn("pip install playwright", pw["detail"])


if __name__ == "__main__":
    unittest.main()
