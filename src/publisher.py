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

# Resumable upload: files over this size go through the
# start/transfer/finish flow instead of one big POST, so a slow
# connection can still finish a 70 MB reel — one chunk at a time,
# each with its own timeout, following the server's offsets.
RESUMABLE_MIN_SIZE = 25 * 1024 * 1024
CHUNK_SIZE = 10 * 1024 * 1024
_BOUNDARY = "----news-oussama-boundary"

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


class AuthPublishError(PublishError):
    """401/403 from Graph: bad/expired token or missing permission.

    A setup problem, not a bad video — never counts toward the
    publish give-up cap (see monitor.record_publish_failure)."""


class TransientPublishError(PublishError):
    """5xx or network failure: retry next cycle — never counts toward
    the publish give-up cap."""


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


def _multipart_body(fields, file_field=None, filename=None,
                    file_bytes=None, file_content_type="video/mp4"):
    """One multipart/form-data body. ``fields`` is a list of
    (name, value) in order; the file part, if any, comes last."""
    parts = []
    for name, value in fields:
        parts.append(
            f"--{_BOUNDARY}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        )
    head = "".join(parts).encode("utf-8")
    if file_field is None:
        return head + f"--{_BOUNDARY}--\r\n".encode()
    file_head = (
        f"--{_BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\n'
        f"Content-Type: {file_content_type}\r\n\r\n"
    ).encode("utf-8")
    return head + file_head + (file_bytes or b"") + \
        f"\r\n--{_BOUNDARY}--\r\n".encode()


def _post_graph(url, data, headers, timeout):
    """One POST to graph.facebook.com; returns the parsed JSON.

    Consent problems become ConsentMissingError, anything else
    becomes PublishError carrying the HTTP status.
    """
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", "replace")
        if CONSENT_ERROR in payload or "professional" in payload.lower():
            raise ConsentMissingError(BROWSER_INSTRUCTIONS) from exc
        if exc.code in (401, 403):
            raise AuthPublishError(
                f"Graph API publish failed ({exc.code}): {payload[:500]}"
            ) from exc
        if exc.code >= 500:
            raise TransientPublishError(
                f"Graph API publish failed ({exc.code}): {payload[:500]}"
            ) from exc
        raise PublishError(
            f"Graph API publish failed ({exc.code}): {payload[:500]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise TransientPublishError(
            f"Graph API publish failed (network): {exc}") from exc


def _post_graph_form(url, params, timeout):
    """POST urlencoded fields (start/finish phases)."""
    data = urllib.parse.urlencode(params).encode("utf-8")
    return _post_graph(
        url, data,
        {"Content-Type": "application/x-www-form-urlencoded"},
        timeout)


def publish_page_graph(page_id: str, text: str, video_path: Path | str,
                       token: str,
                       graph_version: str = "v21.0",
                       resumable_min_size: int = RESUMABLE_MIN_SIZE,
                       chunk_size: int = CHUNK_SIZE) -> dict:
    """Publish a video to a Page via the Graph API (video upload).

    Uses only the standard library so no extra dependency is needed.
    Files over ``resumable_min_size`` go through the resumable
    start/transfer/finish flow; smaller ones use a single POST.
    Returns the Graph response (contains the video/post id).
    """
    video_path = Path(video_path)
    if video_path.stat().st_size > resumable_min_size:
        return publish_page_graph_resumable(
            page_id, text, video_path, token, graph_version,
            chunk_size=chunk_size)
    url = f"https://graph.facebook.com/{graph_version}/{page_id}/videos"
    body = _multipart_body(
        [("access_token", token), ("description", text)],
        file_field="source", filename=video_path.name,
        file_bytes=video_path.read_bytes())
    return _post_graph(
        url, body,
        {"Content-Type": f"multipart/form-data; boundary={_BOUNDARY}"},
        timeout=300)


def publish_page_graph_resumable(page_id: str, text: str,
                                 video_path: Path | str, token: str,
                                 graph_version: str = "v21.0",
                                 chunk_size: int = CHUNK_SIZE) -> dict:
    """Publish a large video via the resumable start/transfer/finish
    flow on /{page-id}/videos.

    The file is read chunk by chunk (never fully into memory). Each
    transfer follows the offsets the server returns, so a failed
    chunk is retried once from the same offset instead of restarting
    the whole upload. Returns the finish-phase response.
    """
    video_path = Path(video_path)
    size = video_path.stat().st_size
    url = f"https://graph.facebook.com/{graph_version}/{page_id}/videos"
    start = _post_graph_form(url, {
        "upload_phase": "start",
        "file_size": str(size),
        "access_token": token,
    }, timeout=60)
    session_id = start.get("upload_session_id")
    if not session_id:
        raise PublishError(
            "Graph resumable upload: no upload_session_id in start "
            f"response: {str(start)[:200]}")
    start_offset = int(start.get("start_offset") or 0)
    end_offset = int(start.get("end_offset") or size)
    stalls = 0
    with open(video_path, "rb") as fh:
        while start_offset < size:
            chunk_end = min(end_offset, size, start_offset + chunk_size)
            fh.seek(start_offset)
            chunk = fh.read(chunk_end - start_offset)
            body = _multipart_body(
                [("upload_phase", "transfer"),
                 ("upload_session_id", session_id),
                 ("start_offset", str(start_offset)),
                 ("access_token", token)],
                file_field="video_file_chunk", filename=video_path.name,
                file_bytes=chunk)
            headers = {"Content-Type":
                       f"multipart/form-data; boundary={_BOUNDARY}"}
            try:
                resp = _post_graph(url, body, headers, timeout=120)
            except (ConsentMissingError, AuthPublishError):
                raise
            except Exception:
                # One retry of the same chunk; a second failure is real.
                resp = _post_graph(url, body, headers, timeout=120)
            new_offset = int(resp.get("start_offset", chunk_end))
            new_end = int(resp.get("end_offset", size))
            if new_offset <= start_offset:
                stalls += 1
                if stalls >= 3:
                    raise PublishError(
                        "Graph resumable upload stalled at byte "
                        f"{start_offset} of {size}")
            else:
                stalls = 0
            start_offset, end_offset = new_offset, new_end
    title = text.strip().splitlines()[0][:100] if text.strip() \
        else "NEWS OUSSAMA"
    return _post_graph_form(url, {
        "upload_phase": "finish",
        "upload_session_id": session_id,
        "title": title,
        "description": text,
        "access_token": token,
    }, timeout=120)


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
