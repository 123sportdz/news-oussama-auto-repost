"""Download posts: read metadata with facebook-cli, fetch media with yt-dlp.

Facebook gives no public feed/API for pages you do not manage, so
discovery is a post URL (pasted, or found with a browser check).
``post read`` returns caption/date/owner but no downloadable media
URL — the actual file comes from yt-dlp.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

FACEBOOK_CLI = "/opt/hatch/bin/facebook-cli"


def _ytdlp() -> str:
    """yt-dlp binary: PATH first, then ~/.local/bin.

    A system-wide pip install does NOT survive a VM rebuild — yt-dlp
    vanished that way on 2026-11-20 and every download failed until it
    was reinstalled with `pip install --user`. ~/.local survives, so
    check it as a fallback whatever PATH the cron runs with.
    """
    found = shutil.which("yt-dlp")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "yt-dlp"
    return str(local) if local.exists() else "yt-dlp"


def post_id_from_url(url: str) -> str | None:
    """The numeric id embedded in a Facebook post/reel URL, if any."""
    match = re.search(r"/(?:reel/|watch/\?v=|videos/|video\.php\?v=)(\d{6,})",
                      url)
    return match.group(1) if match else None


def post_info(url: str, facebook_cli: str = FACEBOOK_CLI) -> dict:
    """Read a post/reel URL and return its metadata.

    Returns: post_id, caption, owner, created (local time), url, media_type.
    Tries facebook-cli first; when it cannot see the post (it returns
    POST_NOT_FOUND for fresh reels even though they are public — verified
    2026-11-20), falls back to yt-dlp metadata, which reads the same
    public post fine. Raises SystemExit only when both fail.
    """
    try:
        return _post_info_cli(url, facebook_cli)
    except SystemExit as exc:
        print(f"post read via facebook-cli failed ({exc}); "
              f"trying yt-dlp metadata …")
        return video_info(url)


def _post_info_cli(url: str, facebook_cli: str = FACEBOOK_CLI) -> dict:
    cmd = [facebook_cli, "post", "read", "--url", url]
    print("+", " ".join(cmd))
    try:
        result = subprocess.run(cmd, text=True, capture_output=True,
                                timeout=60)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"post read timed out for {url}")
    except (FileNotFoundError, OSError) as exc:
        # facebook-cli is not installed on this machine (Windows, Docker)
        # — fall through to the yt-dlp fallback instead of crashing.
        raise SystemExit(f"facebook-cli not available: {exc}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"post read failed for {url}: {result.stdout[:500]}")
    posts = data.get("posts") or []
    if not posts:
        raise SystemExit(f"no post found for {url}: {result.stdout[:500]}")
    p = posts[0]
    pid = p.get("post_id")
    if pid is None:
        raise SystemExit(f"post read returned no post_id for {url}")
    return {
        "post_id": str(pid),
        "caption": p.get("post_caption") or "",
        "owner": p.get("owner_name"),
        "created": (p.get("post_created_at") or {}).get("user_local"),
        "url": p.get("url") or url,
        "media_type": p.get("media_type"),
    }


_TITLE_PREFIX_RE = re.compile(r"^[\d.,KM]+ views · [\d.,KM]+ reactions \| ")


def _clean_title(title: str) -> str:
    """Strip yt-dlp's '3.9K views · 247 reactions | <caption> | <page>'."""
    title = _TITLE_PREFIX_RE.sub("", title or "")
    return title.rsplit(" | ", 1)[0] if " | " in title else title


def video_info(url: str, ytdlp: str | None = None) -> dict:
    """Post metadata from yt-dlp --dump-json (public posts, no login)."""
    ytdlp = ytdlp or _ytdlp()
    cmd = [ytdlp, "--dump-json", "--no-download", url]
    print("+", " ".join(cmd))
    try:
        result = subprocess.run(cmd, text=True, capture_output=True,
                                timeout=90)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"yt-dlp metadata timed out for {url}")
    except (FileNotFoundError, OSError) as exc:
        raise SystemExit(f"yt-dlp not available: {exc}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"yt-dlp metadata failed for {url}: "
                         f"{(result.stdout + result.stderr)[:500]}")
    match = post_id_from_url(url)
    pid = match if match else data.get("id")
    if pid is None:
        raise SystemExit(f"yt-dlp metadata returned no id for {url}")
    caption = (data.get("description") or "").strip() or \
        _clean_title(data.get("title") or "")
    ext = (data.get("ext") or "").lower()
    return {
        "post_id": str(pid),
        "caption": caption,
        "owner": (data.get("uploader") or "").strip() or None,
        "created": data.get("upload_date"),
        "url": url,
        "media_type": "photo" if ext in ("jpg", "jpeg", "png", "webp")
                    else "video",
    }


def download_video(url: str, out_path: Path | str) -> Path:
    """Download a reel/video with yt-dlp. Returns the output path."""
    out_path = Path(out_path)
    cmd = [_ytdlp(), "--no-playlist", "-o", str(out_path), url]
    print("+", " ".join(cmd))
    try:
        result = subprocess.run(cmd, text=True, capture_output=True,
                                timeout=300)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"download timed out for {url}")
    except (FileNotFoundError, OSError) as exc:
        raise SystemExit(f"yt-dlp not available: {exc}")
    if result.returncode != 0 or not out_path.exists():
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        raise SystemExit(f"download failed for {url}")
    return out_path
