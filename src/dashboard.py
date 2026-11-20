"""Local web dashboard (Python standard library only — no Flask needed).

Usage:
  python3 -m src.dashboard            # http://127.0.0.1:8080
  python3 -m src.dashboard --port 8000

Features:
- Edit sources and destinations in the browser (add / enable / disable /
  delete, set page_id), saved straight to config.yaml.
- Queue a post URL, then download + watermark it from the browser
  (button "سحب") — the queue is processed in the background.
- See ready/draft posts with a video preview, a download link, and a
  real "نشر" button per destination (or "نشر للكل"). Publishing runs
  in the background; the result appears in the status banner.
- See seen + published history.
- Download the generated config.yaml.
"""
from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.caption import build_caption  # noqa: E402
from src.config import env, load_config, save_config  # noqa: E402
from src import state as state_mod  # noqa: E402
from src.monitor import (DL, QUEUE, READY, _parse_window, in_publish_window,  # noqa: E402
                         next_window_start, process_queue, process_url,
                         publish_commands, refresh_ready)
from src.publisher import ConsentMissingError, PublishError, publish  # noqa: E402
from src.stats import STATS, refresh_stats  # noqa: E402

STATUS = BASE / "state" / "last_action.json"
_JOBS = {"running": 0}

CSS = """
body{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;
padding:16px;background:#111;color:#eee;direction:rtl}
a{color:#f5c518} input,select,button{padding:6px;margin:2px}
table{border-collapse:collapse;width:100%} td,th{border:1px solid #444;
padding:6px;text-align:right;vertical-align:top}
code{font-size:12px;word-break:break-all} .ok{color:#7CFC00} .bad{color:#f66}
h1{color:#f5c518} form{display:inline}
.status{padding:10px;border:1px solid #f5c518;border-radius:6px;margin:10px 0}
.status.ok{border-color:#7CFC00} .status.bad{border-color:#f66}
button.publish{background:#f5c518;color:#111;font-weight:bold}
video{max-width:320px;max-height:240px;display:block;margin:4px 0}
details{font-size:12px;color:#aaa}
"""


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def row_form(action: str, fields: dict, label: str,
             button_class: str = "") -> str:
    inputs = "".join(
        f'<input name="{esc(k)}" value="{esc(v)}" placeholder="{esc(k)}" size="18">'
        for k, v in fields.items())
    cls = f' class="{button_class}"' if button_class else ""
    return (f'<form method="post" action="{action}">{inputs}'
            f'<button{cls}>{esc(label)}</button></form>')


# ---------------------------------------------------------------- status ---

def set_status(message: str, ok: bool = True) -> None:
    try:
        state_mod.save_json(STATUS, {"message": message, "ok": ok})
    except Exception:
        pass


def get_status() -> dict:
    return state_mod.load_json(STATUS, {})


# ------------------------------------------------------- background jobs ---

def _publish_one(cfg: dict, pid: str, dest_name: str,
                 token: str = "") -> tuple[bool, str]:
    """Publish one ready post to one destination. Returns (ok, message)."""
    windows = cfg.get("settings", {}).get("publish", {}).get("windows") or []
    if not in_publish_window(windows):
        return False, (f"⏸ خارج أوقات النشر — النافذة القادمة "
                       f"{next_window_start(windows)}")
    ready = state_mod.load_json(READY, {})
    rec = ready.get(str(pid))
    if not rec:
        return False, f"المنشور {pid} غير موجود في الجاهز"
    dest = next((d for d in cfg.get("destinations", [])
                 if d.get("name") == dest_name), None)
    if dest is None:
        return False, f"الوجهة {dest_name} غير موجودة"
    if not dest.get("enabled", True):
        return False, f"الوجهة {dest_name} معطّلة"
    if state_mod.is_published(str(pid), dest_name):
        return False, f"المنشور منشور من قبل على {dest_name}"
    settings = cfg.get("settings", {})
    cap = settings.get("caption", {})
    text = build_caption(rec["caption"], cap.get("template", "{caption}"),
                         int(cap.get("max_chars", 1024)),
                         cap.get("hashtags") or [])
    try:
        result = publish(dest, text, rec["watermarked"], token)
    except ConsentMissingError as exc:
        return False, (f"⏸ {dest_name}: موافقة Professional Consent ناقصة — "
                       f"النشر يبقى في الطابور. ({exc})")
    except PublishError as exc:
        return False, f"❌ {dest_name}: {exc}"
    state_mod.mark_published(str(pid), dest_name, result)
    return True, f"✅ نُشر على {dest_name}: {result}"


def _publish_job(pid: str, dest_name: str | None) -> None:
    cfg = load_config()
    token = env("FB_PAGE_ACCESS_TOKEN")
    if dest_name:
        ok, msg = _publish_one(cfg, pid, dest_name, token)
        set_status(msg, ok)
        return
    messages = []
    all_ok = True
    for dest in cfg.get("destinations", []):
        if not dest.get("enabled", True):
            continue
        ok, msg = _publish_one(cfg, pid, dest["name"], token)
        messages.append(msg)
        all_ok = all_ok and ok
    set_status(" | ".join(messages) or "لا توجد وجهات مفعّلة", all_ok)


def _process_queue_job() -> None:
    try:
        cfg = load_config()
        urls = [l.strip() for l in QUEUE.read_text().splitlines()
                if l.strip()] if QUEUE.exists() else []
        if not urls:
            set_status("الطابور فارغ — أضف رابط منشور أولا", False)
            return
        done, remaining = process_queue(
            cfg, urls, int(cfg["settings"].get("max_posts_per_check", 3)))
        QUEUE.write_text("\n".join(remaining) + ("\n" if remaining else ""))
        ready = state_mod.load_json(READY, {})
        set_status(f"✅ تم سحب ومعالجة {len(done)} منشور — جاهز للنشر: "
                   f"{len(ready)}، متبقّي في الطابور: {len(remaining)}")
    except Exception as exc:  # noqa: BLE001 — surfaced in the banner
        set_status(f"❌ خطأ أثناء السحب: {exc}", False)


def _process_url_job(url: str) -> None:
    try:
        cfg = load_config()
        rec = process_url(url, cfg)
        ready = refresh_ready(cfg)
        ready[str(rec["post_id"])] = {**rec,
                                      "publish": publish_commands(cfg, rec)}
        state_mod.save_json(READY, ready)
        set_status(f"✅ تم سحب ومعالجة المنشور {rec['post_id']} — جاهز للنشر")
    except Exception as exc:  # noqa: BLE001 — surfaced in the banner
        set_status(f"❌ خطأ أثناء سحب {url}: {exc}", False)


def _refresh_stats_job() -> None:
    try:
        cfg = load_config()
        stats = refresh_stats(cfg)
        count = sum(len(v.get("destinations", {}))
                    for v in stats.values())
        set_status(f"📊 تم تحديث الإحصائيات لـ {count} منشور منشور")
    except Exception as exc:  # noqa: BLE001 — surfaced in the banner
        set_status(f"❌ خطأ أثناء تحديث الإحصائيات: {exc}", False)


def _run_in_background(target, *args) -> None:
    def wrapper() -> None:
        _JOBS["running"] += 1
        try:
            target(*args)
        finally:
            _JOBS["running"] -= 1

    threading.Thread(target=wrapper, daemon=True).start()


# ------------------------------------------------------------ file serving ---

_PID_RE = re.compile(r"^[0-9A-Za-z_-]+$")


def _resolve_download(pid: str) -> Path | None:
    """Watermarked file for a ready post id, or None. No traversal."""
    if not _PID_RE.match(pid or ""):
        return None
    for suffix in ("-watermarked.mp4", "-watermarked.jpg",
                   "-watermarked.jpeg", "-watermarked.png"):
        candidate = (DL / f"{pid}{suffix}").resolve()
        if candidate.is_file() and DL.resolve() in candidate.parents:
            return candidate
    return None


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

    def _send_file(self, path: Path) -> None:
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition",
                         f'inline; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(data)

    def _redirect_home(self) -> None:
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def do_GET(self):
        if self.path == "/config.yaml":
            cfg = load_config()
            import yaml
            return self._send(yaml.safe_dump(cfg, allow_unicode=True,
                                             sort_keys=False),
                              "text/yaml; charset=utf-8")
        if self.path == "/status.json":
            queue = ([l for l in QUEUE.read_text().splitlines() if l.strip()]
                     if QUEUE.exists() else [])
            ready = state_mod.load_json(READY, {})
            published = state_mod.load_json(state_mod.PUBLISHED, {})
            return self._send(json.dumps({
                "queue": len(queue), "ready": len(ready),
                "published": len(published),
                "busy": _JOBS["running"] > 0,
                "last_action": get_status(),
            }), "application/json; charset=utf-8")
        if self.path.startswith("/file/"):
            found = _resolve_download(self.path[len("/file/"):].split("?")[0])
            if found is None:
                return self._send("<h1>404 — الملف غير موجود</h1>", status=404)
            return self._send_file(found)
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
            QUEUE.parent.mkdir(parents=True, exist_ok=True)
            existing = QUEUE.read_text().splitlines() if QUEUE.exists() else []
            if url and url not in existing:
                existing.append(url)
            QUEUE.write_text("\n".join(existing) + ("\n" if existing else ""))
        elif path == "/queue-process":
            url = get("url").strip()
            if url:
                QUEUE.parent.mkdir(parents=True, exist_ok=True)
                existing = (QUEUE.read_text().splitlines()
                            if QUEUE.exists() else [])
                if url not in existing:
                    existing.append(url)
                QUEUE.write_text("\n".join(existing) + "\n")
                set_status(f"⏳ جارٍ سحب {url} …")
                _run_in_background(_process_url_job, url)
            else:
                set_status("أضف رابط منشور أولا", False)
        elif path == "/process":
            set_status("⏳ جارٍ سحب ومعالجة الطابور …")
            _run_in_background(_process_queue_job)
            return self._redirect_home()
        elif path == "/publish":
            set_status(f"⏳ جارٍ النشر إلى {get('destination')} …")
            _run_in_background(_publish_job, get("pid"), get("destination"))
            return self._redirect_home()
        elif path == "/publish-all":
            set_status("⏳ جارٍ النشر إلى كل الوجهات …")
            _run_in_background(_publish_job, get("pid"), None)
            return self._redirect_home()
        elif path == "/delete-ready":
            pid = get("pid")
            ready = state_mod.load_json(READY, {})
            ready.pop(pid, None)
            state_mod.save_json(READY, ready)
            seen = state_mod.load_json(state_mod.SEEN, {})
            seen.pop(pid, None)
            state_mod.save_json(state_mod.SEEN, seen)
            set_status(f"🗑 حُذف المنشور {pid} من الجاهز (يمكن إعادة سحبه)")
            return self._redirect_home()
        elif path == "/set-caption":
            pid = get("pid")
            caption = get("caption").strip()
            ready = state_mod.load_json(READY, {})
            rec = ready.get(pid)
            if rec and caption:
                rec["caption"] = caption
                rec["publish"] = publish_commands(cfg, rec)
                state_mod.save_json(READY, ready)
                set_status(f"✏️ تم تعديل نص المنشور {pid}")
            else:
                set_status("النص فارغ أو المنشور غير موجود", False)
            return self._redirect_home()
        elif path == "/refresh-stats":
            set_status("⏳ جارٍ تحديث الإحصائيات …")
            _run_in_background(_refresh_stats_job)
            return self._redirect_home()
        elif path == "/settings":
            settings = cfg.setdefault("settings", {})
            try:
                minutes = int(get("check_every_minutes") or 0)
                if minutes > 0:
                    settings["check_every_minutes"] = minutes
                per_check = int(get("max_posts_per_check") or 0)
                if per_check > 0:
                    settings["max_posts_per_check"] = per_check
                size = int(get("wm_size") or 0)
                if size > 0:
                    settings.setdefault("watermark", {})["size_px"] = size
            except ValueError:
                pass
            position = get("wm_position")
            if position in ("bottom-right", "bottom-left", "top-right",
                            "top-left", "center"):
                settings.setdefault("watermark", {})["position"] = position
            template = get("caption_template").strip()
            if template:
                settings.setdefault("caption", {})["template"] = template
            tags = [t.strip() for t in get("hashtags").split(",") if t.strip()]
            settings.setdefault("caption", {})["hashtags"] = tags
            mode = get("mode")
            if mode in ("draft", "auto"):
                settings.setdefault("publish", {})["mode"] = mode
            windows = [w.strip() for w in get("windows").split(",")
                       if w.strip() and _parse_window(w.strip())]
            settings.setdefault("publish", {})["windows"] = windows
            set_status("⚙️ تم حفظ الإعدادات")
        else:
            return self._send("<h1>404</h1>", status=404)
        save_config(cfg)
        self._redirect_home()


def home_page() -> str:
    cfg = load_config()
    ready = state_mod.load_json(READY, {})
    seen = state_mod.load_json(state_mod.SEEN, {})
    published = state_mod.load_json(state_mod.PUBLISHED, {})
    settings = cfg.get("settings", {})
    status = get_status()

    def table(rows, headers):
        head = "".join(f"<th>{esc(h)}</th>" for h in headers)
        body = "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
            for r in rows)
        return f"<table><tr>{head}</tr>{body}</table>"

    status_html = ""
    if status.get("message"):
        cls = "status ok" if status.get("ok") else "status bad"
        status_html = (f'<div id="status-banner" class="{cls}">'
                       f'{esc(status["message"])}</div>')
    else:
        status_html = '<div id="status-banner" class="status">جاهز</div>'

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

    queue_urls = ([l.strip() for l in QUEUE.read_text().splitlines()
                   if l.strip()] if QUEUE.exists() else [])

    ready_rows = []
    for pid, rec in ready.items():
        done = (published.get(pid) or {}).get("destinations", {})
        media = ""
        wm = rec.get("watermarked") or ""
        if _resolve_download(pid) is not None:
            if wm.lower().endswith((".mp4", ".mov", ".webm")):
                media = (f'<video controls preload="metadata" '
                         f'src="/file/{esc(pid)}"></video>')
            else:
                media = (f'<img src="/file/{esc(pid)}" '
                         f'style="max-width:320px">')
            media += f'<br><a href="/file/{esc(pid)}">⬇ تحميل الملف</a>'
        elif wm:
            media = f"<code>{esc(wm)}</code>"
        dest_cells = []
        for p in rec.get("publish", []):
            name = p["destination"]
            if name in done:
                dest_cells.append(f"{esc(name)}: ✅ منشور")
            elif "blocked" in p:
                dest_cells.append(f"{esc(name)}: ⏸ {esc(p['blocked'])}")
            else:
                dest_cells.append(
                    f'<form method="post" action="/publish">'
                    f'<input type="hidden" name="pid" value="{esc(pid)}">'
                    f'<input type="hidden" name="destination" value="{esc(name)}">'
                    f'<button class="publish">نشر إلى {esc(name)}</button>'
                    f'</form>')
        actions = "<br>".join(dest_cells)
        actions += (f'<br><form method="post" action="/publish-all">'
                    f'<input type="hidden" name="pid" value="{esc(pid)}">'
                    f'<button class="publish">نشر للكل</button></form>'
                    f'<form method="post" action="/delete-ready">'
                    f'<input type="hidden" name="pid" value="{esc(pid)}">'
                    f'<button>🗑 حذف</button></form>')
        caption_form = (
            f'<form method="post" action="/set-caption">'
            f'<input type="hidden" name="pid" value="{esc(pid)}">'
            f'<input name="caption" value="{esc(rec.get("caption"))}" '
            f'size="40"><button>✏️ حفظ النص</button></form>')
        ready_rows.append([
            esc(rec.get("owner")),
            esc(rec.get("caption"))[:80] + "<br>" + caption_form,
            media, actions,
        ])

    stats = state_mod.load_json(STATS, {})
    stats_rows = []
    for pid, entry in stats.items():
        for dest, info in (entry.get("destinations") or {}).items():
            eng = info.get("engagement") or {}
            eng_text = " • ".join(f"{k}: {v}" for k, v in eng.items()) or "—"
            stats_rows.append([
                esc(pid), esc(dest),
                (f'<a href="{esc(info.get("url") or "#")}">الرابط</a>'
                 if info.get("url") else "—"),
                esc(eng_text), esc(info.get("refreshed_at") or ""),
            ])

    wm = settings.get("watermark", {})
    cap = settings.get("caption", {})
    pub = settings.get("publish", {})
    settings_form = f"""
<form method="post" action="/settings">
فحص كل <input name="check_every_minutes" value="{esc(settings.get('check_every_minutes'))}" size="4"> دقيقة |
حد أقصى <input name="max_posts_per_check" value="{esc(settings.get('max_posts_per_check'))}" size="3"> منشور |
حجم الشعار <input name="wm_size" value="{esc(wm.get('size_px'))}" size="4">px |
موضع الشعار <select name="wm_position">
<option value="bottom-right"{" selected" if wm.get('position') == 'bottom-right' else ''}>أسفل يمين</option>
<option value="bottom-left"{" selected" if wm.get('position') == 'bottom-left' else ''}>أسفل يسار</option>
<option value="top-right"{" selected" if wm.get('position') == 'top-right' else ''}>أعلى يمين</option>
<option value="top-left"{" selected" if wm.get('position') == 'top-left' else ''}>أعلى يسار</option>
<option value="center"{" selected" if wm.get('position') == 'center' else ''}>الوسط</option>
</select><br>
قالب النص <input name="caption_template" value="{esc(cap.get('template'))}" size="30"> |
هاشتاغات <input name="hashtags" value="{esc(', '.join(cap.get('hashtags') or []))}" size="20" placeholder="#كرة, #أخبار"><br>
الوضع <select name="mode">
<option value="auto"{" selected" if pub.get('mode') == 'auto' else ''}>تلقائي (نشر مباشر)</option>
<option value="draft"{" selected" if pub.get('mode') == 'draft' else ''}>مسودة (مراجعة أولا)</option>
</select> |
أوقات النشر <input name="windows" value="{esc(', '.join(pub.get('windows') or []))}" size="20" placeholder="18:00-23:00">
<button>⚙️ حفظ الإعدادات</button>
</form>"""

    return f"""<!DOCTYPE html><html lang="ar"><head><meta charset="utf-8">
<title>NEWS OUSSAMA — لوحة التحكم</title><style>{CSS}</style></head><body>
<h1>🎬 NEWS OUSSAMA — لوحة التحكم</h1>
{status_html}
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
{row_form("/queue", {"url": ""}, "أضف للطابور")}
{row_form("/queue-process", {"url": ""}, "سحب الآن ⬇")}
<p>في الطابور الآن: {len(queue_urls)} منشور</p>
<form method="post" action="/process"><button>⬇ سحب ومعالجة الطابور</button></form>

<h2>جاهز للنشر ({len(ready)})</h2>
{table(ready_rows, ["المصدر", "النص", "المعاينة + تحميل", "النشر"])}

<h2>⚙️ الإعدادات</h2>
{settings_form}

<h2>📊 إحصائيات المنشورات</h2>
<form method="post" action="/refresh-stats"><button>🔄 تحديث الإحصائيات</button></form>
{table(stats_rows, ["المنشور", "الوجهة", "الرابط", "التفاعل", "آخر تحديث"]) if stats_rows else "<p>لا توجد إحصائيات بعد — انشر منشورا ثم اضغط تحديث الإحصائيات.</p>"}

<h2>السجل</h2>
<p>منشورات معالجة (seen): {len(seen)} | منشورات منشورة: {len(published)}</p>
<p><a href="/config.yaml">⬇ تحميل config.yaml</a></p>
<script>
let wasBusy = false;
async function poll() {{
  try {{
    const r = await fetch('/status.json');
    const s = await r.json();
    const banner = document.getElementById('status-banner');
    if (s.last_action && s.last_action.message && banner) {{
      banner.textContent = s.last_action.message;
      banner.className = 'status ' + (s.last_action.ok ? 'ok' : 'bad');
    }}
    if (wasBusy && !s.busy) location.reload();
    wasBusy = s.busy;
  }} catch (e) {{}}
}}
setInterval(poll, 5000);
</script>
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
