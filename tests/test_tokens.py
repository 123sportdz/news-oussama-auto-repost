"""Tests for the dashboard Tokens page (src/tokens.py).

Tokens are pasted in the dashboard, validated against the Graph API
and written to the local .env — the file download kept failing, so
this is the structural fix. Full token values must never be logged
or rendered: tests assert masking and that error messages never
contain the token.
"""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from src import config as config_mod
from src import dashboard as dashboard_mod
from src import tokens as tokens_mod

FAKE_TOKEN_NEWS = "EAANewsTokenValue1234567890abcdef"
FAKE_TOKEN_DZ7 = "EAADz7TokenValue0987654321fedcba"
NEWS_PAGE = "147624121772177"
DZ7_PAGE = "107469321989814"

_TOKEN_KEYS = [f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}",
               f"FB_PAGE_ACCESS_TOKEN_{DZ7_PAGE}",
               "FB_PAGE_ACCESS_TOKEN"]


def _snapshot_env() -> dict:
    return {k: os.environ.get(k) for k in _TOKEN_KEYS}


def _restore_env(snapshot: dict) -> None:
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _isolate_dotenv(test):
    """Point config/tokens BASE at a temp dir with a fresh dotenv state."""
    test.tmp = tempfile.TemporaryDirectory()
    test.base = Path(test.tmp.name)
    test._orig_config_base = config_mod.BASE
    test._orig_tokens_base = tokens_mod.BASE
    test._orig_loaded = config_mod._DOTENV_LOADED
    test._orig_mtime = config_mod._DOTENV_MTIME_NS
    test._orig_keys = set(config_mod._DOTENV_KEYS)
    test._env_snapshot = _snapshot_env()
    for key in _TOKEN_KEYS:
        os.environ.pop(key, None)
    config_mod.BASE = test.base
    tokens_mod.BASE = test.base
    config_mod._DOTENV_LOADED = False
    config_mod._DOTENV_MTIME_NS = None
    config_mod._DOTENV_KEYS = set()


def _restore_dotenv(test):
    config_mod.BASE = test._orig_config_base
    tokens_mod.BASE = test._orig_tokens_base
    config_mod._DOTENV_LOADED = test._orig_loaded
    config_mod._DOTENV_MTIME_NS = test._orig_mtime
    config_mod._DOTENV_KEYS = test._orig_keys
    _restore_env(test._env_snapshot)
    test.tmp.cleanup()


class FakeResponse:
    """Minimal urlopen response: context manager with .read()."""

    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make_urlopen(debug: dict, me: dict, error=None):
    """Fake urlopen dispatching on the Graph path; error raises it."""
    def fake(req, timeout=None):
        if error is not None:
            raise error
        url = req.full_url
        if "debug_token" in url:
            return FakeResponse(debug)
        if "/me?" in url:
            return FakeResponse(me)
        raise AssertionError(f"unexpected Graph URL: {url}")
    return fake


class MaskTokenTest(unittest.TestCase):
    def test_long_token_is_masked(self):
        masked = tokens_mod.mask_token(FAKE_TOKEN_NEWS)
        self.assertEqual(masked, "EAAN…cdef")
        self.assertNotIn(FAKE_TOKEN_NEWS[4:-4], masked)

    def test_short_token_shows_nothing(self):
        self.assertEqual(tokens_mod.mask_token("abc"), "****")
        self.assertEqual(tokens_mod.mask_token(""), "")


class EnvFileTest(unittest.TestCase):
    def setUp(self):
        _isolate_dotenv(self)

    def tearDown(self):
        _restore_dotenv(self)

    def test_write_creates_env_and_read_back(self):
        tokens_mod.write_env_tokens(
            {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": FAKE_TOKEN_NEWS})
        env_file = self.base / ".env"
        self.assertTrue(env_file.is_file())
        self.assertEqual(
            tokens_mod.read_env_tokens()[f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}"],
            FAKE_TOKEN_NEWS)

    def test_write_preserves_other_lines_and_updates(self):
        env_file = self.base / ".env"
        env_file.write_text(
            "# comment\nDASHBOARD_PORT=8080\n"
            f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}=old-value\n",
            encoding="utf-8")
        tokens_mod.write_env_tokens(
            {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": FAKE_TOKEN_NEWS,
             f"FB_PAGE_ACCESS_TOKEN_{DZ7_PAGE}": FAKE_TOKEN_DZ7})
        text = env_file.read_text(encoding="utf-8")
        self.assertIn("# comment", text)
        self.assertIn("DASHBOARD_PORT=8080", text)
        self.assertIn(FAKE_TOKEN_NEWS, text)
        self.assertNotIn("old-value", text)

    def test_write_removes_key(self):
        tokens_mod.write_env_tokens(
            {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": FAKE_TOKEN_NEWS})
        tokens_mod.write_env_tokens(
            {}, remove=(f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}",))
        self.assertEqual(tokens_mod.read_env_tokens(), {})

    def test_env_reload_picks_up_tokens_written_while_running(self):
        # The dashboard process started before .env existed; a token
        # pasted in the Tokens page must work without a restart.
        self.assertEqual(
            config_mod.env(f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}"), "")
        tokens_mod.write_env_tokens(
            {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": FAKE_TOKEN_NEWS})
        self.assertEqual(
            config_mod.env(f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}"),
            FAKE_TOKEN_NEWS)

    def test_env_reload_picks_up_changed_value(self):
        tokens_mod.write_env_tokens(
            {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": FAKE_TOKEN_NEWS})
        self.assertEqual(
            config_mod.env(f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}"),
            FAKE_TOKEN_NEWS)
        env_file = self.base / ".env"
        env_file.write_text(
            f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}=rotated-token-value\n",
            encoding="utf-8")
        os.utime(env_file, ns=(10**18, 10**18))  # force a new mtime
        self.assertEqual(
            config_mod.env(f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}"),
            "rotated-token-value")

    def test_real_environment_beats_dotenv(self):
        tokens_mod.write_env_tokens(
            {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": FAKE_TOKEN_NEWS})
        with mock.patch.dict(
                "os.environ",
                {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": "from-real-env"},
                clear=False):
            self.assertEqual(
                config_mod.env(f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}"),
                "from-real-env")


class ValidateTokenTest(unittest.TestCase):
    def _valid(self, page_id=NEWS_PAGE, name="News Dz"):
        debug = {"data": {"is_valid": True, "type": "PAGE",
                          "scopes": ["pages_show_list",
                                     "pages_read_engagement",
                                     "pages_manage_posts"],
                          "expires_at": 0}}
        me = {"id": page_id, "name": name}
        return make_urlopen(debug, me)

    def test_valid_page_token(self):
        result = tokens_mod.validate_token(
            FAKE_TOKEN_NEWS, NEWS_PAGE, urlopen=self._valid())
        self.assertTrue(result["ok"])
        self.assertEqual(result["page_name"], "News Dz")
        self.assertIn("pages_manage_posts", result["scopes"])
        self.assertEqual(result["type"], "PAGE")

    def test_token_for_another_page_is_rejected(self):
        result = tokens_mod.validate_token(
            FAKE_TOKEN_NEWS, DZ7_PAGE, urlopen=self._valid())
        self.assertFalse(result["ok"])
        self.assertIn(DZ7_PAGE, result["error"])
        self.assertNotIn(FAKE_TOKEN_NEWS, result["error"])

    def test_missing_publish_scope_is_rejected(self):
        debug = {"data": {"is_valid": True, "type": "PAGE",
                          "scopes": ["pages_show_list"],
                          "expires_at": 0}}
        result = tokens_mod.validate_token(
            FAKE_TOKEN_NEWS, NEWS_PAGE,
            urlopen=make_urlopen(debug, {"id": NEWS_PAGE, "name": "News Dz"}))
        self.assertFalse(result["ok"])
        self.assertIn("pages_manage_posts", result["error"])

    def test_user_token_is_rejected(self):
        debug = {"data": {"is_valid": True, "type": "USER",
                          "scopes": ["pages_manage_posts"],
                          "expires_at": 0}}
        result = tokens_mod.validate_token(
            FAKE_TOKEN_NEWS, NEWS_PAGE,
            urlopen=make_urlopen(debug, {"id": NEWS_PAGE, "name": "News Dz"}))
        self.assertFalse(result["ok"])
        self.assertIn("USER", result["error"])

    def test_invalid_token(self):
        debug = {"data": {"is_valid": False, "type": "PAGE",
                          "scopes": [], "expires_at": 0}}
        result = tokens_mod.validate_token(
            FAKE_TOKEN_NEWS, NEWS_PAGE,
            urlopen=make_urlopen(debug, {"id": NEWS_PAGE, "name": "News Dz"}))
        self.assertFalse(result["ok"])

    def test_graph_http_error_never_leaks_token(self):
        payload = io.BytesIO(
            b'{"error": {"message": "Invalid OAuth access token"}}')
        error = urllib.error.HTTPError(
            "https://graph.facebook.com/v21.0/debug_token", 400,
            "Bad Request", {}, payload)
        result = tokens_mod.validate_token(
            FAKE_TOKEN_NEWS, NEWS_PAGE, urlopen=make_urlopen({}, {}, error))
        self.assertFalse(result["ok"])
        self.assertIn("Invalid OAuth", result["error"])
        self.assertNotIn(FAKE_TOKEN_NEWS, result["error"])

    def test_network_failure_is_a_clean_error(self):
        result = tokens_mod.validate_token(
            FAKE_TOKEN_NEWS, NEWS_PAGE,
            urlopen=make_urlopen(
                {}, {}, urllib.error.URLError("no network")))
        self.assertFalse(result["ok"])
        self.assertIn("unreachable", result["error"])

    def test_empty_token(self):
        result = tokens_mod.validate_token("", NEWS_PAGE)
        self.assertFalse(result["ok"])


class TokenStatusTest(unittest.TestCase):
    def setUp(self):
        _isolate_dotenv(self)
        self.cfg = {"destinations": [
            {"name": "NewsDz9", "page_id": NEWS_PAGE},
            {"name": "aljazaer07", "page_id": DZ7_PAGE},
            {"name": "Oussama — profile", "kind": "profile"},
        ]}

    def tearDown(self):
        _restore_dotenv(self)

    def _rows(self):
        return {r["name"]: r
                for r in tokens_mod.destination_token_status(self.cfg)}

    def test_missing_then_configured_then_ok(self):
        rows = self._rows()
        self.assertEqual(rows["NewsDz9"]["status"], "missing")
        self.assertEqual(rows["aljazaer07"]["status"], "missing")
        self.assertNotIn("Oussama — profile", rows)  # profile needs none
        tokens_mod.write_env_tokens(
            {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": FAKE_TOKEN_NEWS})
        rows = self._rows()
        self.assertEqual(rows["NewsDz9"]["status"], "configured")
        self.assertEqual(rows["NewsDz9"]["masked"], "EAAN…cdef")
        tokens_mod.save_token_status({
            NEWS_PAGE: {"ok": True, "page_name": "News Dz",
                        "token_fingerprint":
                            tokens_mod.token_fingerprint(FAKE_TOKEN_NEWS),
                        "checked_at": "2026-11-21T00:00:00"}})
        rows = self._rows()
        self.assertEqual(rows["NewsDz9"]["status"], "ok")
        self.assertEqual(rows["NewsDz9"]["page_name"], "News Dz")

    def test_new_token_after_failed_check_is_configured_not_invalid(self):
        tokens_mod.write_env_tokens(
            {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": "bad-token-value"})
        tokens_mod.save_token_status({
            NEWS_PAGE: {"ok": False, "error": "التوكن غير صالح",
                        "token_fingerprint":
                            tokens_mod.token_fingerprint("bad-token-value"),
                        "checked_at": "2026-11-21T00:00:00"}})
        self.assertEqual(self._rows()["NewsDz9"]["status"], "invalid")
        tokens_mod.write_env_tokens(
            {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": FAKE_TOKEN_NEWS})
        # The old "invalid" verdict was for a different token.
        self.assertEqual(self._rows()["NewsDz9"]["status"], "configured")


class ValidateStoredTokensTest(unittest.TestCase):
    """Daily re-validation: a token can die after it was pasted."""

    def setUp(self):
        _isolate_dotenv(self)
        self.cfg = {"destinations": [
            {"name": "NewsDz9", "page_id": NEWS_PAGE},
            {"name": "aljazaer07", "page_id": DZ7_PAGE},
            {"name": "Oussama — profile", "kind": "profile"},
        ]}

    def tearDown(self):
        _restore_dotenv(self)

    def _valid_urlopen(self):
        debug = {"data": {"is_valid": True, "type": "PAGE",
                          "scopes": ["pages_manage_posts",
                                     "pages_show_list"],
                          "expires_at": 0}}
        return make_urlopen(debug, {"id": NEWS_PAGE, "name": "News Dz"})

    def test_missing_token_reported_missing_not_invalid(self):
        rows = tokens_mod.validate_stored_tokens(self.cfg)
        by_name = {r["name"]: r for r in rows}
        self.assertEqual(by_name["NewsDz9"]["status"], "missing")
        self.assertEqual(by_name["aljazaer07"]["status"], "missing")
        self.assertNotIn("Oussama — profile", by_name)

    def test_stored_token_revalidated_and_status_saved(self):
        tokens_mod.write_env_tokens(
            {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": FAKE_TOKEN_NEWS})
        rows = tokens_mod.validate_stored_tokens(
            self.cfg, urlopen=self._valid_urlopen())
        by_name = {r["name"]: r for r in rows}
        self.assertEqual(by_name["NewsDz9"]["status"], "ok")
        self.assertEqual(by_name["NewsDz9"]["page_name"], "News Dz")
        self.assertEqual(by_name["aljazaer07"]["status"], "missing")
        stored = tokens_mod.load_token_status()
        self.assertTrue(stored[NEWS_PAGE]["ok"])
        self.assertEqual(stored[NEWS_PAGE]["page_name"], "News Dz")

    def test_dead_token_reported_invalid(self):
        tokens_mod.write_env_tokens(
            {f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}": FAKE_TOKEN_NEWS})
        debug = {"data": {"is_valid": False, "type": "PAGE",
                          "scopes": [], "expires_at": 0}}
        rows = tokens_mod.validate_stored_tokens(
            self.cfg,
            urlopen=make_urlopen(debug, {"id": NEWS_PAGE, "name": "News Dz"}))
        by_name = {r["name"]: r for r in rows}
        self.assertEqual(by_name["NewsDz9"]["status"], "invalid")
        self.assertIn("غير صالح", by_name["NewsDz9"]["error"])


class DashboardSaveTokensTest(unittest.TestCase):
    def setUp(self):
        _isolate_dotenv(self)
        self.cfg = {"destinations": [
            {"name": "NewsDz9", "page_id": NEWS_PAGE},
            {"name": "aljazaer07", "page_id": DZ7_PAGE},
        ]}

    def tearDown(self):
        _restore_dotenv(self)

    def test_valid_token_is_saved_invalid_is_not(self):
        def fake_validate(token, page_id, urlopen=None):
            if token == FAKE_TOKEN_NEWS:
                return {"ok": True, "page_id": page_id,
                        "page_name": "News Dz", "type": "PAGE",
                        "scopes": ["pages_manage_posts"], "expires_at": 0,
                        "error": ""}
            return {"ok": False, "page_id": page_id, "page_name": "",
                    "type": "", "scopes": [], "expires_at": None,
                    "error": "التوكن غير صالح"}

        form = {f"token_{NEWS_PAGE}": [FAKE_TOKEN_NEWS],
                f"token_{DZ7_PAGE}": ["bad-token-value"]}
        with mock.patch.object(tokens_mod, "validate_token", fake_validate):
            messages, all_ok = dashboard_mod._save_tokens(self.cfg, form)
        self.assertFalse(all_ok)
        joined = " | ".join(messages)
        self.assertIn("NewsDz9", joined)
        self.assertIn("aljazaer07", joined)
        tokens = tokens_mod.read_env_tokens()
        self.assertEqual(
            tokens[f"FB_PAGE_ACCESS_TOKEN_{NEWS_PAGE}"], FAKE_TOKEN_NEWS)
        self.assertNotIn(f"FB_PAGE_ACCESS_TOKEN_{DZ7_PAGE}", tokens)
        # The rejected token must not appear anywhere in .env.
        self.assertNotIn(
            "bad-token-value", (self.base / ".env").read_text())

    def test_tokens_page_renders_masked_only(self):
        page = dashboard_mod.tokens_page()
        self.assertIn("توكنات الصفحات", page)
        self.assertIn(f"token_{NEWS_PAGE}", page)
        self.assertIn(f"token_{DZ7_PAGE}", page)
        self.assertNotIn(FAKE_TOKEN_NEWS, page)


if __name__ == "__main__":
    unittest.main()
