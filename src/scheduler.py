"""Scheduler: run the monitor loop every N minutes (from config).

Usage:
  python3 -m src.scheduler            # loop forever (Ctrl+C to stop)
  python3 -m src.scheduler --once     # a single check
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.config import load_config  # noqa: E402


def run_once() -> int:
    try:
        return subprocess.run(
            [sys.executable, "-m", "src.monitor"], cwd=BASE,
            timeout=3600).returncode
    except subprocess.TimeoutExpired:
        print("monitor run timed out after 1h — skipping this check")
        return 1


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="src.scheduler")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    if a.once:
        raise SystemExit(run_once())
    cfg = load_config()
    minutes = int(cfg["settings"]["check_every_minutes"])
    print(f"Scheduler running: check every {minutes} min (Ctrl+C to stop).")
    while True:
        run_once()
        print(f"--- waiting {minutes} min... ---")
        time.sleep(minutes * 60)


if __name__ == "__main__":
    main()
