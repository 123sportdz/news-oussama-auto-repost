"""Dedup + publish history state (state/seen.json, state/published.json).

Rule that must never break: a post_id is processed once. ``seen.json``
records every post that was downloaded/watermarked; ``published.json``
records every successful publish, one entry per (post_id, destination),
so a retry can never duplicate a success.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
STATE = BASE / "state"
SEEN = STATE / "seen.json"
PUBLISHED = STATE / "published.json"
READY = STATE / "ready.json"
QUEUE = STATE / "queue.txt"


def load_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    """Write JSON atomically: temp file in the same dir + os.replace.

    A plain write_text can be killed mid-write and leave a truncated
    file; load_json then returns the default {} and seen.json /
    published.json silently "lose" all history (and posts get
    re-processed / re-published).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, path)


def is_seen(post_id: str, seen: dict | None = None) -> bool:
    seen = seen if seen is not None else load_json(SEEN, {})
    return str(post_id) in seen


def mark_seen(post_id: str, record: dict) -> dict:
    seen = load_json(SEEN, {})
    seen[str(post_id)] = record
    save_json(SEEN, seen)
    return seen


def is_published(post_id: str, destination: str,
                 published: dict | None = None) -> bool:
    published = published if published is not None else load_json(PUBLISHED, {})
    entry = published.get(str(post_id), {})
    return destination in (entry.get("destinations") or {})


def mark_published(post_id: str, destination: str, result: dict) -> dict:
    published = load_json(PUBLISHED, {})
    entry = published.setdefault(str(post_id), {"destinations": {}})
    entry["destinations"][destination] = result
    save_json(PUBLISHED, published)
    return published
