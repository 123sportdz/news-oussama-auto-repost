"""Config loading, validation and saving for NEWS OUSSAMA auto-repost.

The single source of truth is ``config.yaml`` at the repo root.
Page IDs are public Facebook identifiers, not secrets — they live
here on purpose. Real secrets (tokens, app secrets) live in ``.env``
and are never written to this file.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE / "config.yaml"

DEFAULTS = {
    "settings": {
        "check_every_minutes": 30,
        "max_posts_per_check": 3,
        "watermark": {"enabled": True, "position": "bottom-right",
                      "size_px": 194, "margin_px": 30},
        "caption": {"template": "{caption}", "max_chars": 1024,
                    "hashtags": []},
        "editor": {"crop_to_9x16": False, "max_duration_seconds": 0,
                   "loudnorm": False},
        "publish": {"mode": "draft"},
    }
}


def _deep_merge(base: dict, over: dict) -> dict:
    if not isinstance(over, dict):
        return dict(base)
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | str = CONFIG_PATH) -> dict:
    """Load config.yaml and fill in any missing settings with defaults."""
    path = Path(path)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        loaded = {}
    cfg = _deep_merge(DEFAULTS, loaded)
    if not isinstance(cfg.get("settings"), dict):
        cfg["settings"] = dict(DEFAULTS["settings"])
    if not isinstance(cfg["settings"].get("publish"), dict):
        cfg["settings"]["publish"] = dict(DEFAULTS["settings"]["publish"])
    # publish windows must be a list — a single string in YAML would
    # otherwise be iterated character by character and block all
    # publishing silently.
    windows = cfg.get("settings", {}).get("publish", {}).get("windows", [])
    if isinstance(windows, str):
        cfg["settings"]["publish"]["windows"] = [windows]
    return cfg


def save_config(cfg: dict, path: Path | str = CONFIG_PATH) -> None:
    path = Path(path)
    path.write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def enabled_sources(cfg: dict) -> list[dict]:
    return [s for s in cfg.get("sources", []) if s.get("enabled", True)]


def enabled_destinations(cfg: dict) -> list[dict]:
    return [d for d in cfg.get("destinations", []) if d.get("enabled", True)]


def validate_config(cfg: dict) -> list[str]:
    """Return a list of problems (empty = valid)."""
    problems: list[str] = []
    if not cfg.get("sources"):
        problems.append("no sources configured")
    for src in cfg.get("sources", []):
        if not src.get("url"):
            problems.append(f"source {src.get('name', '?')} has no url")
    if not cfg.get("destinations"):
        problems.append("no destinations configured")
    for dst in cfg.get("destinations", []):
        if not dst.get("url") and not dst.get("page_id"):
            problems.append(f"destination {dst.get('name', '?')} has no url/page_id")
        if dst.get("kind") != "profile" and not dst.get("page_id"):
            problems.append(
                f"destination {dst.get('name', '?')}: page_id missing — "
                "publish once via the browser, then post read returns owner_id"
            )
    settings = cfg.get("settings", {})
    for key, minimum in (("check_every_minutes", 1),
                         ("max_posts_per_check", 1)):
        try:
            value = int(settings.get(key, minimum))
        except (TypeError, ValueError):
            problems.append(f"{key} must be a number >= {minimum}")
            continue
        if value < minimum:
            problems.append(f"{key} must be >= {minimum}")
    windows = settings.get("publish", {}).get("windows", [])
    if isinstance(windows, str):
        problems.append("publish.windows must be a list, not a string")
    elif not isinstance(windows, list):
        problems.append("publish.windows must be a list")
    else:
        for w in windows:
            parts = str(w).split("-")
            if len(parts) != 2 or not all(
                    len(p) == 5 and p[2] == ":" for p in parts):
                problems.append(f"publish window {w!r} is not HH:MM-HH:MM")
    return problems


_DOTENV_LOADED = False
_DOTENV_MTIME_NS: int | None = None
_DOTENV_KEYS: set[str] = set()


def _parse_dotenv(path: Path) -> dict[str, str]:
    """KEY=VALUE lines from a .env file (comments and blanks skipped)."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"").strip("'")
        if key:
            values[key] = value
    return values


def _load_dotenv() -> None:
    """Read BASE/.env (KEY=VALUE lines) into os.environ as defaults.

    The README promises a token in .env works — before this, nothing
    ever read the file, so the Graph API token path was dead on local
    runs (only Docker's env_file worked).

    The file is re-read whenever its mtime changes: the dashboard
    Tokens page writes .env while the server is running, and a token
    pasted there must be picked up by the next publish without a
    restart. Keys that came from .env are updated on reload; keys the
    real environment already had are never overwritten, and keys
    removed from .env are dropped again.
    """
    global _DOTENV_LOADED, _DOTENV_MTIME_NS
    dotenv = BASE / ".env"
    try:
        mtime_ns = dotenv.stat().st_mtime_ns
    except OSError:
        mtime_ns = None
    if _DOTENV_LOADED and mtime_ns == _DOTENV_MTIME_NS:
        return
    _DOTENV_LOADED = True
    _DOTENV_MTIME_NS = mtime_ns
    if mtime_ns is None:
        return
    try:
        values = _parse_dotenv(dotenv)
    except OSError:
        return
    for key in list(_DOTENV_KEYS):
        if key not in values:
            os.environ.pop(key, None)
            _DOTENV_KEYS.discard(key)
    for key, value in values.items():
        if key not in os.environ or key in _DOTENV_KEYS:
            os.environ[key] = value
            _DOTENV_KEYS.add(key)


def reload_dotenv() -> None:
    """Force the next env() call to re-read BASE/.env (after a write)."""
    global _DOTENV_LOADED
    _DOTENV_LOADED = False
    _load_dotenv()


def env(key: str, default: str = "") -> str:
    """Read an optional secret from the environment (or .env)."""
    _load_dotenv()
    return os.environ.get(key, default)
