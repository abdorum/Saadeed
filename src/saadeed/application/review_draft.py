"""حالة الاستخدام: من المسودة إلى تقرير المراجعة (المعمارية §٥).

المسار:
  تقطيع ← استخراج (نداء ١) + مرور حتمي ← توجيه كل ادعاء ← متحققات حتمية
  ← حَكَم الأحاديث غير المحسومة (نداء ٢، عند الحاجة) ← ميزان السداد ← القوالب ← حارس الإسناد ← تقرير.

ما يقرره النموذج: أين الادعاءات ونوعها (١)، وهل حديث المسودة يطابق مرشحًا من المخزن لفظًا أو معنًى (٢).
ما لا يقرره أبدًا: نص المصدر، والحالة، والأثر، والإجراء، ونص الشرح.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from saadeed import __version__
from saadeed.application.citation_guard import CitationGuard
from saadeed.application.crosscheck import cross_check
from saadeed.application.extraction import extract_claims, is_generalization, llm_error_ar
from saadeed.application.library_check import check_rulings, check_sayings, gate_generalizations
from saadeed.application.prompts import PromptSet
from saadeed.application.safety_net import safety_net
from saadeed.application.suggestion_guard import safe_suggestion
from saadeed.domain.enums import (
    ClaimType,
    Confidence,
    ContentLevel,
    MatchType,
    OverreachType,
    Relation,
    SegmentKind,
    Severity,
    SourceRole,
    TrackBucket,
)
from saadeed.domain.models import (
    Claim,
    Coverage,
    DraftInfo,
    Evidence,
    Finding,
    ManifestStamp,
    MapEntry,
    Meta,
    RelationResult,
    ReviewReport,
    Sentence,
    SourceRef,
    Span,
    Summary,
)
from saadeed.domain.policy import POLICY_VERSION, Signal, apply
from saadeed.domain.ports import LibraryPort, LLMError, LLMPort, LLMUsage
from saadeed.domain.templates import explanation_for, next_step_for
from saadeed.text.footnotes import Footnotes, find_footnotes, strip_ref
from saadeed.text.markers import canonical_books, parse_ref
from saadeed.text.normalize import find_span, normalize
from saadeed.text.segment import split_sentences, word_count
from saadeed.verifiers.base import Outcome
from saadeed.verifiers.hadith import HadithPending, HadithVerifier
from saadeed.verifiers.quran import QuranVerifier

MAX_WORDS = 3000
SNIPPET_WORDS = 70


class DraftError(ValueError):
    """مسودة غير صالحة (فارغة أو أطول من الحد)."""


@dataclass
class ReviewConfig:
    enable_overreach: bool = False
    """فحص التجاوز (FR-36، S): مطفأ في المنتج حتى يجتاز معيار الإسقاط F8."""
    quran_mode: str = "deterministic"
    """deterministic (سديد) أو llm (خط الأساس B1: النموذج يحكم على الآيات)."""
    max_words: int = MAX_WORDS


@dataclass
class _Ctx:
    usage: list[LLMUsage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    degraded: bool = False
    calls: int = 0


class ReviewDraft:
    def __init__(
        self,
        llm: LLMPort | None,
        quran: QuranVerifier,
        hadith: HadithVerifier,
        guard: CitationGuard,
        prompts: PromptSet,
        coverage: Coverage,
        manifest: ManifestStamp,
        config: ReviewConfig | None = None,
        quran_llm_judge: Any = None,
        library: LibraryPort | None = None,
    ) -> None:
        self.llm = llm
        self.quran = quran
        self.hadith = hadith
        self.guard = guard
        self.prompts = prompts
        self.coverage = coverage
        self.manifest = manifest
        self.config = config or ReviewConfig()
        self.quran_llm_judge = quran_llm_judge
        self.library = library

    # ─────────────────────────────── المدخل ───────────────────────────────
    def review(self, text: str) -> ReviewReport:
        t0 = time.monotonic()
        text = text.replace("\r\n", "\n")
        if not text.strip():
            raise DraftError("المسودة فارغة")
        wc = word_count(text)
        if wc > self.config.max_words:
            raise DraftError(f"المسودة أطول من الحد ({wc} كلمة، والحد {self.config.max_words})")

        ctx = _Ctx()
        if wc < 30:
            ctx.warnings.append("النص قصير. سديد صُمّم للمسودة الكاملة، وقد فُحص ما فيه.")
        # الحواشي مصادر الكاتب لا ادعاءاته: لا تُقرأ ادعاءات، وتُلحق بما أشار إليها (E-023).
        notes = find_footnotes(text)
        sentences = [s for s in split_sentences(text) if not notes.in_zone(s.span.start)]
        ex = extract_claims(text, sentences, self.llm, self.prompts.extract)
        ctx.usage += ex.usage
        ctx.calls += len(ex.usage)
        ctx.warnings += ex.warnings
        not_checked: list[str] = []
        if ex.llm_failed:
            ctx.degraded = self.llm is not None
            not_checked.append(
                "الادعاءات غير المعلَّمة (أقوال، وأرقام، وإجماع، وتعميم، وإحالات): لم تُستخرج لأن النموذج غير متاح، وفُحصت الآيات والأحاديث المعلَّمة وحدها"
            )
        elif ex.failed_parts:
            ctx.degraded = True
            not_checked.append(
                f"الادعاءات غير المعلَّمة في {ex.failed_parts} من أجزاء المسودة: تعذّر استخراجها، وفُحصت الآيات والأحاديث المعلَّمة فيها"
            )

        claims = ex.claims
        if self.config.quran_mode == "deterministic":
            claims, cc_notes = cross_check(
                text, claims, sentences, self.quran.index, is_generalization
            )
            ctx.warnings += cc_notes
        claims = safety_net(text, claims, sentences, ex.kinds)
        claims = _with_footnotes(text, claims, notes)
        claims = _drop_noise(text, claims)
        for i, cl in enumerate(claims, start=1):
            cl.id = f"c{i}"
        if self.config.enable_overreach:
            # الاستنتاج المربوط بحديث يُفحص بالعلاقة (BR-19)، فلا يُكرَّر ادعاءً مستقلًا.
            concl = [
                c.linked_conclusion
                for c in claims
                if c.type is ClaimType.HADITH_QUOTE and c.linked_conclusion
            ]
            claims = [
                c
                for c in claims
                if c.type in (ClaimType.QURAN_QUOTE, ClaimType.HADITH_QUOTE)
                or not any(c.span.overlaps(s) for s in concl)
            ]

        outcomes: dict[str, Outcome] = {}
        pending: dict[str, HadithPending] = {}
        relation_needed: list[Claim] = []

        for cl in claims:
            out = self._route(cl)
            if isinstance(out, HadithPending):
                pending[cl.id] = out
            else:
                outcomes[cl.id] = out
            if (
                self.config.enable_overreach
                and cl.type is ClaimType.HADITH_QUOTE
                and cl.linked_conclusion
            ):
                relation_needed.append(cl)

        judged = self._judge(text, claims, pending, relation_needed, ctx)
        for cid, pend in pending.items():
            cl = next(c for c in claims if c.id == cid)
            j = judged.get(cid, {})
            if j.get("_failed"):
                outcomes[cid] = Outcome(
                    Signal.SYSTEM_UNAVAILABLE,
                    facts={"error": "تعذّر الحكم على المعنى"},
                    confidence=Confidence.LOW,
                )
            else:
                outcomes[cid] = self.hadith.resolve_with_judgment(
                    cl.text,
                    _as_wording(cl),
                    cl.hints.cited_book,
                    pend,
                    j.get("match"),
                    j.get("candidate"),
                )

        if self.library is not None:
            # ثلاث خطوات مستقلة بالتوازي: الأقوال بالمكتبة، وأحكام الأحاديث، وبوابة التعميم.
            with ThreadPoolExecutor(max_workers=3) as pool:
                f_say = pool.submit(
                    check_sayings, claims, outcomes, self.library, self.llm, self.prompts.sayings
                )
                f_rul = pool.submit(
                    check_rulings, claims, outcomes, self.library, self.llm, self.prompts.rulings
                )
                f_gate = pool.submit(
                    gate_generalizations, text, claims, outcomes, self.llm, self.prompts.gate
                )
                upd, usage, warns = f_say.result()
                upd2, usage2 = f_rul.result()
                gen, usage3 = f_gate.result()
            outcomes.update(upd)
            outcomes.update(upd2)
            for u in (usage, usage2, usage3):
                ctx.usage += u
                ctx.calls += len(u)
            ctx.warnings += warns
            claims = [c for c in claims if c.id not in gen]

        claims = _drop_echoes(claims, outcomes)
        findings = [self._finding(cl, outcomes[cl.id]) for cl in claims]
        findings += self._overreach_findings(text, relation_needed, outcomes, judged, len(claims))
        findings = self.guard.guard(findings)
        if self.guard.dropped:
            ctx.warnings.append(
                f"حارس الإسناد أسقط {len(self.guard.dropped)} شاهدًا غير موجود في المخزن"
            )
            self.guard.dropped.clear()
        findings = self._suggestions(findings, ctx)
        draft_map = build_map(sentences, findings, ex.kinds)
        return self._report(text, wc, findings, not_checked, ctx, t0, draft_map)

    def _suggestions(self, findings: list[Finding], ctx: _Ctx) -> list[Finding]:
        """اقتراح الصياغة المولَّد للتعميم والإجماع، بعد حارس الاقتراح (ADR-0014)."""
        out: list[Finding] = []
        rejected = 0
        for f in findings:
            raw = f.claim.hints.rephrase
            if raw and f.rule_id in ("BR-14", "BR-15"):
                sug = safe_suggestion(raw, f.claim.text, self.quran.index, self.hadith.index)
                if sug:
                    f = f.model_copy(update={"suggestion": sug})
                else:
                    rejected += 1
            out.append(f)
        if rejected:
            ctx.warnings.append(f"حارس الاقتراح أسقط {rejected} اقتراح صياغة مولَّدًا")
        return out

    # ─────────────────────────────── التوجيه ───────────────────────────────
    def _route(self, cl: Claim) -> Outcome | HadithPending:
        t = cl.type
        if t is ClaimType.GROUP_JUDGMENT:
            return Outcome(Signal.GROUP_JUDGMENT, confidence=Confidence.MEDIUM)
        # المستوى (ج/د) يحيل الأحكام والأقوال والوقائع، لا التعميم اللفظي ولا الرقم (E-009).
        if t not in (
            ClaimType.QURAN_QUOTE,
            ClaimType.HADITH_QUOTE,
            ClaimType.TAKHRIJ,
            ClaimType.GENERALIZATION,
            ClaimType.STATISTIC,
        ):
            if t is ClaimType.PERSONAL_CASE or cl.level is ContentLevel.D:
                return Outcome(Signal.FATWA_REQUIRED, confidence=Confidence.MEDIUM)
            if t is ClaimType.RULING or cl.level is ContentLevel.C:
                return Outcome(
                    Signal.SPECIALIST_REQUIRED,
                    evidence=[self._fiqh_link(cl.text)],
                    confidence=Confidence.MEDIUM,
                )
        if t is ClaimType.QURAN_QUOTE:
            if self.config.quran_mode == "llm" and self.quran_llm_judge is not None:
                return self.quran_llm_judge(cl)
            return self._quran(cl)
        if t in (ClaimType.HADITH_QUOTE, ClaimType.TAKHRIJ):
            return self.hadith.verify_deterministic(cl.text, _as_wording(cl), cl.hints.cited_book)
        if t is ClaimType.ATTRIBUTED_SAYING and cl.hints.presented_as_verbatim:
            # قول منقول بنصه قد يكون أثرًا في كتب السنة (قول أبي سلمة في البخاري): يُبحث حرفيًا
            # دون نموذج، فإن وُجد عُرض موضعه، وإلا سُئل عن مصدره كما كان.
            probe = self.hadith.verify_deterministic(cl.text, False, cl.hints.cited_book)
            if isinstance(probe, Outcome) and probe.signal in (
                Signal.HADITH_AUTHENTIC_MATCH,
                Signal.HADITH_LOCATE_ONLY,
            ):
                probe.notes.append("قول منقول بنصه، ووُجد في كتب السنة")
                return probe
        if t in (ClaimType.ATTRIBUTED_SAYING, ClaimType.STATISTIC, ClaimType.HISTORICAL_EVENT):
            if cl.hints.source_mentioned:
                return Outcome(
                    Signal.SOURCING_CITED_OUT_OF_COVERAGE,
                    facts={"source_mentioned": cl.hints.source_mentioned},
                )
            return Outcome(Signal.SOURCING_NO_SOURCE, confidence=Confidence.HIGH)
        if t is ClaimType.CONSENSUS_CLAIM:
            return Outcome(
                Signal.CONSENSUS, evidence=[self._fiqh_link(cl.text)], confidence=Confidence.HIGH
            )
        if t is ClaimType.GENERALIZATION:
            return Outcome(Signal.GENERALIZATION, confidence=Confidence.MEDIUM)
        return Outcome(Signal.SOURCING_NO_SOURCE, confidence=Confidence.LOW)

    def _fiqh_link(self, text: str) -> Evidence:
        """رابط بحث في الموسوعة الفقهية بالدرر (دور LINK): يبدأ منه الكاتب التوثيق."""
        return Evidence(
            ref=SourceRef(
                source_id="dorar_fiqh",
                item_id="search",
                citation="بحث في الموسوعة الفقهية (الدرر السنية)",
                url=self.hadith.linker.fiqh_search_url(text),
            ),
            role=SourceRole.LINK,
            text="",
            match_type=MatchType.NONE,
            match_reason="رابط بحث يفتحه الإنسان، لا استدعاء آلي",
        )

    def _quran(self, cl: Claim) -> Outcome:
        """الآية، مع أثر الفحص المتقاطع: آية قُدّمت حديثًا (BR-22)، وحديث قُدّم آية (BR-04 + شاهده)."""
        out = self.quran.verify(cl.text, cl.hints.cited_ref)
        if cl.hints.presented_as is ClaimType.HADITH_QUOTE:
            if out.signal in (Signal.QURAN_MATCH, Signal.QURAN_WRONG_REFERENCE):
                return Outcome(
                    Signal.QURAN_AS_HADITH, out.evidence, out.facts, Confidence.HIGH, out.notes
                )
            out.notes.append("والمسودة تنسبه إلى النبي ﷺ، وأكثره من القرآن")
            return out
        if out.signal is Signal.QURAN_NOT_IN_MUSHAF:
            probe = self.hadith.verify_deterministic(cl.text, True, None)
            if isinstance(probe, Outcome) and probe.signal is Signal.HADITH_KNOWN_WEAK:
                out.facts["found_elsewhere"] = (
                    " وهو مدرج في قائمة سديد لـ«المشتهر الذي لا يصح» حديثًا، فلا يُنسب إلى القرآن ولا إلى النبي ﷺ إلا ببيان حاله."
                )
                out.evidence = [*out.evidence, *probe.evidence[:1]]
            elif (
                isinstance(probe, Outcome)
                and probe.evidence
                and probe.signal
                in (
                    Signal.HADITH_AUTHENTIC_MATCH,
                    Signal.HADITH_LOCATE_ONLY,
                    Signal.HADITH_MISATTRIBUTED,
                )
            ):
                first = probe.evidence[0]
                out.facts["found_elsewhere"] = (
                    f" وقد وجدنا نصه حديثًا في {first.ref.citation}، فلعله حديث لا آية."
                )
                out.evidence = [*out.evidence, first]
        return out

    # ─────────────────────────────── الحَكَم ───────────────────────────────
    def _judge(
        self,
        text: str,
        claims: list[Claim],
        pending: dict[str, HadithPending],
        relation_needed: list[Claim],
        ctx: _Ctx,
    ) -> dict[str, dict[str, Any]]:
        ids = list(dict.fromkeys([*pending.keys(), *(c.id for c in relation_needed)]))
        if not ids:
            return {}
        if self.llm is None:
            return {i: {"_failed": True} for i in ids}
        by_id = {c.id: c for c in claims}
        blocks: list[str] = []
        for cid in ids:
            cl = by_id[cid]
            lines = [f"- id: {cid}", f"  quote: {cl.text}"]
            if cl.linked_conclusion and any(r.id == cid for r in relation_needed):
                lines.append(
                    f"  conclusion: {text[cl.linked_conclusion.start : cl.linked_conclusion.end]}"
                )
            cands = pending[cid].candidates if cid in pending else []
            for c in cands:
                lines.append(f"  candidate {c.key}: {_snippet(c.text_plain, cl.text)}")
            if cid not in pending:
                # حديث محسوم حتميًا ويحتاج فحص العلاقة فقط: لفظه في المسودة هو لفظه في المخزن.
                lines.append("  candidate (resolved): لفظ المسودة نفسه موجود في المخزن")
            blocks.append("\n".join(lines))
        system, user = self.prompts.judge.render(ITEMS="\n\n".join(blocks))
        try:
            resp = self.llm.generate_json(system=system, user=user, max_tokens=3000)
        except LLMError as e:
            ctx.degraded = True
            ctx.warnings.append(f"تعذّر نداء الحَكَم: {llm_error_ar(e)}")
            return {i: {"_failed": True} for i in ids}
        ctx.usage.append(resp.usage)
        ctx.calls += 1
        items = resp.data.get("items", [])
        out: dict[str, dict[str, Any]] = {}
        for it in items if isinstance(items, list) else []:
            if isinstance(it, dict) and it.get("id") in ids:
                out[it["id"]] = it
        for i in ids:
            out.setdefault(i, {"match": "NONE", "candidate": None})
        return out

    # ─────────────────────────────── التجاوز (S) ───────────────────────────────
    def _overreach_findings(
        self,
        text: str,
        claims: list[Claim],
        outcomes: dict[str, Outcome],
        judged: dict[str, dict[str, Any]],
        offset: int,
    ) -> list[Finding]:
        out: list[Finding] = []
        for cl in claims:
            base = outcomes.get(cl.id)
            if base is None or base.signal not in (
                Signal.HADITH_AUTHENTIC_MATCH,
                Signal.HADITH_PARAPHRASE_DECLARED,
                Signal.HADITH_LOCATE_ONLY,
                Signal.HADITH_PARAPHRASE_AS_WORDING,
                Signal.HADITH_MISATTRIBUTED,
            ):
                continue
            j = judged.get(cl.id, {})
            try:
                rel = Relation(str(j.get("relation")))
            except ValueError:
                continue
            if rel is Relation.SUPPORTS or cl.linked_conclusion is None:
                continue
            concl_text = text[cl.linked_conclusion.start : cl.linked_conclusion.end]
            excess = j.get("excess") or ""
            # الجزء الزائد يجب أن يكون منسوخًا من المسودة؛ وإلا نعرض الاستنتاج كله.
            if not excess or find_span(concl_text, excess) is None:
                excess = concl_text
            try:
                otype = OverreachType(str(j.get("overreach_type")))
            except ValueError:
                otype = None
            concl_claim = Claim(
                id=f"c{offset + len(out) + 1}",
                text=concl_text,
                span=cl.linked_conclusion,
                type=ClaimType.HADITH_CONCLUSION,
                level=ContentLevel.B,
                origin="llm",
            )
            facts = {"overreach_type": otype.label_ar if otype else "تجاوز", "excess": excess}
            outcome = Outcome(
                Signal.CONCLUSION_EXCEEDS,
                evidence=base.evidence[:1],
                facts=facts,
                confidence=Confidence.LOW,
                relation=RelationResult(relation=rel, overreach_type=otype, excess_text=excess),
                notes=[f"مبني على الحديث في الملاحظة {cl.id}"],
            )
            out.append(self._finding(concl_claim, outcome))
        return out

    # ─────────────────────────────── الملاحظة والتقرير ───────────────────────────────
    def _finding(self, cl: Claim, out: Outcome) -> Finding:
        rule = apply(out.signal)
        facts = {
            "claim_type": cl.type.label_ar,
            "cited_ref": cl.hints.cited_ref,
            "cited_book": cl.hints.cited_book,
        }
        facts.update(out.facts)
        notes = list(out.notes)
        if cl.type is ClaimType.HADITH_QUOTE and not cl.hints.attributed_to_prophet:
            notes.append(
                "لم تنسبه المسودة إلى النبي ﷺ ولا قدّمته رواية؛ فإن كان نقلًا عن عالم فاذكر قائله"
            )
        return Finding(
            id=cl.id,
            claim=cl,
            evidence_status=rule.status,
            severity=rule.severity,
            action=rule.action,
            reason=rule.reason,
            rule_id=rule.rule_id,
            evidence=out.evidence,
            relation=out.relation,
            explanation=explanation_for(rule.rule_id, facts),
            next_step=next_step_for(rule.rule_id, facts),
            confidence=out.confidence,
            notes=notes,
            hadith_ruling=_ruling(out),
        )

    def _report(
        self,
        text: str,
        wc: int,
        findings: list[Finding],
        not_checked: list[str],
        ctx: _Ctx,
        t0: float,
        draft_map: list[MapEntry] | None = None,
    ) -> ReviewReport:
        by_bucket = {b.value: 0 for b in TrackBucket}
        by_sev = {s.value: 0 for s in Severity if s is not Severity.NONE}
        for f in findings:
            by_bucket[f.bucket.value] += 1
            if f.severity is not Severity.NONE:
                by_sev[f.severity.value] += 1
            if f.bucket is TrackBucket.NOT_CHECKED:
                not_checked.append(f"{f.id}: {f.claim.text[:50]}")
        risky = [
            f for f in findings if f.bucket in (TrackBucket.NEEDS_VERIFICATION, TrackBucket.REFER)
        ]
        risky.sort(key=lambda f: (f.severity.rank, f.claim.span.start))
        return ReviewReport(
            draft=DraftInfo(char_count=len(text), word_count=wc),
            summary=Summary(
                total_claims=len(findings),
                by_bucket=by_bucket,
                by_severity=by_sev,
                not_checked=not_checked,
            ),
            top_risks=[f.id for f in risky],
            findings=findings,
            draft_map=draft_map or [],
            coverage=self.coverage,
            meta=Meta(
                saadeed_version=__version__,
                llm=self.llm.model_id if self.llm else "none",
                prompt_versions=self.prompts.versions(),
                policy_version=POLICY_VERSION,
                manifest=self.manifest,
                duration_ms=int((time.monotonic() - t0) * 1000),
                llm_calls=ctx.calls,
                prompt_tokens=sum(u.prompt_tokens for u in ctx.usage),
                completion_tokens=sum(u.completion_tokens for u in ctx.usage),
                warnings=ctx.warnings,
                degraded=ctx.degraded,
            ),
        )


_EVIDENCE_KIND = {
    ClaimType.QURAN_QUOTE: SegmentKind.QURAN,
    ClaimType.HADITH_QUOTE: SegmentKind.HADITH,
}


def _with_footnotes(text: str, claims: list[Claim], notes: Footnotes) -> list[Claim]:
    """يُسقط ما وقع في قسم الحواشي، ويُلحق بكل ادعاء حاشيته: تخريجًا للحديث، ومصدرًا للقول."""
    out: list[Claim] = []
    for cl in claims:
        if notes.in_zone(cl.span.start):
            continue
        hints = cl.hints.model_copy(update={"cited_book": strip_ref(cl.hints.cited_book)})
        note = notes.ref_after(text, cl.span.end)
        if note:
            if cl.type in (ClaimType.HADITH_QUOTE, ClaimType.TAKHRIJ):
                hints.cited_book = hints.cited_book or note
            elif cl.type is not ClaimType.QURAN_QUOTE and parse_ref(note) is None:
                # حاشية هي إحالة آية («[الأعراف: 31]») ليست مصدرًا لقول الكاتب.
                hints.source_mentioned = hints.source_mentioned or note
        update: dict[str, object] = {"hints": hints}
        books = canonical_books(hints.source_mentioned)
        if (
            cl.type in (ClaimType.ATTRIBUTED_SAYING, ClaimType.HISTORICAL_EVENT)
            and books
            and "other" not in books
        ):
            # المصدر المذكور من الكتب الستة («أخرجه البخاري (4563)»): يُفحص فيها، لا «خارج التغطية» (E-027).
            hints.cited_book = hints.source_mentioned
            hints.attributed_to_prophet = False
            update["type"] = ClaimType.HADITH_QUOTE
            update["level"] = ContentLevel.A
        out.append(cl.model_copy(update=update))
    return out


_SAHIH = {"bukhari": "صحيح البخاري", "muslim": "صحيح مسلم"}


def _ruling(out: Outcome) -> str | None:
    """الحكم المنقول: من الصحيحين بدورهما (احتجاج)، أو من موضع حكم في المكتبة."""
    if out.facts.get("ruling"):
        return str(out.facts["ruling"])
    if out.signal in (Signal.HADITH_AUTHENTIC_MATCH, Signal.HADITH_PARAPHRASE_DECLARED):
        books = [_SAHIH[e.ref.source_id] for e in out.evidence if e.ref.source_id in _SAHIH]
        if books:
            return f"صحيح: في {books[0]}، وأحاديثه متلقاة بالقبول عند أهل العلم"
    return None


def _bracketed(text: str, cl: Claim) -> bool:
    """هل الاقتباس بين قوسي المصحف ﴿﴾ في المسودة نفسها؟"""
    before = text[max(0, cl.span.start - 3) : cl.span.start]
    after = text[cl.span.end : cl.span.end + 3]
    return "﴿" in before or "﴾" in after


def _in_citation(text: str, cl: Claim) -> bool:
    """هل الموضع داخل إحالة بين قوسين مربعين [المصدر، الطبعة، الصفحة]؟"""
    left = text[max(0, cl.span.start - 120) : cl.span.start]
    right = text[cl.span.end : cl.span.end + 200]
    return left.rfind("[") > left.rfind("]") and "]" in right


def _drop_noise(text: str, claims: list[Claim]) -> list[Claim]:
    """ما ليس ادعاءً يُفحص (v2.6، خطبة «السنة النبوية»):
    - كلمة أو كلمتان من آية سبق نقلها كاملة («تأملوا: ﴿فَخُذُوهُ﴾»): إحالة إلى الآية لا اقتباس جديد.
    - عبارة قرآنية قصيرة بلا أقواس داخل قول منسوب إلى عالم: من كلامه، لا اقتباس من الكاتب.
    - «حديث» قصير داخل إحالة بين قوسين مربعين (اسم كتاب: «[ابن أبي يعلى، «طبقات الحنابلة»…]»).
    """
    quran_norm = [normalize(c.text) for c in claims if c.type is ClaimType.QURAN_QUOTE]
    sayings = [c.span for c in claims if c.type is ClaimType.ATTRIBUTED_SAYING]
    out: list[Claim] = []
    for cl in claims:
        n = len(normalize(cl.text).split())
        if cl.type is ClaimType.QURAN_QUOTE:
            if n <= 2:
                me = normalize(cl.text)
                if any(me in q and q != me for q in quran_norm) or n == 1:
                    continue
            if (
                n <= 6
                and not _bracketed(text, cl)
                and not cl.hints.cited_ref
                and any(cl.span.overlaps(s) for s in sayings)
            ):
                continue
        if cl.type is ClaimType.HADITH_QUOTE and n <= 3 and _in_citation(text, cl):
            continue
        out.append(cl)
    return out


def _drop_echoes(claims: list[Claim], outcomes: dict[str, Outcome]) -> list[Claim]:
    """الآية التي جاءت جزءًا من آية نُقلت قبلها في المسودة نفسها، وطابقت الموضع نفسه بلا إحالة:
    صدى للأولى («﴿وَمَا آتَاكُمُ الرَّسُولُ فَخُذُوهُ﴾» بعد نقل الآية كاملة)، فلا تُعرض ملاحظةً ثانية."""
    seen: list[tuple[set[str], str]] = []
    out: list[Claim] = []
    for cl in claims:
        o = outcomes.get(cl.id)
        if cl.type is ClaimType.QURAN_QUOTE and o is not None and o.signal is Signal.QURAN_MATCH:
            ids = {e.ref.item_id for e in o.evidence}
            me = normalize(cl.text)
            if not cl.hints.cited_ref and any(ids & s and me in t for s, t in seen):
                continue
            seen.append((ids, me))
        out.append(cl)
    return out


def _as_wording(cl: Claim) -> bool:
    """يُعدّ «مقدَّمًا بلفظه» ما نُسب إلى النبي ﷺ بتنصيص. والاقتباس بلا نسبة ليس لفظ حديث (E-020)."""
    return cl.hints.presented_as_verbatim and cl.hints.attributed_to_prophet


def build_map(
    sentences: list[Sentence], findings: list[Finding], kinds: dict[int, SegmentKind]
) -> list[MapEntry]:
    """خريطة المسودة: صنف كل جملة. ما ثبت بالفحص (آية أو حديث) يتقدم على تصنيف النموذج."""
    out: list[MapEntry] = []
    for s in sentences:
        inside = [f for f in findings if f.claim.span.overlaps(s.span)]
        kind, source = kinds.get(s.index), "llm"
        for f in inside:
            ek = _EVIDENCE_KIND.get(f.claim.type)
            if ek is not None and f.claim.span.overlaps(s.span):
                kind, source = ek, "evidence"
                break
        if kind is None:
            kind, source = SegmentKind.UNLABELED, "none"
        out.append(
            MapEntry(
                index=s.index,
                span=s.span,
                kind=kind,
                finding_ids=[f.id for f in inside],
                kind_source=source,
            )
        )
    return out


def _snippet(passage: str, quote: str, width: int = SNIPPET_WORDS) -> str:
    """نافذة من نص الحديث حول أكثر المواضع شبهًا بالاقتباس (لتوفير الرموز)."""
    words = passage.split()
    if len(words) <= width:
        return passage
    q = set(normalize(quote).split())
    norms = [normalize(w) for w in words]
    best, best_i = -1, 0
    for i in range(0, len(words) - width + 1, 5):
        score = sum(1 for w in norms[i : i + width] if w in q)
        if score > best:
            best, best_i = score, i
    return ("… " if best_i else "") + " ".join(words[best_i : best_i + width]) + " …"


def span_text(text: str, span: Span) -> str:
    return text[span.start : span.end]
