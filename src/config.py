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
                   "loudnorm": False, "cover_frame_seconds": 3.0},
        "publish": {"mode": "draft"},
    }
}


def _deep_merge(base: dict, over: dict) -> dict:
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
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = _deep_merge(DEFAULTS, cfg)
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
    if int(settings.get("check_every_minutes", 30)) < 1:
        problems.append("check_every_minutes must be >= 1")
    if int(settings.get("max_posts_per_check", 3)) < 1:
        problems.append("max_posts_per_check must be >= 1")
    return problems


def env(key: str, default: str = "") -> str:
    """Read an optional secret from the environment (or .env via shell)."""
    return os.environ.get(key, default)
