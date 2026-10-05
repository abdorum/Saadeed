"""متحقق الآيات (ADR-0004): حتمي بالكامل، ولا يستدعي النموذج اللغوي.

الخطوات (المعمارية §٧.١):
1. تطبيع الاقتباس إلى كلمات.
2. بحث في فهرس n-gram للكلمات على المصحف كله (تسلسل واحد، فالاقتباس قد يمتد على آيتين).
3. محاذاة كلمة بكلمة على نافذة كل مرشح، واختيار الأفضل.
4. القرار بعتبات ثابتة (تُضبط على dev فقط): مطابق / يختلف / ليس في المصحف.
5. فحص الإحالة المذكورة مقابل الموضع الفعلي.

النتيجة نفسها لكل تشغيل: لا عشوائية ولا نموذج.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from saadeed.domain.enums import Confidence, MatchType, SourceRole
from saadeed.domain.models import Evidence, SourceRef, Span
from saadeed.domain.policy import Signal
from saadeed.domain.ports import Ayah, QuranRepo
from saadeed.domain.quran_meta import citation as quran_citation
from saadeed.text.align import Alignment, align, diff_summary, rasm_key, relax_rasm
from saadeed.text.markers import parse_ref
from saadeed.text.normalize import normalize
from saadeed.verifiers.base import Outcome

# العتبات (تُضبط على dev وحده، وكل تغيير يُسجَّل في ERRORS.md)
MIN_WORDS = 2
"""أقل اقتباس يُفحص. والكلمة الواحدة لا تكفي للحكم."""
MISMATCH_MIN_SCORE = 0.6
MISMATCH_MIN_MATCHED = 3
WINDOW_PAD = 4
MAX_ANCHORS = 8


@dataclass
class _Word:
    norm: str
    disp: str
    sura: int
    aya: int


@dataclass(frozen=True)
class Run:
    """مقطع من الاقتباس (`q_start:q_end` بالكلمات) يطابق المصحف حرفيًا في `g_start:g_end`."""

    q_start: int
    q_end: int
    g_start: int
    g_end: int

    @property
    def length(self) -> int:
        return self.q_end - self.q_start


MERGE_MIN_RUN = 3
"""أقصر مقطع يُعدّ جزءًا من آية مدموجة."""
MERGE_MIN_COVERAGE = 0.85
"""نسبة كلمات الاقتباس التي يجب أن تغطيها المقاطع القرآنية لنقول: آيتان مدموجتان."""
MERGE_MIN_GAP = 4
"""أقل مسافة (بالكلمات) بين موضعي المقطعين في المصحف ليُعدّا موضعين مختلفين."""


def _pair_words(text: str) -> list[tuple[str, str]]:
    """كلمات العرض مع مقابلها المطبَّع. وتُحذف الكلمات التي هي علامات وقف فقط."""
    pairs: list[tuple[str, str]] = []
    for raw in text.split():
        norm = normalize(raw)
        if not norm:
            continue
        for part in norm.split():
            pairs.append((part, raw))
    return pairs


class QuranIndex:
    """فهرس المصحف: تسلسل كلمات واحد، وفهارس n-gram عليه."""

    def __init__(self, repo: QuranRepo) -> None:
        self.repo = repo
        self.words: list[_Word] = []
        self.ayah_ranges: dict[tuple[int, int], tuple[int, int]] = {}
        for ay in repo.all_ayat():
            start = len(self.words)
            for norm, disp in _pair_words(ay.text_simple):
                self.words.append(_Word(norm, disp, ay.sura, ay.aya))
            self.ayah_ranges[(ay.sura, ay.aya)] = (start, len(self.words))
        self._norms = [w.norm for w in self.words]
        self._keys = [rasm_key(n) for n in self._norms]
        self._tri: dict[tuple[str, str, str], list[int]] = defaultdict(list)
        self._bi: dict[tuple[str, str], list[int]] = defaultdict(list)
        k = self._keys
        for i in range(len(k) - 1):
            self._bi[(k[i], k[i + 1])].append(i)
            if i + 2 < len(k):
                self._tri[(k[i], k[i + 1], k[i + 2])].append(i)

    def anchors(self, q_norm: list[str]) -> list[int]:
        q = [rasm_key(w) for w in q_norm]
        votes: Counter[int] = Counter()
        if len(q) >= 3:
            for i in range(len(q) - 2):
                for pos in self._tri.get((q[i], q[i + 1], q[i + 2]), ()):
                    votes[pos - i] += 1
        if not votes and len(q) >= 2:
            for i in range(len(q) - 1):
                for pos in self._bi.get((q[i], q[i + 1]), ()):
                    votes[pos - i] += 1
        # ترتيب حتمي: الأكثر أصواتًا، ثم الأسبق في المصحف.
        return [a for a, _ in sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_ANCHORS]]

    def best_alignment(self, q: list[str], q_disp: list[str]) -> tuple[int, Alignment] | None:
        best: tuple[int, Alignment] | None = None
        for anchor in self.anchors(q):
            lo = max(0, anchor - WINDOW_PAD)
            hi = min(len(self.words), anchor + len(q) + WINDOW_PAD)
            window = self._norms[lo:hi]
            disp = [w.disp for w in self.words[lo:hi]]
            al = align(q, window, q_disp, disp)
            if al is None:
                continue
            key = (al.score, al.matched, -lo)
            if best is None or key > (best[1].score, best[1].matched, -best[0]):
                best = (lo, al)
        return best

    def occurrences(self, keys: list[str]) -> list[int]:
        """مواضع تسلسل كلمات (بمفاتيح الرسم) في المصحف حرفيًا. ثلاث كلمات فأكثر."""
        if len(keys) < 3:
            return []
        n = len(keys)
        return [
            p
            for p in self._tri.get((keys[0], keys[1], keys[2]), ())
            if self._keys[p : p + n] == keys
        ]

    def runs(self, q_norm: list[str], min_len: int) -> list[Run]:
        """أكبر تغطية للاقتباس بمقاطع قرآنية حرفية لا يقل كل منها عن `min_len` كلمة.

        برمجة ديناميكية حتمية: لكل موضع أطول مقطع يبدأ منه، ثم أفضل تقسيم يغطي أكثر الكلمات.
        تكشف الآية داخل جملة، والآيتين المدموجتين في اقتباس واحد (الفحص المتقاطع، ADR-0014).
        """
        keys = [rasm_key(w) for w in q_norm]
        n = len(keys)
        if n < min_len or min_len < 3:
            return []
        longest = [0] * n
        for j in range(n - 2):
            cands = list(self._tri.get((keys[j], keys[j + 1], keys[j + 2]), ()))
            length = 3 if cands else 0
            while cands and j + length < n:
                nxt = [
                    p
                    for p in cands
                    if p + length < len(self._keys) and self._keys[p + length] == keys[j + length]
                ]
                if not nxt:
                    break
                cands = nxt
                length += 1
            longest[j] = length
        best = [0] * (n + 1)
        back: list[tuple[int, int] | None] = [None] * (n + 1)
        for i in range(1, n + 1):
            best[i], back[i] = best[i - 1], None
            for j in range(0, i - min_len + 1):
                if longest[j] >= i - j and best[j] + (i - j) > best[i]:
                    best[i], back[i] = best[j] + (i - j), (j, i)
        segs: list[tuple[int, int]] = []
        i = n
        while i > 0:
            if back[i] is None:
                i -= 1
            else:
                j, _ = back[i]
                segs.append((j, i))
                i = j
        segs.reverse()
        out: list[Run] = []
        prev_end: int | None = None
        for j, i in segs:
            occ = self.occurrences(keys[j:i])
            if not occ:
                continue
            # نفضّل الموضع الملاصق للمقطع السابق، ثم الأسبق في المصحف (حتمي).
            g = next((p for p in occ if prev_end is not None and 0 <= p - prev_end <= 3), occ[0])
            out.append(Run(j, i, g, g + (i - j)))
            prev_end = g + (i - j)
        return out

    def ayat_between(self, g_start: int, g_end: int) -> list[tuple[int, int]]:
        seen: list[tuple[int, int]] = []
        for w in self.words[g_start:g_end]:
            key = (w.sura, w.aya)
            if not seen or seen[-1] != key:
                seen.append(key)
        return seen


class QuranVerifier:
    def __init__(self, repo: QuranRepo, index: QuranIndex | None = None) -> None:
        self.repo = repo
        self.index = index or QuranIndex(repo)

    def verify(self, quote: str, cited_ref: str | None = None) -> Outcome:
        q_pairs = _pair_words(quote)
        q = [n for n, _ in q_pairs]
        q_disp = [d for _, d in q_pairs]
        if len(q) < MIN_WORDS:
            return Outcome(
                Signal.QURAN_NOT_IN_MUSHAF,
                facts={"note": "اقتباس قصير جدًا"},
                confidence=Confidence.LOW,
                notes=["الاقتباس أقصر من أن يُحكم عليه، فعومل معاملة ما لم يُعثر عليه"],
            )

        found = self.index.best_alignment(q, q_disp)
        if found is None:
            return self._merged(q) or Outcome(
                Signal.QURAN_NOT_IN_MUSHAF, confidence=Confidence.HIGH
            )
        lo, al = found
        g_start, g_end = lo + al.src_start, lo + al.src_end
        al.ops = relax_rasm(al.ops, q, self.index._norms[g_start:g_end])
        exact = all(o.op == "equal" for o in al.ops) and (g_end - g_start) == len(q)
        if not exact:
            merged = self._merged(q)
            if merged is not None:
                return merged
        if not exact and (al.score < MISMATCH_MIN_SCORE or al.matched < MISMATCH_MIN_MATCHED):
            return Outcome(Signal.QURAN_NOT_IN_MUSHAF, confidence=Confidence.HIGH)

        notes_rasm = ["فرق رسم لا يُنبَّه عليه"] if exact and al.matched < len(q) else []
        if exact and cited_ref:
            # العبارة قد تتكرر في المصحف: نقبل الإحالة إلى أي موضع تطابقه حرفيًا.
            alt = self._exact_occurrence_matching_ref(q, cited_ref)
            if alt is not None:
                g_start, g_end = alt
        ayat = self.index.ayat_between(g_start, g_end)
        evidence = self._evidence(ayat, g_start, g_end, al, exact)
        cit = evidence.ref.citation
        facts = {"citation": cit, "cited_ref": cited_ref}

        if not exact:
            count, summary = diff_summary(al.ops)
            facts.update(diff_count=count, diff_summary=summary)
            notes = []
            if cited_ref and not self._ref_ok(cited_ref, ayat):
                notes.append(f"والإحالة المذكورة ({cited_ref}) لا توافق الموضع أيضًا")
            return Outcome(Signal.QURAN_TEXT_MISMATCH, [evidence], facts, Confidence.HIGH, notes)

        if cited_ref and not self._ref_ok(cited_ref, ayat):
            if parse_ref(cited_ref) is None:
                return Outcome(
                    Signal.QURAN_MATCH,
                    [evidence],
                    facts,
                    Confidence.HIGH,
                    [f"لم نتمكن من قراءة الإحالة «{cited_ref}» فلم نفحصها"],
                )
            return Outcome(Signal.QURAN_WRONG_REFERENCE, [evidence], facts, Confidence.HIGH)
        return Outcome(Signal.QURAN_MATCH, [evidence], facts, Confidence.HIGH, notes_rasm)

    def _merged(self, q: list[str]) -> Outcome | None:
        """آيتان (أو أكثر) من موضعين مختلفين قُدّمتا اقتباسًا واحدًا (BR-21)."""
        runs = self.index.runs(q, MERGE_MIN_RUN)
        if len(runs) < 2 or sum(r.length for r in runs) < MERGE_MIN_COVERAGE * len(q):
            return None
        apart = any(
            not (0 <= b.g_start - a.g_end < MERGE_MIN_GAP)
            for a, b in zip(runs, runs[1:], strict=False)
        )
        if not apart:
            return None
        evidence = [
            self._evidence(
                self.index.ayat_between(r.g_start, r.g_end), r.g_start, r.g_end, None, True
            )
            for r in runs
        ]
        parts = "، و".join(
            f"«{' '.join(w.disp for w in self.index.words[r.g_start : r.g_end])}» ({e.ref.citation})"
            for r, e in zip(runs, evidence, strict=True)
        )
        return Outcome(
            Signal.QURAN_MERGED,
            evidence,
            {"citation": evidence[0].ref.citation, "parts": parts, "parts_count": len(runs)},
            Confidence.HIGH,
        )

    def _exact_occurrence_matching_ref(
        self, q: list[str], cited_ref: str
    ) -> tuple[int, int] | None:
        parsed = parse_ref(cited_ref)
        if parsed is None:
            return None
        sura, a, b = parsed
        n = len(q)
        norms = self.index._norms
        for anchor in self.index.anchors(q) + self._all_occurrences(q):
            if anchor >= 0 and [rasm_key(w) for w in norms[anchor : anchor + n]] == [
                rasm_key(w) for w in q
            ]:
                ayat = self.index.ayat_between(anchor, anchor + n)
                if any(s == sura and a <= ay <= b for s, ay in ayat):
                    return anchor, anchor + n
        return None

    def _all_occurrences(self, q_norm: list[str]) -> list[int]:
        q = [rasm_key(w) for w in q_norm]
        if len(q) >= 3:
            return list(self.index._tri.get((q[0], q[1], q[2]), ()))
        return list(self.index._bi.get((q[0], q[1]), ())) if len(q) == 2 else []

    @staticmethod
    def _ref_ok(cited_ref: str, ayat: list[tuple[int, int]]) -> bool:
        parsed = parse_ref(cited_ref)
        if parsed is None:
            return True  # لا نحكم على إحالة لم نقرأها
        sura, a, b = parsed
        return any(s == sura and a <= ay <= b for s, ay in ayat)

    def _evidence(
        self,
        ayat: list[tuple[int, int]],
        g_start: int,
        g_end: int,
        al: Alignment | None,
        exact: bool,
    ) -> Evidence:
        first, last = ayat[0], ayat[-1]
        sura = first[0]
        if first[0] == last[0]:
            cit = quran_citation(sura, first[1], last[1])
            item_id = f"{sura}:{first[1]}" if first == last else f"{sura}:{first[1]}-{last[1]}"
        else:
            cit = f"{quran_citation(first[0], first[1])} — {quran_citation(last[0], last[1])}"
            item_id = f"{first[0]}:{first[1]}-{last[0]}:{last[1]}"
        text = render_ayat(self.repo, ayat)
        whole = self._covers_whole_ayat(ayat, g_start, g_end)
        if exact:
            mt = MatchType.NORMALIZED if whole else MatchType.PARTIAL
            reason = "تطابق تام بعد حذف التشكيل" if whole else "تطابق تام مع جزء من الآية"
        else:
            mt = MatchType.MISMATCH
            reason = "تشابه عالٍ مع اختلاف في كلمات"
        return Evidence(
            ref=SourceRef(
                source_id="quran",
                item_id=item_id,
                citation=cit,
                url=self.repo.ayah_url(sura, first[1]),
            ),
            role=SourceRole.REFERENCE_TEXT,
            text=text,
            match_type=mt,
            match_reason=reason,
            diff=al.ops if (al is not None and not exact) else [],
            highlight=[Span(start=0, end=len(text))] if whole else [],
        )

    def _covers_whole_ayat(self, ayat: list[tuple[int, int]], g_start: int, g_end: int) -> bool:
        a0 = self.index.ayah_ranges[ayat[0]][0]
        a1 = self.index.ayah_ranges[ayat[-1]][1]
        return g_start == a0 and g_end == a1


def render_ayat(repo: QuranRepo, ayat: list[tuple[int, int]]) -> str:
    """نص الشاهد القرآني: الرسم العثماني من المخزن، ورقم كل آية بعدها."""
    parts: list[str] = []
    for s, a in ayat:
        ay: Ayah | None = repo.get(s, a)
        if ay:
            parts.append(f"{ay.text_uthmani} ({a})")
    return " ".join(parts)


def ayat_from_item_id(item_id: str) -> list[tuple[int, int]]:
    """«2:255» أو «33:70-71» أو «2:285-3:1» ← قائمة (سورة، آية)."""
    from saadeed.domain.quran_meta import AYA_COUNTS

    if "-" not in item_id:
        s, a = item_id.split(":")
        return [(int(s), int(a))]
    left, right = item_id.split("-")
    s1, a1 = (int(x) for x in left.split(":"))
    if ":" in right:
        s2, a2 = (int(x) for x in right.split(":"))
    else:
        s2, a2 = s1, int(right)
    out: list[tuple[int, int]] = []
    s, a = s1, a1
    while (s, a) <= (s2, a2):
        out.append((s, a))
        a += 1
        if a > AYA_COUNTS[s - 1]:
            s, a = s + 1, 1
    return out
