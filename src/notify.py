"""Telegram notifications for NEWS OUSSAMA.

One-way alerts only: publish summaries, a dead Facebook session, an
invalid Page token. No commands, no polling, no extra dependency —
plain urllib to api.telegram.org.

Setup (2 minutes, once): talk to @BotFather on Telegram, /newbot,
paste the bot token + your chat id in the dashboard (home page,
"🔔 تنبيهات Telegram") or in .env as TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID. Until both are set, every call here is a silent
no-op — nothing breaks, nothing is sent.

The bot token is a secret: it is never logged and never rendered in
full (only the last 4 chars may appear in a masked status line).
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.config import env  # noqa: E402

TELEGRAM_API = "https://api.telegram.org"


def configured() -> bool:
    """True when a bot token and a chat id are both set."""
    return bool(env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"))


def send_telegram(text: str, urlopen=None) -> bool:
    """Send one Telegram message. Never raises; False when not
    configured or when Telegram cannot be reached.

    ``urlopen`` is injectable for tests.
    """
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    urlopen = urlopen or urllib.request.urlopen
    body = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{TELEGRAM_API}/bot{token}/sendMessage",
        data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False
    return bool(isinstance(payload, dict) and payload.get("ok"))


def notify(text: str, urlopen=None) -> bool:
    """Notify when configured, silently skip otherwise."""
    return send_telegram(text, urlopen=urlopen)


if __name__ == "__main__":
    import sys as _sys
    ok = send_telegram(" ".join(_sys.argv[1:])
                       or "🧪 NEWS OUSSAMA — test notification")
    print("sent" if ok else "not configured / failed — set "
          "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID first")
