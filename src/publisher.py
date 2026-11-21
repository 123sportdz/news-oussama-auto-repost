"""Publish watermarked posts to Facebook Pages / profile.

Two routes, in order:
1. Graph API — needs a Page access token (``FB_PAGE_ACCESS_TOKEN``
   in .env). A long-lived Page token is the only way to publish
   unattended. Page tokens are PER PAGE: one token never covers two
   Pages, so ``token_for_destination`` prefers a per-page token
   (``FB_PAGE_ACCESS_TOKEN_<page_id>`` or the env var named in the
   destination's ``token_env``) and only falls back to the single
   shared ``FB_PAGE_ACCESS_TOKEN``.
2. facebook-cli fallback — ``facebook-cli pages posts create``.
   Each publish asks the user for approval (a card), so it is never
   fully unattended.

Both routes fail with a clear error when Professional Consent is
missing: that approval can only be given by the Page admin inside
Facebook. When that happens, publish from the browser instead —
switch into the Page, create a Reel, upload the watermarked file.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from src.config import env

CONSENT_ERROR = "PROFESSIONAL_CONSENT_REQUIRED"

BROWSER_INSTRUCTIONS = (
    "Professional Consent is missing for this Page. The Page admin must "
    "approve it inside Facebook first. Until then, publish from the "
    "browser: open the Page, switch into it, create a Reel, upload the "
    "watermarked file, paste the caption, set audience to Public."
)


class ConsentMissingError(RuntimeError):
    """Raised when Facebook refuses a Page write for missing consent."""


class PublishError(RuntimeError):
    """Raised when a publish attempt fails for another reason."""


def token_for_destination(destination: dict, fallback: str = "") -> str:
    """Access token for one Page destination.

    Order: (1) the env var named in the destination's ``token_env``
    (e.g. ``FB_PAGE_TOKEN_NEWSDZ9``); (2) ``FB_PAGE_ACCESS_TOKEN_<page_id>``;
    (3) the shared ``fallback`` (the single ``FB_PAGE_ACCESS_TOKEN``).
    Returns "" when nothing is set — the caller then uses facebook-cli.
    """
    name = destination.get("token_env")
    if name:
        token = env(str(name))
        if token:
            return token
    page_id = destination.get("page_id") or ""
    if page_id:
        token = env(f"FB_PAGE_ACCESS_TOKEN_{page_id}")
        if token:
            return token
    return fallback or ""


def publish_page_graph(page_id: str, text: str, video_path: Path | str,
                       token: str,
                       graph_version: str = "v21.0") -> dict:
    """Publish a video to a Page via the Graph API (video upload).

    Uses only the standard library so no extra dependency is needed.
    Returns the Graph response (contains the video/post id).
    """
    url = f"https://graph.facebook.com/{graph_version}/{page_id}/videos"
    boundary = "----news-oussama-boundary"
    video_path = Path(video_path)
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="access_token"\r\n\r\n'
        f"{token}\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="description"\r\n\r\n'
        f"{text}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="source"; filename="{video_path.name}"\r\n'
        "Content-Type: video/mp4\r\n\r\n"
    ).encode("utf-8") + video_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", "replace")
        if CONSENT_ERROR in payload or "professional" in payload.lower():
            raise ConsentMissingError(BROWSER_INSTRUCTIONS) from exc
        raise PublishError(f"Graph API publish failed ({exc.code}): {payload[:500]}") from exc


def publish_page_cli(page_id: str, text: str, video_path: Path | str,
                     facebook_cli: str = "/opt/hatch/bin/facebook-cli") -> dict:
    """Publish a video to a Page with facebook-cli (asks for approval)."""
    cmd = [facebook_cli, "pages", "posts", "create", "--page-id", page_id,
           "--text", text, "--privacy", "PUBLIC", "--file", str(video_path)]
    print("+", " ".join(cmd))
    try:
        result = subprocess.run(cmd, text=True, capture_output=True,
                                timeout=180)
    except subprocess.TimeoutExpired:
        raise PublishError("facebook-cli publish timed out")
    except (FileNotFoundError, OSError) as exc:
        raise PublishError(f"facebook-cli not available: {exc}")
    out = (result.stdout or "") + (result.stderr or "")
    if CONSENT_ERROR in out:
        raise ConsentMissingError(BROWSER_INSTRUCTIONS)
    if result.returncode != 0:
        raise PublishError(f"facebook-cli publish failed: {out[:500]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout}


def publish_profile_cli(text: str, video_path: Path | str,
                        facebook_cli: str = "/opt/hatch/bin/facebook-cli") -> dict:
    """Publish a video to the personal profile with facebook-cli."""
    cmd = [facebook_cli, "post", "create", "--message", text,
           "--file", str(video_path)]
    print("+", " ".join(cmd))
    try:
        result = subprocess.run(cmd, text=True, capture_output=True,
                                timeout=180)
    except subprocess.TimeoutExpired:
        raise PublishError("facebook-cli profile publish timed out")
    except (FileNotFoundError, OSError) as exc:
        raise PublishError(f"facebook-cli not available: {exc}")
    if result.returncode != 0:
        raise PublishError(
            f"facebook-cli profile publish failed: {(result.stdout + result.stderr)[:500]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout}


def publish(destination: dict, text: str, video_path: Path | str,
             token: str = "") -> dict:
    """Publish to one destination, picking Graph API first, CLI second.

    Returns the publish response. Raises ConsentMissingError or
    PublishError. Never publishes to a destination without a page_id.
    """
    if destination.get("kind") == "profile":
        return publish_profile_cli(text, video_path)
    page_id = destination.get("page_id") or ""
    if not page_id:
        raise PublishError(
            f"destination {destination.get('name')}: page_id missing — "
            "publish once via the browser, then post read returns owner_id")
    page_token = token_for_destination(destination, token)
    if page_token:
        return publish_page_graph(page_id, text, video_path, page_token)
    return publish_page_cli(page_id, text, video_path)
