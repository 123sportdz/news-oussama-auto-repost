#!/usr/bin/env python3
"""Thin wrapper — the real monitor lives in src/monitor.py.

Usage:
  python3 monitor.py                 # process queue.txt
  python3 monitor.py --url <url>     # add one URL to the queue and process it
  python3 monitor.py --dry-run       # show what would happen, change nothing
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.monitor import main  # noqa: E402

if __name__ == "__main__":
    main()
