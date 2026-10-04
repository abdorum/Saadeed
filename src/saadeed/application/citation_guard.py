"""حارس الإسناد (FR-52، م١): آخر بوابة قبل الإخراج.

لكل شاهد: يُعاد جلب نصه من المخزن بمعرّفه، ويُستبدل به النص المعروض.
والمعرّف غير الموجود يُسقط ويُسجَّل. وإن سقط كل شاهد لملاحظة تعتمد على شاهد، صارت «لم يُفحص».
فلا يصل إلى المستخدم نص شرعي لم يخرج من المخزن، مهما حدث قبله.
"""

from __future__ import annotations

from saadeed.domain.enums import EvidenceStatus, SourceRole
from saadeed.domain.models import Evidence, Finding
from saadeed.domain.policy import Signal, apply
from saadeed.domain.ports import KnownWeakRepo, QuranRepo, TextSourcePort
from saadeed.domain.templates import explanation_for, next_step_for
from saadeed.verifiers.quran import ayat_from_item_id, render_ayat

_NEEDS_EVIDENCE = {
    EvidenceStatus.SUPPORTED,
    EvidenceStatus.PARTIALLY_SUPPORTED,
    EvidenceStatus.FOUND_NO_RULING,
    EvidenceStatus.EXCEEDS_SOURCE,
}


class CitationGuard:
    def __init__(
        self, quran: QuranRepo, texts: dict[str, TextSourcePort], known_weak: KnownWeakRepo | None
    ) -> None:
        self.quran = quran
        self.texts = texts
        self.known_weak = known_weak
        self.dropped: list[str] = []

    def _refetch(self, ev: Evidence) -> str | None:
        sid, iid = ev.ref.source_id, ev.ref.item_id
        if ev.role is SourceRole.LINK:
            return ""
        if sid == "quran":
            try:
                ayat = ayat_from_item_id(iid)
            except (ValueError, IndexError):
                return None
            if not ayat or any(self.quran.get(s, a) is None for s, a in ayat):
                return None
            return render_ayat(self.quran, ayat)
        if sid == "known_weak":
            kw = self.known_weak.get(iid) if self.known_weak else None
            return kw.text if kw else None
        src = self.texts.get(sid)
        p = src.get(iid) if src else None
        return p.text_display if p else None

    def guard(self, findings: list[Finding]) -> list[Finding]:
        out: list[Finding] = []
        for f in findings:
            kept: list[Evidence] = []
            for ev in f.evidence:
                text = self._refetch(ev)
                if text is None:
                    self.dropped.append(f"{f.id}: {ev.ref.source_id}:{ev.ref.item_id}")
                    continue
                kept.append(
                    ev.model_copy(update={"text": text}) if ev.role is not SourceRole.LINK else ev
                )
            substantive = [e for e in kept if e.role is not SourceRole.LINK]
            if f.evidence and not substantive and f.evidence_status in _NEEDS_EVIDENCE:
                rule = apply(Signal.SYSTEM_UNAVAILABLE)
                facts = {"error": "أُسقط الشاهد لأنه غير موجود في المخزن"}
                f = f.model_copy(
                    update={
                        "evidence_status": rule.status,
                        "severity": rule.severity,
                        "action": rule.action,
                        "reason": rule.reason,
                        "rule_id": rule.rule_id,
                        "evidence": kept,
                        "explanation": explanation_for(rule.rule_id, facts),
                        "next_step": next_step_for(rule.rule_id, facts),
                    }
                )
            else:
                f = f.model_copy(update={"evidence": kept})
            out.append(f)
        return out
