# صور سديد ومصادرها

| الملف | ما هو | مصدره |
|---|---|---|
| `logo.svg` | الشعار: النجمة الهادية ذهبية على الكحلي | يُحرَّر مباشرة |
| `pipeline.png` | مسار المراجعة: المحطات الثماني، ومثال يمر بها | `src/pipeline.html` |
| `core-architecture.png` | بنية النواة: الطبقات، والمنافذ، والمحوّلات، والمحطات الثماني | صورة جاهزة |
| `social-preview.png` | صورة المعاينة (1280×640) في إعدادات المستودع على GitHub | `src/social-preview.html` |

**الألوان والخطوط من هوية الصفحة نفسها** (`web/assets/app.css`):
- الألوان: الكحلي `#0B2542`، والرَّقّ `#F5E7D0`، وذهبي النجمة `#E2B456` للشعار وحده.
- الخطوط: Amiri للشعار والعناوين، وIBM Plex Sans Arabic للنص، وكلاهما بترخيص SIL OFL.

**إعادة الرسم:**
```bash
cd docs/assets/src
uv run --with playwright playwright install chromium          # مرة واحدة
uv run --with playwright python render.py pipeline.html ../pipeline.png 1300 1000 2 transparent
uv run --with playwright python render.py social-preview.html ../social-preview.png 1280 640 1
```

ثم قُلّصت الصور إلى لوحة من 256 لونًا، فصارت ربع حجمها بلا فرق مرئي.
