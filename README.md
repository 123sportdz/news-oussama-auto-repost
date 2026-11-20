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
   - صفحة: `facebook-cli pages posts create --page-id <id> --text "..." --privacy PUBLIC --file <mp4>`
     (فيديو واحد MP4 في صفحة = Reel)
   - بروفايل: `facebook-cli post create --message "..." --file <mp4>`
   - أو عبر Graph API إذا عيّنت `FB_PAGE_ACCESS_TOKEN` في `.env`.
4. **منع التكرار (Dedup):** كل `post_id` يتسجّل في `state/seen.json` بعد
   المعالجة، وكل نشر ناجح يتسجّل في `state/published.json` لكل وجهة —
   منشور واحد ما يتنشرش مرتين أبدا.

### الحدود الصادقة — اقراها قبل ما تتوقع السحر

- **فيسبوك ما يعطيش Feed/API عام لصفحات ماشي تاعك.** جرّبنا في 2026-11-20
  وفشل: `yt-dlp` لقائمة صفحة/ريلز، RSSHub (حجب Cloudflare)، mbasic curl،
  و `facebook-cli pages posts list` (للصفحات المدارة برك). الاكتشاف يكون
  بـ **رابط منشور تلصقو** أو **فحص بالمتصفح** (Chrome تاعك، مسجّل فيه).
- **النشر عبر API يحتاج Professional Consent.** كل أمر `pages` يرجّع
  `PROFESSIONAL_CONSENT_REQUIRED` حتى يوافق مدير الصفحة داخل فيسبوك.
  **النشر من المتصفح يخدم** (مجرّب على الصفحتين — شوف "تجربة حقيقية" تحت).
- **النص محدود بـ 1024 حرف** في منشور الصفحة — المشروع يقصّر تلقائيا.
- **فحص حقوق النشر:** فيسبوك يفحص الفيديو قبل النشر؛ في تجربة NewsDz9 الفحص
  كان مازال جاري وقت النشر، وفي aljazaer07 تعدّى ("Your reel is safe to publish!").

### التثبيت

**Linux / macOS:**
```bash
git clone <repo-url> news-oussama-repost
cd news-oussama-repost
./setup.sh            # يفحص python/ffmpeg/yt-dlp، يثبّت المكتبات، يتحقق من الإعدادات
```

**Windows:**
```powershell
# ثبّت Python 3.10+ من python.org، و ffmpeg من https://ffmpeg.org/download.html
# (وأضفهم للـ PATH)، بعدها:
git clone <repo-url> news-oussama-repost
cd news-oussama-repost
.\setup.bat
```
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
./setup.sh --auto          # حلقة دورية كل N دقيقة (من config.yaml)
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
- **أو يدويا** في `config.yaml`:
```yaml
sources:
  - url: https://www.facebook.com/goalalgeria16
    name: Goal Algeria
    enabled: true
destinations:
  - url: https://www.facebook.com/NewsDz9
    name: NewsDz9
    page_id: '61552757798044'
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

### كيفاش تجيب Page ID

الـ ID ما يبانش في واجهة فيسبوك. الطريقة المجرّبة:
1. انشر أي ريل/منشور على الصفحة من المتصفح (مرة واحدة).
2. اقرا المنشور: `facebook-cli post read --url <رابط الريل>`
3. `owner_id` اللي يرجع **هو الـ page_id** — عمّرو في `config.yaml`.

### تجربة حقيقية — 2026-11-20 ✅

| الصفحة | page_id | الريل التجريبي |
|---|---|---|
| NewsDz9 — "News Dz (بلادي أنفو)"، 9.9K متابع | `61552757798044` | https://www.facebook.com/reel/1169537658859941 |
| aljazaer07 — "الجزائر سبعة"، 37K متابع | `100083258325099` | https://www.facebook.com/reel/980161941419171 |

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
├── setup.sh / run.sh      # تشغيل بأمر واحد
├── src/
│   ├── config.py          # تحميل/حفظ/تحقق من config.yaml
│   ├── downloader.py      # post read + yt-dlp
│   ├── editor.py          # ffmpeg: شعار، قص 9:16، تقليم، loudnorm، صورة غلاف
│   ├── caption.py         # قالب النص + هاشتاغ + حد 1024 حرف
│   ├── publisher.py       # Graph API (token) أو facebook-cli، مع خطأ واضح للـ Consent
│   ├── state.py           # seen.json + published.json (منع التكرار)
│   ├── monitor.py         # معالجة الطابور
│   ├── scheduler.py       # حلقة كل N دقيقة
│   └── dashboard.py       # لوحة تحكم محلية (stdlib فقط، بلا Flask)
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
   success. Page: `facebook-cli pages posts create` (one MP4 = a Reel);
   profile: `facebook-cli post create`; or Graph API with
   `FB_PAGE_ACCESS_TOKEN` in `.env`.
4. **Dedup:** every `post_id` is recorded in `state/seen.json`, every
   successful publish per destination in `state/published.json` — a post is
   never reposted twice.

### Honest limits

- **Facebook offers no public feed/API for pages you do not manage.**
  Tested 2026-11-20 and failed: yt-dlp page/reels listing, RSSHub
  (Cloudflare block), mbasic curl, `facebook-cli pages posts list`
  (managed pages only). Discovery = **paste a post URL** or a **browser
  check** in your own logged-in Chrome.
- **Page API publishing needs Professional Consent.** Every `pages` command
  returns `PROFESSIONAL_CONSENT_REQUIRED` until the Page admin approves it
  inside Facebook. **Browser publishing works** (verified on both pages).
- **Page post captions are limited to 1024 chars** — truncated automatically.
- **Copyright check:** Facebook scans the video before publishing; on NewsDz9
  the check was still running at publish time, on aljazaer07 it passed
  ("Your reel is safe to publish!").

### Install

**Linux / macOS:** `git clone <repo-url> && cd news-oussama-repost && ./setup.sh`
**Windows:** install Python 3.10+ and ffmpeg, add them to PATH, then
`pip install -r requirements.txt` and `python monitor.py`.
**Docker (optional):** `cp .env.example .env && docker compose up --build`
(dashboard: `docker compose --profile dashboard up`, port 8080).

### One-command run

```bash
./setup.sh                 # checks + process the queue once
./setup.sh --url <url>     # queue one post and process it now
./setup.sh --auto          # loop every N minutes (from config.yaml)
./setup.sh --dashboard     # dashboard at http://127.0.0.1:8080
```

### Changing sources / destinations

Use the dashboard (http://127.0.0.1:8080) — add / enable / disable / delete,
edit `page_id`, download the generated `config.yaml` — or edit `config.yaml`
directly (same shape as the Arabic example above).

### How to get a Page ID

The ID is not shown in the Facebook UI. Proven method:
1. Publish any reel/post on the Page once, from the browser.
2. Read it: `facebook-cli post read --url <reel url>`
3. The returned `owner_id` **is the page_id** — put it in `config.yaml`.

### Verified test reels — 2026-11-20 ✅

| Page | page_id | Test reel |
|---|---|---|
| NewsDz9 — "News Dz (بلادي أنفو)", 9.9K followers | `61552757798044` | https://www.facebook.com/reel/1169537658859941 |
| aljazaer07 — "الجزائر سبعة", 37K followers | `100083258325099` | https://www.facebook.com/reel/980161941419171 |

Original clip: Goal Algeria reel https://facebook.com/reel/1668308364143510/
("ثنائية مازة و حاج موسى 🎩🪄", 7s, 720×1280). yt-dlp download + ffmpeg
watermark verified. Published on NewsDz9 at 03:10 CET and on aljazaer07 at
03:47 CET (after the user's 2FA approval). Both Public, same caption, logo
visible bottom-right.

**Copyright note:** the user states the clips come from his own live
broadcasts and that the source pages repost them — that is his claim, not
our verification. A logo does not transfer ownership, and Facebook detects
duplicate video. Only use this on content you have the right to repost.

### Tests

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall src tests repost.py monitor.py watermark.py
```

## License

MIT — see [LICENSE](LICENSE).
