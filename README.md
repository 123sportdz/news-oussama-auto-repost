# NEWS OUSSAMA — إعادة النشر التلقائي | Facebook Auto-Repost

> **الفكرة:** نسحب المقاطع والمنشورات من صفحات فيسبوك نحددها، نعدّل كل مقطع قبل نشره
> (قصّ 9:16، تقليم، تطبيع الصوت، إضافة شعار NEWS OUSSAMA)، ونعيد رفعه على صفحاتنا
> الخاصة مع نفس العنوان والوصف الأصليين — كأننا نشرناه بأنفسنا، ماشي مشاركة.

> **The idea:** pull clips/posts from Facebook pages you specify, edit each clip
> before publishing (9:16 crop, trim, audio normalisation, NEWS OUSSAMA logo),
> and re-upload it to your own pages with the original title/caption and
> description preserved — as if you published it yourself, not a share.

---

## 🇩🇿 العربية

### كيفاش يخدم

1. **السحب (Discovery):** تحط رابط منشور/ريل في الطابور (`state/queue.txt`) أو من
   لوحة التحكم. نقرا المنشور بـ `facebook-cli post read` باش نجيب النص والتاريخ
   والمالك، ونحمّل الفيديو بـ `yt-dlp`.
2. **التعديل (Edit):** `ffmpeg` يحط الشعار أسفل اليمين (194px، هامش 30px)،
   ويقدر يقصّ للـ 9:16، يقصّر المدة، ويوحّد الصوت (`loudnorm`) — كلها من
   `config.yaml → settings.editor`.
3. **النشر (Publish):** لكل وجهة على حدة، باش فشل وحدة ما يكرّرش الناجحة.
   - صفحة عبر Graph API (الطريقة الأساسية للنشر التلقائي): توكن طويل
     الأمد خاص بكل صفحة (`FB_PAGE_ACCESS_TOKEN_<page_id>` في `.env`) —
     عيّنو من لوحة التحكم، قسم **🔑 توكنات الصفحات** (يتحقق من التوكن
     ويحفظو وحدو، بلا ما تحمّل أي ملف). شوف `docs/get-page-tokens.md`.
   - بروفايل: `facebook-cli post create --message "..." --file <mp4>`
   - احتياطي للصفحات: `facebook-cli pages posts create --page-id <id> ...`
     — بصح هاد الطريق يطلب موافقة في كل مرة ويتحبس غالبا بـ Sentinel
     ("media artifact registration requires an attributable caller").
4. **منع التكرار (Dedup):** كل `post_id` يتسجّل في `state/seen.json` بعد
   المعالجة، وكل نشر ناجح يتسجّل في `state/published.json` لكل وجهة —
   منشور واحد ما يتنشرش مرتين أبدا.

### الحدود الصادقة — اقراها قبل ما تتوقع السحر

- **فيسبوك ما يعطيش Feed/API عام لصفحات ماشي تاعك.** جرّبنا في 2026-11-20
  وفشل: `yt-dlp` لقائمة صفحة/ريلز، RSSHub (حجب Cloudflare)، mbasic curl،
  و `facebook-cli pages posts list` (للصفحات المدارة برك). الاكتشاف يكون
  بـ **رابط منشور تلصقو** أو **فحص بالمتصفح** (Chrome تاعك، مسجّل فيه).
- **النشر التلقائي يحتاج توكن لكل صفحة.** النشر بـ `facebook-cli`
  يرجّع غالبا `PROFESSIONAL_CONSENT_REQUIRED` أو يتوقف بـ Sentinel —
  ماشي طريق النشر التلقائي. الطريق الصح: توكن Graph API طويل الأمد
  لكل صفحة (من تطبيق NEWS OUSSAMA الخاص بيك)، يتحط من لوحة التحكم →
  **🔑 توكنات الصفحات**. **النشر من المتصفح يخدم** (مجرّب على
  الصفحتين — شوف "تجربة حقيقية" تحت) كبديل يدوي.
- **النص محدود بـ 1024 حرف** في منشور الصفحة — المشروع يقصّر تلقائيا.
- **فحص حقوق النشر:** فيسبوك يفحص الفيديو قبل النشر؛ في تجربة NewsDz9 الفحص
  كان مازال جاري وقت النشر، وفي aljazaer07 تعدّى ("Your reel is safe to publish!").

### التثبيت

**Linux / macOS:**
```bash
git clone https://github.com/123sportdz/news-oussama-auto-repost news-oussama-repost
cd news-oussama-repost
./setup.sh            # يفحص python/ffmpeg/yt-dlp، يثبّت المكتبات، يتحقق من الإعدادات
```

**Windows:**
```powershell
# ثبّت Python 3.10+ من python.org، و ffmpeg من https://ffmpeg.org/download.html
# (وأضفهم للـ PATH)، بعدها:
git clone https://github.com/123sportdz/news-oussama-auto-repost news-oussama-repost
cd news-oussama-repost
.\setup.bat
```

بعد التثبيت: شغّل لوحة التحكم (`.\setup.bat --dashboard` على ويندوز،
`./setup.sh --dashboard` على لينكس)، وافتح قسم **🔑 توكنات الصفحات**
والصق توكن كل صفحة (الطريقة في `docs/get-page-tokens.md`) — بلا هاد
الخطوة النشر التلقائي على الصفحات ما يخدمش.
> ملاحظة: ملفات `.sh` لا تعمل في PowerShell — استعمل `.\setup.bat` و `.\run.bat` على ويندوز، أو افتح Git Bash (يأتي مع git) وشغّل `./setup.sh`.

أو بـ Docker (اختياري):
```bash
cp .env.example .env
docker compose up --build            # المراقبة الدورية
docker compose --profile dashboard up  # + لوحة التحكم على :8080
```

### التشغيل بأمر واحد

```bash
./setup.sh                 # فحص + معالجة الطابور مرة واحدة
./setup.sh --url <رابط>     # أضف منشور وعالجو فورا
./setup.sh --auto          # حلقة دورية كل N دقيقة (من config.yaml): اكتشاف منشورات جديدة من المصادر، ثم معالجة ونشر
./setup.sh --dashboard     # لوحة التحكم على http://127.0.0.1:8080
```

### تغيير المصادر والوجهات

- **من لوحة التحكم** (http://127.0.0.1:8080): إضافة / تفعيل / تعطيل / حذف،
  وتعديل `page_id` — تحفظ مباشرة في `config.yaml`، وتقدر تحمّل الملف منها.
  فيها أيضا زر **سحب الآن ⬇** لمعالجة رابط فورا، زر **سحب ومعالجة الطابور**،
  معاينة الفيديو + تحميله، وزر **نشر** لكل وجهة أو **نشر للكل** — النتيجة
  تظهر في شريط الحالة أعلى الصفحة، والصفحة تتحدث وحدها كل 5 ثواني أثناء
  المعالجة. وتقدر تعدّل نص أي منشور قبل نشره، وتغيّر كل الإعدادات من
  قسم **الإعدادات** (الشعار، الفحص، الوضع، أوقات النشر)، وتشوف
  **إحصائيات** المنشورات (تعليقات/إعجابات...) بزر تحديث الإحصائيات.
  وقسم **🔑 توكنات الصفحات** يوري حالة توكن كل صفحة (ناقص / محفوظ /
  صالح / غير صالح) ويخليك تلصق التوكنات — يتحقق منها ويحفظها في
  `.env` وحدو.
- **أو يدويا** في `config.yaml`:
```yaml
sources:
  - url: https://www.facebook.com/goalalgeria16
    name: Goal Algeria
    enabled: true
destinations:
  - url: https://www.facebook.com/NewsDz9
    name: NewsDz9
    page_id: '147624121772177'
    enabled: true
settings:
  check_every_minutes: 30
  max_posts_per_check: 3
  watermark: {enabled: true, position: bottom-right, size_px: 194, margin_px: 30}
  caption: {template: '{caption}', max_chars: 1024, hashtags: []}
  editor: {crop_to_9x16: false, max_duration_seconds: 0, loudnorm: false}
  publish: {mode: auto, windows: []}  # draft = تجهيز برك، auto = نشر تلقائي
  # windows: أوقات النشر فقط، مثلا ["18:00-23:00"] — فارغة = أي وقت
```

### حماية من التكرار

نفس المقطع يعاد نشره من المصدر برابط جديد؟ المشروع يحسب بصمة (SHA-256)
لملف الفيديو/الصورة، وإذا البصمة موجودة من قبل يتخطاه — ما يعاودش ينشر
نفس المقطع مرتين.

### تنبيهات Telegram 🔔

النشر، فشل الاكتشاف، وموت توكن صفحة — كلها توصل تنبيه فوري على
Telegram. أنشئ بوت من `@BotFather` (`/newbot`)، وجيب معرّف الشات من
`@userinfobot`، والصقهم في الداشبورد (بطاقة "🔔 تنبيهات Telegram") أو
في `.env` (`TELEGRAM_BOT_TOKEN` و `TELEGRAM_CHAT_ID`). بلا هاد القيمتين
التنبيهات ساكتة — ما يتعطل والو.

### تشغيل تلقائي مع ويندوز

`.\autostart.bat` يسجّل مهمة مجدولة تشغّل `setup.bat --auto` عند كل
تسجيل دخول — بلا ما تشغلو بيدك بعد إعادة التشغيل. للإزالة:
`.\autostart.bat remove`.

### نسخة احتياطية لحالة النشر 💾

كل فحص يدير نسخة من `state/` في `backups/` إذا فاتت 24 ساعة على آخر
نسخة (يحتفظ بآخر 7). للاسترجاع — وقّف الحلقة التلقائية أولا، بعدها:
`python -m src.backup --restore backups/state-YYYYMMDD-HHMMSS.zip`

### فحص التوكنات اليومي

التوكنات بلا تاريخ انتهاء بصح يموتو إذا بدّلت كلمة السر ولا نحّيت
التطبيق ولا خسرت دورك في الصفحة. كل دورة تشوف إذا فات نهار على آخر
فحص، وإذا فات تعاود التحقق من التوكنات عبر Graph API — والتوكن الميت
يوصلك تنبيه Telegram، وحالتو تتبدل في الداشبورد.

### تقرير الأداء عبر Graph API 📊

زر "🔄 تحديث الإحصائيات" في الداشبورد يقرا المشاهدات والإعجابات
والتعليقات لكل منشور منشور — عبر Graph API بالتوكنات (يخدم على
ويندوز)، مع الرجوع لـ `facebook-cli` للبروفايل والوجهات بلا توكن.

### فلتر الجودة

الكليبات الأقصر من مدة معينة تتجاهل (ما تتنشرش). فعّلو من الداشبورد
(حقل "أقصر مدة للكليب" في الإعدادات) أو من `config.yaml`:
`editor.min_duration_seconds` — القيمة 0 تعني الكل مقبول.

### تنظيف ملفات التحميل 🧹

`state/downloads/` كان يكبر بلا توقف (441 MB في 22-11-2026). كل فحص
يحذف ملفات المنشورات المنشورة في كل الوجهات والأقدم من
`settings.cleanup.keep_days` (الافتراضي 30 يوم، 0 = ما يتحذف والو).
المنشورات الجاهزة والملفات المجهولة ما تتمسش أبدا. زر "🧹 تنظيف
الملفات القديمة" في الداشبورد يدير نفس الشيء يدويا، أو:
`python -m src.cleanup --dry-run`

### كلمة سر للداشبورد 🔐

الداشبورد بلا كلمة سر يثق في `localhost` برك. إذا بغيت تفتحو من برا
(مثلا عبر نفق للهاتف)، حط `DASHBOARD_PASSWORD=` في `.env` — بعدها
المتصفح يطلب كلمة السر قبل ما يفتح أي صفحة.

### فحص جلسة فيسبوك

صفحة التشخيص في الداشبورد تبين عمر جلسة الاكتشاف (`state/fb-auth.json`)
— إذا فاتت 60 يوم تنبهك أنها قديمة، وإذا الاكتشاف لقى 0 منشورات سجّل
الدخول مجددا: `python -m src.discover --login`

### قراءة المنشورات: بديل تلقائي

`facebook-cli post read` ما يشوفش المنشورات الجداد (يرجع "post not
available" مع أنها عمومية — تم التحقق في 2026-11-20). لهدا `post_info`
إذا فشل يجرب تلقائيا معلومات yt-dlp لنفس الرابط (العنوان، الوصف،
الناشر، التاريخ) — التحميل والمعالجة يكملوا بلا توقف.

### كيفاش تجيب Page ID

الـ ID ما يبانش في واجهة فيسبوك. الطريقة الصحيحة (Graph ID):
1. في Graph API Explorer، نفّذ `GET /NewsDz9` أو `GET /aljazaer07`
   — الرد فيه الـ `id` الصحيح.
2. أو من `GET /me/accounts` — كل صفحة فيها `id` + `access_token`.
> ⚠️ **ما تستعملش `owner_id` تاع ريل منشور.** الـ ID اللي يرجع من
> `facebook-cli post read` هو الـ profile ID تاع الصفحة، والـ Graph API
> يرفضو (code 100, subcode 33). الـ Graph ID الصحيح للصفحتين راهو
> أصلا في `config.yaml` — ما تحتاجش تجيبو من جديد.

### تجربة حقيقية — 2026-11-20 ✅

| الصفحة | page_id | الريل التجريبي |
|---|---|---|
| NewsDz9 — "News Dz (بلادي أنفو)"، 9.9K متابع | `147624121772177` | https://www.facebook.com/reel/1169537658859941 |
| aljazaer07 — "الجزائر سبعة"، 37K متابع | `107469321989814` | https://www.facebook.com/reel/980161941419171 |

- المقطع الأصلي: Goal Algeria، ريل https://facebook.com/reel/1668308364143510/
  ("ثنائية مازة و حاج موسى 🎩🪄"، 7 ثواني، 720×1280).
- التحميل بـ yt-dlp + الشعار بـ ffmpeg: مجرّب وناجح.
- النشر على NewsDz9 تم 03:10 CET، وعلى aljazaer07 تم 03:47 CET (بعد موافقة
  2FA على جهاز المستخدم). الزوج Public، النص نفسه، والشعار باين أسفل اليمين.
- **ملاحظة عن حقوق النشر:** المستخدم يقول المقاطع من بثوثه المباشرة وأن
  صفحات المصدر تعيد نشرها — هادا كلامه، موش تحقق منا. الشعار ما ينقلش الملكية،
  وفيسبوك يكشف الفيديو المكرر. استعمل المشروع على محتوى عندك حق فيه.

### بنية المشروع

```
├── config.yaml            # المصادر + الوجهات + الإعدادات (عدّلها براحتك)
├── setup.sh / run.sh      # تشغيل بأمر واحد (Linux/macOS)
├── setup.bat / run.bat / dashboard.bat / discover.bat  # ويندوز
├── .dockerignore          # state/ والجلسة و.env ما يدخلوش في صورة Docker
├── src/
│   ├── config.py          # تحميل/حفظ/تحقق من config.yaml + قراءة .env
│   ├── downloader.py      # post read + yt-dlp (fallback)
│   ├── editor.py          # ffmpeg: شعار، قص 9:16، تقليم، loudnorm، صور
│   ├── caption.py         # قالب النص + هاشتاغ + حد 1024 حرف
│   ├── publisher.py       # Graph API (توكن لكل صفحة) أو facebook-cli، مع خطأ واضح للـ Consent
│   ├── tokens.py          # إعداد التوكنات: تحقق من Graph API + كتابة .env (لوحة التحكم)
│   ├── state.py           # seen.json + published.json (منع التكرار، حفظ ذرّي)
│   ├── monitor.py         # معالجة الطابور + إعادة محاولة الفاشل (3 مرات)
│   ├── scheduler.py       # حلقة كل N دقيقة
│   ├── discover.py        # اكتشاف المنشورات من المصادر (Playwright + تسجيل دخول مرة واحدة)
│   ├── diagnostics.py     # فحص النظام (9 فحوصات)
│   ├── stats.py           # إحصائيات المنشورات المنشورة
│   └── dashboard.py       # لوحة تحكم محلية (stdlib فقط، بلا Flask — على 127.0.0.1 فقط، بلا دخول)
├── repost.py / monitor.py / watermark.py   # أغلفة رقيقة للتوافق مع الإصدار القديم
├── tests/                 # اختبارات unittest — python3 -m unittest discover -s tests -v
├── .github/workflows/ci.yml
├── Dockerfile / docker-compose.yml
└── state/                 # طابور + سجل (ما يتنشرش في Git — شوف .gitignore)
```

### الاختبارات

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall src tests repost.py monitor.py watermark.py
```

---

## 🇬🇧 English

### How it works

1. **Pull:** put a post/reel URL in the queue (`state/queue.txt`) or via the
   dashboard. `facebook-cli post read` fetches caption/date/owner, `yt-dlp`
   downloads the video.
2. **Edit:** ffmpeg adds the NEWS OUSSAMA logo bottom-right (194px, 30px
   margin), optionally crops to 9:16, trims duration and normalises audio
   (`loudnorm`) — all from `config.yaml → settings.editor`.
3. **Publish:** one destination at a time, so one failure never duplicates a
   success. Page via the Graph API (the unattended route): a long-lived
   token per Page (`FB_PAGE_ACCESS_TOKEN_<page_id>` in `.env`) — set it
   from the dashboard, **🔑 Page tokens** section (it validates the token
   and saves it, no file download needed). See `docs/get-page-tokens.md`.
   Profile: `facebook-cli post create`; Pages fallback:
   `facebook-cli pages posts create` — but that route asks approval every
   time and usually stalls on Sentinel ("media artifact registration
   requires an attributable caller").
4. **Dedup:** every `post_id` is recorded in `state/seen.json`, every
   successful publish per destination in `state/published.json` — a post is
   never reposted twice.

### Honest limits

- **Facebook offers no public feed/API for pages you do not manage.**
  Tested 2026-11-20 and failed: yt-dlp page/reels listing, RSSHub
  (Cloudflare block), mbasic curl, `facebook-cli pages posts list`
  (managed pages only). Discovery = **paste a post URL** or a **browser
  check** in your own logged-in Chrome.
- **Unattended publishing needs one token per Page.** Publishing with
  `facebook-cli` usually returns `PROFESSIONAL_CONSENT_REQUIRED` or
  stalls on Sentinel — it is not the unattended route. The working
  route is a long-lived Graph API token per Page (from your own NEWS
  OUSSAMA app), pasted in the dashboard → **🔑 Page tokens**.
  **Browser publishing works** (verified on both pages).
- **Page post captions are limited to 1024 chars** — truncated automatically.
- **Copyright check:** Facebook scans the video before publishing; on NewsDz9
  the check was still running at publish time, on aljazaer07 it passed
  ("Your reel is safe to publish!").

### Install

**Linux / macOS:** `git clone https://github.com/123sportdz/news-oussama-auto-repost news-oussama-repost && cd news-oussama-repost && ./setup.sh`
**Windows:** install Python 3.10+ and ffmpeg, add them to PATH, then
`git clone https://github.com/123sportdz/news-oussama-auto-repost news-oussama-repost`, `cd news-oussama-repost`, `.\setup.bat`
(`.\setup.bat --dashboard` for the panel, `.\discover.bat` for discovery).
Then open the dashboard and paste each Page token in **🔑 Page tokens**
(how-to in `docs/get-page-tokens.md`) — without this step, automatic
publishing to the Pages does not work.
**Docker (optional):** `cp .env.example .env && docker compose up --build`
(dashboard: `docker compose --profile dashboard up`, port 8080).

### One-command run

```bash
./setup.sh                 # checks + process the queue once
./setup.sh --url <url>     # queue one post and process it now
./setup.sh --auto          # loop every N minutes (from config.yaml): discover new source posts, then process + publish
./setup.sh --dashboard     # dashboard at http://127.0.0.1:8080
```

### Changing sources / destinations

Use the dashboard (http://127.0.0.1:8080) — add / enable / disable / delete,
edit `page_id`, download the generated `config.yaml` — or edit `config.yaml`
directly (same shape as the Arabic example above).

### How to get a Page ID

The ID is not shown in the Facebook UI. Correct way (Graph ID):
1. In the Graph API Explorer, run `GET /NewsDz9` or `GET /aljazaer07` —
   the response has the correct `id`.
2. Or `GET /me/accounts` — each Page has `id` + `access_token`.
> ⚠️ **Do NOT use a published reel's `owner_id`.** That is the Page's
> *profile* ID, which the Graph API rejects (code 100, subcode 33).
> The correct Graph IDs for both Pages are already in `config.yaml`.

### Verified test reels — 2026-11-20 ✅

| Page | page_id | Test reel |
|---|---|---|
| NewsDz9 — "News Dz (بلادي أنفو)", 9.9K followers | `147624121772177` | https://www.facebook.com/reel/1169537658859941 |
| aljazaer07 — "الجزائر سبعة", 37K followers | `107469321989814` | https://www.facebook.com/reel/980161941419171 |

Original clip: Goal Algeria reel https://facebook.com/reel/1668308364143510/
("ثنائية مازة و حاج موسى 🎩🪄", 7s, 720×1280). yt-dlp download + ffmpeg
watermark verified. Published on NewsDz9 at 03:10 CET and on aljazaer07 at
03:47 CET (after the user's 2FA approval). Both Public, same caption, logo
visible bottom-right.

**Copyright note:** the user states the clips come from his own live
broadcasts and that the source pages repost them — that is his claim, not
our verification. A logo does not transfer ownership, and Facebook detects
duplicate video. Only use this on content you have the right to repost.

### Telegram alerts, autostart, backups, token checks, Graph stats, quality filter

- **Telegram alerts:** create a bot via `@BotFather`, get your chat id
  from `@userinfobot`, paste both in the dashboard ("🔔 تنبيهات
  Telegram") or in `.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
  Silent until both are set.
- **Autostart on Windows:** `.\autostart.bat` registers the auto loop
  at logon; `.\autostart.bat remove` removes it.
- **State backups:** every run backs up `state/` to `backups/` when the
  last backup is older than 24h (keeps 7). Restore:
  `python -m src.backup --restore backups/state-YYYYMMDD-HHMMSS.zip`
  (stop the auto loop first).
- **Daily token check:** stored Page tokens are re-validated once a day;
  a dead token triggers a Telegram alert and shows in the dashboard.
- **Performance stats:** the dashboard refresh reads views/likes/
  comments via the Graph API (works on Windows), falling back to
  `facebook-cli` for the profile.
- **Quality filter:** clips shorter than `editor.min_duration_seconds`
  are skipped (0 = off), settable in the dashboard settings.
- **Download retention:** every run deletes download files of posts
  published everywhere and older than `settings.cleanup.keep_days`
  (default 30, 0 = never). Ready posts and unknown files are never
  touched. Manual run from the dashboard ("🧹 تنظيف الملفات القديمة")
  or `python -m src.cleanup --dry-run`.
- **Dashboard password:** set `DASHBOARD_PASSWORD` in `.env` before
  exposing the port (e.g. via a tunnel); empty keeps the old
  localhost-only trust.
- **Session age in diagnostics:** the dashboard diagnostics show how
  old the Facebook discovery session is and warn past 60 days.

### Tests

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall src tests repost.py monitor.py watermark.py
```

## License

MIT — see [LICENSE](LICENSE).
