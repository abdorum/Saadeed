"""شبكة الأمان (E-019، E-020): ما يفوت النموذج في المسودة الطويلة يُلتقط بالقواعد.

النموذج الخفيف يقرأ الخطبة فيُسقط بعض ما يُفحص: قصة سلفية بلا مصدر، وقولًا بين علامتي تنصيص
بلا قائل، وكلامًا نُسب إلى «بعض العلماء». وهذه كلها **تزيد الفحص ولا تنقصه**:
لا تحذف ادعاءً ولا تغيّر نوع ادعاء استخرجه النموذج، ولا تصدر حكمًا؛ الحكم من جدول القواعد.

1. **الجمل التي وصفتها خريطة المسودة** قصةً أو أثرًا أو نقلًا عن عالم، ولا ادعاء فيها:
   تُجمع المتتالية من العائلة نفسها ادعاءً واحدًا يُسأل عن مصدره (BR-12، أو BR-13 إن ذُكر مصدر).
2. **كل اقتباس بين «» من ست كلمات فأكثر** لم يغطّه ادعاء: قول منسوب يُبحث أولًا في كتب السنة
   حرفيًا (في التوجيه)، فإن لم يوجد سُئل عن قائله ومصدره.
"""

from __future__ import annotations

import re

from saadeed.domain.enums import ClaimType, ContentLevel, SegmentKind
from saadeed.domain.models import Claim, ClaimHints, Sentence, Span
from saadeed.text.markers import has_prophetic_context, takhrij_after
from saadeed.text.normalize import strip_diacritics

QUOTE_MIN_WORDS = 6
"""أقصر اقتباس يُعدّ قولًا يُسأل عن قائله. ما دونه عبارة («فمغثه مغثًا شديدًا») لا قول."""

# القصة والأثر عائلة واحدة (قصة الربيع تبدأ بتعريفه ثم تُروى)، والنقل عن عالم عائلة.
_FAMILY = {
    SegmentKind.STORY: "narrative",
    SegmentKind.ATHAR: "narrative",
    SegmentKind.SCHOLAR: "scholar",
}
_QUOTE = re.compile(r"«([^«»]{2,1500})»")
_VERSE = re.compile(r"﴿[^﴾]*﴾")
# ذكرُ مصدرٍ بعد القول أو في جملته: «ذكره ابن القيم في زاد المعاد»، «(الفوائد، ص 12)».
_SOURCE_CUE = re.compile(
    r"(?:^|\s)(?:ذكره|ذكرها|نقله|قاله|أورده|اورده|رواه|أخرجه|اخرجه|في\s+كتابه|في\s+كتاب|انظر|يُنظر|ينظر|"
    r"وفي\s+الصحيحين|في\s+الصحيحين|في\s+صحيح)\s*[^\n.،؛]{2,60}"
)


def safety_net(
    text: str, claims: list[Claim], sentences: list[Sentence], kinds: dict[int, SegmentKind]
) -> list[Claim]:
    """يعيد الادعاءات مع ما التقطته الشبكة، مرتبةً بالموضع. المعرّفات يعيد ترقيمها المستدعي."""
    out = list(claims)
    out += _from_map(text, out, sentences, kinds)
    out += _from_quotes(text, out)
    out.sort(key=lambda c: (c.span.start, c.span.end))
    return out


def _takhrij(after: str) -> str | None:
    return takhrij_after(after)


def _covered(span: Span, claims: list[Claim]) -> bool:
    return any(c.span.overlaps(span) for c in claims)


def _source_in(fragment: str) -> str | None:
    # البحث على النص بلا تشكيل: «وَفي الصَّحِيحَينِ» هي «وفي الصحيحين».
    # ولا يتجاوز جملته: «…». الرابعة: ولا يذكرها لأحد — ليس مصدرًا للقول السابق.
    frag = re.split(r"[.!؟?\n]", strip_diacritics(fragment))[0]
    m = _SOURCE_CUE.search(frag)
    return m.group(0).strip() if m else None


def _from_map(
    text: str, claims: list[Claim], sentences: list[Sentence], kinds: dict[int, SegmentKind]
) -> list[Claim]:
    """الجمل الموصوفة قصةً أو أثرًا أو نقلًا عن عالم بلا ادعاء: تُجمع المتتالية من الصنف نفسه.

    والجملة التي لها ادعاء (آية في قول الربيع مثلًا) لا تقطع القصة إن عادت بعدها.
    """
    runs: list[tuple[str, list[Sentence], set[SegmentKind]]] = []
    gap = 0
    for s in sentences:
        kind = kinds.get(s.index, SegmentKind.UNLABELED)
        family = _FAMILY.get(kind)
        if family is not None and not _covered(s.span, claims):
            if runs and runs[-1][0] == family and gap <= 1:
                runs[-1][1].append(s)
                runs[-1][2].add(kind)
            else:
                runs.append((family, [s], {kind}))
            gap = 0
        else:
            gap += 1
    out: list[Claim] = []
    for _, group, seen in runs:
        ctype = (
            ClaimType.HISTORICAL_EVENT if SegmentKind.STORY in seen else ClaimType.ATTRIBUTED_SAYING
        )
        span = Span(start=group[0].span.start, end=group[-1].span.end)
        body = text[span.start : span.end]
        out.append(
            Claim(
                id="",
                text=body,
                span=span,
                type=ctype,
                level=ContentLevel.B,
                hints=ClaimHints(presented_as_verbatim=False, source_mentioned=_source_in(body)),
                origin="net-map",
            )
        )
    return out


def _from_quotes(text: str, claims: list[Claim]) -> list[Claim]:
    out: list[Claim] = []
    for m in _QUOTE.finditer(text):
        body = m.group(1).strip()
        if len(_VERSE.sub(" ", body).split()) < QUOTE_MIN_WORDS:
            continue
        start = m.start(1) + (len(m.group(1)) - len(m.group(1).lstrip()))
        span = Span(start=start, end=start + len(body))
        if _covered(span, claims + out):
            continue
        after = text[m.end() : m.end() + 80]
        # «كما جاء في حديث أبي هريرة قال: «جاء رجل إلى النبي ﷺ…»»: رواية، فتُفحص حديثًا.
        narrated = has_prophetic_context(text, span.start, span.end)
        out.append(
            Claim(
                id="",
                text=body,
                span=span,
                type=ClaimType.HADITH_QUOTE if narrated else ClaimType.ATTRIBUTED_SAYING,
                level=ContentLevel.A if narrated else ContentLevel.B,
                hints=ClaimHints(
                    presented_as_verbatim=True,
                    attributed_to_prophet=narrated,
                    cited_book=_takhrij(after) if narrated else None,
                    source_mentioned=None if narrated else _source_in(after),
                ),
                origin="net-quote",
            )
        )
    return out
