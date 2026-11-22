#!/bin/bash
# NEWS OUSSAMA Auto Repost — تشغيل بضغطة واحدة
#   ./setup.sh              — يفحص كلش، ويشغّل المراقبة مرة واحدة
#   ./setup.sh --url <رابط>  — يضيف منشور ويعالجو فورا
#   ./setup.sh --auto       — يشغّل المراقبة في حلقة كل N دقيقة (Ctrl+C للإيقاف)
#   ./setup.sh --dashboard — يشغّل لوحة التحكم على http://127.0.0.1:8080
set -u
cd "$(dirname "$0")"
echo "== NEWS OUSSAMA Auto Repost — فحص الجاهزية =="
fail=0
check() { if eval "$2" >/dev/null 2>&1; then echo "  ✅ $1"; else echo "  ❌ $1 — $3"; fail=1; fi; }

check "Python 3" "python3 --version" "ثبّت Python 3.10+"
check "ffmpeg" "command -v ffmpeg" "ثبّت ffmpeg (https://ffmpeg.org/download.html)"
check "yt-dlp" "python3 -m yt_dlp --version" "سيتم تثبيته من requirements.txt"
check "config.yaml" "test -f config.yaml" "الملف ناقص"
check "الشعار" "test -f assets/watermark-320.png" "الملف ناقص"

echo ""
echo "== تثبيت المكتبات =="
python3 -m pip install --quiet -r requirements.txt \
  || python3 -m pip install --quiet --break-system-packages -r requirements.txt \
  || { echo "  ❌ فشل تثبيت المكتبات — جرّب يدويا: pip install -r requirements.txt"; fail=1; }

echo ""
echo "== فيسبوك =="
if command -v facebook-cli >/dev/null 2>&1 || [ -x /opt/hatch/bin/facebook-cli ]; then
  CLI="${FACEBOOK_CLI:-/opt/hatch/bin/facebook-cli}"
  command -v facebook-cli >/dev/null 2>&1 && CLI="facebook-cli"
  if me_out=$("$CLI" me 2>/dev/null) && [ -n "$me_out" ]; then
    echo "  ✅ مربوط: $(echo "$me_out" | head -c 120)"
  else
    echo "  ⚠️  facebook-cli موجود بصح الحساب ماشي مربوط — اربطو أولا"
  fi
  if "$CLI" pages list 2>&1 | grep -q PROFESSIONAL_CONSENT_REQUIRED; then
    echo "  ⚠️  الصفحات: Professional Consent مازال ناقص"
    echo "     النشر عبر API محبوس حتى توافق عليه. البديل: النشر من المتصفح (Chrome تاعك)"
    echo "     المعالجة (تحميل + شعار + تجهيز) تخدم عادي — النشر يبقى معلّق حتى توافق على Consent."
  else
    echo "  ✅ الصفحات: قائمة الصفحات تتقرا"
  fi
else
  echo "  ⚠️  facebook-cli ماشي مثبّت على هاد الجهاز — نشر البروفايل غير متاح هنا"
  echo "     نشر الصفحات يخدم عبر Graph API بتوكنات الصفحات (ما يحتاجش facebook-cli)"
  echo "     (الأسهل: لوحة التحكم ← 🔑 توكنات الصفحات — الصق التوكن ويتحفظ وحدو)"
fi
echo ""
if [ "$fail" = "1" ]; then echo "الفحص فيه نواقص (شوف ❌ فوق)، بصح المعالجة (تحميل + شعار + تجهيز) تقدر تكمل عادي."; fi

case "${1:-}" in
  --auto)
    echo "== وضع أوتوماتيكي: فحص دوري (Ctrl+C للإيقاف) =="
    exec python3 -m src.scheduler
    ;;
  --dashboard)
    echo "== لوحة التحكم: http://127.0.0.1:8080 =="
    exec python3 -m src.dashboard
    ;;
  *)
    python3 monitor.py "$@"
    ;;
esac
