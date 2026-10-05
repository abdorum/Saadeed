"""متحقق الأحاديث (المعمارية §٧.٢، ADR-0010).

الترتيب:
1. قائمة المشتهر الذي لا يصح (تطابق تقريبي حتمي) ← BR-05.
2. تطابق حرفي بعد التطبيع في الكتب الستة (حتمي) ← BR-06 / BR-09 / BR-10.
3. ما لم يُحسم حتميًا: نجهّز أفضل 5 مرشحين من المخزن، ويحكم النموذج: لفظ أو معنى أو لا يطابق.
   **النموذج يعيد معرّف مرشح عرضناه عليه فقط**، ولا يرى غير المخزن ولا يكتب نصًا.
4. الدور يحدد الحالة: «مؤيَّد» من مصدر احتجاج وحده، و«وُجد دون حكم» من مصدر موضع.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from saadeed.domain.enums import Confidence, MatchType, SourceRole
from saadeed.domain.models import Evidence, SourceRef, Span
from saadeed.domain.policy import Signal
from saadeed.domain.ports import KnownWeak, KnownWeakRepo, Passage, ReferenceLinker, TextSourcePort
from saadeed.text.markers import canonical_books
from saadeed.text.matn_signs import matn_signs
from saadeed.text.normalize import find_span, normalize
from saadeed.text.stem import light_stem, stems
from saadeed.verifiers.base import Outcome

KNOWN_WEAK_MIN = 88
"""أدنى تشابه مع بند في قائمة المشتهر (0–100)."""
VERBATIM_FUZZY_MIN = 93
"""أدنى تشابه جزئي يُعدّ نقلًا باللفظ مع فروق يسيرة."""
MIN_QUERY_WORDS = 3
"""أقل عدد كلمات للمطابقة التقريبية."""
MIN_EXACT_WORDS = 2
"""أقل عدد كلمات للمطابقة الحرفية («الدين النصيحة» كلمتان)."""
BOOK_PRESENCE_MIN = 85
"""أدنى تشابه لعدّ الحديث موجودًا في الكتاب المنسوب إليه (الروايات تختلف يسيرًا: «بالنية/بالنيات»)."""
TOP_K = 5

BOOK_SHORT = {
    "bukhari": "البخاري",
    "muslim": "مسلم",
    "abudawud": "أبي داود",
    "tirmidhi": "الترمذي",
    "nasai": "النسائي",
    "ibnmajah": "ابن ماجه",
}


@dataclass
class _Doc:
    source_id: str
    role: SourceRole
    item_id: str
    norm: str
    tokens: set[str]
    stems: set[str]


@dataclass
class Candidate:
    key: str
    """«source_id:item_id» — المعرّف الذي يعيده الحَكَم."""
    source_id: str
    item_id: str
    role: SourceRole
    score: float
    text_plain: str


@dataclass
class HadithPending:
    """حديث لم يُحسم حتميًا، ينتظر حكم النموذج."""

    candidates: list[Candidate] = field(default_factory=list)


class HadithIndex:
    def __init__(self, sources: list[TextSourcePort]) -> None:
        self.sources = {s.info.id: s for s in sources}
        self.docs: list[_Doc] = []
        inv: dict[str, list[int]] = defaultdict(list)
        stem_inv: dict[str, list[int]] = defaultdict(list)
        for src in sources:
            role = src.info.role
            for p in src.all_passages():
                norm = p.text_norm if p.text_norm is not None else normalize(p.text_plain)
                toks = set(norm.split())
                sts = {light_stem(t) for t in toks}
                idx = len(self.docs)
                self.docs.append(_Doc(src.info.id, role, p.item_id, norm, toks, sts))
                for t in toks:
                    inv[t].append(idx)
                for t in sts:
                    stem_inv[t].append(idx)
        self.inv = dict(inv)
        self.stem_inv = dict(stem_inv)
        self.pos = {(d.source_id, d.item_id): i for i, d in enumerate(self.docs)}
        n = len(self.docs) or 1
        self.idf = {t: math.log(n / len(ids)) for t, ids in self.inv.items()}
        self.stem_idf = {t: math.log(n / len(ids)) for t, ids in self.stem_inv.items()}

    def exact_hits(self, q_norm: str) -> list[int]:
        """مواضع الاقتباس حرفيًا (بعد التطبيع) في كل الكتب."""
        toks = q_norm.split()
        if len(toks) < MIN_EXACT_WORDS or any(t not in self.inv for t in toks):
            return []
        rare = sorted(set(toks), key=lambda t: len(self.inv[t]))[:2]
        cand = set(self.inv[rare[0]])
        for t in rare[1:]:
            cand &= set(self.inv[t])
        return sorted(i for i in cand if q_norm in self.docs[i].norm)

    def book_contains(self, source_id: str, q_norm: str) -> bool:
        """هل في هذا الكتاب حديث يحمل الاقتباس، ولو بفروق رواية يسيرة؟"""
        for i in self.exact_hits(q_norm):
            if self.docs[i].source_id == source_id:
                return True
        for i, _ in self.ranked(q_norm, k=10, only=source_id):
            if fuzz.partial_ratio(q_norm, self.docs[i].norm) >= BOOK_PRESENCE_MIN:
                return True
        return False

    def ranked(
        self, q_norm: str, k: int = TOP_K, only: str | None = None
    ) -> list[tuple[int, float]]:
        """استرجاع معجمي على الجذوع الخفيفة (E-004): مجموع IDF للجذوع المشتركة، مع تصحيح لطول الحديث."""
        toks = stems(q_norm)
        scores: dict[int, float] = defaultdict(float)
        for t in toks:
            w = self.stem_idf.get(t)
            if w is None:
                continue
            for i in self.stem_inv[t]:
                if only is None or self.docs[i].source_id == only:
                    scores[i] += w
        ranked = sorted(
            (
                (i, s / (1 + 0.15 * math.log(1 + len(self.docs[i].tokens))))
                for i, s in scores.items()
            ),
            key=lambda x: (-x[1], x[0]),
        )
        return ranked[:k]


class HadithVerifier:
    def __init__(
        self,
        index: HadithIndex,
        known_weak: KnownWeakRepo | None,
        linker: ReferenceLinker,
    ) -> None:
        self.index = index
        self.known_weak = known_weak
        self.linker = linker
        self._kw: list[tuple[KnownWeak, list[str]]] = []
        if known_weak:
            for kw in known_weak.all():
                self._kw.append((kw, [normalize(v) for v in [kw.text, *kw.variants]]))

    # ── ١. المشتهر ──
    def known_weak_match(self, text: str) -> KnownWeak | None:
        q = normalize(text)
        if not q:
            return None
        best: tuple[float, KnownWeak] | None = None
        for kw, variants in self._kw:
            for v in variants:
                if v in q:
                    score = 100.0
                else:
                    shorter, longer = sorted((q, v), key=len)
                    if len(shorter.split()) < 2 or len(shorter) < 0.6 * len(longer):
                        score = fuzz.ratio(q, v)
                    else:
                        score = max(fuzz.ratio(q, v), fuzz.partial_ratio(shorter, longer))
                if score >= KNOWN_WEAK_MIN and (best is None or score > best[0]):
                    best = (score, kw)
        return best[1] if best else None

    # ── ٢ و٤. الحتمي ──
    def verify_deterministic(
        self, text: str, presented_as_verbatim: bool, cited_book: str | None
    ) -> Outcome | HadithPending:
        kw = self.known_weak_match(text)
        if kw is not None:
            return self._known_weak_outcome(kw)

        q = normalize(text)
        hits = self.index.exact_hits(q)
        match_type = MatchType.NORMALIZED
        if not hits:
            ranked = self.index.ranked(q, k=TOP_K)
            for i, _ in ranked:
                if (
                    len(q.split()) >= MIN_QUERY_WORDS
                    and fuzz.partial_ratio(q, self.index.docs[i].norm) >= VERBATIM_FUZZY_MIN
                ):
                    hits.append(i)
            match_type = MatchType.PARTIAL
            if not hits:
                return HadithPending([self._candidate(i, s) for i, s in self._candidate_pool(q)])
        return self._found(
            text, hits, match_type, presented_as_verbatim, cited_book, by_meaning=False
        )

    def _candidate_pool(self, q: str) -> list[tuple[int, float]]:
        """أفضل 3 من كل الكتب + أفضل 2 من مصادر الاحتجاج، ومصادر الاحتجاج أولًا (ERRORS.md E-002).

        فالحديث الذي في البخاري والترمذي معًا لا يُعرض للحَكَم من الترمذي وحده.
        """
        overall = self.index.ranked(q, k=3)
        authentic_ids = [
            sid for sid, src in self.index.sources.items() if src.info.role is SourceRole.AUTHENTIC
        ]
        auth: list[tuple[int, float]] = []
        for sid in authentic_ids:
            auth += self.index.ranked(q, k=2, only=sid)
        auth = sorted(auth, key=lambda x: -x[1])[:2]
        seen: set[int] = set()
        pool: list[tuple[int, float]] = []
        for i, s in [*overall, *auth]:
            if i not in seen:
                seen.add(i)
                pool.append((i, s))
        pool.sort(key=lambda x: (self.index.docs[x[0]].role is not SourceRole.AUTHENTIC, -x[1]))
        return pool[:TOP_K]

    def _candidate(self, i: int, s: float) -> Candidate:
        d = self.index.docs[i]
        return Candidate(
            key=f"{d.source_id}:{d.item_id}",
            source_id=d.source_id,
            item_id=d.item_id,
            role=d.role,
            score=round(s, 3),
            text_plain=self._passage(i).text_plain,
        )

    # ── ٣. بعد حكم النموذج ──
    def resolve_with_judgment(
        self,
        text: str,
        presented_as_verbatim: bool,
        cited_book: str | None,
        pending: HadithPending,
        judged_match: str | None,
        judged_key: str | None,
    ) -> Outcome:
        offered = {c.key: c for c in pending.candidates}
        if judged_match in ("VERBATIM", "PARAPHRASE") and judged_key in offered:
            c = offered[judged_key]
            idx = self._doc_index(c.source_id, c.item_id)
            if idx is not None:
                by_meaning = (
                    judged_match == "PARAPHRASE"
                    or fuzz.partial_ratio(normalize(text), self.index.docs[idx].norm) < 80
                )
                mt = MatchType.PARAPHRASE if by_meaning else MatchType.PARTIAL
                return self._found(
                    text, [idx], mt, presented_as_verbatim, cited_book, by_meaning=by_meaning
                )
        notes = []
        if judged_key and judged_key not in offered:
            notes.append("أُسقط معرّف أعاده النموذج لأنه ليس من المرشحين المعروضين (حارس الإسناد)")
        return self.not_found(text, notes)

    def not_found(self, text: str, notes: list[str] | None = None) -> Outcome:
        """«لم يُعثر عليه»، وتُرفع خطورته إن كان في متنه قرينة (BR-23). القرينة لا تحكم بالوضع."""
        signs = matn_signs(text)
        return Outcome(
            Signal.HADITH_NOT_FOUND_WITH_SIGNS if signs else Signal.HADITH_NOT_FOUND,
            facts={
                "search_url": self.linker.hadith_search_url(text),
                "matn_sign": "، ".join(signs),
            },
            confidence=Confidence.MEDIUM,
            notes=list(notes or []),
            evidence=[self._dorar_evidence(text)],
        )

    # ── أدوات ──
    def _found(
        self,
        text: str,
        hits: list[int],
        match_type: MatchType,
        presented_as_verbatim: bool,
        cited_book: str | None,
        by_meaning: bool,
    ) -> Outcome:
        docs = [self.index.docs[i] for i in hits]
        authentic = [i for i, d in zip(hits, docs, strict=True) if d.role is SourceRole.AUTHENTIC]
        locate = [i for i, d in zip(hits, docs, strict=True) if d.role is SourceRole.LOCATE]
        found_books = {d.source_id for d in docs}
        cited = canonical_books(cited_book)
        cited_known = cited - {"other"}

        def evidence_for(idxs: list[int]) -> list[Evidence]:
            seen: set[str] = set()
            out: list[Evidence] = []
            for i in idxs:
                d = self.index.docs[i]
                if d.source_id in seen:
                    continue
                seen.add(d.source_id)
                out.append(self._evidence(i, text, match_type))
                if len(out) == 2:
                    break
            return out

        # الشاهد من الكتاب الذي نسبه الكاتب إليه يتقدّم.
        def cited_first(idxs: list[int]) -> list[int]:
            return sorted(idxs, key=lambda i: self.index.docs[i].source_id not in cited)

        authentic, locate = cited_first(authentic), cited_first(locate)
        if authentic:
            ev = evidence_for(authentic + locate)
            facts = {"citation": ev[0].ref.citation, "citation_book": self._books_ar(found_books)}
            conf = Confidence.MEDIUM if by_meaning else Confidence.HIGH
            q_norm = normalize(text)
            missing = {
                b for b in cited_known - found_books if not self.index.book_contains(b, q_norm)
            }
            if missing:
                facts["cited_book"] = cited_book
                return Outcome(Signal.HADITH_MISATTRIBUTED, ev, facts, conf)
            if by_meaning:
                sig = (
                    Signal.HADITH_PARAPHRASE_AS_WORDING
                    if presented_as_verbatim
                    else Signal.HADITH_PARAPHRASE_DECLARED
                )
                notes = [] if presented_as_verbatim else ["منقول بالمعنى"]
                return Outcome(sig, ev, facts, conf, notes)
            return Outcome(Signal.HADITH_AUTHENTIC_MATCH, ev, facts, conf)

        ev = evidence_for(locate)
        ev.append(self._dorar_evidence(text))
        facts = {"citation": ev[0].ref.citation, "citation_book": self._books_ar(found_books)}
        notes = []
        if cited_known & {"bukhari", "muslim"}:
            notes.append(f"نُسب في المسودة إلى «{cited_book}»، ولم نجده فيه")
        if by_meaning:
            notes.append("وُجد بالمعنى لا باللفظ")
        return Outcome(Signal.HADITH_LOCATE_ONLY, ev, facts, Confidence.MEDIUM, notes)

    def _known_weak_outcome(self, kw: KnownWeak) -> Outcome:
        ev = Evidence(
            ref=SourceRef(
                source_id="known_weak",
                item_id=kw.id,
                citation="قائمة المشتهر الذي لا يصح",
                url=kw.url,
            ),
            role=SourceRole.RULING,
            text=kw.text,
            match_type=MatchType.PARTIAL,
            match_reason="تشابه عالٍ مع بند في قائمة المشتهر",
        )
        facts = {
            "ruling": kw.ruling_ar,
            "ruling_source": kw.ruling_source,
            "draft_note": "" if kw.verified else " (تنبيه: هذا البند في القائمة لم يُعتمد بعد)",
        }
        if kw.verified and kw.reviewed_by:
            notes = [f"راجع هذا البند على مصدره: {kw.reviewed_by}، في {kw.reviewed_on or '—'}"]
        else:
            notes = ["بند قائمة المشتهر بانتظار الاعتماد البشري"]
        evidence = [ev]
        alt = kw.alternative
        idx = self._doc_index(alt.source_id, alt.item_id) if alt else None
        if idx is not None:
            anchor = alt.anchor or ""  # type: ignore[union-attr]
            # «في معناه» لا «بلفظه»: نوع المطابقة PARAPHRASE، والتظليل بالعبارة المرجعية وحدها.
            alt_ev = self._evidence(idx, anchor, MatchType.PARAPHRASE)
            span = find_span(alt_ev.text, anchor) if anchor else None
            alt_ev = alt_ev.model_copy(
                update={
                    "match_reason": "البديل في معناه (من قائمة المشتهر، ونصه من المخزن)",
                    "highlight": [Span(start=span[0], end=span[1])] if span else [],
                }
            )
            evidence.append(alt_ev)
            if alt_ev.role is SourceRole.AUTHENTIC:
                facts["alternative_note"] = (
                    f" وفي معناه ما ثبت في {alt_ev.ref.citation}، وهو معروض بجانبه."
                )
            else:
                facts["alternative_note"] = (
                    f" ويُروى في معناه في {alt_ev.ref.citation}، وهو معروض بجانبه، والحكم عليه خارج ما يملكه سديد."
                )
        return Outcome(Signal.HADITH_KNOWN_WEAK, evidence, facts, Confidence.HIGH, notes)

    def _passage(self, idx: int) -> Passage:
        d = self.index.docs[idx]
        p = self.index.sources[d.source_id].get(d.item_id)
        assert p is not None
        return p

    def _doc_index(self, source_id: str, item_id: str) -> int | None:
        return self.index.pos.get((source_id, item_id))

    def _evidence(self, idx: int, quote: str, match_type: MatchType) -> Evidence:
        d = self.index.docs[idx]
        p = self._passage(idx)
        src = self.index.sources[d.source_id]
        span = find_span(p.text_display, quote) if match_type is not MatchType.PARAPHRASE else None
        reason = {
            MatchType.NORMALIZED: "تطابق حرفي بعد حذف التشكيل",
            MatchType.PARTIAL: "تطابق باللفظ مع فروق يسيرة",
            MatchType.PARAPHRASE: "تشابه في المعنى (بحكم النموذج على مرشحين من المخزن)",
        }.get(match_type, "تطابق")
        return Evidence(
            ref=SourceRef(
                source_id=d.source_id,
                item_id=d.item_id,
                citation=f"{src.info.name_ar}، رقم {p.number} (بترقيم مجموعة البيانات)",
                url=self.linker.hadith_search_url(quote or p.text_plain),
            ),
            role=d.role,
            text=p.text_display,
            match_type=match_type,
            match_reason=reason,
            highlight=[Span(start=span[0], end=span[1])] if span else [],
        )

    def _dorar_evidence(self, quote: str) -> Evidence:
        return Evidence(
            ref=SourceRef(
                source_id="dorar",
                item_id="search",
                citation="بحث في الدرر السنية",
                url=self.linker.hadith_search_url(quote),
            ),
            role=SourceRole.LINK,
            text="",
            match_type=MatchType.NONE,
            match_reason="رابط بحث يفتحه الإنسان، لا استدعاء آلي",
        )

    @staticmethod
    def _books_ar(books: set[str]) -> str:
        names = [
            BOOK_SHORT[b]
            for b in ("bukhari", "muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah")
            if b in books
        ]
        return " و".join(names) if names else "—"
