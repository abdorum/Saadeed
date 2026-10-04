"""حالة الاستخدام: من المسودة إلى تقرير المراجعة (المعمارية §٥).

المسار:
  تقطيع ← استخراج (نداء ١) + مرور حتمي ← توجيه كل ادعاء ← متحققات حتمية
  ← حَكَم الأحاديث غير المحسومة (نداء ٢، عند الحاجة) ← ميزان السداد ← القوالب ← حارس الإسناد ← تقرير.

ما يقرره النموذج: أين الادعاءات ونوعها (١)، وهل حديث المسودة يطابق مرشحًا من المخزن لفظًا أو معنًى (٢).
ما لا يقرره أبدًا: نص المصدر، والحالة، والأثر، والإجراء، ونص الشرح.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from saadeed import __version__
from saadeed.application.citation_guard import CitationGuard
from saadeed.application.extraction import extract_claims
from saadeed.application.prompts import PromptSet
from saadeed.domain.enums import (
    ClaimType,
    Confidence,
    ContentLevel,
    OverreachType,
    Relation,
    Severity,
    TrackBucket,
)
from saadeed.domain.models import (
    Claim,
    Coverage,
    DraftInfo,
    Finding,
    ManifestStamp,
    Meta,
    RelationResult,
    ReviewReport,
    Span,
    Summary,
)
from saadeed.domain.policy import POLICY_VERSION, Signal, apply
from saadeed.domain.ports import LLMError, LLMPort, LLMUsage
from saadeed.domain.templates import explanation_for, next_step_for
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
        sentences = split_sentences(text)
        ex = extract_claims(text, sentences, self.llm, self.prompts.extract)
        ctx.usage += ex.usage
        ctx.calls += len(ex.usage)
        ctx.warnings += ex.warnings
        not_checked: list[str] = []
        if ex.llm_failed:
            not_checked.append(
                "الادعاءات غير المعلَّمة (أقوال، وأرقام، وإجماع، وتعميم، وإحالات): لم تُستخرج لأن النموذج غير متاح، وفُحصت الآيات والأحاديث المعلَّمة وحدها"
            )

        claims = ex.claims
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
                    cl.hints.presented_as_verbatim,
                    cl.hints.cited_book,
                    pend,
                    j.get("match"),
                    j.get("candidate"),
                )

        findings = [self._finding(cl, outcomes[cl.id]) for cl in claims]
        findings += self._overreach_findings(
            text, relation_needed, outcomes, judged, len(ex.claims)
        )
        findings = self.guard.guard(findings)
        if self.guard.dropped:
            ctx.warnings.append(
                f"حارس الإسناد أسقط {len(self.guard.dropped)} شاهدًا غير موجود في المخزن"
            )
            self.guard.dropped.clear()
        return self._report(text, wc, findings, not_checked, ctx, t0)

    # ─────────────────────────────── التوجيه ───────────────────────────────
    def _route(self, cl: Claim) -> Outcome | HadithPending:
        t = cl.type
        if t is ClaimType.GROUP_JUDGMENT:
            return Outcome(Signal.GROUP_JUDGMENT, confidence=Confidence.MEDIUM)
        if t not in (ClaimType.QURAN_QUOTE, ClaimType.HADITH_QUOTE, ClaimType.TAKHRIJ):
            if t is ClaimType.PERSONAL_CASE or cl.level is ContentLevel.D:
                return Outcome(Signal.FATWA_REQUIRED, confidence=Confidence.MEDIUM)
            if t is ClaimType.RULING or cl.level is ContentLevel.C:
                return Outcome(Signal.SPECIALIST_REQUIRED, confidence=Confidence.MEDIUM)
        if t is ClaimType.QURAN_QUOTE:
            if self.config.quran_mode == "llm" and self.quran_llm_judge is not None:
                return self.quran_llm_judge(cl)
            return self.quran.verify(cl.text, cl.hints.cited_ref)
        if t in (ClaimType.HADITH_QUOTE, ClaimType.TAKHRIJ):
            return self.hadith.verify_deterministic(
                cl.text, cl.hints.presented_as_verbatim, cl.hints.cited_book
            )
        if t in (ClaimType.ATTRIBUTED_SAYING, ClaimType.STATISTIC, ClaimType.HISTORICAL_EVENT):
            if cl.hints.source_mentioned:
                return Outcome(
                    Signal.SOURCING_CITED_OUT_OF_COVERAGE,
                    facts={"source_mentioned": cl.hints.source_mentioned},
                )
            return Outcome(Signal.SOURCING_NO_SOURCE, confidence=Confidence.HIGH)
        if t is ClaimType.CONSENSUS_CLAIM:
            return Outcome(Signal.CONSENSUS, confidence=Confidence.HIGH)
        if t is ClaimType.GENERALIZATION:
            return Outcome(Signal.GENERALIZATION, confidence=Confidence.MEDIUM)
        return Outcome(Signal.SOURCING_NO_SOURCE, confidence=Confidence.LOW)

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
            ctx.warnings.append(f"تعذّر نداء الحَكَم: {e}")
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
            notes=out.notes,
        )

    def _report(
        self,
        text: str,
        wc: int,
        findings: list[Finding],
        not_checked: list[str],
        ctx: _Ctx,
        t0: float,
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
            ),
        )


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
