# دليل التوسعة: كيف تضيف إلى سديد دون أن تكسره

> **الضمان هنا اختبار لا وعد:** `tests/unit/test_extensibility.py` يفشل إن أضفت نوعًا أو صنفًا أو قاعدة أو دورًا ونسيت توصيله في إحدى الطبقات. فالتوسعة الناقصة لا تمر من بوابة الـ commit.
>
> **القاعدة الذهبية:** النواة (`domain`، `text`، `verifiers`، `application`) لا تعرف شيئًا عن العالم الخارجي، وتفرض ذلك أداة `import-linter`. وكل ما يلمس مصدرًا أو نموذجًا أو شبكة محوّل في `adapters/`.

## ١. إضافة مصدر أو استبداله («وصلة»)
المصادر وصلات خلف منافذ ثابتة. **فصل مصدر أو تغيير دوره لا يحتاج كودًا:**

```toml
# data/manifest.toml
[[source]]
id = "tirmidhi"
adapter = "open_hadith"      # أي محوّل ينفّذ المنفذ
role = "LOCATE"              # ما يجوز للمصدر أن يقرره: REFERENCE_TEXT · AUTHENTIC · RULING · LOCATE · LINK
name_ar = "جامع الترمذي"
files = ["processed/tirmidhi.json"]
version = "…"
license = "…"
```

- **احذف الكتلة** ← فُصل المصدر.
- **غيّر `role`** ← تغيّر ما يجوز له أن يقرره. مثلًا من `LOCATE` إلى `LINK` يجعله رابطًا فقط.
- **كل تقرير يحمل بصمة الملف**، فيُعرف بماذا فُحصت كل مسودة.

**ولمصدر بصيغة جديدة:**
1. اكتب محوّلًا في `src/saadeed/adapters/sources/` ينفّذ المنفذ المناسب في `domain/ports.py`:
   - `QuranRepo` للمصحف.
   - `TextSourcePort` لكتاب حديث.
   - `KnownWeakRepo` لمصدر أحكام منقولة.
   - `ReferenceLinker` لروابط البحث.
2. سجّله باسمه في `adapters/bootstrap.py` (`load_sources`).
3. أضف كتلته في `data/manifest.toml`، وأمر تنزيله إن لزم في `adapters/sources/build.py`.
4. أضف اختبار عقد في `tests/contract/`.

> **شرط المصدر الشرعي:** أن يكون مسمّى في الحزمة العلمية للمسابقة أو معتمدًا من مختص، وأن تُعلن رخصته.

## ٢. إضافة نوع ادعاء جديد (مثلًا: «دعاء مأثور»)
1. **المسرد أولًا** (`docs/planning/10-glossary.md`): الاسم الفصيح، والمعرّف، وما ليس هو.
2. `domain/enums.py`: القيمة في `ClaimType` وتسميتها في `_LABEL_PAIRS`.
3. **مساره** في `application/review_draft.py` (`_route`): أي متحقق يفحصه، وأي إشارة يعطي.
4. **تعليمات الاستخراج:** نسخة جديدة `prompts/extract_vN.md` (لا تُعدَّل نسخة قائمة)، ثم تقييم dev وتسجيل أي تراجع في `eval/ERRORS.md`.
5. **حالات اختبار** للفئة في البنك، وتسجيل التعديل في البروتوكول §١٢ قبل تجميد test.

## ٣. إضافة قاعدة إلى «ميزان السداد»
1. `domain/policy.py`: إشارة جديدة في `Signal`، وصفها في `RULES` (الحالة والسبب والأثر والإجراء).
2. `domain/templates.py`: قالب الشرح وقالب الخطوة التالية **بالمعرّف نفسه** (`BR-NN`).
3. **صف في جدول المتطلبات** §٥.١، ويراجعه المرشد الشرعي.
4. وصفها في `tests/unit/test_policy_templates.py`.

## ٤. إضافة صنف إلى «خريطة المسودة»
1. `domain/enums.py`: القيمة في `SegmentKind` وتسميتها.
2. لونها في `web/assets/app.css` (`--k-<الصنف>`)، ومفتاحها في `KIND_VAR` في `web/assets/app.js`.
3. سطرها في تعليمات الاستخراج (نسخة جديدة).

## ٥. إضافة مزود نموذج
محوّل في `adapters/llm/` ينفّذ `LLMPort.generate_json`. ثم سطر في `adapters/factory.py`. **ثم:** `SAADEED_LLM_PROVIDER=…` في `.env`، **ولا تعديل في النواة.**

## بوابة كل تغيير
```bash
uv run pytest -q && uv run ruff check src tests && uv run lint-imports
```
