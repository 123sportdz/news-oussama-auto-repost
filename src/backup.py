"""Automatic backup of state/ — the publish history that prevents
re-publishing.

state/ (seen.json, published.json, ready.json, queue.txt, failed.txt)
is the only thing standing between the project and re-publishing
everything after a reinstall or a lost folder. Every monitor run
backs it up when the last backup is older than 24h, keeping the 7
newest zips in backups/. A backup failure never blocks the run.

Restore (stop the auto loop first):
  python -m src.backup --restore backups/state-YYYYMMDD-HHMMSS.zip
"""
from __future__ import annotations

import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import state as state_mod  # noqa: E402

STATE_DIR = state_mod.STATE
BACKUP_DIR = BASE / "backups"
KEEP_DEFAULT = 7
MAX_AGE_HOURS_DEFAULT = 24

# Never backed up: in-flight temp files and the run lock.
_SKIP_SUFFIXES = (".tmp",)
_SKIP_NAMES = {"monitor.lock"}


def _zip_name(now: datetime) -> str:
    return f"state-{now.strftime('%Y%m%d-%H%M%S')}.zip"


def list_backups() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob("state-*.zip"))


def backup_state(now: datetime | None = None,
                 keep: int = KEEP_DEFAULT) -> Path:
    """Zip state/ now; prune to the newest ``keep`` backups."""
    now = now or datetime.now()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / _zip_name(now)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(STATE_DIR.rglob("*")):
            if not path.is_file():
                continue
            if path.name in _SKIP_NAMES:
                continue
            if any(path.name.endswith(s) for s in _SKIP_SUFFIXES):
                continue
            # The videos themselves are NOT backed up: they can be
            # re-downloaded, and including them made one backup 460 MB
            # (2026-11-22). What must never be lost is the history —
            # seen/published/ready/queue/failed — which is kilobytes.
            if "downloads" in path.relative_to(STATE_DIR).parts:
                continue
            zf.write(path, path.relative_to(STATE_DIR))
    for old in list_backups()[: -keep] if keep > 0 else []:
        old.unlink(missing_ok=True)
    return dest


def backup_state_if_due(max_age_hours: int = MAX_AGE_HOURS_DEFAULT,
                        keep: int = KEEP_DEFAULT,
                        now: datetime | None = None) -> Path | None:
    """Backup when no backup newer than ``max_age_hours`` exists."""
    now = now or datetime.now()
    cutoff = now - timedelta(hours=max_age_hours)
    for path in reversed(list_backups()):
        try:
            stamp = datetime.strptime(path.stem, "state-%Y%m%d-%H%M%S")
        except ValueError:
            continue
        if stamp >= cutoff:
            return None
    return backup_state(now=now, keep=keep)


def restore_state(zip_path: Path | str) -> Path:
    """Restore state/ from a backup zip. Refuses while a monitor run
    holds the lock — stop the auto loop first, then restore."""
    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise SystemExit(f"backup not found: {zip_path}")
    if (STATE_DIR / "monitor.lock").exists():
        raise SystemExit(
            "a monitor run is active (state/monitor.lock exists) — "
            "stop the auto loop first, then restore")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(STATE_DIR)
    return STATE_DIR


def main(argv: list[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="src.backup")
    ap.add_argument("--restore", default="",
                    help="restore state/ from this backup zip")
    a = ap.parse_args(argv)
    if a.restore:
        restore_state(a.restore)
        print(f"restored state/ from {a.restore}")
        return
    dest = backup_state()
    print(f"backed up state/ to {dest}")


if __name__ == "__main__":
    main()
