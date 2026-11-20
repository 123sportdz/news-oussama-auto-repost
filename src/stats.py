"""Post-publish stats: read likes / comments / views of published reels.

Uses the same ``facebook-cli post read`` that already works for source
posts. Engagement fields are not guaranteed to be present — whatever
the CLI returns is kept, and missing numbers simply stay empty.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import state as state_mod  # noqa: E402
from src.downloader import FACEBOOK_CLI  # noqa: E402

STATS = BASE / "state" / "stats.json"

ENGAGEMENT_KEYS = ("like", "comment", "share", "view", "reaction", "play")


def read_post_raw(url: str, facebook_cli: str = FACEBOOK_CLI) -> dict | None:
    """Raw first post dict from ``facebook-cli post read --url``."""
    cmd = [facebook_cli, "post", "read", "--url", url]
    result = subprocess.run(cmd, text=True, capture_output=True)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    posts = data.get("posts") or []
    return posts[0] if posts else None


def extract_engagement(post: dict) -> dict:
    """Numeric engagement fields (likes/comments/shares/views...)."""
    out: dict = {}

    def walk(obj, prefix: str = "") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                flat = f"{prefix}{key}".lower()
                if isinstance(value, (int, float)) and any(
                        s in flat for s in ENGAGEMENT_KEYS):
                    out[key] = value
                elif isinstance(value, (dict, list)):
                    walk(value, f"{prefix}{key}.")
        elif isinstance(obj, list):
            for item in obj:
                walk(item, prefix)

    walk(post)
    return out


def stats_url(result) -> str | None:
    """Best URL to re-read a published post, from its publish result."""
    if not isinstance(result, dict):
        return None
    if result.get("url"):
        return result["url"]
    vid = result.get("id") or result.get("video_id") or result.get("post_id")
    if vid:
        return f"https://www.facebook.com/reel/{vid}"
    return None


def refresh_stats(cfg: dict, facebook_cli: str = FACEBOOK_CLI) -> dict:
    """Refresh stats for every published (post, destination) with a URL.

    Returns the full stats dict, also saved to state/stats.json.
    """
    published = state_mod.load_json(state_mod.PUBLISHED, {})
    stats = state_mod.load_json(STATS, {})
    for pid, entry in published.items():
        for dest, result in (entry.get("destinations") or {}).items():
            url = stats_url(result)
            if not url:
                continue
            raw = read_post_raw(url, facebook_cli)
            if raw is None:
                continue
            stats.setdefault(str(pid), {}).setdefault(
                "destinations", {})[dest] = {
                "url": url,
                "engagement": extract_engagement(raw),
                "refreshed_at": datetime.now().isoformat(timespec="seconds"),
            }
    state_mod.save_json(STATS, stats)
    return stats
