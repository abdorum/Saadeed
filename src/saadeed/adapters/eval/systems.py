"""الأنظمة المقارنة (البروتوكول §٤): سديد، وB0 (النموذج العام)، وB1 (سديد دون المطابق الحتمي)."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from saadeed.adapters.factory import Engine
from saadeed.application.prompts import load_prompt
from saadeed.application.review_draft import ReviewConfig
from saadeed.domain.enums import Confidence
from saadeed.domain.models import Claim
from saadeed.domain.policy import Signal
from saadeed.domain.ports import LLMError, LLMPort
from saadeed.text.markers import parse_ref
from saadeed.text.normalize import find_span
from saadeed.verifiers.base import Outcome


class Pred(BaseModel):
    span: tuple[int, int]
    claim_type: str
    evidence_status: str
    reason: str | None
    action: str
    source: str | None = None
    """المصدر الذي ذكره النظام (B0)."""
    correct_text: str | None = None
    quote: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    issue: str | None = None


class SystemRun(BaseModel):
    system: str
    carrier_id: str
    run: int
    preds: list[Pred] = Field(default_factory=list)
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


def run_saadeed(
    engine: Engine, llm: LLMPort, text: str, overreach: bool, quran_mode: str = "deterministic"
) -> SystemRun:
    judge = _b1_quran_judge(engine, llm) if quran_mode == "llm" else None
    rev = engine.reviewer(
        llm, ReviewConfig(enable_overreach=overreach, quran_mode=quran_mode), quran_llm_judge=judge
    )
    t0 = time.monotonic()
    rep = rev.review(text)
    preds = [
        Pred(
            span=(f.claim.span.start, f.claim.span.end),
            claim_type=f.claim.type.value,
            evidence_status=f.evidence_status.value,
            reason=f.reason.value if f.reason else None,
            action=f.action.value,
            quote=f.claim.text,
            evidence=[
                {
                    "source_id": e.ref.source_id,
                    "item_id": e.ref.item_id,
                    "role": e.role.value,
                    "text": e.text,
                    "match_type": e.match_type.value,
                }
                for e in f.evidence
            ],
        )
        for f in rep.findings
    ]
    return SystemRun(
        system="",
        carrier_id="",
        run=0,
        preds=preds,
        latency_ms=int((time.monotonic() - t0) * 1000),
        prompt_tokens=rep.meta.prompt_tokens,
        completion_tokens=rep.meta.completion_tokens,
        llm_calls=rep.meta.llm_calls,
        warnings=rep.meta.warnings,
    )


_B0_ACTION = {"SUPPORTED": "NONE", "NEEDS_VERIFICATION": "VERIFY", "REFER": "REFER"}


def run_baseline(engine: Engine, llm: LLMPort, text: str) -> SystemRun:
    """B0: النموذج نفسه بتعليمات جيدة، والمخطط نفسه تقريبًا، ولا مخزن ولا قواعد."""
    p = engine.prompts.baseline
    system, user = p.render(DRAFT=text)
    t0 = time.monotonic()
    try:
        resp = llm.generate_json(system=system, user=user, max_tokens=6000)
    except LLMError as e:
        return SystemRun(system="B0", carrier_id="", run=0, error=str(e))
    preds: list[Pred] = []
    for f in resp.data.get("findings", resp.data.get("items", [])) or []:
        if not isinstance(f, dict) or not f.get("quote"):
            continue
        span = find_span(text, str(f["quote"]))
        if span is None:
            continue
        verdict = str(f.get("verdict", "NEEDS_VERIFICATION")).upper()
        preds.append(
            Pred(
                span=span,
                claim_type=str(f.get("type") or ""),
                evidence_status=verdict,
                reason=None,
                action=_B0_ACTION.get(verdict, "VERIFY"),
                source=(str(f["source"]) if f.get("source") else None),
                correct_text=(str(f["correct_text"]) if f.get("correct_text") else None),
                quote=text[span[0] : span[1]],
                issue=(str(f["issue"]) if f.get("issue") else None),
            )
        )
    return SystemRun(
        system="B0",
        carrier_id="",
        run=0,
        preds=preds,
        latency_ms=int((time.monotonic() - t0) * 1000),
        prompt_tokens=resp.usage.prompt_tokens,
        completion_tokens=resp.usage.completion_tokens,
        llm_calls=1,
    )


def _b1_quran_judge(engine: Engine, llm: LLMPort):
    """B1: النموذج يحكم على الآية بدل المطابق الحتمي (لقياس أثر الحتمية، ADR-0004)."""
    prompt = load_prompt(engine_prompts_dir(engine) / "b1_quran_judge_v1.md")

    def judge(cl: Claim) -> Outcome:
        system, user = prompt.render(QUOTE=cl.text, REF=cl.hints.cited_ref or "—")
        try:
            data = llm.generate_json(system=system, user=user, max_tokens=800).data
        except LLMError:
            return Outcome(
                Signal.SYSTEM_UNAVAILABLE, facts={"error": "B1"}, confidence=Confidence.LOW
            )
        if not data.get("is_quran"):
            return Outcome(Signal.QURAN_NOT_IN_MUSHAF)
        if not data.get("exact"):
            return Outcome(Signal.QURAN_TEXT_MISMATCH)
        parsed = parse_ref(cl.hints.cited_ref) if cl.hints.cited_ref else None
        if (
            parsed
            and data.get("sura")
            and (
                parsed[0] != data.get("sura")
                or not parsed[1] <= int(data.get("aya") or 0) <= parsed[2]
            )
        ):
            return Outcome(Signal.QURAN_WRONG_REFERENCE)
        return Outcome(Signal.QURAN_MATCH)

    return judge


def engine_prompts_dir(engine: Engine):
    from saadeed.adapters.bootstrap import PROMPTS_DIR

    return PROMPTS_DIR
