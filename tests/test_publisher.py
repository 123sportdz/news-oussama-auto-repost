"""Tests for per-page Graph API tokens in publisher.py.

Page tokens are per Page: a token for NewsDz9 must never be sent
for aljazaer07, and vice versa. The shared FB_PAGE_ACCESS_TOKEN is
only a fallback when no per-page token is set.
"""
import unittest
from pathlib import Path
from unittest import mock

from src import publisher


class TokenForDestinationTest(unittest.TestCase):
    def test_per_page_token_beats_shared_fallback(self):
        with mock.patch.dict(
                "os.environ",
                {"FB_PAGE_ACCESS_TOKEN_147624121772177": "token-news",
                 "FB_PAGE_ACCESS_TOKEN": "token-shared"},
                clear=False):
            got = publisher.token_for_destination(
                {"name": "NewsDz9", "page_id": "147624121772177"},
                fallback="token-shared")
        self.assertEqual(got, "token-news")

    def test_each_page_gets_its_own_token(self):
        with mock.patch.dict(
                "os.environ",
                {"FB_PAGE_ACCESS_TOKEN_147624121772177": "token-news",
                 "FB_PAGE_ACCESS_TOKEN_107469321989814": "token-dz7"},
                clear=False):
            news = publisher.token_for_destination(
                {"name": "NewsDz9", "page_id": "147624121772177"})
            dz7 = publisher.token_for_destination(
                {"name": "aljazaer07", "page_id": "107469321989814"})
        self.assertEqual(news, "token-news")
        self.assertEqual(dz7, "token-dz7")
        self.assertNotEqual(news, dz7)

    def test_token_env_name_beats_per_page_var(self):
        with mock.patch.dict(
                "os.environ",
                {"FB_PAGE_TOKEN_NEWSDZ9": "token-named",
                 "FB_PAGE_ACCESS_TOKEN_147624121772177": "token-news"},
                clear=False):
            got = publisher.token_for_destination(
                {"name": "NewsDz9", "page_id": "147624121772177",
                 "token_env": "FB_PAGE_TOKEN_NEWSDZ9"})
        self.assertEqual(got, "token-named")

    def test_fallback_when_no_per_page_token(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            got = publisher.token_for_destination(
                {"name": "NewsDz9", "page_id": "147624121772177"},
                fallback="token-shared")
        self.assertEqual(got, "token-shared")

    def test_empty_when_nothing_set(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            got = publisher.token_for_destination(
                {"name": "NewsDz9", "page_id": "147624121772177"})
        self.assertEqual(got, "")


class PublishRoutingTest(unittest.TestCase):
    def test_publish_uses_per_page_token_even_without_fallback(self):
        calls = {}

        def fake_graph(page_id, text, video_path, token):
            calls["token"] = token
            return {"id": "v1"}

        orig_graph = publisher.publish_page_graph
        orig_cli = publisher.publish_page_cli
        publisher.publish_page_graph = fake_graph
        publisher.publish_page_cli = lambda *a: (_ for _ in ()).throw(
            AssertionError("CLI must not be called when a token exists"))
        try:
            with mock.patch.dict(
                    "os.environ",
                    {"FB_PAGE_ACCESS_TOKEN_147624121772177": "token-news"},
                    clear=False):
                publisher.publish(
                    {"name": "NewsDz9", "page_id": "147624121772177"},
                    "caption", Path("x.mp4"), token="")
        finally:
            publisher.publish_page_graph = orig_graph
            publisher.publish_page_cli = orig_cli
        self.assertEqual(calls["token"], "token-news")

    def test_publish_falls_back_to_cli_without_any_token(self):
        calls = {}

        def fake_cli(page_id, text, video_path):
            calls["page_id"] = page_id
            return {"raw": "ok"}

        orig_cli = publisher.publish_page_cli
        publisher.publish_page_cli = fake_cli
        try:
            with mock.patch.dict("os.environ", {}, clear=True):
                publisher.publish(
                    {"name": "NewsDz9", "page_id": "147624121772177"},
                    "caption", Path("x.mp4"), token="")
        finally:
            publisher.publish_page_cli = orig_cli
        self.assertEqual(calls["page_id"], "147624121772177")


class GraphPublishRequestTest(unittest.TestCase):
    """publish_page_graph builds a correct multipart video upload.

    The Graph route is the one that has never run against Facebook
    live — so the request it builds must at least be proven correct
    here: right endpoint, POST, multipart body carrying the token,
    the description and the file bytes.
    """

    def setUp(self):
        self.tmp = Path(__file__).parent / "tmp-graph-publish"
        self.tmp.mkdir(exist_ok=True)
        self.video = self.tmp / "clip.mp4"
        self.video.write_bytes(b"\x00\x00\x00\x18ftypmp42FAKEVIDEO")

    def tearDown(self):
        for p in self.tmp.iterdir():
            p.unlink()
        self.tmp.rmdir()

    def _capture_urlopen(self, body=b'{"id": "987654321"}'):
        seen = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return body

        def fake_urlopen(req, timeout=None):
            seen["req"] = req
            return FakeResp()

        return seen, fake_urlopen

    def test_posts_multipart_video_to_page_videos_endpoint(self):
        seen, fake = self._capture_urlopen()
        with mock.patch.object(publisher.urllib.request, "urlopen", fake):
            result = publisher.publish_page_graph(
                "147624121772177", "ثنائية مازة و حاج موسى",
                self.video, "token-news")
        self.assertEqual(result, {"id": "987654321"})
        req = seen["req"]
        self.assertEqual(
            req.full_url,
            "https://graph.facebook.com/v21.0/147624121772177/videos")
        self.assertEqual(req.get_method(), "POST")
        self.assertIn("multipart/form-data; boundary=",
                      req.headers["Content-type"])
        body = req.data
        self.assertIn(b'name="access_token"\r\n\r\ntoken-news', body)
        self.assertIn("ثنائية مازة و حاج موسى".encode("utf-8"), body)
        self.assertIn(b'name="source"; filename="clip.mp4"', body)
        self.assertIn(b"FAKEVIDEO", body)

    def test_consent_error_becomes_consent_missing_error(self):
        import io
        import urllib.error

        err = urllib.error.HTTPError(
            "https://graph.facebook.com/v21.0/147624121772177/videos",
            400, "Bad Request", {}, io.BytesIO(
                b'{"error": {"message": "PROFESSIONAL_CONSENT_REQUIRED"}}'))
        with mock.patch.object(publisher.urllib.request, "urlopen",
                               side_effect=err):
            with self.assertRaises(publisher.ConsentMissingError):
                publisher.publish_page_graph(
                    "147624121772177", "cap", self.video, "token-news")

    def test_other_http_error_becomes_publish_error_with_code(self):
        import io
        import urllib.error

        err = urllib.error.HTTPError(
            "https://graph.facebook.com/v21.0/147624121772177/videos",
            403, "Forbidden", {}, io.BytesIO(
                b'{"error": {"message": "not allowed"}}'))
        with mock.patch.object(publisher.urllib.request, "urlopen",
                               side_effect=err):
            with self.assertRaises(publisher.PublishError) as ctx:
                publisher.publish_page_graph(
                    "147624121772177", "cap", self.video, "token-news")
        self.assertIn("403", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
