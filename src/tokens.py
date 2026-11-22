"""Page-token setup for the dashboard.

The .env file with the two Page tokens kept failing to reach the
user's machine (the file download was refused twice), so the dashboard
now takes the tokens directly: paste each Page token, it is validated
against the Graph API and written to the local .env (gitignored).

Tokens are NEVER logged, never rendered in full (masked: first 4 +
"…" + last 4 chars), and never leave the machine except in the
validation calls straight to graph.facebook.com. Validation needs no
App Secret: a token can debug itself via /debug_token, and /me with a
Page token returns the Page itself.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import state as state_mod  # noqa: E402
from src.config import reload_dotenv  # noqa: E402

GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
VALIDATE_TIMEOUT = 10


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def token_fingerprint(token: str) -> str:
    """First 12 hex chars of SHA-256 — ties a stored validation to the
    exact token that was checked, without storing anything reversible."""
    return hashlib.sha256((token or "").strip().encode("utf-8")).hexdigest()[:12]


def mask_token(token: str) -> str:
    """First 4 + "…" + last 4 chars; short tokens show only "****".

    Nothing that could let someone reconstruct the token is ever
    displayed or logged.
    """
    token = (token or "").strip()
    if len(token) <= 8:
        return "****" if token else ""
    return f"{token[:4]}…{token[-4:]}"


def env_key_for_page(page_id: str) -> str:
    return f"FB_PAGE_ACCESS_TOKEN_{page_id}"


def _parse_env_file(path: Path) -> tuple[list[str], dict[str, str]]:
    """(.env lines, {KEY: value}) — comments and blank lines preserved."""
    lines = (path.read_text(encoding="utf-8").splitlines()
             if path.exists() else [])
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip().strip("\"").strip("'")
    return lines, values


def read_env_tokens() -> dict[str, str]:
    """Per-page + shared token values currently in .env (callers must mask)."""
    _, values = _parse_env_file(BASE / ".env")
    return {k: v for k, v in values.items()
            if k == "FB_PAGE_ACCESS_TOKEN" or
            k.startswith("FB_PAGE_ACCESS_TOKEN_")}


def write_env_tokens(updates: dict[str, str],
                     remove: tuple[str, ...] = ()) -> None:
    """Merge token keys into .env (atomic write, other lines untouched).

    ``updates`` maps env key -> token value; ``remove`` lists keys to
    delete. The file is written with 0o600 permissions where the OS
    supports it, and the running process re-reads it immediately so a
    token pasted in the dashboard works for the next publish without
    a restart. Never prints or logs any token value.
    """
    dotenv = BASE / ".env"
    lines, values = _parse_env_file(dotenv)
    values.update(updates)
    for key in remove:
        values.pop(key, None)
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates or key in remove:
                seen.add(key)
                if key in updates:
                    out.append(f"{key}={updates[key]}")
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    text = "\n".join(out) + ("\n" if out else "")
    dotenv.parent.mkdir(parents=True, exist_ok=True)
    tmp = dotenv.with_suffix(".env.tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, dotenv)
    reload_dotenv()


def _graph_get(path: str, params: dict, urlopen) -> dict:
    """One Graph GET, JSON-decoded. Raises ValueError on Graph errors."""
    query = urllib.parse.urlencode(params)
    url = f"{GRAPH_BASE}/{path}?{query}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urlopen(req, timeout=VALIDATE_TIMEOUT) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001 — fall back to the status code
            payload = {}
        message = ((payload.get("error") or {}).get("message")
                   or f"HTTP {exc.code}")
        raise ValueError(f"Graph: {message}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"Graph unreachable: {exc}") from exc
    if isinstance(payload, dict) and payload.get("error"):
        raise ValueError(f"Graph: {payload['error'].get('message', 'error')}")
    return payload


def validate_token(token: str, page_id: str,
                   urlopen=None) -> dict:
    """Check a pasted Page token against the Graph API.

    Two calls, no App Secret needed: /debug_token with the token
    itself as the access token (a token can debug itself), then /me
    with the token (a Page token returns the Page). Returns a dict
    with ok/page_name/scopes/expires_at/error — never the token.
    """
    urlopen = urlopen or urllib.request.urlopen
    token = (token or "").strip()
    if not token:
        return {"ok": False, "page_id": page_id, "page_name": "",
                "type": "", "scopes": [], "expires_at": None,
                "error": "التوكن فارغ"}
    try:
        debug = _graph_get(
            "debug_token",
            {"input_token": token, "access_token": token}, urlopen)
        data = debug.get("data") or {}
        me = _graph_get("me", {"fields": "id,name",
                               "access_token": token}, urlopen)
    except ValueError as exc:
        return {"ok": False, "page_id": page_id, "page_name": "",
                "type": "", "scopes": [], "expires_at": None,
                "error": str(exc)}
    scopes = data.get("scopes") or []
    problems: list[str] = []
    if not data.get("is_valid"):
        problems.append("التوكن غير صالح (is_valid = false)")
    if (data.get("type") or "") != "PAGE":
        problems.append(
            f"نوع التوكن {data.get('type') or '؟'} — لازم PAGE، موش USER")
    if "pages_manage_posts" not in scopes:
        problems.append("التوكن ما فيهش صلاحية pages_manage_posts")
    if str(me.get("id") or "") != str(page_id):
        problems.append(
            f"التوكن تاع صفحة أخرى (id {me.get('id') or '؟'}) — "
            f"لازم {page_id}")
    return {"ok": not problems,
            "page_id": page_id,
            "page_name": str(me.get("name") or ""),
            "type": str(data.get("type") or ""),
            "scopes": scopes,
            "expires_at": data.get("expires_at"),
            "error": "؛ ".join(problems) if problems else ""}


def load_token_status() -> dict:
    # Path computed at call time (not import time) so tests can point
    # BASE at a temp dir.
    return state_mod.load_json(BASE / "state" / "token_status.json", {})


def save_token_status(status: dict) -> None:
    state_mod.save_json(BASE / "state" / "token_status.json", status)


def validate_stored_tokens(cfg: dict, urlopen=None) -> list[dict]:
    """Re-validate every stored Page token against the Graph API.

    A token that was fine can die later (the user changes their
    Facebook password, removes the app, or loses their Page role) —
    this is how the project finds out before the next publish fails.
    Updates state/token_status.json in the same shape the Tokens page
    writes, and returns one row per Page destination: name / page_id /
    status ("ok" / "invalid" / "missing") / page_name / error /
    checked_at. Destinations with no token at all are reported as
    "missing" and never alert — that is a setup state, not a failure.
    """
    stored = load_token_status()
    tokens = read_env_tokens()
    rows: list[dict] = []
    for dest in cfg.get("destinations", []):
        if dest.get("kind") == "profile":
            continue
        page_id = str(dest.get("page_id") or "")
        name = dest.get("name") or page_id
        key = env_key_for_page(page_id)
        value = tokens.get(key, "")
        if not value:
            rows.append({"name": name, "page_id": page_id,
                         "status": "missing", "page_name": "",
                         "error": "ما كاين حتى توكن — الصقو في صفحة التوكنات",
                         "checked_at": ""})
            continue
        result = validate_token(value, page_id, urlopen=urlopen)
        checked_at = now_iso()
        stored[page_id] = {
            **result,
            "token_fingerprint": token_fingerprint(value),
            "checked_at": checked_at,
        }
        rows.append({"name": name, "page_id": page_id,
                     "status": "ok" if result["ok"] else "invalid",
                     "page_name": result.get("page_name", ""),
                     "error": result.get("error", ""),
                     "checked_at": checked_at})
    save_token_status(stored)
    return rows


def destination_token_status(cfg: dict) -> list[dict]:
    """One status row per Page destination (profile needs no token).

    status: "missing" (no token in .env) / "ok" (validated against
    this Page) / "invalid" (a validation failed) / "configured"
    (token saved, not validated yet). Tokens are only ever masked.
    """
    stored = load_token_status()
    tokens = read_env_tokens()
    rows = []
    for dest in cfg.get("destinations", []):
        if dest.get("kind") == "profile":
            continue
        page_id = str(dest.get("page_id") or "")
        key = env_key_for_page(page_id)
        value = tokens.get(key, "")
        entry = stored.get(page_id) or {}
        same_token = (entry.get("token_fingerprint") ==
                      token_fingerprint(value)) if value else False
        if not value:
            status = "missing"
        elif same_token and entry.get("ok"):
            status = "ok"
        elif same_token and entry.get("ok") is False:
            status = "invalid"
        else:
            # Token changed (or never validated): the old check no
            # longer applies — it must be validated again.
            status = "configured"
        rows.append({
            "name": dest.get("name") or page_id,
            "page_id": page_id,
            "env_key": key,
            "present": bool(value),
            "masked": mask_token(value),
            "status": status,
            "page_name": entry.get("page_name", ""),
            "checked_at": entry.get("checked_at", ""),
            "error": entry.get("error", ""),
        })
    return rows
