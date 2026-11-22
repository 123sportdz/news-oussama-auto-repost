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


def run_discover() -> int:
    """One discovery pass: new source posts enter the queue.

    Guarded: a missing Playwright install, an expired Facebook
    session or a slow Facebook never blocks the monitor — the run
    is logged and the monitor still runs on what is already queued.
    """
    try:
        return subprocess.run(
            [sys.executable, "-m", "src.discover"], cwd=BASE,
            timeout=900).returncode
    except subprocess.TimeoutExpired:
        print("discovery timed out after 15m — skipping this check")
        return 1
    except OSError as exc:
        print(f"discovery could not start: {exc}")
        return 1


def run_monitor() -> int:
    try:
        return subprocess.run(
            [sys.executable, "-m", "src.monitor"], cwd=BASE,
            timeout=3600).returncode
    except subprocess.TimeoutExpired:
        print("monitor run timed out after 1h — skipping this check")
        return 1


def run_token_check() -> None:
    """Validate stored Page tokens once a day; alert on dead ones.

    A Page token has no expiry date but dies when the user changes
    their Facebook password, removes the app, or loses their Page
    role. The marker file keeps this to one check per day; a failure
    to check never blocks the monitor.
    """
    from datetime import date

    from src import tokens as tokens_mod
    marker = tokens_mod.BASE / "state" / "last_token_check"
    today = date.today().isoformat()
    try:
        if marker.exists() and marker.read_text(
                encoding="utf-8").strip() == today:
            return
    except OSError:
        pass
    try:
        cfg = load_config()
        rows = tokens_mod.validate_stored_tokens(cfg)
    except Exception as exc:  # noqa: BLE001 — the check must not block
        print(f"token check failed: {exc}")
        return
    bad = [r for r in rows if r["status"] == "invalid"]
    if bad:
        from src.notify import notify
        notify("⚠️ NEWS OUSSAMA — توكنات ميتة، النشر للصفحات متوقف:\n"
               + "\n".join(f"• {r['name']}: {r['error']}" for r in bad)
               + "\nأعد جيب التوكنات من صفحة التوكنات في الداشبورد.")
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(today, encoding="utf-8")
    except OSError:
        pass


def run_once(discover: bool = True) -> int:
    """One full cycle: discover new posts, then process + publish."""
    if discover:
        run_discover()
    run_token_check()
    return run_monitor()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="src.scheduler")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--no-discover", action="store_true",
                    help="skip the discovery pass (monitor only)")
    a = ap.parse_args(argv)
    if a.once:
        raise SystemExit(run_once(discover=not a.no_discover))
    cfg = load_config()
    minutes = int(cfg["settings"]["check_every_minutes"])
    print(f"Scheduler running: check every {minutes} min (Ctrl+C to stop).")
    while True:
        run_once(discover=not a.no_discover)
        print(f"--- waiting {minutes} min... ---")
        time.sleep(minutes * 60)


if __name__ == "__main__":
    main()
