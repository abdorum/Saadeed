#!/usr/bin/env bash
# نشر سديد على Hugging Face Spaces بأمر واحد (ADR-0012، T-203).
#
# المطلوب في .env (لا يُرفع شيء منه إلى GitHub):
#   HF_TOKEN=hf_...            رمز بصلاحية كتابة (huggingface.co/settings/tokens)
#   HF_SPACE=user/saadeed      اسم المساحة
#   GEMINI_API_KEY=...         مفتاح النموذج الافتراضي (gemini-3.5-flash-lite)، يُضاف سرًّا في المساحة
#   GROQ_API_KEY=...           (اختياري) بديل
#
# الاستعمال:  bash deploy/deploy_hf.sh
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
: "${HF_TOKEN:?ضع HF_TOKEN في .env}"
: "${HF_SPACE:?ضع HF_SPACE في .env (مثل user/saadeed)}"
API=https://huggingface.co/api
AUTH="Authorization: Bearer ${HF_TOKEN}"
NAME="${HF_SPACE#*/}"; OWNER="${HF_SPACE%%/*}"

echo "١) إنشاء المساحة ${HF_SPACE} (إن لم توجد)…"
WHO=$(curl -s -H "$AUTH" "$API/whoami-v2" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("name",""))')
ORG_JSON=""; [ "$OWNER" != "$WHO" ] && ORG_JSON=",\"organization\":\"$OWNER\""
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"type\":\"space\",\"name\":\"$NAME\",\"sdk\":\"docker\",\"private\":false$ORG_JSON}" "$API/repos/create")
echo "   الحالة: $code (409 = موجودة مسبقًا)"

echo "٢) إضافة الإعداد والمفاتيح أسرارًا في المساحة…"
put_secret() {
  curl -s -o /dev/null -w "   $1: %{http_code}\n" -X POST -H "$AUTH" -H "Content-Type: application/json" \
    -d "{\"key\":\"$1\",\"value\":\"$2\"}" "$API/spaces/${HF_SPACE}/secrets"
}
put_secret SAADEED_LLM_PROVIDER "${SAADEED_LLM_PROVIDER:-gemini}"
put_secret SAADEED_LLM_MODEL "${SAADEED_LLM_MODEL:-gemini-3.5-flash-lite}"
[ -n "${GEMINI_API_KEY:-}" ] && put_secret GEMINI_API_KEY "$GEMINI_API_KEY"
[ -n "${GROQ_API_KEY:-}" ] && put_secret GROQ_API_KEY "$GROQ_API_KEY"

echo "٣) تجهيز نسخة النشر من آخر commit…"
TMP=$(mktemp -d)
git archive HEAD Dockerfile .dockerignore pyproject.toml uv.lock LICENSE src prompts web \
  data/manifest.toml data/manifest.tanzil.toml data/known_weak.json data/vendor data/SOURCES.md \
  eval/reports/dev_v4c_saadeed-B0.json | tar -x -C "$TMP"
{
  printf -- '---\ntitle: سديد\nemoji: 📖\ncolorFrom: green\ncolorTo: red\nsdk: docker\napp_port: 7860\npinned: false\nlicense: mit\nshort_description: مراجِع ما قبل النشر للمسودات الدعوية العربية\n---\n\n'
  cat README.md
} > "$TMP/README.md"

echo "٤) الدفع إلى المساحة…"
cd "$TMP"
git init -q -b main && git add -A && git -c user.name=saadeed -c user.email=deploy@saadeed.local commit -q -m "deploy: $(date -u +%FT%TZ)"
git push -q -f "https://user:${HF_TOKEN}@huggingface.co/spaces/${HF_SPACE}" main
cd - >/dev/null && rm -rf "$TMP"
echo "✓ دُفع. البناء يستغرق بضع دقائق: https://huggingface.co/spaces/${HF_SPACE}"
echo "  والرابط المباشر: https://${OWNER//_/-}-${NAME//_/-}.hf.space"
