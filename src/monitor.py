"""Monitor: process the URL queue — read, download, edit, draft/publish.

Discovery — honest note:
  Facebook gives NO public feed/API for pages you do not manage.
  Tested 2026-11-20 and FAILED: yt-dlp page/reels listing, RSSHub
  (Cloudflare block), mbasic curl, facebook-cli pages posts list
  (only managed pages). What DOES work:
    1. Browser check — open each source page in your own Chrome
       and take the latest post URLs.
    2. Paste a post/reel URL — fastest and 100% reliable.
  So the queue (state/queue.txt, one URL per line) is filled by
  (1) or (2); this script does everything else automatically.

Usage:
  python3 -m src.monitor              # process queue.txt (up to max per check)
  python3 -m src.monitor --url <url>  # add one URL to the queue and process it
  python3 -m src.monitor --dry-run    # show what would happen, change nothing
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import state as state_mod  # noqa: E402
from src.caption import build_caption  # noqa: E402
from src.config import (CONFIG_PATH, enabled_destinations, enabled_sources,  # noqa: E402
                        load_config)
from src.downloader import download_video, post_info  # noqa: E402
from src.editor import watermark_photo, watermark_video  # noqa: E402
from src.publisher import ConsentMissingError, PublishError, publish  # noqa: E402

QUEUE = BASE / "state" / "queue.txt"
READY = BASE / "state" / "ready.json"
DL = BASE / "state" / "downloads"


def publish_commands(cfg: dict, record: dict) -> list[dict]:
    """Publish commands for one watermarked record.

    In draft mode these are saved only — nothing is published.
    In auto mode the caller may run them, but only when page_id is set
    and Professional Consent is approved; otherwise they stay queued.
    """
    settings = cfg.get("settings", {})
    cap = settings.get("caption", {})
    text = build_caption(record["caption"], cap.get("template", "{caption}"),
                         int(cap.get("max_chars", 1024)),
                         cap.get("hashtags") or [])
    cmds = []
    for d in cfg.get("destinations", []):
        if not d.get("enabled", True):
            continue
        if d.get("kind") == "profile":
            cmds.append({
                "destination": d["name"],
                "command": ["facebook-cli", "post", "create", "--message", text,
                            "--file", record["watermarked"]],
            })
        else:
            pid = d.get("page_id") or ""
            if not pid:
                cmds.append({"destination": d["name"],
                             "blocked": "page_id missing — publish once via the "
                             "browser, then post read returns owner_id"})
            else:
                cmds.append({
                    "destination": d["name"],
                    "command": ["facebook-cli", "pages", "posts", "create",
                                "--page-id", pid, "--text", text,
                                "--privacy", "PUBLIC",
                                "--file", record["watermarked"]],
                })
    return cmds


def file_sha256(path: Path | str) -> str:
    """SHA-256 of a media file — the content fingerprint for dedup."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_duplicate_by_hash(seen: dict, content_hash: str,
                           exclude_pid: str = "") -> str | None:
    """Post id of an earlier post with the same video/photo bytes, if any.

    Source pages often repost the same clip under a new post id — post_id
    dedup alone would publish it twice.
    """
    for pid, rec in seen.items():
        if pid != str(exclude_pid) and rec.get("content_hash") == content_hash:
            return str(pid)
    return None


def _parse_window(window: str) -> tuple[int, int] | None:
    try:
        start, end = window.split("-", 1)
        sh, sm = (int(x) for x in start.split(":"))
        eh, em = (int(x) for x in end.split(":"))
        return (sh * 60 + sm, eh * 60 + em)
    except (ValueError, AttributeError):
        return None


def in_publish_window(windows: list[str] | None,
                      now: datetime | None = None) -> bool:
    """True when publishing is allowed now. Empty list = always allowed.

    Windows are local-time "HH:MM-HH:MM" ranges; overnight ranges
    (e.g. "22:00-01:00") work too.
    """
    if not windows:
        return True
    now = now or datetime.now()
    minute = now.hour * 60 + now.minute
    for window in windows:
        parsed = _parse_window(window)
        if parsed is None:
            continue
        start, end = parsed
        if start <= end:
            if start <= minute < end:
                return True
        elif minute >= start or minute < end:
            return True
    return False


def next_window_start(windows: list[str] | None,
                      now: datetime | None = None) -> str | None:
    """Start ("HH:MM") of the next publish window, or None if always open."""
    if not windows:
        return None
    now = now or datetime.now()
    minute = now.hour * 60 + now.minute
    starts = sorted(
        p[0] for w in windows if (p := _parse_window(w)) is not None)
    if not starts:
        return None
    for start in starts:
        if start > minute:
            return f"{start // 60:02d}:{start % 60:02d}"
    first = starts[0]
    return f"{first // 60:02d}:{first % 60:02d}"


def refresh_ready(cfg: dict) -> dict:
    """Recompute publish commands for ready posts from the CURRENT config,
    so a page_id filled in later unblocks them without reprocessing."""
    ready = state_mod.load_json(READY, {})
    for rec in ready.values():
        if "caption" in rec and "watermarked" in rec:
            rec["publish"] = publish_commands(cfg, rec)
    state_mod.save_json(READY, ready)
    return ready


def process_url(url: str, cfg: dict) -> dict:
    """Process one post URL: read -> download -> edit -> record.

    Skips posts already in seen.json (never repost the same post_id).
    Returns the record (new or already-seen).
    """
    info = post_info(url)
    pid = str(info["post_id"])
    if state_mod.is_seen(pid):
        print(f"SKIP already seen: {pid} ({info['caption'][:60]})")
        return state_mod.load_json(state_mod.SEEN, {})[pid]

    print(f"NEW: {pid} | {info['owner']} | {info['created']} | {info['caption']}")
    DL.mkdir(parents=True, exist_ok=True)
    wm_settings = cfg["settings"].get("watermark", {})
    editor = cfg["settings"].get("editor", {})
    is_photo = (info.get("media_type") or "").lower().find("photo") >= 0
    raw = DL / f"{pid}.{'jpg' if is_photo else 'mp4'}"
    wm = DL / f"{pid}-watermarked.{'jpg' if is_photo else 'mp4'}"
    if not raw.exists():
        download_video(url, raw)
    content_hash = file_sha256(raw)
    seen = state_mod.load_json(state_mod.SEEN, {})
    dup = find_duplicate_by_hash(seen, content_hash, exclude_pid=pid)
    if dup:
        print(f"DUPLICATE content of {dup} — skipping re-edit/repost")
        raw.unlink(missing_ok=True)
        state_mod.mark_seen(pid, {**info, "content_hash": content_hash,
                                  "duplicate_of": dup})
        return seen[dup]
    if not wm.exists():
        if is_photo:
            watermark_photo(raw, wm, size=int(wm_settings.get("size_px", 320)),
                            margin=int(wm_settings.get("margin_px", 30)))
        else:
            watermark_video(
                raw, wm,
                size_px=int(wm_settings.get("size_px", 194)),
                margin=int(wm_settings.get("margin_px", 30)),
                position=wm_settings.get("position", "bottom-right"),
                crop_to_9x16=bool(editor.get("crop_to_9x16", False)),
                max_duration_seconds=int(editor.get("max_duration_seconds", 0)),
                loudnorm=bool(editor.get("loudnorm", False)),
            )
    record = {**info, "raw": str(raw), "watermarked": str(wm),
              "content_hash": content_hash}
    state_mod.mark_seen(pid, record)
    return record


FAILED = BASE / "state" / "failed.txt"
LOCK = BASE / "state" / "monitor.lock"


class RunLock:
    """One processing run at a time (cron vs manual vs dashboard).

    Without this, the 30-min cron and a manual/dashboard run process the
    same queue at once: two ffmpeg re-encodes on a 1.5-CPU box each run
    at half speed and both hit the 300s timeout (seen 2026-11-20), and
    both write the same ready.json. The lock file holds the owner's PID;
    a lock whose PID is dead is stale and gets taken over.
    """

    def __init__(self, path: Path = LOCK) -> None:
        self.path = path
        self.acquired = False

    def __enter__(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            self.acquired = True
            return True
        except FileExistsError:
            try:
                pid = int(self.path.read_text().strip())
                os.kill(pid, 0)  # alive?
                return False
            except (ValueError, ProcessLookupError, PermissionError,
                    OSError):
                self.path.unlink(missing_ok=True)
                return self.__enter__()

    def __exit__(self, *exc) -> bool:
        if self.acquired:
            self.path.unlink(missing_ok=True)
        return False


def process_queue(cfg: dict, urls: list[str], limit: int,
                  dry_run: bool = False) -> tuple[list[str], list[str]]:
    """Process up to ``limit`` URLs. Returns (done, remaining).

    Progress is saved after EVERY url (ready.json + queue.txt), and one
    failing url is recorded in state/failed.txt instead of stalling or
    losing the whole batch — a hung or broken download used to block
    everything with no timeout and no saved progress. A second run
    (cron/manual/dashboard) while one holds the lock does nothing and
    leaves the queue untouched.
    """
    with RunLock() as locked:
        if not locked:
            print("another processing run is already active — skipping")
            return [], urls
        return _process_queue_locked(cfg, urls, limit, dry_run)


def _process_queue_locked(cfg: dict, urls: list[str], limit: int,
                          dry_run: bool = False) -> tuple[list[str],
                                                         list[str]]:
    ready = refresh_ready(cfg)
    done, remaining = [], []
    for i, url in enumerate(urls[:limit]):
        if dry_run:
            print(f"[dry-run] would process {url}")
            remaining.append(url)
            continue
        try:
            rec = process_url(url, cfg)
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            # SystemExit is what process_url raises on download/read
            # failures — it is a BaseException, not an Exception.
            print(f"FAILED {url}: {exc}")
            FAILED.parent.mkdir(parents=True, exist_ok=True)
            with open(FAILED, "a", encoding="utf-8") as fh:
                fh.write(f"{url} | {exc}\n")
            continue
        rec["publish"] = publish_commands(cfg, rec)
        ready[str(rec["post_id"])] = rec
        done.append(url)
        state_mod.save_json(READY, ready)
        rest = urls[i + 1:]
        QUEUE.write_text("\n".join(rest) + ("\n" if rest else ""))
    remaining += urls[limit:]
    state_mod.save_json(READY, ready)
    return done, remaining


def publish_ready(cfg: dict, token: str = "") -> None:
    """Auto mode: publish every ready post to destinations not yet done.

    Each (post_id, destination) is published at most once — see
    state.mark_published. Consent errors leave the post queued.
    """
    ready = state_mod.load_json(READY, {})
    windows = cfg.get("settings", {}).get("publish", {}).get("windows") or []
    if not in_publish_window(windows):
        print(f"  ⏸ outside publish window; next window starts "
              f"{next_window_start(windows)}")
        return
    for pid, rec in ready.items():
        settings = cfg.get("settings", {})
        cap = settings.get("caption", {})
        text = build_caption(rec["caption"], cap.get("template", "{caption}"),
                             int(cap.get("max_chars", 1024)),
                             cap.get("hashtags") or [])
        for dest in cfg.get("destinations", []):
            if not dest.get("enabled", True):
                continue
            name = dest["name"]
            if state_mod.is_published(pid, name):
                continue
            try:
                result = publish(dest, text, rec["watermarked"], token)
            except ConsentMissingError as exc:
                print(f"  ⏸ {name}: {exc}")
                continue
            except PublishError as exc:
                print(f"  ❌ {name}: {exc}")
                continue
            state_mod.mark_published(pid, name, result)
            print(f"  ✅ published to {name}: {result}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="src.monitor")
    ap.add_argument("--url", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--discover", action="store_true",
                    help="find new posts from source pages first "
                    "(needs Playwright + one-time Facebook login)")
    ap.add_argument("--config", default=str(CONFIG_PATH))
    a = ap.parse_args(argv)

    cfg = load_config(a.config)
    print(f"Sources enabled: {[s['name'] for s in enabled_sources(cfg)]}")
    print(f"Destinations enabled: {[d['name'] for d in enabled_destinations(cfg)]}")
    settings = cfg["settings"]
    print(f"Publish mode: {settings['publish']['mode']} | "
          f"check every {settings['check_every_minutes']} min | "
          f"max {settings['max_posts_per_check']} per check")

    if a.discover:
        from src.discover import discover_all
        print("Discovering new posts from source pages …")
        try:
            discover_all(cfg)
        except SystemExit as exc:
            print(f"Discovery skipped: {exc}")

    if a.url:
        QUEUE.parent.mkdir(parents=True, exist_ok=True)
        existing = QUEUE.read_text().splitlines() if QUEUE.exists() else []
        for u in a.url:
            if u not in existing:
                existing.append(u)
        QUEUE.write_text("\n".join(existing) + "\n")

    urls = [l.strip() for l in QUEUE.read_text().splitlines()
            if l.strip()] if QUEUE.exists() else []
    refresh_ready(cfg)
    if not urls:
        print("Queue is empty (state/queue.txt). Add a post URL with --url, "
              "or wait for the browser check to fill it.")
        print("Sources to check next:")
        for s in enabled_sources(cfg):
            print(f"  - {s['name']}: {s['url']}")
        return

    done, remaining = process_queue(cfg, urls,
                                    int(settings["max_posts_per_check"]),
                                    dry_run=a.dry_run)
    QUEUE.write_text("\n".join(remaining) + ("\n" if remaining else ""))
    ready = state_mod.load_json(READY, {})
    print(f"\nProcessed {len(done)}, ready in state/ready.json: {len(ready)}, "
          f"remaining in queue: {len(remaining)}")
    if settings["publish"]["mode"] == "draft":
        print("Mode is draft: nothing was published. Review state/ready.json, "
              "then publish each watermarked file.")
    elif not a.dry_run:
        from src.config import env
        publish_ready(cfg, token=env("FB_PAGE_ACCESS_TOKEN"))


if __name__ == "__main__":
    main()
