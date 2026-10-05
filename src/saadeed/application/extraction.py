"""الاستخراج: نداء النموذج على المسودة (أو على أجزائها إن طالت)، ثم الدمج مع المرور الحتمي (FR-11–13).

قواعد الأمان هنا:
- كل ادعاء يعيده النموذج يجب أن يوجد نصه **حرفيًا** في المسودة (بعد التطبيع)، وإلا أُسقط.
- الآيات والأحاديث المعلَّمة تُفحص حتى لو فاتت النموذج أو تعطل.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from saadeed.application.prompts import Prompt
from saadeed.domain.enums import ClaimType, ContentLevel, SegmentKind
from saadeed.domain.models import Claim, ClaimHints, Sentence, Span
from saadeed.domain.ports import LLMError, LLMPort, LLMUsage
from saadeed.text.markers import Marked, has_prophetic_context, scan
from saadeed.text.normalize import find_span, normalize, normalize_with_map

_TYPES = {t.value for t in ClaimType}
# «التعميم» لا يُقبل إلا بلفظ إطلاق صريح (ERRORS.md E-007): حارس حتمي على حكم النموذج.
_ABSOLUTE = re.compile(
    r"(?:^|\s)(?:و|ف)?(?:كل|كله|كلهم|كلها|جميع|جميعا|جميعهم|كافه|قاطبه|دايما|ابدا|مطلقا|البته|احد|لا يوجد|لا يكاد|ليس هناك|لا تجد|لم يعد)(?:\s|$)"
)
_LEVELS = {lv.value for lv in ContentLevel}
_QUOTE_TYPES = {ClaimType.QURAN_QUOTE, ClaimType.HADITH_QUOTE}


@dataclass
class ExtractionResult:
    claims: list[Claim]
    usage: list[LLMUsage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    llm_failed: bool = False
    kinds: dict[int, SegmentKind] = field(default_factory=dict)
    """صنف كل جملة كما رآه النموذج (خريطة المسودة، v2.5). وصف لا يغيّر أي قاعدة."""
    failed_parts: int = 0
    """أجزاء المسودة الطويلة التي تعذّر استخراجها (والباقي استُخرج)."""


CHUNK_WORDS = 300
"""حجم الجزء حين تطول المسودة. النموذج الخفيف يُسقط ادعاءات حين يقرأ 1200 كلمة دفعة واحدة
(E-019)، ويلتقطها حين يقرأ ثلاثمئة. والمسودة التي لا تزيد على CHUNK_MAX تبقى نداءً واحدًا."""
CHUNK_MAX = 450
MAX_PARALLEL = 6


def chunk_sentences(sentences: list[Sentence]) -> list[list[Sentence]]:
    """أجزاء متتالية من جمل كاملة. ترقيم الجمل عام، فالخريطة والمواضع لا تتأثر بالتقسيم."""
    sizes = [len(s.text.split()) for s in sentences]
    if sum(sizes) <= CHUNK_MAX:
        return [sentences]
    parts: list[list[Sentence]] = [[]]
    words = 0
    for s, n in zip(sentences, sizes, strict=True):
        if parts[-1] and words + n > CHUNK_WORDS:
            parts.append([])
            words = 0
        parts[-1].append(s)
        words += n
    return parts


def llm_error_ar(e: Exception) -> str:
    """سبب التعذّر بعبارة للمستخدم، دون نص استجابة المزود (فيه معرّفات حسابه)."""
    msg = str(e).lower()
    if "413" in msg or "too large" in msg or "context" in msg:
        return "المسودة أكبر من حدّ الطلب لدى مزود النموذج"
    if "429" in msg or "rate" in msg or "quota" in msg or "exhausted" in msg:
        return "تجاوزنا حدّ الاستخدام لدى مزود النموذج مؤقتًا؛ أعد المحاولة بعد دقيقة"
    if "401" in msg or "403" in msg or "api key" in msg or "api_key" in msg or "مفتاح" in msg:
        return "مفتاح مزود النموذج غير صالح أو غير مضبوط"
    if "timeout" in msg or "timed out" in msg:
        return "انتهت مهلة الاتصال بمزود النموذج"
    return "تعذّر الاتصال بمزود النموذج"


def render_sentences(sentences: list[Sentence]) -> str:
    return "\n".join(f"[{s.index}] {s.text}" for s in sentences)


def _str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def extract_claims(
    text: str,
    sentences: list[Sentence],
    llm: LLMPort | None,
    prompt: Prompt,
) -> ExtractionResult:
    warnings: list[str] = []
    usage: list[LLMUsage] = []
    raw: list[dict[str, Any]] = []
    raw_map: Any = None
    llm_failed = False
    failed_parts = 0
    parts = chunk_sentences(sentences)
    if llm is not None:

        def call(part: list[Sentence]) -> Any:
            system, user = prompt.render(SENTENCES=render_sentences(part))
            try:
                return llm.generate_json(system=system, user=user, max_tokens=6000)
            except LLMError as e:
                return e

        # الأجزاء متوازية: زمن المسودة الطويلة قريب من زمن جزء واحد.
        with ThreadPoolExecutor(max_workers=min(len(parts), MAX_PARALLEL)) as pool:
            results = list(pool.map(call, parts))
        raw_map = []
        errors: list[LLMError] = []
        for resp in results:
            if isinstance(resp, LLMError):
                errors.append(resp)
                continue
            usage.append(resp.usage)
            claims = resp.data.get("claims", resp.data.get("items", []))
            raw += [c for c in claims if isinstance(c, dict)] if isinstance(claims, list) else []
            part_map = resp.data.get("map")
            if isinstance(part_map, list):
                raw_map += part_map
        if errors:
            failed_parts = len(errors)
            llm_failed = failed_parts == len(parts)
            where = "" if llm_failed else f" في {failed_parts} من {len(parts)} أجزاء المسودة"
            warnings.append(
                f"تعذّر استخراج الادعاءات غير المعلَّمة بالنموذج{where}: {llm_error_ar(errors[0])}"
            )
    else:
        llm_failed = True

    sent_starts = {s.index: s.span.start for s in sentences}
    llm_claims: list[Claim] = []
    for c in raw:
        ctype = _str(c.get("type"))
        quote = _str(c.get("quote"))
        if ctype not in _TYPES or not quote:
            continue
        hint = sent_starts.get(c.get("s") if isinstance(c.get("s"), int) else -1, 0)
        span = find_span(text, quote, start_hint=hint)
        if span is None:
            span = _sentence_fallback(quote, c.get("s"), sentences)
        if span is None:
            warnings.append(f"أُسقط ادعاء لم يوجد نصه في المسودة: «{quote[:40]}»")
            continue
        level = _str(c.get("level")) or "B"
        claim_type = ClaimType(ctype)
        if claim_type is ClaimType.GENERALIZATION and not is_generalization(
            text[span[0] : span[1]]
        ):
            continue  # وعظ أو حكمة عامة بلا لفظ إطلاق: ليس تعميمًا قابلًا للفحص
        if claim_type in _QUOTE_TYPES:
            level = "A"
        concl_span = None
        concl = _str(c.get("conclusion"))
        if concl and claim_type is ClaimType.HADITH_QUOTE:
            cs = find_span(text, concl, start_hint=span[1])
            if cs is not None:
                concl_span = Span(start=cs[0], end=cs[1])
        llm_claims.append(
            Claim(
                id="",
                text=text[span[0] : span[1]],
                span=Span(start=span[0], end=span[1]),
                type=claim_type,
                level=ContentLevel(level if level in _LEVELS else "B"),
                hints=ClaimHints(
                    presented_as_verbatim=c.get("verbatim") is not False,
                    cited_ref=_str(c.get("ref")),
                    cited_book=_str(c.get("book"))
                    or (_str(c.get("source")) if claim_type is ClaimType.HADITH_QUOTE else None),
                    source_mentioned=_str(c.get("source")),
                    speaker=_str(c.get("speaker")),
                    attributed_to_prophet=claim_type is not ClaimType.HADITH_QUOTE
                    or has_prophetic_context(text, span[0], span[1]),
                    rephrase=_str(c.get("rephrase"))
                    if claim_type in (ClaimType.GENERALIZATION, ClaimType.CONSENSUS_CLAIM)
                    else None,
                ),
                linked_conclusion=concl_span,
                origin="llm",
            )
        )

    merged = _merge(text, llm_claims, scan(text))
    _link_conclusions(text, merged, sentences)
    for i, cl in enumerate(merged, start=1):
        cl.id = f"c{i}"
    return ExtractionResult(
        merged, usage, warnings, llm_failed, _parse_map(raw_map, sent_starts), failed_parts
    )


_KINDS = {k.value for k in SegmentKind} - {SegmentKind.UNLABELED.value}
# النموذج قد يخلط أسماء الأصناف بأنواع الادعاءات؛ نقبلها بمقابلها بدل إهمالها.
_KIND_ALIASES = {
    "QURAN_QUOTE": "QURAN",
    "HADITH_QUOTE": "HADITH",
    "TAKHRIJ": "HADITH",
    "ATTRIBUTED_SAYING": "SCHOLAR",
    "STATISTIC": "FACT",
    "HISTORICAL_EVENT": "STORY",
    "CONSENSUS_CLAIM": "RULING",
    "GENERALIZATION": "FACT",
    "GROUP_JUDGMENT": "RULING",
    "PERSONAL_CASE": "RULING",
    "HADITH_CONCLUSION": "EXHORTATION",
}


def _parse_map(raw: Any, sent_starts: dict[int, int]) -> dict[int, SegmentKind]:
    """`[[0, "QURAN"], …]` أو `[{"s": 0, "kind": "QURAN"}, …]`. وما لا يُفهم يُهمل بصمت."""
    out: dict[int, SegmentKind] = {}
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, list | tuple) and len(item) == 2:
            idx, kind = item
        elif isinstance(item, dict):
            idx, kind = item.get("s"), item.get("kind")
        else:
            continue
        kind = _KIND_ALIASES.get(str(kind), str(kind))
        if isinstance(idx, int) and idx in sent_starts and kind in _KINDS:
            out[idx] = SegmentKind(kind)
    return out


def _merge(text: str, llm_claims: list[Claim], marked: list[Marked]) -> list[Claim]:
    """يدمج ادعاءات النموذج مع المرور الحتمي. والمعلَّم يُقدَّم في الموضع والقرائن."""
    out: list[Claim] = []
    used_marks: set[int] = set()

    for cl in llm_claims:
        if cl.type is ClaimType.TAKHRIJ:
            continue  # تُلحق بالحديث السابق أدناه
        if cl.type in _QUOTE_TYPES:
            for mi, m in enumerate(marked):
                mspan = Span(start=m.start, end=m.end)
                if mspan.overlaps(cl.span):
                    used_marks.add(mi)
                    kind = ClaimType.QURAN_QUOTE if m.kind == "quran" else ClaimType.HADITH_QUOTE
                    cl = cl.model_copy(
                        update={
                            "text": m.text,
                            "span": mspan,
                            "type": kind,
                            "origin": "both",
                            "hints": cl.hints.model_copy(
                                update={
                                    "cited_ref": m.cited_ref or cl.hints.cited_ref,
                                    "cited_book": m.cited_book or cl.hints.cited_book,
                                    "presented_as_verbatim": m.verbatim
                                    and cl.hints.presented_as_verbatim,
                                    "attributed_to_prophet": True,
                                }
                            ),
                        }
                    )
                    break
        if any(o.span.iou(cl.span) > 0.6 and o.type is cl.type for o in out):
            continue
        out.append(cl)

    for mi, m in enumerate(marked):
        if mi in used_marks:
            continue
        mspan = Span(start=m.start, end=m.end)

        def nested_verse(o: Claim, m: Marked = m, mspan: Span = mspan) -> bool:
            # آية معلَّمة ﴿ ﴾ داخل حديث: تُفحص بالمصحف ادعاءً مستقلًا، والحديث في كتب السنة (E-021).
            return (
                m.kind == "quran"
                and o.type is ClaimType.HADITH_QUOTE
                and o.span.start <= mspan.start
                and mspan.end <= o.span.end
            )

        if any(
            o.span.overlaps(mspan) and o.type in _QUOTE_TYPES and not nested_verse(o) for o in out
        ):
            continue
        out.append(
            Claim(
                id="",
                text=m.text,
                span=mspan,
                type=ClaimType.QURAN_QUOTE if m.kind == "quran" else ClaimType.HADITH_QUOTE,
                level=ContentLevel.A,
                hints=ClaimHints(
                    presented_as_verbatim=m.verbatim, cited_ref=m.cited_ref, cited_book=m.cited_book
                ),
                origin="marker",
            )
        )

    # نسبة التخريج التي استخرجها النموذج منفصلة تُلحق بأقرب حديث قبلها.
    for cl in llm_claims:
        if cl.type is not ClaimType.TAKHRIJ:
            continue
        prev = [
            o
            for o in out
            if o.type is ClaimType.HADITH_QUOTE
            and o.span.end <= cl.span.start + 5
            and cl.span.start - o.span.end < 150
        ]
        if prev and not prev[-1].hints.cited_book:
            target = prev[-1]
            idx = out.index(target)
            out[idx] = target.model_copy(
                update={"hints": target.hints.model_copy(update={"cited_book": cl.text})}
            )

    out.sort(key=lambda c: (c.span.start, c.span.end))
    return out


_CONCLUSION_STARTS = (
    "فمن",
    "فدل",
    "فهذا يدل",
    "وهذا يدل",
    "وهذا يعني",
    "فهذا يعني",
    "ومعنى ذلك",
    "وعليه",
    "فاذن",
    "اذن",
    "فعلم",
    "فيفهم",
    "ومن هنا",
    "فالحديث يدل",
    "والحديث يدل",
    "وفي هذا دليل",
    "ففي هذا دليل",
)


def _link_conclusions(text: str, claims: list[Claim], sentences: list[Sentence]) -> None:
    """ربط احتياطي حتمي إن لم يربط النموذج: استنتاج يبدأ بصيغة («فمن…»، «فدلّ…») بعد الحديث مباشرة،
    في بقية جملته أو في الجملة التالية."""
    for i, cl in enumerate(claims):
        if cl.type is not ClaimType.HADITH_QUOTE or cl.linked_conclusion is not None:
            continue
        window_end = next((s.span.end for s in sentences if s.span.start >= cl.span.end), len(text))
        window = text[cl.span.end : window_end]
        norm, idx = normalize_with_map(window)
        best = None
        for marker in _CONCLUSION_STARTS:
            k = norm.find(marker)
            if k >= 0 and (k == 0 or norm[k - 1] == " ") and (best is None or k < best):
                best = k
        if best is None or best > 40:
            continue
        start = cl.span.end + idx[best]
        stop = next(
            (s.span.end for s in sentences if s.span.start <= start < s.span.end), window_end
        )
        claims[i] = cl.model_copy(update={"linked_conclusion": Span(start=start, end=stop)})


REORDER_MIN = 0.9
"""نسبة كلمات الاقتباس التي يجب أن توجد في الجملة نفسها لنقبل اقتباسًا أعاد النموذج ترتيبه."""


def _sentence_fallback(quote: str, s_idx: Any, sentences: list[Sentence]) -> tuple[int, int] | None:
    """النموذج أحيانًا يعيد ترتيب كلمات الاقتباس. فإن كانت كلماته في الجملة التي أشار إليها،
    أخذنا **نص الجملة نفسها من المسودة** (لا نص النموذج). وإلا أُسقط الادعاء كما كان."""
    if not isinstance(s_idx, int) or not (0 <= s_idx < len(sentences)):
        return None
    q = normalize(quote).split()
    sent = sentences[s_idx]
    if len(q) < 3:
        return None
    words = set(normalize(sent.text).split())
    if sum(1 for w in q if w in words) < REORDER_MIN * len(q):
        return None
    return sent.span.start, sent.span.end


def is_generalization(fragment: str) -> bool:
    """حارس التعميم (E-007): لفظ إطلاق صريح، وإلا فهو وعظ أو حكمة عامة."""
    return bool(_ABSOLUTE.search(" " + normalize(fragment) + " "))


def same_text(a: str, b: str) -> bool:
    return normalize(a) == normalize(b)
