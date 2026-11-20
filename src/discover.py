"""Discover new posts from source pages.

Why a real browser: Facebook gives no public feed or API for pages you
do not manage, and yt-dlp cannot list a page at all — verified
2026-11-20, the /reels, /videos and bare page URLs all return
"Unsupported URL" from yt-dlp's Facebook extractor. The only reliable
way is a logged-in browser session.

How it works: Playwright opens Chromium once, you log into Facebook a
single time, the session is saved to state/fb-auth.json (cookies only,
no password is stored), and every later run reuses it.

Setup (once, on the machine that runs the project):
  pip install playwright
  python -m playwright install chromium
  python -m src.discover --login   # a browser window opens — log in, close it

Usage:
  python -m src.discover            # find new posts, append to queue.txt
  python -m src.monitor --discover  # discover, then process + publish
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import state as state_mod  # noqa: E402
from src.config import load_config  # noqa: E402
from src.monitor import QUEUE  # noqa: E402

AUTH_FILE = BASE / "state" / "fb-auth.json"

# /reel/123..., /watch/?v=123..., /video.php?v=123...
POST_RE = re.compile(r"/(?:reel/|watch/\?v=|videos/|video\.php\?v=)(\d{6,})")


def extract_post_urls(html: str) -> list[str]:
    """Post/reel URLs found in a Facebook page's HTML, in first-seen order.

    Pure function — no browser needed, so it is unit-testable.
    """
    seen: dict[str, None] = {}
    for match in POST_RE.finditer(html or ""):
        pid = match.group(1)
        seen.setdefault(f"https://www.facebook.com/reel/{pid}", None)
    return list(seen)


def _playwright_missing() -> str:
    return ("Playwright غير مثبّت — ثبّته أولا:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium\n"
            "  python -m src.discover --login")


def login(auth_file: Path = AUTH_FILE) -> Path:
    """One-time Facebook login: opens a browser window, saves the session."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(_playwright_missing())
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto("https://www.facebook.com/login",
                  wait_until="domcontentloaded")
        print("سجّل الدخول إلى فيسبوك في النافذة المفتوحة، ثم اضغط Enter هنا.")
        input()
        ctx.storage_state(path=str(auth_file))
        browser.close()
    print(f"تم حفظ الجلسة في {auth_file} — لن تحتاج لتسجيل الدخول مجددا.")
    return auth_file


def discover_source(page_url: str, limit: int = 5,
                    scroll_steps: int = 4,
                    auth_file: Path = AUTH_FILE) -> list[str]:
    """Latest post/reel URLs from one source page (logged-in browser)."""
    if not auth_file.exists():
        raise SystemExit(
            "لم يتم تسجيل الدخول بعد — شغّل أولا: python -m src.discover --login")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(_playwright_missing())
    found: dict[str, None] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(auth_file))
        page = ctx.new_page()
        for tab in ("/reels", "/videos", ""):
            try:
                page.goto(page_url.rstrip("/") + tab,
                          wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
            except Exception as exc:  # noqa: BLE001 — next tab may work
                print(f"  ! {tab or 'page'}: {exc}")
                continue
            for _ in range(scroll_steps):
                for url in extract_post_urls(page.content()):
                    found.setdefault(url, None)
                if len(found) >= limit:
                    break
                page.evaluate(
                    "window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
            if len(found) >= limit:
                break
        browser.close()
    return list(found)[:limit]


def _post_id_from_url(url: str) -> str:
    match = POST_RE.search(url)
    return match.group(1) if match else url


def discover_all(cfg: dict) -> dict:
    """Discover new posts from every enabled source, append to the queue.

    Returns a per-source report: {name: {"found": n, "new": n, "urls": [...]}}.
    """
    discovery = cfg.get("settings", {}).get("discovery", {})
    limit = int(discovery.get("max_per_source", 5))
    scroll_steps = int(discovery.get("scroll_steps", 4))
    auth_file = Path(discovery.get("auth_file") or str(AUTH_FILE))
    if not auth_file.is_absolute():
        auth_file = BASE / auth_file
    seen = state_mod.load_json(state_mod.SEEN, {})
    queued = ([l.strip() for l in QUEUE.read_text().splitlines()
               if l.strip()] if QUEUE.exists() else [])
    report: dict = {}
    new_urls: list[str] = []
    for src in cfg.get("sources", []):
        if not src.get("enabled", True):
            continue
        name = src.get("name") or src.get("url")
        try:
            urls = discover_source(src["url"], limit=limit,
                                   scroll_steps=scroll_steps,
                                   auth_file=auth_file)
        except SystemExit as exc:
            report[name] = {"found": 0, "new": 0, "urls": [],
                            "error": str(exc)}
            continue
        fresh = [u for u in urls
                 if _post_id_from_url(u) not in seen and u not in queued]
        new_urls.extend(fresh)
        report[name] = {"found": len(urls), "new": len(fresh), "urls": fresh}
        print(f"  {name}: found {len(urls)}, new {len(fresh)}")
    if new_urls:
        QUEUE.parent.mkdir(parents=True, exist_ok=True)
        QUEUE.write_text("\n".join(queued + new_urls) + "\n")
    return report


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="src.discover")
    ap.add_argument("--login", action="store_true",
                    help="one-time Facebook login, saves the session")
    ap.add_argument("--limit", type=int, default=0,
                    help="max new posts per source (default: from config)")
    a = ap.parse_args(argv)
    if a.login:
        login()
        return
    cfg = load_config()
    if a.limit:
        cfg.setdefault("settings", {}).setdefault(
            "discovery", {})["max_per_source"] = a.limit
    report = discover_all(cfg)
    total_new = sum(r["new"] for r in report.values())
    print(f"Discovery done: {total_new} new post(s) added to the queue.")


if __name__ == "__main__":
    main()
