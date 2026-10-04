"""المقاييس (البروتوكول §٦) والإحصاء (§٧): تعريفات حرفية، ومكتبة قياسية فقط.

لكل حالة: نطابقها بأفضل ملاحظة متداخلة (IoU ≥ 0.5). «التنبيه» = إجراء غير NONE.
"""

from __future__ import annotations

import math
import random
import re
from collections import defaultdict
from statistics import median
from typing import Any

from rapidfuzz import fuzz

from saadeed.adapters.eval.bank import GROUP_OF, TestCase
from saadeed.adapters.eval.systems import Pred, SystemRun
from saadeed.adapters.factory import Engine
from saadeed.domain.models import Span
from saadeed.text.markers import canonical_books, parse_ref
from saadeed.text.normalize import normalize

IOU_MIN = 0.5
_WEAK_WORDS = re.compile(r"ضعيف|موضوع|لا يصح|لا أصل|لا اصل|مكذوب|باطل|منكر|لم يثبت|غير ثابت")


def match_pred(case: TestCase, preds: list[Pred]) -> Pred | None:
    cs = Span(start=case.span[0], end=case.span[1])
    best: tuple[float, Pred] | None = None
    for p in preds:
        iou = cs.iou(Span(start=p.span[0], end=p.span[1]))
        if iou >= IOU_MIN and (
            best is None or iou > best[0] or (iou == best[0] and p.action != "NONE")
        ):
            best = (iou, p)
    return best[1] if best else None


def flagged(p: Pred | None) -> bool:
    return p is not None and p.action != "NONE"


def correct(case: TestCase, p: Pred | None) -> bool:
    """للـ McNemar: المعيب نُبّه عليه، والسليم لم يُنبَّه عليه."""
    return flagged(p) if case.defective else not flagged(p)


def _ratio(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def bootstrap_ci(
    values: list[int], iters: int = 1000, seed: int = 70
) -> tuple[float, float] | None:
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    stats = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return round(stats[int(0.025 * iters)], 4), round(stats[int(0.975 * iters) - 1], 4)


def mcnemar_exact(b: int, c: int) -> float | None:
    """اختبار McNemar الدقيق (ذو الطرفين) على الحالات المتعارضة فقط."""
    n = b + c
    if n == 0:
        return None
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return round(min(1.0, 2 * p), 6)


class CitationChecker:
    """يفحص المراجع التي يذكرها أي نظام بالأداة نفسها (§٦: الاستشهاد المختلق)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def check_pred(self, p: Pred) -> str:
        """يعيد: ok · fabricated · unverifiable · none."""
        if p.evidence:  # سديد: الشواهد من المخزن
            for e in p.evidence:
                if (
                    e["role"] in ("AUTHENTIC", "LOCATE", "REFERENCE_TEXT")
                    and e["match_type"] in ("NORMALIZED", "PARTIAL", "EXACT")
                    and fuzz.partial_ratio(normalize(p.quote), normalize(e["text"])) < 60
                ):
                    return "fabricated"
            return "ok"
        if not p.source or (p.action != "NONE" and not p.correct_text):
            return "none"
        text = p.correct_text or p.quote
        ref = parse_ref(p.source) or parse_ref(_extract_ref(p.source) or "")
        if ref:
            sura, a, b = ref
            ayat = [self.engine.sources.quran.get(sura, x) for x in range(a, b + 1)]
            if not all(ayat):
                return "fabricated"
            joined = normalize(" ".join(x.text_simple for x in ayat if x))
            return "ok" if fuzz.partial_ratio(normalize(text), joined) >= 85 else "fabricated"
        books = canonical_books(p.source) - {"other"}
        if books:
            q = normalize(text)
            return (
                "ok"
                if all(self.engine.hadith.index.book_contains(b, q) for b in books)
                else "fabricated"
            )
        return "unverifiable"


_REF_IN_TEXT = re.compile(r"(?:سورة\s+)?([ء-ي\s]{2,20})[\s:،,]*(?:الآية|آية|اية)?\s*(\d+)")


def _extract_ref(source: str) -> str | None:
    m = _REF_IN_TEXT.search(source)
    return f"{m.group(1).strip()}: {m.group(2)}" if m else None


def compute(
    cases: list[TestCase], runs: dict[str, list[SystemRun]], engine: Engine
) -> dict[str, Any]:
    """يحسب المقاييس لكل نظام (التشغيل الأول) والاتساق (عبر التشغيلات)."""
    checker = CitationChecker(engine)
    by_carrier = defaultdict(list)
    for c in cases:
        by_carrier[c.carrier_id].append(c)
    out: dict[str, Any] = {"systems": {}, "n_cases": len(cases)}
    per_case_correct: dict[str, dict[str, bool]] = {}

    for system, system_runs in runs.items():
        first = {r.carrier_id: r for r in system_runs if r.run == 1}
        defective = [c for c in cases if c.defective]
        sound = [c for c in cases if not c.defective]
        det = strict = fa = 0
        det_vec: list[int] = []
        fa_vec: list[int] = []
        crit_miss: list[str] = []
        extracted = 0
        by_cat: dict[str, list[int]] = defaultdict(list)
        by_group: dict[str, list[int]] = defaultdict(list)
        fabricated = unverifiable = 0
        fab_confirmed = false_acc = 0
        referral_ok = referral_n = 0
        tp_flags = all_flags = 0
        exceeds_tp = exceeds_all = 0
        correct_map: dict[str, bool] = {}
        for c in cases:
            run = first.get(c.carrier_id)
            p = match_pred(c, run.preds) if run else None
            if p is not None:
                extracted += 1
            is_flag = flagged(p)
            correct_map[c.case_id] = correct(c, p)
            if c.defective:
                det += is_flag
                det_vec.append(int(is_flag))
                strict += int(is_flag and p is not None and p.reason == c.expected.reason)
                if c.critical and not is_flag:
                    crit_miss.append(c.case_id)
            else:
                fa += is_flag
                fa_vec.append(int(is_flag))
            by_cat[c.category].append(int(correct_map[c.case_id]))
            by_group[GROUP_OF.get(c.category, c.category)].append(int(correct_map[c.case_id]))
            if is_flag:
                all_flags += 1
                tp_flags += int(c.defective)
            if p is not None:
                st = checker.check_pred(p)
                fabricated += st == "fabricated"
                if c.category == "O1":
                    unverifiable += st == "unverifiable"
            if (
                c.category == "H7"
                and p is not None
                and (p.action == "NONE" or (p.source and p.evidence_status == "SUPPORTED"))
            ):
                fab_confirmed += 1
            if c.category in ("H8a", "H8b") and p is not None:
                accused = (
                    p.evidence_status == "CONTRADICTED"
                    or p.reason == "KNOWN_WEAK"
                    or bool(p.issue and _WEAK_WORDS.search(p.issue))
                )
                false_acc += int(accused)
            if c.category in ("O5", "O6"):
                referral_n += 1
                referral_ok += int(p is not None and p.action == "REFER")
            if (
                c.category in ("H9", "H10")
                and p is not None
                and p.evidence_status == "EXCEEDS_SOURCE"
            ):
                exceeds_all += 1
                exceeds_tp += int(c.category == "H9")
        lat = [r.latency_ms for r in first.values()]
        per_case_correct[system] = correct_map
        out["systems"][system] = {
            "detection": _ratio(det, len(defective)),
            "detection_ci": bootstrap_ci(det_vec),
            "detection_strict": _ratio(strict, len(defective)) if system != "B0" else None,
            "false_alarm": _ratio(fa, len(sound)),
            "false_alarm_ci": bootstrap_ci(fa_vec),
            "precision": _ratio(tp_flags, all_flags),
            "critical_missed": len(crit_miss),
            "critical_missed_ids": crit_miss,
            "critical_total": sum(1 for c in cases if c.critical),
            "fabricated_citations": fabricated,
            "fabricated_confirmed_H7": fab_confirmed,
            "unverifiable_sourcing_O1": unverifiable,
            "false_accusation_H8": false_acc,
            "mandatory_referral": _ratio(referral_ok, referral_n),
            "exceeds_precision": _ratio(exceeds_tp, exceeds_all),
            "extraction_recall": _ratio(extracted, len(cases)),
            "by_category": {k: _ratio(sum(v), len(v)) for k, v in sorted(by_cat.items())},
            "by_group": {k: _ratio(sum(v), len(v)) for k, v in sorted(by_group.items())},
            "latency_p50_ms": int(median(lat)) if lat else None,
            "latency_p95_ms": int(sorted(lat)[max(0, math.ceil(0.95 * len(lat)) - 1)])
            if lat
            else None,
            "tokens": sum(r.prompt_tokens + r.completion_tokens for r in first.values()),
            "llm_calls": sum(r.llm_calls for r in first.values()),
            "errors": [r.error for r in first.values() if r.error],
            "consistency": _consistency(cases, system_runs),
        }

    if "saadeed" in per_case_correct and "B0" in per_case_correct:
        s, b = per_case_correct["saadeed"], per_case_correct["B0"]
        b_only = sum(1 for k in s if s[k] and not b.get(k))
        c_only = sum(1 for k in s if b.get(k) and not s[k])
        out["mcnemar_saadeed_vs_B0"] = {
            "saadeed_only": b_only,
            "b0_only": c_only,
            "p": mcnemar_exact(b_only, c_only),
        }
    return out


def _consistency(cases: list[TestCase], system_runs: list[SystemRun]) -> float | None:
    runs = sorted({r.run for r in system_runs})
    if len(runs) < 2:
        return None
    by_run = {k: {r.carrier_id: r for r in system_runs if r.run == k} for k in runs}
    same = 0
    for c in cases:
        sigs = set()
        for k in runs:
            r = by_run[k].get(c.carrier_id)
            p = match_pred(c, r.preds) if r else None
            sigs.add((p.evidence_status, p.reason, p.action) if p else ("MISS",))
        same += len(sigs) == 1
    return round(same / len(cases), 4)
