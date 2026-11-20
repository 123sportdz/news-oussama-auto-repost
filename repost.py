#!/usr/bin/env python3
"""Thin wrapper — the real pipeline lives in src/.

Usage:
  python3 repost.py --url https://www.facebook.com/reel/1668308364143510/
  python3 repost.py --file state/queue.txt
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import load_config  # noqa: E402
from src.downloader import post_info  # noqa: E402
from src.monitor import process_url  # noqa: E402
from src.state import load_json, save_json, SEEN  # noqa: E402


def process(url):
    return process_url(url, load_config())


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", action="append", default=[])
    ap.add_argument("--file")
    a = ap.parse_args()
    urls = list(a.url)
    if a.file:
        urls += [l.strip() for l in Path(a.file).read_text().splitlines()
                 if l.strip()]
    if not urls:
        ap.error("give --url or --file")
    cfg = load_config()
    for u in urls:
        process_url(u, cfg)
    print("\nDone. Seen:", len(load_json(SEEN, {})))


if __name__ == "__main__":
    main()
