"""مطابقة الأقوال المنسوبة إلى العلماء بمكتبة كتبهم (v2.6).

القول المنقول بنصه («قال ابن كثير: "…"») يُبحث عنه في المكتبة (وصلة حية)،
ثم يحكم النموذج: هل الموضع يحمله بلفظه أم بمعناه أم لا، وهل مؤلفه من نُسب إليه.
والحالة والأثر والإجراء من جدول القواعد (BR-24..27)، والنص المعروض من المكتبة لا من النموذج.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from saadeed.domain.enums import ClaimType, Confidence, MatchType, SourceRole
from saadeed.domain.models import Claim, Evidence, SourceRef
from saadeed.domain.policy import Signal
from saadeed.domain.ports import LibraryHit, LibraryPort, LLMError, LLMPort
from saadeed.verifiers.base import Outcome

# ما يُرسل إلى المكتبة: الأقوال المنسوبة التي لم يحسمها مخزن السنة.
_OPEN = (Signal.SOURCING_NO_SOURCE, Signal.SOURCING_CITED_OUT_OF_COVERAGE)
_MAX_SAYINGS = 15


def eligible(cl: Claim, out: Outcome) -> bool:
    """قول منسوب إلى عالم، أو قصة وأثر منقول بنصه (القصص في كتب الزهد والتاريخ)."""
    if out.signal not in _OPEN:
        return False
    n = len(cl.text.split())
    if cl.type is ClaimType.ATTRIBUTED_SAYING:
        return n >= 4 and (bool(cl.hints.speaker) or n >= 6)
    return cl.type is ClaimType.HISTORICAL_EVENT and n >= 5


def check_sayings(
    claims: list[Claim],
    outcomes: dict[str, Outcome],
    library: LibraryPort,
    llm: LLMPort | None,
    prompt: Any,
) -> tuple[dict[str, Outcome], list[Any], list[str]]:
    """يعيد: النتائج المحدّثة، واستهلاك النموذج، والتحذيرات."""
    todo = [c for c in claims if c.id in outcomes and eligible(c, outcomes[c.id])][:_MAX_SAYINGS]
    if not todo or llm is None or prompt is None:
        return {}, [], []
    with ThreadPoolExecutor(max_workers=min(8, len(todo))) as pool:
        hits = dict(
            zip(
                [c.id for c in todo],
                pool.map(lambda c: library.search(c.text, c.hints.speaker), todo),
                strict=True,
            )
        )

    def block(c: Claim) -> str:
        lines = [
            f"- id: {c.id}",
            f"  saying: {c.text}",
            f"  attributed_to: {c.hints.speaker or '—'}",
        ]
        for i, h in enumerate(hits[c.id], start=1):
            lines.append(f"  candidate {i}: [{h.book_name} — {h.author_name}] {h.text[:450]}")
        if not hits[c.id]:
            lines.append("  (لا مواضع)")
        return "\n".join(lines)

    def judge(c: Claim) -> tuple[dict, Any]:
        # نداء لكل قول، بالتوازي: أسرع بكثير من نداء واحد طويل.
        if not hits[c.id]:
            return {"id": c.id, "match": "NONE"}, None
        system, user = prompt.render(ITEMS=block(c))
        try:
            resp = llm.generate_json(system=system, user=user, max_tokens=400)
        except LLMError:
            return {}, None
        items = resp.data.get("items", [])
        it = next((x for x in items if isinstance(x, dict)), {}) if isinstance(items, list) else {}
        return {**it, "id": c.id}, resp.usage

    with ThreadPoolExecutor(max_workers=min(8, len(todo))) as pool:
        results = list(pool.map(judge, todo))
    judged = {c.id: r for c, (r, _) in zip(todo, results, strict=True) if r}
    usages = [u for _, u in results if u is not None]
    if not judged:
        return {}, usages, ["تعذّر الحكم على الأقوال المنسوبة بالمكتبة، فبقيت «تحقق من مصدره»"]

    updated: dict[str, Outcome] = {}
    for c in todo:
        j = judged.get(c.id, {})
        cands = hits[c.id]
        try:
            idx = int(j.get("candidate")) - 1
        except (TypeError, ValueError):
            idx = -1
        hit = cands[idx] if 0 <= idx < len(cands) else None
        match = j.get("match")
        speaker = c.hints.speaker or "قائله"
        if hit is None or match not in ("VERBATIM", "PARAPHRASE"):
            if c.id not in judged:
                continue  # تعذّر الحكم (شبكة أو نموذج): تبقى النتيجة السابقة
            updated[c.id] = Outcome(
                Signal.SAYING_NOT_FOUND,
                evidence=[],
                facts={"speaker": speaker},
                confidence=Confidence.MEDIUM,
            )
            continue
        facts = {
            "book": f"«{hit.book_name}»",
            "author": hit.author_name,
            "where": _where(hit),
            "speaker": speaker,
        }
        same = (
            not c.hints.speaker
            or library.same_author(c.hints.speaker, hit.author_name)
            or j.get("same_author")
        )
        if not same:
            sig = Signal.SAYING_OTHER_AUTHOR
        elif match == "VERBATIM":
            sig = Signal.SAYING_FOUND
        else:
            sig = Signal.SAYING_FOUND_PARAPHRASE
        updated[c.id] = Outcome(
            sig,
            evidence=[_evidence(library, hit, match)],
            facts=facts,
            confidence=Confidence.HIGH if match == "VERBATIM" else Confidence.MEDIUM,
        )
    return updated, usages, []


def _where(h: LibraryHit) -> str:
    parts = []
    if h.vol and h.vol != "0":
        parts.append(f"ج{h.vol}")
    if h.page:
        parts.append(f"ص{h.page}")
    return f" ({'، '.join(parts)})" if parts else ""


def _evidence(library: LibraryPort, h: LibraryHit, match: str) -> Evidence:
    return Evidence(
        ref=SourceRef(
            source_id=library.source_id,
            item_id=h.item_id,
            citation=f"{h.book_name} — {h.author_name}{_where(h)}",
            url=h.url,
        ),
        role=SourceRole.LOCATE,
        text=h.text,
        match_type=MatchType.EXACT if match == "VERBATIM" else MatchType.PARAPHRASE,
        match_reason="موضع من مكتبة تراث (بحث حي)، وحكم المطابقة من الحَكَم",
    )


# ───────────── حكم الحديث المنقول (v2.6) ─────────────
_GRADE_WORDS = ("صحيح", "صححه", "حسن", "حسنه", "ضعيف", "ضعفه", "موضوع", "منكر")
_GRADES = {"صحيح", "حسن", "صحيح لغيره", "حسن لغيره", "ضعيف", "ضعيف جدا", "موضوع", "منكر"}
_OPEN_HADITH = (Signal.HADITH_LOCATE_ONLY, Signal.HADITH_NOT_FOUND)


def check_rulings(
    claims: list[Claim],
    outcomes: dict[str, Outcome],
    library: LibraryPort,
    llm: LLMPort | None,
    prompt: Any,
) -> tuple[dict[str, Outcome], list[Any]]:
    """للحديث الذي وُجد دون حكم أو لم يوجد: يُبحث في المكتبة عن موضع فيه حكم محدّث عليه،
    ويستخرج النموذج الحكم وقائله **من نص الموضع فقط**، ثم يُتحقق حتميًا أن الكلمتين في الموضع.
    لا تتغير الأبعاد الثلاثة: الحكم يُعرض منسوبًا إلى قائله، والقرار للخطيب."""
    todo = [
        c
        for c in claims
        if c.type in (ClaimType.HADITH_QUOTE, ClaimType.TAKHRIJ)
        and c.id in outcomes
        and outcomes[c.id].signal in _OPEN_HADITH
        and len(c.text.split()) >= 3
    ][:10]
    if not todo or llm is None or prompt is None:
        return {}, []

    def find(c: Claim) -> list[LibraryHit]:
        return [h for h in library.search(c.text) if any(w in h.text for w in _GRADE_WORDS)][:5]

    with ThreadPoolExecutor(max_workers=min(8, len(todo))) as pool:
        hits = dict(zip([c.id for c in todo], pool.map(find, todo), strict=True))

    def judge(c: Claim) -> tuple[str, dict, Any]:
        if not hits[c.id]:
            return c.id, {}, None
        lines = [f"- id: {c.id}", f"  hadith: {c.text}"]
        for i, h in enumerate(hits[c.id], start=1):
            lines.append(f"  candidate {i}: [{h.book_name} — {h.author_name}] {h.text[:500]}")
        system, user = prompt.render(ITEMS="\n".join(lines))
        try:
            resp = llm.generate_json(system=system, user=user, max_tokens=300)
        except LLMError:
            return c.id, {}, None
        items = resp.data.get("items", [])
        it = next((x for x in items if isinstance(x, dict)), {}) if isinstance(items, list) else {}
        return c.id, it, resp.usage

    with ThreadPoolExecutor(max_workers=min(8, len(todo))) as pool:
        results = list(pool.map(judge, todo))
    usages = [u for _, _, u in results if u is not None]
    updated: dict[str, Outcome] = {}
    for cid, it, _ in results:
        try:
            hit = hits[cid][int(it.get("candidate")) - 1]
        except (TypeError, ValueError, IndexError):
            continue
        grade = str(it.get("grade") or "").strip()
        grader = str(it.get("grader") or "").strip()
        where = str(it.get("where") or "").strip()
        # حارس: لا حكم ولا محدّث إلا ما في نص الموضع نفسه.
        stem = grader.replace("الشيخ ", "").split()[-1] if grader else ""
        if grade not in _GRADES or not stem or stem not in hit.text:
            continue
        if not any(w in hit.text for w in (grade.split()[0], grade[:3])):
            continue
        old = outcomes[cid]
        ruling = f"{grade} عند {grader}" + (f" ({where})" if where else "")
        ruling += f"، نقلًا عن «{hit.book_name}» في مكتبة تراث"
        ev = _evidence(library, hit, "VERBATIM").model_copy(
            update={
                "role": SourceRole.RULING,
                "match_reason": "موضع فيه حكم محدّث على الحديث (مكتبة تراث)",
            }
        )
        updated[cid] = Outcome(
            old.signal,
            evidence=[*old.evidence, ev],
            facts={**old.facts, "ruling": ruling},
            confidence=old.confidence,
            notes=old.notes,
            relation=old.relation,
        )
    return updated, usages


# ───────────── بوابة التعميم (v2.6) ─────────────
def gate_generalizations(
    text: str, claims: list[Claim], outcomes: dict[str, Outcome], llm: LLMPort | None, prompt: Any
) -> tuple[set[str], list[Any]]:
    """التعميم يُعرض فقط إن رآه النموذج، في سياق فقرته، تعميمًا مضللًا أو خطأ في الفهم.
    والعبارة الوعظية المعتادة أو الضمير العائد على مذكور قبله لا تُعرض (نعم/لا فقط)."""
    todo = [
        c
        for c in claims
        if c.type is ClaimType.GENERALIZATION
        and c.id in outcomes
        and outcomes[c.id].signal is Signal.GENERALIZATION
    ][:15]
    if not todo or llm is None or prompt is None:
        return set(), []

    def ask(c: Claim) -> tuple[str, bool | None, Any]:
        a = max(0, c.span.start - 350)
        ctx = text[a : c.span.end + 200]
        system, user = prompt.render(PARAGRAPH=ctx, PHRASE=c.text)
        try:
            resp = llm.generate_json(system=system, user=user, max_tokens=120)
        except LLMError:
            return c.id, None, None
        v = resp.data.get("misleading")
        return c.id, v if isinstance(v, bool) else None, resp.usage

    with ThreadPoolExecutor(max_workers=min(8, len(todo))) as pool:
        res = list(pool.map(ask, todo))
    drop = {cid for cid, v, _ in res if v is False}
    return drop, [u for _, _, u in res if u is not None]
