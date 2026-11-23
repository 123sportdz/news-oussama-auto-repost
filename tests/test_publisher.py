"""Tests for per-page Graph API tokens in publisher.py.

Page tokens are per Page: a token for NewsDz9 must never be sent
for aljazaer07, and vice versa. The shared FB_PAGE_ACCESS_TOKEN is
only a fallback when no per-page token is set.
"""
import json
import re
import unittest
import urllib.error
import urllib.parse
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


class _JsonResp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


class _ResumableServer:
    """Scripted fake for the start/transfer/finish flow."""

    def __init__(self, file_size, fail_first_transfer=False, stall=False):
        self.file_size = file_size
        self.fail_first_transfer = fail_first_transfer
        self.stall = stall
        self.requests = []
        self.transfer_bodies = []
        self._transfer_calls = 0

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        data = req.data or b""
        if b"upload_phase=start" in data:
            return _JsonResp({"video_id": "v1", "upload_session_id": "s1",
                              "start_offset": 0,
                              "end_offset": self.file_size})
        if b'"upload_phase"\r\n\r\ntransfer' in data:
            self._transfer_calls += 1
            self.transfer_bodies.append(data)
            if self.fail_first_transfer and self._transfer_calls == 1:
                raise urllib.error.URLError("connection reset")
            off = int(re.search(rb'start_offset"\r\n\r\n(\d+)',
                                data).group(1))
            if self.stall:
                return _JsonResp({"start_offset": off,
                                  "end_offset": self.file_size})
            # Next offset = this offset + the bytes actually sent.
            head = re.search(
                rb'video_file_chunk"; filename="[^"]+"\r\n'
                rb'Content-Type: video/mp4\r\n\r\n', data)
            chunk = data[head.end():].rsplit(b"\r\n--", 1)[0]
            nxt = min(off + len(chunk), self.file_size)
            return _JsonResp({"start_offset": nxt,
                              "end_offset": self.file_size})
        if b"upload_phase=finish" in data:
            return _JsonResp({"video_id": "v1", "success": True})
        raise AssertionError(f"unexpected request: {data[:80]!r}")


class ResumableUploadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).parent / "tmp-resumable-publish"
        self.tmp.mkdir(exist_ok=True)
        # 25 distinct bytes, so each chunk's content is checkable.
        self.video = self.tmp / "clip.mp4"
        self.video.write_bytes(bytes(range(25)))

    def tearDown(self):
        for p in self.tmp.iterdir():
            p.unlink()
        self.tmp.rmdir()

    def test_large_file_goes_through_start_transfer_finish(self):
        server = _ResumableServer(file_size=25)
        with mock.patch.object(publisher.urllib.request, "urlopen", server):
            result = publisher.publish_page_graph_resumable(
                "147624121772177", "ثنائية مازة\nسطر ثاني",
                self.video, "token-news", chunk_size=10)
        self.assertEqual(result, {"video_id": "v1", "success": True})
        kinds = []
        for req in server.requests:
            data = req.data or b""
            if b"upload_phase=start" in data:
                kinds.append("start")
                params = urllib.parse.parse_qs(data.decode())
                self.assertEqual(params["file_size"], ["25"])
                self.assertEqual(params["access_token"], ["token-news"])
            elif b'"upload_phase"\r\n\r\ntransfer' in data:
                kinds.append("transfer")
            elif b"upload_phase=finish" in data:
                kinds.append("finish")
                params = urllib.parse.parse_qs(data.decode())
                self.assertEqual(params["title"], ["ثنائية مازة"])
                self.assertEqual(params["description"],
                                 ["ثنائية مازة\nسطر ثاني"])
        self.assertEqual(kinds, ["start", "transfer", "transfer",
                                 "transfer", "finish"])
        # Chunks carry exactly the file's bytes, in order.
        self.assertIn(bytes(range(0, 10)), server.transfer_bodies[0])
        self.assertIn(bytes(range(10, 20)), server.transfer_bodies[1])
        self.assertIn(bytes(range(20, 25)), server.transfer_bodies[2])

    def test_dispatcher_picks_resumable_above_threshold(self):
        server = _ResumableServer(file_size=25)
        with mock.patch.object(publisher.urllib.request, "urlopen", server):
            publisher.publish_page_graph(
                "147624121772177", "cap", self.video, "token-news",
                resumable_min_size=10, chunk_size=10)
        kinds = [b"upload_phase=start" in (r.data or b"")
                 for r in server.requests]
        self.assertTrue(kinds[0])
        self.assertEqual(len(server.requests), 5)

    def test_transfer_failure_retries_the_same_chunk_once(self):
        server = _ResumableServer(file_size=25, fail_first_transfer=True)
        with mock.patch.object(publisher.urllib.request, "urlopen", server):
            result = publisher.publish_page_graph_resumable(
                "147624121772177", "cap", self.video, "token-news",
                chunk_size=10)
        self.assertEqual(result, {"video_id": "v1", "success": True})
        # 1 failed + 3 successful transfers, then finish.
        self.assertEqual(len(server.transfer_bodies), 4)
        self.assertEqual(len(server.requests), 6)

    def test_start_failure_raises_without_any_transfer(self):
        import io

        err = urllib.error.HTTPError(
            "https://graph.facebook.com/v21.0/147624121772177/videos",
            400, "Bad Request", {}, io.BytesIO(
                b'{"error": {"message": "bad file_size"}}'))
        with mock.patch.object(publisher.urllib.request, "urlopen",
                               side_effect=err):
            with self.assertRaises(publisher.PublishError):
                publisher.publish_page_graph_resumable(
                    "147624121772177", "cap", self.video, "token-news")

    def test_stalled_upload_raises_after_three_stalls(self):
        server = _ResumableServer(file_size=25, stall=True)
        with mock.patch.object(publisher.urllib.request, "urlopen", server):
            with self.assertRaises(publisher.PublishError) as ctx:
                publisher.publish_page_graph_resumable(
                    "147624121772177", "cap", self.video, "token-news",
                    chunk_size=10)
        self.assertIn("stalled", str(ctx.exception))
        self.assertEqual(len(server.transfer_bodies), 3)


class GraphErrorClassificationTest(unittest.TestCase):
    """_post_graph sorts failures so the monitor can tell a bad
    video (count toward give-up) from a bad setup (never counts)."""

    def setUp(self):
        self.tmp = Path(__file__).parent / "tmp-graph-errors"
        self.tmp.mkdir(exist_ok=True)
        self.video = self.tmp / "clip.mp4"
        self.video.write_bytes(b"\x00\x00\x00\x18ftypmp42FAKEVIDEO")

    def tearDown(self):
        for p in self.tmp.iterdir():
            p.unlink()
        self.tmp.rmdir()

    def _http_error(self, code):
        import io
        return urllib.error.HTTPError(
            "https://graph.facebook.com/v21.0/147624121772177/videos",
            code, "Error", {}, io.BytesIO(
                b'{"error": {"message": "boom"}}'))

    def _call(self, side_effect):
        with mock.patch.object(publisher.urllib.request, "urlopen",
                               side_effect=side_effect):
            return publisher.publish_page_graph(
                "147624121772177", "cap", self.video, "token-news")

    def test_401_and_403_become_auth_errors(self):
        for code in (401, 403):
            with self.assertRaises(publisher.AuthPublishError):
                self._call(self._http_error(code))

    def test_500_becomes_transient_error(self):
        with self.assertRaises(publisher.TransientPublishError):
            self._call(self._http_error(500))

    def test_400_stays_a_plain_publish_error(self):
        with self.assertRaises(publisher.PublishError) as ctx:
            self._call(self._http_error(400))
        self.assertIs(type(ctx.exception), publisher.PublishError)

    def test_network_error_becomes_transient_error(self):
        with self.assertRaises(publisher.TransientPublishError):
            self._call(urllib.error.URLError("connection reset"))


if __name__ == "__main__":
    unittest.main()
