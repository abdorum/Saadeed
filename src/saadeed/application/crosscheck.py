"""الفحص المتقاطع (ADR-0014): لا نثق بتصنيف النموذج وحده.

النموذج يقول «أين الادعاء وما نوعه»، لكن خطأه في النوع يُضيّع الفحص: آية صنّفها «تعميمًا» لا تصل
إلى المصحف، وآية نُسبت إلى النبي ﷺ تُبحث في كتب الحديث فلا توجد. فبعد الاستخراج، وقبل التوجيه:

1. **كل ادعاء ليس آية** يُعرض على فهرس المصحف حرفيًا (مقاطع لا تقل عن 4 كلمات):
   - إن غطّت المقاطع القرآنية 80% منه فهو آية: يُعاد تصنيفه، ويُحفظ ما قدّمه به الكاتب
     («حديث») ليحكم الجدول بـ BR-22.
   - وإن كانت الآية جزءًا منه: تُفصل ادعاءً مستقلًا. والتعميم يُقصّ إلى ما بقي من كلام الكاتب.
   - والآية داخل حديث تُترك: الحديث يُفحص في كتب الحديث.
2. **كل جملة** تُمسح بحثًا عن آية غير معلَّمة (5 كلمات فأكثر) لم يلتقطها أحد.

حتمي بالكامل: الفهرس نفسه والعتبات نفسها تعطي النتيجة نفسها دائمًا، ويعمل حتى إن تعطل النموذج.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from saadeed.domain.enums import ClaimType, ContentLevel
from saadeed.domain.models import Claim, Sentence, Span
from saadeed.text.normalize import normalize
from saadeed.verifiers.quran import QuranIndex, Run

IN_CLAIM_MIN = 4
"""أقصر مقطع قرآني يُعتدّ به داخل ادعاء آخر."""
FREE_SCAN_MIN = 5
"""أقصر آية غير معلَّمة تُلتقط من جملة لا ادعاء فيها (أعلى، لأن العبارات القصيرة الشائعة تتكرر)."""
RETYPE_COVERAGE = 0.8
"""إن غطّت المقاطع القرآنية هذه النسبة من الادعاء فهو آية."""
REMAINDER_MIN = 3
"""أقل ما يبقى من كلام الكاتب بعد فصل الآية ليبقى ادعاءً مستقلًا."""

_LEAD = '«“"(﴿['
_TRAIL = "،,.؛;:!؟?»«\"'()﴿﴾[]{}"
_SKIP = {ClaimType.QURAN_QUOTE, ClaimType.TAKHRIJ, ClaimType.HADITH_CONCLUSION}


@dataclass(frozen=True)
class _Tok:
    start: int
    end: int
    norm: str


def _tokens(text: str, span: Span) -> list[_Tok]:
    out: list[_Tok] = []
    for m in re.finditer(r"\S+", text[span.start : span.end]):
        raw = m.group()
        lead = len(raw) - len(raw.lstrip(_LEAD))
        end = span.start + m.start() + len(raw.rstrip(_TRAIL))
        for part in normalize(raw).split():
            out.append(_Tok(span.start + m.start() + lead, end, part))
    return out


def _split_vocatives(toks: list[_Tok], index: QuranIndex) -> list[_Tok]:
    return [_Tok(t.start, t.end, part) for t in toks for part in index.split_vocative(t.norm)]


def _run_span(toks: list[_Tok], r: Run) -> Span:
    return Span(start=toks[r.q_start].start, end=toks[r.q_end - 1].end)


def _verse_claim(text: str, span: Span) -> Claim:
    return Claim(
        id="",
        text=text[span.start : span.end],
        span=span,
        type=ClaimType.QURAN_QUOTE,
        level=ContentLevel.A,
        origin="crosscheck",
    )


def cross_check(
    text: str,
    claims: list[Claim],
    sentences: list[Sentence],
    index: QuranIndex,
    is_generalization: Callable[[str], bool],
) -> tuple[list[Claim], list[str]]:
    """يعيد الادعاءات بعد الفحص المتقاطع، مع ملاحظات تُضاف إلى تحذيرات التقرير."""
    out: list[Claim] = []
    notes: list[str] = []
    for cl in claims:
        if cl.type in _SKIP:
            out.append(cl)
            continue
        toks = _tokens(text, cl.span)
        toks = _split_vocatives(toks, index)
        runs = index.runs([t.norm for t in toks], IN_CLAIM_MIN)
        if not runs:
            out.append(cl)
            continue
        covered = sum(r.length for r in runs)
        if covered >= RETYPE_COVERAGE * len(toks):
            presented = cl.type if cl.type is ClaimType.HADITH_QUOTE else None
            out.append(
                cl.model_copy(
                    update={
                        "type": ClaimType.QURAN_QUOTE,
                        "level": ContentLevel.A,
                        "origin": f"{cl.origin}+crosscheck",
                        "hints": cl.hints.model_copy(update={"presented_as": presented}),
                    }
                )
            )
            if presented is None:
                notes.append(
                    f"الفحص المتقاطع: «{cl.text[:40]}» آية، وقد صنّفها النموذج «{cl.type.label_ar}»"
                )
            continue
        if cl.type is ClaimType.HADITH_QUOTE:
            out.append(cl)  # آية يقرؤها الحديث نفسه: يُفحص الحديث في كتب الحديث
            continue
        for r in runs:
            out.append(_verse_claim(text, _run_span(toks, r)))
        if cl.type is ClaimType.GENERALIZATION:
            rest = _largest_remainder(toks, runs)
            if rest is None:
                continue
            span = Span(start=rest[0].start, end=rest[-1].end)
            if is_generalization(text[span.start : span.end]):
                out.append(
                    cl.model_copy(update={"text": text[span.start : span.end], "span": span})
                )
            continue
        out.append(cl)

    taken = [c.span for c in out if c.type in (ClaimType.QURAN_QUOTE, ClaimType.HADITH_QUOTE)]
    for s in sentences:
        toks = _split_vocatives(_tokens(text, s.span), index)
        for r in index.runs([t.norm for t in toks], FREE_SCAN_MIN):
            span = _run_span(toks, r)
            if any(span.overlaps(t) for t in taken):
                continue
            out.append(_verse_claim(text, span))
            taken.append(span)

    out.sort(key=lambda c: (c.span.start, c.span.end))
    return out, notes


def _largest_remainder(toks: list[_Tok], runs: list[Run]) -> list[_Tok] | None:
    inside = {i for r in runs for i in range(r.q_start, r.q_end)}
    blocks: list[list[_Tok]] = []
    cur: list[_Tok] = []
    for i, t in enumerate(toks):
        if i in inside:
            if cur:
                blocks.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        blocks.append(cur)
    blocks = [b for b in blocks if len(b) >= REMAINDER_MIN]
    return max(blocks, key=len) if blocks else None
