"""System diagnostics: check every piece of the pipeline and say plainly
what is broken, instead of failing silently.

Each check returns {"name", "ok", "detail"}. The dashboard shows them
and saves the last run to state/diagnostics.json.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import state as state_mod  # noqa: E402
from src.config import load_config  # noqa: E402
from src.discover import AUTH_FILE  # noqa: E402

DIAGNOSTICS = BASE / "state" / "diagnostics.json"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _run(cmd: list[str], timeout: int = 25) -> tuple[int, str]:
    try:
        result = subprocess.run(cmd, text=True, capture_output=True,
                                timeout=timeout)
        return result.returncode, (result.stdout + result.stderr)[:600]
    except FileNotFoundError:
        return 127, "command not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def run_checks(cfg: dict | None = None) -> list[dict]:
    cfg = cfg or load_config()
    checks: list[dict] = []

    checks.append(_check("Python", True, sys.version.split()[0]))

    ffmpeg = shutil.which("ffmpeg")
    checks.append(_check("ffmpeg", bool(ffmpeg),
                         ffmpeg or "غير موجود — ثبّته وأضفه للـ PATH"))

    code, out = _run(["yt-dlp", "--version"])
    checks.append(_check("yt-dlp", code == 0,
                         out.strip().splitlines()[-1]
                         if out.strip() else "غير موجود"))

    try:
        import playwright  # noqa: F401
        checks.append(_check("Playwright (اكتشاف المنشورات)", True,
                             "مثبّت"))
    except ImportError:
        checks.append(_check(
            "Playwright (اكتشاف المنشورات)", False,
            "غير مثبّت — شغّل: pip install playwright && "
            "python -m playwright install chromium"))

    checks.append(_check(
        "جلسة فيسبوك (اكتشاف المنشورات)", AUTH_FILE.exists(),
        "موجودة" if AUTH_FILE.exists()
        else "غير موجودة — شغّل: python -m src.discover --login"))

    cli = shutil.which("facebook-cli") or "/opt/hatch/bin/facebook-cli"
    code, out = _run([cli, "pages", "list"])
    if "PROFESSIONAL_CONSENT_REQUIRED" in out:
        checks.append(_check(
            "فيسبوك API (النشر التلقائي)", False,
            "موافقة Professional Consent ناقصة — النشر من المتصفح فقط"))
    elif code == 0:
        checks.append(_check("فيسبوك API (النشر التلقائي)", True,
                             "الصفحات متاحة"))
    else:
        checks.append(_check("فيسبوك API (النشر التلقائي)", False,
                             out.strip()[:200] or "facebook-cli لا يعمل"))

    try:
        sources = [s for s in cfg.get("sources", []) if s.get("enabled")]
        dests = [d for d in cfg.get("destinations", []) if d.get("enabled")]
        missing_ids = [d["name"] for d in dests
                       if d.get("kind") != "profile"
                       and not d.get("page_id")]
        checks.append(_check(
            "الإعدادات", bool(sources) and bool(dests)
            and not missing_ids,
            f"{len(sources)} مصادر، {len(dests)} وجهات"
            + (f" — page_id ناقص: {', '.join(missing_ids)}"
               if missing_ids else "")))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("الإعدادات", False, str(exc)))

    try:
        import shutil as _sh
        free_gb = _sh.disk_usage(BASE).free / (1024 ** 3)
        checks.append(_check("مساحة القرص", free_gb > 1,
                             f"{free_gb:.1f} GB متاحة"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("مساحة القرص", False, str(exc)))

    queue = BASE / "state" / "queue.txt"
    n_queue = len([l for l in queue.read_text().splitlines() if l.strip()]) \
        if queue.exists() else 0
    ready = state_mod.load_json(state_mod.READY, {})
    published = state_mod.load_json(state_mod.PUBLISHED, {})
    checks.append(_check("حالة الطابور", True,
                         f"في الطابور: {n_queue} • جاهز: {len(ready)} • "
                         f"منشور: {len(published)}"))
    return checks


def run_and_save(cfg: dict | None = None) -> list[dict]:
    checks = run_checks(cfg)
    state_mod.save_json(DIAGNOSTICS, {"checks": checks})
    return checks
