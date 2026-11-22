"""Post-publish stats: read likes / comments / views of published reels.

Two routes, Graph API first:
1. Graph API — needs the Page token of the destination (already in
   .env for publishing). Works on Windows, where facebook-cli is not
   installed. Likes/comments come from the video node, views from
   video_insights (total_video_views, lifetime).
2. facebook-cli fallback — ``facebook-cli post read`` (the VM route,
   and the profile route, which has no Graph token).

Engagement fields are not guaranteed to be present — whatever the
source returns is kept, and missing numbers simply stay empty.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import state as state_mod  # noqa: E402
from src.config import env  # noqa: E402
from src.downloader import FACEBOOK_CLI  # noqa: E402
from src.publisher import token_for_destination  # noqa: E402

STATS = BASE / "state" / "stats.json"

ENGAGEMENT_KEYS = ("like", "comment", "share", "view", "reaction", "play")
GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


def read_post_raw(url: str, facebook_cli: str = FACEBOOK_CLI) -> dict | None:
    """Raw first post dict from ``facebook-cli post read --url``."""
    cmd = [facebook_cli, "post", "read", "--url", url]
    try:
        result = subprocess.run(cmd, text=True, capture_output=True,
                                timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
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
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)) and any(
                        s in flat for s in ENGAGEMENT_KEYS):
                    # first (top-level) value wins — a nested key with
                    # the same name must not overwrite it
                    out.setdefault(key, value)
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
    vid = result.get("video_id")
    if vid:
        return f"https://www.facebook.com/reel/{vid}"
    # a bare post id is only a reel when the result says so (or says
    # nothing) — a photo post id guessed as a reel URL never resolves
    media = (result.get("media_type") or result.get("type") or "video")
    if str(media).lower() in ("video", "reel"):
        vid = result.get("id") or result.get("post_id")
        if vid:
            return f"https://www.facebook.com/reel/{vid}"
    return None


def _graph_get(path: str, params: dict, token: str,
               urlopen=None) -> dict | None:
    """One Graph GET, JSON-decoded; None on any failure (partial stats
    are better than no stats)."""
    urlopen = urlopen or urllib.request.urlopen
    params = {**params, "access_token": token}
    url = f"{GRAPH_BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    return payload


def video_id_from_result(result) -> str | None:
    """The Graph video id of a publish result (Graph returns {"id": ...})."""
    if not isinstance(result, dict):
        return None
    return (result.get("video_id") or result.get("id")
            or result.get("post_id")) or None


def read_post_graph(video_id: str, token: str,
                    urlopen=None) -> dict:
    """Engagement of one published Page video via the Graph API.

    Likes/comments from the video node, views from video_insights.
    Each call is independent — a failed views lookup keeps the
    likes/comments instead of dropping the whole row.
    """
    out: dict = {}
    node = _graph_get(
        str(video_id),
        {"fields": "likes.summary(true).limit(0),"
                   "comments.summary(true).limit(0)"},
        token, urlopen)
    if node:
        likes = ((node.get("likes") or {}).get("summary") or {}).get(
            "total_count")
        comments = ((node.get("comments") or {}).get("summary") or {}).get(
            "total_count")
        if isinstance(likes, (int, float)):
            out["likes"] = likes
        if isinstance(comments, (int, float)):
            out["comments"] = comments
    insights = _graph_get(
        f"{video_id}/video_insights",
        {"metric": "total_video_views", "period": "lifetime"},
        token, urlopen)
    if insights:
        values = (((insights.get("data") or [{}])[0]).get("values") or [])
        if values:
            views = values[-1].get("value")
            if isinstance(views, (int, float)):
                out["views"] = views
    return out


def refresh_stats_graph(cfg: dict, urlopen=None) -> dict:
    """Refresh stats via the Graph API for Page destinations with a
    token. Returns the full stats dict, also saved to state/stats.json.
    Destinations without a token (profile, missing token) are skipped
    — the CLI fallback in refresh_stats covers them.
    """
    published = state_mod.load_json(state_mod.PUBLISHED, {})
    stats = state_mod.load_json(STATS, {})
    shared = env("FB_PAGE_ACCESS_TOKEN")
    dests = {d.get("name"): d for d in cfg.get("destinations", [])}
    for pid, entry in published.items():
        for dest_name, result in (entry.get("destinations") or {}).items():
            dest = dests.get(dest_name)
            if not dest or dest.get("kind") == "profile":
                continue
            token = token_for_destination(dest, shared)
            video_id = video_id_from_result(result)
            if not token or not video_id:
                continue
            engagement = read_post_graph(video_id, token, urlopen)
            if not engagement:
                continue
            stats.setdefault(str(pid), {}).setdefault(
                "destinations", {})[dest_name] = {
                "url": f"https://www.facebook.com/reel/{video_id}",
                "engagement": engagement,
                "source": "graph",
                "refreshed_at": datetime.now().isoformat(timespec="seconds"),
            }
    state_mod.save_json(STATS, stats)
    return stats


def refresh_stats(cfg: dict, facebook_cli: str = FACEBOOK_CLI) -> dict:
    """Refresh stats for every published (post, destination) with a URL.

    Graph API first for Page destinations with a token (works on
    Windows, where facebook-cli is not installed); facebook-cli for
    the rest (profile, missing token). Returns the full stats dict,
    also saved to state/stats.json.
    """
    stats = refresh_stats_graph(cfg)
    published = state_mod.load_json(state_mod.PUBLISHED, {})
    for pid, entry in published.items():
        for dest, result in (entry.get("destinations") or {}).items():
            if (stats.get(str(pid), {}).get("destinations", {})
                    .get(dest, {}).get("source") == "graph"):
                continue  # already fresh from Graph
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
