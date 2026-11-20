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
                {"FB_PAGE_ACCESS_TOKEN_61552757798044": "token-news",
                 "FB_PAGE_ACCESS_TOKEN": "token-shared"},
                clear=False):
            got = publisher.token_for_destination(
                {"name": "NewsDz9", "page_id": "61552757798044"},
                fallback="token-shared")
        self.assertEqual(got, "token-news")

    def test_each_page_gets_its_own_token(self):
        with mock.patch.dict(
                "os.environ",
                {"FB_PAGE_ACCESS_TOKEN_61552757798044": "token-news",
                 "FB_PAGE_ACCESS_TOKEN_100083258325099": "token-dz7"},
                clear=False):
            news = publisher.token_for_destination(
                {"name": "NewsDz9", "page_id": "61552757798044"})
            dz7 = publisher.token_for_destination(
                {"name": "aljazaer07", "page_id": "100083258325099"})
        self.assertEqual(news, "token-news")
        self.assertEqual(dz7, "token-dz7")
        self.assertNotEqual(news, dz7)

    def test_token_env_name_beats_per_page_var(self):
        with mock.patch.dict(
                "os.environ",
                {"FB_PAGE_TOKEN_NEWSDZ9": "token-named",
                 "FB_PAGE_ACCESS_TOKEN_61552757798044": "token-news"},
                clear=False):
            got = publisher.token_for_destination(
                {"name": "NewsDz9", "page_id": "61552757798044",
                 "token_env": "FB_PAGE_TOKEN_NEWSDZ9"})
        self.assertEqual(got, "token-named")

    def test_fallback_when_no_per_page_token(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            got = publisher.token_for_destination(
                {"name": "NewsDz9", "page_id": "61552757798044"},
                fallback="token-shared")
        self.assertEqual(got, "token-shared")

    def test_empty_when_nothing_set(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            got = publisher.token_for_destination(
                {"name": "NewsDz9", "page_id": "61552757798044"})
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
                    {"FB_PAGE_ACCESS_TOKEN_61552757798044": "token-news"},
                    clear=False):
                publisher.publish(
                    {"name": "NewsDz9", "page_id": "61552757798044"},
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
                    {"name": "NewsDz9", "page_id": "61552757798044"},
                    "caption", Path("x.mp4"), token="")
        finally:
            publisher.publish_page_cli = orig_cli
        self.assertEqual(calls["page_id"], "61552757798044")


if __name__ == "__main__":
    unittest.main()
