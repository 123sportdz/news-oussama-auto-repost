"""Local web dashboard (Python standard library only — no Flask needed).

Usage:
  python3 -m src.dashboard            # http://127.0.0.1:8080
  python3 -m src.dashboard --port 8000

Features:
- Edit sources and destinations in the browser (add / enable / disable /
  delete, set page_id), saved straight to config.yaml.
- Queue a post URL for processing.
- See ready/draft posts with their publish commands.
- See seen + published history.
- Download the generated config.yaml.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.config import load_config, save_config  # noqa: E402
from src import state as state_mod  # noqa: E402

CSS = """
body{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;
padding:16px;background:#111;color:#eee;direction:rtl}
a{color:#f5c518} input,select,button{padding:6px;margin:2px}
table{border-collapse:collapse;width:100%} td,th{border:1px solid #444;
padding:6px;text-align:right;vertical-align:top}
code{font-size:12px;word-break:break-all} .ok{color:#7CFC00} .bad{color:#f66}
h1{color:#f5c518} form{display:inline}
"""


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def row_form(action: str, fields: dict, label: str) -> str:
    inputs = "".join(
        f'<input name="{esc(k)}" value="{esc(v)}" placeholder="{esc(k)}" size="18">'
        for k, v in fields.items())
    return (f'<form method="post" action="{action}">{inputs}'
            f'<button>{esc(label)}</button></form>')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console quiet
        pass

    def _send(self, body: str, ctype: str = "text/html; charset=utf-8",
              status: int = 200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/config.yaml":
            cfg = load_config()
            import yaml
            return self._send(yaml.safe_dump(cfg, allow_unicode=True,
                                             sort_keys=False),
                              "text/yaml; charset=utf-8")
        if self.path in ("/", ""):
            return self._send(home_page())
        self._send("<h1>404</h1>", status=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(
            self.rfile.read(length).decode("utf-8"))
        get = lambda k, d="": (form.get(k) or [d])[0]
        cfg = load_config()
        path = self.path
        if path == "/add-source":
            cfg.setdefault("sources", []).append({
                "url": get("url"), "name": get("name") or get("url"),
                "enabled": True, "types": ["reel", "video", "post", "photo"]})
        elif path == "/add-destination":
            cfg.setdefault("destinations", []).append({
                "url": get("url"), "name": get("name") or get("url"),
                "page_id": get("page_id") or "", "enabled": True})
        elif path == "/toggle-source":
            src = cfg["sources"][int(get("i"))]
            src["enabled"] = not src.get("enabled", True)
        elif path == "/toggle-destination":
            dst = cfg["destinations"][int(get("i"))]
            dst["enabled"] = not dst.get("enabled", True)
        elif path == "/delete-source":
            del cfg["sources"][int(get("i"))]
        elif path == "/delete-destination":
            del cfg["destinations"][int(get("i"))]
        elif path == "/set-page-id":
            cfg["destinations"][int(get("i"))]["page_id"] = get("page_id")
        elif path == "/queue":
            url = get("url").strip()
            queue = BASE / "state" / "queue.txt"
            queue.parent.mkdir(parents=True, exist_ok=True)
            existing = queue.read_text().splitlines() if queue.exists() else []
            if url and url not in existing:
                existing.append(url)
            queue.write_text("\n".join(existing) + ("\n" if existing else ""))
        save_config(cfg)
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()


def home_page() -> str:
    cfg = load_config()
    ready = state_mod.load_json(state_mod.READY, {})
    seen = state_mod.load_json(state_mod.SEEN, {})
    published = state_mod.load_json(state_mod.PUBLISHED, {})
    settings = cfg.get("settings", {})

    def table(rows, headers):
        head = "".join(f"<th>{esc(h)}</th>" for h in headers)
        body = "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
            for r in rows)
        return f"<table><tr>{head}</tr>{body}</table>"

    src_rows = []
    for i, s in enumerate(cfg.get("sources", [])):
        src_rows.append([
            esc(s.get("name")), f'<a href="{esc(s.get("url"))}">{esc(s.get("url"))}</a>',
            "✅" if s.get("enabled", True) else "❌",
            (f'<form method="post" action="/toggle-source">'
             f'<input type="hidden" name="i" value="{i}">'
             f'<button>{"تعطيل" if s.get("enabled", True) else "تفعيل"}</button></form>'
             f'<form method="post" action="/delete-source">'
             f'<input type="hidden" name="i" value="{i}">'
             f'<button>حذف</button></form>'),
        ])
    dst_rows = []
    for i, d in enumerate(cfg.get("destinations", [])):
        dst_rows.append([
            esc(d.get("name")), esc(d.get("page_id") or "— (ناقص)"),
            "✅" if d.get("enabled", True) else "❌",
            (row_form("/set-page-id", {"i": i, "page_id": d.get("page_id") or ""},
                      "حفظ page_id")
             + f'<form method="post" action="/toggle-destination">'
               f'<input type="hidden" name="i" value="{i}">'
               f'<button>{"تعطيل" if d.get("enabled", True) else "تفعيل"}</button></form>'
             + f'<form method="post" action="/delete-destination">'
               f'<input type="hidden" name="i" value="{i}">'
               f'<button>حذف</button></form>'),
        ])
    ready_rows = []
    for pid, rec in ready.items():
        cmds = "<br>".join(
            (f"{esc(p['destination'])}: "
             f"<code>{esc(' '.join(p['command']))}</code>"
             if "command" in p else
             f"{esc(p['destination'])}: <span class='bad'>{esc(p['blocked'])}</span>")
            for p in rec.get("publish", []))
        ready_rows.append([
            esc(rec.get("owner")), esc(rec.get("caption"))[:80],
            f"<code>{esc(rec.get('watermarked'))}</code><br>{cmds}",
            "✅" if pid in published else "مسودة",
        ])

    return f"""<!DOCTYPE html><html lang="ar"><head><meta charset="utf-8">
<title>NEWS OUSSAMA — لوحة التحكم</title><style>{CSS}</style></head><body>
<h1>🎬 NEWS OUSSAMA — لوحة التحكم</h1>
<p>الوضع: <b>{esc(settings.get('publish', {}).get('mode'))}</b> |
فحص كل {esc(settings.get('check_every_minutes'))} دقيقة |
حد أقصى {esc(settings.get('max_posts_per_check'))} منشور لكل فحص |
شعار: {esc(settings.get('watermark', {}).get('position'))} {esc(settings.get('watermark', {}).get('size_px'))}px</p>

<h2>المصادر</h2>
{table(src_rows, ["الاسم", "الرابط", "مفعّل", "إجراءات"])}
{row_form("/add-source", {"name": "", "url": ""}, "إضافة مصدر")}

<h2>الوجهات (صفحاتك)</h2>
{table(dst_rows, ["الاسم", "page_id", "مفعّل", "إجراءات"])}
{row_form("/add-destination", {"name": "", "url": "", "page_id": ""}, "إضافة وجهة")}

<h2>أضف منشور للطابور</h2>
{row_form("/queue", {"url": ""}, "إضافة رابط منشور/ريل")}

<h2>جاهز للنشر ({len(ready)})</h2>
{table(ready_rows, ["المصدر", "النص", "الملف + أوامر النشر", "الحالة"])}

<h2>السجل</h2>
<p>منشورات معالجة (seen): {len(seen)} | منشورات منشورة: {len(published)}</p>
<p><a href="/config.yaml">⬇ تحميل config.yaml</a></p>
</body></html>"""


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="src.dashboard")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args(argv)
    server = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"Dashboard: http://{a.host}:{a.port}  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
