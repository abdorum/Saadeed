# ٠٤ — المعمارية الهندسية

> **الحالة:** النسخة 2 — 4 أكتوبر 2026 · **مشتقة من:** [المتطلبات](03-requirements.md) والمبادئ م١٢–م١٦
> **القرارات:** 0001 السداسية · 0002 التقنيات · 0003 النموذج · 0004 الآيات · 0009 الأبعاد · 0010 المصادر · 0011 التجاوز · 0012 النشر
> الرسوم بلغة **Mermaid**، يعرضها GitHub تلقائيًا. والمعرّفات في الكود بالإنجليزية بحسب المسرد.
>
> **ما تغيّر عن النسخة 1:**
> 1. **نشر واحد:** حاوية على HF Spaces تخدم الـ API والواجهة الثابتة معًا. لا Vercel ولا Next.js.
> 2. **منفذ موحّد للمصادر النصية** (`TextSourcePort`) مع **ملف المرجعية المعتمدة** وأدوار المصادر. والكتب الستة من Open-Hadith-Data.
> 3. **الملاحظة بثلاثة أبعاد.** و`LLMPort` بوظيفتين فقط (`extract_claims` و`judge_hadiths`). والشرح من قوالب.

---

## ١. السياق: سديد ومن حوله (المستوى الأول في نموذج C4)

```mermaid
flowchart LR
    U1["👤 الخطيب / المعرِّف"] -->|يضع مسودة| S
    U2["🏢 مؤسسة دعوية"] -->|"API (لاحقًا)"| S
    U3["⚖️ المحكّم"] -->|يجرّب الأمثلة ويعيد التقييم| S
    S(["سديد<br/>مراجِع ما قبل النشر"])
    S -->|استخراج، وحكم بالمعنى والعلاقة| LLM["🤖 نموذج لغوي<br/>Gemini Flash افتراضيًا"]
    S -->|بيانات مبنية مسبقًا + ملف المرجعية| D[("📚 المخزن<br/>المصحف · الكتب الستة · المشتهر")]
    S -.->|رابط بحث فقط| DR["🌐 الدرر السنية"]
```

## ٢. الحاويات والنشر

```mermaid
flowchart LR
    subgraph HF["Hugging Face Spaces (Docker، حاوية واحدة)"]
        WEB["الواجهة الثابتة<br/>HTML + Tailwind + Alpine.js<br/>(RTL) على /"]
        A["HTTP API<br/>FastAPI على /v1"]
        WEB -->|"fetch /v1/reviews"| A
        A --> C["النواة<br/>saadeed (Python 3.12)"]
        C --> DATA[("data/processed + manifest.toml<br/>داخل الصورة")]
        C --> CACHE[("ذاكرة مؤقتة<br/>بحسب بصمة المدخل")]
    end
    C -->|LLMPort| G["Gemini API"]
    M["مراقب إتاحة"] -->|"GET /v1/health كل 10 دقائق"| A
    CLI["CLI<br/>saadeed review"] --> C
    EV["مشغّل التقييم<br/>saadeed eval"] --> C
```

> **مراقب الإتاحة إلزامي:** HF Spaces المجانية تنام بعد 48 ساعة بلا طلبات. والمراقب يبقيها مستيقظة طوال التحكيم (7–22 أكتوبر).

## ٣. المعمارية السداسية (المنافذ والمحوّلات)

```mermaid
flowchart TB
    subgraph IN["محوّلات الدخول — Driving adapters"]
        CLI2[CLI · typer]
        API2["HTTP · FastAPI<br/>+ الواجهة الثابتة"]
        EVAL2[Eval runner]
    end
    subgraph CORE["النواة — لا تعرف العالم الخارجي"]
        UC["ReviewDraft<br/>حالة الاستخدام"]
        V["المتحققات<br/>Quran · Hadith · Sourcing · Wording · Referral"]
        P["ميزان السداد<br/>SeverityPolicy (جدول BR)"]
        G2["حارس الإسناد<br/>CitationGuard"]
        T["النص العربي<br/>تطبيع · تقطيع"]
        PORTS{{"المنافذ — Ports<br/>LLMPort · QuranRepo · TextSourcePort<br/>KnownWeakRepo · ReferenceLinker · Cache"}}
        UC --> V --> P --> G2
        V --> T
        V --> PORTS
        G2 --> PORTS
    end
    subgraph OUT["محوّلات الخروج — Driven adapters"]
        GM[Gemini]
        FK["Fake / Replay"]
        QJ["Tanzil"]
        HJ["Open-Hadith-Data<br/>(كتاب لكل مصدر)"]
        KW["Known-weak JSON"]
        DL["Dorar link builder"]
        MF[["manifest.toml<br/>الأدوار والإصدارات"]]
    end
    IN --> UC
    PORTS --> OUT
    MF -.->|يحدد أي المحوّلات تُفعَّل وبأي دور| HJ
```

**قواعد الاعتماد** (تفرضها أداة `import-linter` في كل بناء):

| الطبقة | تستورد من | لا تستورد أبدًا |
|---|---|---|
| `domain` | المكتبة القياسية وpydantic فقط | أي شيء آخر |
| `text` | `domain` | المحوّلات |
| `verifiers` | `domain`، `text`، `application.ports` | المحوّلات |
| `application` | `domain`، `text`، `verifiers` | المحوّلات |
| `adapters` | أي طبقة | — |

## ٤. نموذج النطاق

```mermaid
classDiagram
    class Claim {
        +str id
        +str text
        +Span span
        +ClaimType type
        +ContentLevel level
        +dict hints  "تنصيص، إحالة مذكورة، نسبة تخريج"
        +Span linked_conclusion  "اختياري"
    }
    class SourceRef {
        +str source_id  "quran / bukhari / abudawud…"
        +str item_id   "2:255 / 1"
        +str citation  "البقرة: ٢٥٥"
        +str url
    }
    class Evidence {
        +SourceRef ref
        +SourceRole role
        +str text  "من المخزن دائمًا"
        +MatchType match_type
        +str match_reason
        +list~DiffOp~ diff
        +list~Span~ highlight
    }
    class Finding {
        +Claim claim
        +EvidenceStatus evidence_status
        +Severity severity
        +Action action
        +Reason reason
        +str rule_id  "BR-xx"
        +list~Evidence~ evidence
        +RelationResult relation  "اختياري (FR-36)"
        +str explanation  "من قالب"
        +str next_step  "من قالب"
        +Confidence confidence
        +bucket() TrackBucket  "محسوب من action"
    }
    class ReviewReport {
        +str schema_version
        +Summary summary
        +list~str~ top_risks
        +list~Finding~ findings
        +Coverage coverage
        +Meta meta  "ومنه بصمة manifest"
    }
    Claim "1" --> "1" Finding : يُفحص فيصير
    Finding "1" --> "*" Evidence
    Evidence --> SourceRef
    ReviewReport "1" --> "*" Finding
```

## ٥. مسار الفحص (تسلسل الاستدعاءات)

```mermaid
sequenceDiagram
    autonumber
    participant In as محوّل الدخول
    participant UC as ReviewDraft
    participant TX as النص العربي
    participant LLM as LLMPort
    participant V as المتحققات
    participant P as ميزان السداد
    participant G as حارس الإسناد
    participant R as المخازن (Repos)
    In->>UC: review(draft_text)
    UC->>TX: segment + normalize
    UC->>LLM: extract_claims(sentences) → JSON بمخطط صارم
    Note over UC,LLM: نداء واحد للمسودة كلها، ويُتحقق من المخطط<br/>وإن فشل يُعاد مرة واحدة، ثم «لم يُفحص»
    UC->>TX: مرور حتمي: ﴿ ﴾ و«قال تعالى» و«قال ﷺ» و«رواه»
    UC->>V: route(claims) بحسب النوع والمستوى
    V->>R: بحث حتمي (الآيات، والمشتهر، والتطابق الحرفي في الكتب الستة)
    opt أحاديث غير محسومة حتميًا، أو لها استنتاج مربوط
        V->>LLM: judge_hadiths(كل الأحاديث + مرشحوها) → {candidate_id, match_type, relation}
        Note over V,LLM: نداء واحد للمسودة. يعيد معرّفات ومواضع، لا نصوصًا
    end
    V-->>UC: نتائج التحقق
    UC->>P: apply(BR table) → evidence_status, severity, action, reason, rule_id
    UC->>UC: القوالب → explanation + next_step
    UC->>G: guard(findings)
    G->>R: get(ref) لكل شاهد
    Note over G,R: النص المعروض يُستبدل بنص المخزن<br/>والمعرّف غير الموجود يُسقط ويُسجَّل
    G-->>UC: findings محروسة
    UC-->>In: ReviewReport 1.0 (ومعه بصمة manifest)
```

## ٦. توجيه الادعاءات إلى المتحققات

```mermaid
flowchart TD
    C["ادعاء"] --> L{"المستوى ج أو د؟<br/>أو حكم على جماعة؟"}
    L -->|نعم| RF["ReferralPolicy → أحِل إلى مختص"]
    L -->|لا| T{"النوع"}
    T -->|QURAN_QUOTE| Q["QuranVerifier (حتمي)"]
    T -->|"HADITH_QUOTE / TAKHRIJ"| H["HadithVerifier"]
    T -->|"ATTRIBUTED_SAYING / STATISTIC / HISTORICAL_EVENT"| S["SourcingVerifier"]
    T -->|"CONSENSUS_CLAIM / GENERALIZATION"| W["WordingVerifier"]
    Q & H & S & W & RF --> POL["ميزان السداد"]
```

## ٧. المتحققان الأساسيان

### ٧.١ مطابق الآيات (حتمي بالكامل، ولا يستدعي النموذج)

```mermaid
flowchart TD
    A["نص مقتبس"] --> N["تطبيع<br/>حذف التشكيل والتطويل وعلامات الوقف<br/>توحيد الألفات · ى→ي · ة→ه · حذف الألف الخنجرية"]
    N --> I["بحث في فهرس n-gram للكلمات<br/>(المصحف بالرسم الإملائي المطبَّع)"]
    I --> C{"مرشحون؟"}
    C -->|لا| NQ["لا مطابقة<br/>→ BR-04 إن قُدِّم آيةً"]
    C -->|نعم| AL["محاذاة كلمة بكلمة على نافذة المرشح<br/>(قد تمتد على آيات متتالية)"]
    AL --> S{"درجة التشابه"}
    S -->|"تطابق تام"| EX["EXACT / NORMALIZED → BR-01"]
    S -->|"جزء من آية"| PA["PARTIAL → BR-01"]
    S -->|"فوق العتبة مع فروق"| MM["TEXT_MISMATCH + diff → BR-02"]
    S -->|"تحت العتبة"| NQ
    EX & PA --> RC{"إحالة مذكورة؟"}
    RC -->|"نعم وتخالف"| WR["WRONG_REFERENCE → BR-03"]
```

- **العرض:** المطابقة على النص الإملائي المطبَّع، وعرض الآية للمستخدم **بالرسم العثماني من المخزن**.
- **العتبات** تُضبط على مجموعة التطوير فقط.
- **quran-detector** (MIT): يُجرَّب ساعة في T-106 كاشفًا للآيات غير المعلَّمة. والمحاذاة والفرق من كودنا في كل الأحوال.

### ٧.٢ متحقق الأحاديث

```mermaid
flowchart TD
    A["نص حديث + نسبة مذكورة؟"] --> K{"في قائمة المشتهر؟<br/>(تطابق تقريبي)"}
    K -->|نعم| KW["KNOWN_WEAK + الحكم بلفظه ورابطه → BR-05"]
    K -->|لا| SUB{"جزء حرفي بعد التطبيع<br/>في مصدر AUTHENTIC أو LOCATE؟"}
    SUB -->|نعم| ROLE
    SUB -->|لا| RET["استرجاع top-5 من كل المصادر<br/>(BM25 على n-gram الحروف)"]
    RET --> J["الحَكَم (نداء واحد للمسودة)<br/>لفظ · بالمعنى · لا يطابق<br/>يرى المرشحين فقط، ويعيد معرّفًا"]
    J -->|لفظ أو معنى| ROLE{"دور المصدر الذي وُجد فيه"}
    J -->|لا يطابق| NF["NOT_FOUND + رابط الدرر → BR-11"]
    ROLE -->|LOCATE وحده| FN["FOUND_NO_RULING + الموضع + رابط الدرر → BR-10"]
    ROLE -->|AUTHENTIC| MT{"بالمعنى ويُقدَّم لفظًا؟"}
    MT -->|نعم| PW["PARAPHRASED_AS_WORDING → BR-07"]
    MT -->|لا| AT{"نسبة مذكورة تخالف الكتاب؟"}
    AT -->|نعم| MA["MISATTRIBUTED → BR-09"]
    AT -->|لا| SU["مؤيَّد → BR-06 / BR-08"]
    SU -.->|"له استنتاج مربوط (S)"| REL["العلاقة من الحَكَم نفسه<br/>EXCEEDS → BR-19 (ملاحظة مستقلة)"]
```

## ٨. المنافذ (Ports)، بالتوقيعات لا بالتنفيذ

| المنفذ | الوظائف | المحوّلات |
|---|---|---|
| `LLMPort` | `extract_claims(sentences) → ClaimSet` · `judge_hadiths(items) → list[Judgment]` | Gemini، وFake (للاختبارات)، وReplay (للتقييم) |
| `QuranRepo` | `search(normalized_tokens) → candidates` · `get(ref) → Ayah` | Tanzil |
| `TextSourcePort` | `search(text, k) → candidates` · `find_substring(normalized) → hits` · `get(item_id) → Passage` · `info → SourceInfo(role, version…)` | `OpenHadithSource` (مثيل لكل كتاب). ولاحقًا: كتاب نصي محلي، وMCP |
| `KnownWeakRepo` | `match(text) → KnownWeak?` | JSON منتقى |
| `ReferenceLinker` | `search_url(text) → url` | رابط بحث الدرر |
| `Cache` | `get/put(key)` | ذاكرة، وملفات (تسجيلات الإعادة) |

**ملف المرجعية** (`data/manifest.toml`) يُقرأ عند الإقلاع:
- يحدد أي المحوّلات تُفعَّل، وبأي دور.
- وتُحسب بصمته وتُوضع في `meta` كل تقرير.
- ويُبنى منه `GET /v1/coverage` وصفحة التغطية.

```toml
# مثال مختصر
[manifest]
id = "saadeed-2026.10-v1"

[[source]]
id = "bukhari"
name_ar = "صحيح البخاري"
role = "AUTHENTIC"
adapter = "open_hadith"
file = "data/processed/bukhari.json"
sha256 = "…"
license = "ODbL-1.0 (Open-Hadith-Data)"
reviewed_by = "محمد عبدالرحمن"

[[source]]
id = "abudawud"
name_ar = "سنن أبي داود"
role = "LOCATE"
# … والبقية
```

## ٩. منظومة التقييم

```mermaid
flowchart LR
    BANK[("بنك الاختبار<br/>dev / test · jsonl")] --> RUN["مشغّل التقييم<br/>systems × runs"]
    GEN["مولّدات الحالات<br/>(آيات وأحاديث بتحوير برمجي)"] --> BANK
    RUN --> S1["سديد"]
    RUN --> S2["B0 — النموذج العام"]
    RUN --> S3["B1 — سديد دون المطابق الحتمي"]
    S1 & S2 & S3 --> REC[("تسجيلات الاستجابات")]
    REC -->|replay| RUN
    S1 & S2 & S3 --> MET["المقاييس + McNemar + Bootstrap"]
    MET --> REP["eval/reports/*.md · *.json"]
    REP --> PAGE["صفحة: كيف نعرف أن سديد يعمل؟"]
    REP --> ERR["ERRORS.md"]
```

التفاصيل في [بروتوكول التقييم](05-evaluation-protocol.md).

## ١٠. بناء البيانات

```mermaid
flowchart LR
    R1["Tanzil: إملائي بسيط + عثماني<br/>(CC BY 3.0، دون تعديل)"] --> B["data/build/*.py<br/>تنزيل · تحقق من البصمة · فهرسة"]
    R2["Open-Hadith-Data: الكتب الستة<br/>(ODbL)"] --> B
    R3["قائمة المشتهر<br/>(يعتمدها محمد + روابط الدرر)"] --> B
    B --> P[("data/processed/*.json")]
    B --> MF["data/manifest.toml<br/>الأدوار · الإصدارات · البصمات"]
    B --> SRC["data/SOURCES.md<br/>المصدر · الرخصة · النسبة"]
    P --> T["عيّنة الـ20 مقابل الدرر<br/>(النص والترقيم)"]
```

- **نص Tanzil يُحفظ كما هو.** والتطبيع والفهارس تُحسب عند التحميل، فلا نكتب فوق النص (شرط الرخصة).
- **Open-Hadith-Data:** نأخذ عمود الحديث من النسخة المشكولة للعرض، ومن غير المشكولة للبحث. ونحذف علامات الاتجاه (U+200F) والمسافات المزدوجة. ونترك الشرح.

## ١١. بنية المستودع

```
saadeed/
├─ pyproject.toml            ← uv · Python 3.12 · ruff · pytest · import-linter
├─ src/saadeed/
│  ├─ domain/                ← models.py · enums.py · policy.py (ميزان السداد) · templates.py
│  ├─ text/                  ← normalize.py · segment.py
│  ├─ verifiers/             ← quran.py · hadith.py · sourcing.py · wording.py · referral.py
│  ├─ application/           ← ports.py · review_draft.py · citation_guard.py · manifest.py
│  └─ adapters/
│     ├─ llm/                ← gemini.py · fake.py · replay.py
│     ├─ sources/            ← tanzil.py · open_hadith.py · known_weak.py · dorar_links.py
│     ├─ cache/
│     ├─ cli/                ← typer
│     └─ api/                ← fastapi (ويخدم web/)
├─ web/                      ← index.html · report.html · coverage.html · results.html · assets/
├─ prompts/                  ← extract_v1.md · judge_hadiths_v1.md · baseline_v1.md (مُصدَّرة برقم)
├─ data/                     ← raw/ · build/ · processed/ · manifest.toml · SOURCES.md
├─ eval/                     ← bank/ · generators/ · systems/ · recordings/ · reports/ · ERRORS.md
├─ tests/                    ← unit/ · contract/ (عقود المنافذ)
├─ docs/
├─ Dockerfile · README.md · CLAUDE.md · LICENSE (MIT للكود) · data/LICENSE (ODbL للبيانات المشتقة)
```

## ١٢. تكلفة النموذج لكل مسودة (تقدير يُستبدل بالقياس)

| النداء | العدد | ملاحظة |
|---|---|---|
| استخراج الادعاءات | 1 | المسودة كلها في نداء واحد |
| الحَكَم (الأحاديث + التجاوز) | 0–1 | كل الأحاديث غير المحسومة حتميًا في نداء واحد |
| الشرح | 0 | من قوالب (ADR-0009) |
| **المجموع** | **1–2** | الآيات والمشتهر والتطابق الحرفي والسياسة بلا نموذج |

---

## الخلاصة (للمراجعة السريعة)

- **نواة سداسية لا تعرف العالم الخارجي.** و`import-linter` يفرض ذلك.
- **رابط واحد:** حاوية على HF Spaces تخدم الواجهة الثابتة والـ API معًا، ومراقب إتاحة يبقيها مستيقظة.
- **النموذج في موضعين فقط**، وكلاهما يعيد **معرّفات ومواضع** لا نصوصًا:
  1. الاستخراج.
  2. الحَكَم على الأحاديث غير المحسومة وعلاقة الاستنتاج بها.
- **ما عدا ذلك حتمي:** الآيات، والمشتهر، والتطابق الحرفي، وميزان السداد، والقوالب.
- **المصادر خلف منفذ واحد بأدوار معلنة** في ملف المرجعية. وإضافة كتاب = محوّل أو سطر، دون مساس بالنواة.
- **نداء أو نداءان لكل مسودة.**
