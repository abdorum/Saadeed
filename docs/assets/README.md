# صور سديد ومصادرها

| الملف | ما هو | مصدره |
|---|---|---|
| `logo.svg` | الشعار: «سديد» بخط Aref Ruqaa على اللازوردي، والحروف مسارات فلا يحتاج عرضه إلى الخط | `src/logo.py` |
| `architecture.png` | بنية سديد: النواة وطبقاتها، والمنافذ، والمحوّلات | `src/architecture.html` |
| `pipeline.png` | مسار المراجعة: المحطات الثماني، ومثال يمر بها | `src/pipeline.html` |
| `screenshot-report.png` | لقطة حقيقية من الصفحة المنشورة: مثال «خطبة قصيرة»، والحاشية الأولى مفتوحة | المتصفح |
| `social-preview.png` | صورة المعاينة (1280×640) في إعدادات المستودع على GitHub | `src/social-preview.html` |

**الألوان والخطوط من هوية الصفحة نفسها** (`web/assets/app.css`):
- الألوان: اللازوردي `#1F3A63`، والذهبي `#B8913F` للزخرفة وحدها، والرَّقّ `#F0E8D6`.
- الخطوط: IBM Plex Sans Arabic للنص، وAref Ruqaa للشعار، وكلاهما بترخيص SIL OFL.

**إعادة الرسم:**
```bash
cd docs/assets/src
uv run --with playwright playwright install chromium          # مرة واحدة
uv run --with playwright python render.py architecture.html ../architecture.png 1300 1000 2 transparent
uv run --with playwright python render.py pipeline.html ../pipeline.png 1300 1000 2 transparent
uv run --with playwright python render.py social-preview.html ../social-preview.png 1280 640 1
uv run --with fonttools --with uharfbuzz python logo.py ArefRuqaa-Bold.ttf ../logo.svg
```

ثم قُلّصت الصور إلى لوحة من 256 لونًا، فصارت ربع حجمها بلا فرق مرئي.
