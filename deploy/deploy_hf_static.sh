#!/usr/bin/env bash
# نشر واجهة سديد على Hugging Face Space ثابتة (مجانية)، والمعالجة على الخادم.
# Docker Spaces المجانية صارت تتطلب PRO (أكتوبر 2026)، فالواجهة وحدها على HF،
# وهي تنادي الـ API على SAADEED_API_URL (يسمح بها CORS في app.py).
# وإن تعذّر الخادم بقيت الصفحة تعرض الأمثلة المحفوظة وأسئلة «كيف نعرف».
#
# المطلوب في .env:
#   HF_TOKEN=hf_...            رمز بصلاحية كتابة
#   HF_SPACE=user/saadeed      اسم المساحة
#   SAADEED_API_URL=https://example.org/saadeed/   (اختياري؛ هذا الافتراضي أدناه)
#
# الاستعمال:  bash deploy/deploy_hf_static.sh
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
: "${HF_TOKEN:?ضع HF_TOKEN في .env}"
: "${HF_SPACE:?ضع HF_SPACE في .env (مثل user/saadeed)}"
API_URL="${SAADEED_API_URL:-https://ibnadam.duckdns.org/saadeed/}"
API=https://huggingface.co/api
AUTH="Authorization: Bearer ${HF_TOKEN}"
NAME="${HF_SPACE#*/}"; OWNER="${HF_SPACE%%/*}"

echo "١) إنشاء المساحة الثابتة ${HF_SPACE} (إن لم توجد)…"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"type\":\"space\",\"name\":\"$NAME\",\"sdk\":\"static\",\"private\":false}" "$API/repos/create")
echo "   الحالة: $code (409 = موجودة مسبقًا)"

echo "٢) تجهيز الواجهة من آخر commit، والـ API: ${API_URL}"
TMP=$(mktemp -d)
git archive HEAD:web | tar -x -C "$TMP"
git show HEAD:LICENSE > "$TMP/LICENSE"
python3 - "$TMP/index.html" "$API_URL" <<'EOF'
import sys
p, url = sys.argv[1], sys.argv[2]
s = open(p, encoding="utf-8").read()
tag = f'<meta name="saadeed-api" content="{url}">\n'
assert '<meta charset="utf-8">\n' in s
open(p, "w", encoding="utf-8").write(s.replace('<meta charset="utf-8">\n', '<meta charset="utf-8">\n' + tag, 1))
EOF
{
  printf -- '---\ntitle: سديد\nemoji: 📖\ncolorFrom: green\ncolorTo: red\nsdk: static\napp_file: index.html\npinned: false\nlicense: mit\nshort_description: مراجِع ما قبل النشر للمسودات الدعوية العربية\n---\n\n'
  git show HEAD:README.md
} > "$TMP/README.md"

echo "٣) الدفع إلى المساحة…"
cd "$TMP"
git init -q -b main && git add -A && git -c user.name=saadeed -c user.email=deploy@saadeed.local commit -q -m "deploy: $(date -u +%FT%TZ)"
git push -q -f "https://user:${HF_TOKEN}@huggingface.co/spaces/${HF_SPACE}" main
cd - >/dev/null && rm -rf "$TMP"
SUB="$(echo "${OWNER}-${NAME}" | tr 'A-Z_.' 'a-z--')"
echo "✓ دُفع: https://huggingface.co/spaces/${HF_SPACE}"
echo "  والرابط المباشر: https://${SUB}.static.hf.space"
