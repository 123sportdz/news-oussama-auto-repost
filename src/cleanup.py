"""Download retention: state/downloads/ grows forever otherwise.

Every processed clip leaves a raw file + a watermarked file behind
(441 MB / 27 files on the VM on 2026-11-22, and counting). Nothing
ever deleted them. This module deletes files that are safe to lose:

- the post is published to EVERY enabled destination, AND
- the post is not in ready.json (ready posts still need their
  watermarked file to publish), AND
- the file is older than settings.cleanup.keep_days (default 30).

Files whose post is unknown (not in published.json) are never
deleted — they may belong to a run in progress. keep_days = 0
disables cleanup entirely. Runs best-effort at the end of every
monitor run; a failure never blocks the run.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import state as state_mod  # noqa: E402
from src.monitor import DL  # noqa: E402

KEEP_DAYS_DEFAULT = 30


def _post_id_from_filename(name: str) -> str:
    """'113…-watermarked.mp4' -> '113…'; 'goal-166….mp4' -> same stem."""
    stem = Path(name).stem
    if stem.endswith("-watermarked"):
        stem = stem[: -len("-watermarked")]
    return stem


def _fully_published(pid: str, cfg: dict) -> bool:
    """True when every enabled destination already has this post."""
    dests = [d for d in cfg.get("destinations", [])
             if d.get("enabled", True)]
    if not dests:
        return False
    published = state_mod.load_json(state_mod.PUBLISHED, {})
    return all(state_mod.is_published(pid, d["name"], published)
               for d in dests)


def cleanup_downloads(cfg: dict, now: float | None = None,
                      dry_run: bool = False) -> dict:
    """Delete old, fully-published download files.

    Returns {"deleted": [names], "freed_bytes": int, "kept": int}.
    """
    keep_days = int((cfg.get("settings", {}) or {}).get("cleanup", {})
                    .get("keep_days", KEEP_DAYS_DEFAULT) or 0)
    result: dict = {"deleted": [], "freed_bytes": 0, "kept": 0}
    if keep_days <= 0 or not DL.exists():
        return result
    now = now if now is not None else time.time()
    cutoff = now - keep_days * 86400
    ready = state_mod.load_json(state_mod.READY, {})
    for path in sorted(DL.iterdir()):
        if not path.is_file():
            continue
        pid = _post_id_from_filename(path.name)
        if (path.stat().st_mtime >= cutoff
                or pid in ready
                or not _fully_published(pid, cfg)):
            result["kept"] += 1
            continue
        size = path.stat().st_size
        if not dry_run:
            path.unlink(missing_ok=True)
        result["deleted"].append(path.name)
        result["freed_bytes"] += size
    return result


def main(argv: list[str] | None = None) -> None:
    import argparse
    from src.config import load_config
    ap = argparse.ArgumentParser(prog="src.cleanup")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be deleted, delete nothing")
    a = ap.parse_args(argv)
    cfg = load_config()
    result = cleanup_downloads(cfg, dry_run=a.dry_run)
    for name in result["deleted"]:
        print(f"{'would delete' if a.dry_run else 'deleted'}: {name}")
    print(f"{len(result['deleted'])} file(s), "
          f"{result['freed_bytes'] / (1024 * 1024):.1f} MB freed, "
          f"{result['kept']} kept")


if __name__ == "__main__":
    main()
