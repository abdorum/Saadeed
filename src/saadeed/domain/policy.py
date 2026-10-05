"""ميزان السداد: جدول القواعد BR-01..20 (المتطلبات §٥.١)، منقولًا حرفيًا.

**النموذج اللغوي لا يحدد هنا شيئًا.** المتحققات تقرر «الإشارة» (Signal) بحقائق حتمية
أو بمدخلات من النموذج (نوع المطابقة، العلاقة)، والجدول وحده يحوّلها إلى الأبعاد الثلاثة.
تعديل أي صف هنا = تعديل في المتطلبات، ويراجعه المرشد الشرعي.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from saadeed.domain.enums import Action, EvidenceStatus, Reason, Severity

POLICY_VERSION = "BR-2026.10.05-v2.5"


class Signal(StrEnum):
    """ما وجده المتحقق، بلغة شروط الجدول. لكل إشارة قاعدة واحدة."""

    QURAN_MATCH = "QURAN_MATCH"  # BR-01
    QURAN_TEXT_MISMATCH = "QURAN_TEXT_MISMATCH"  # BR-02
    QURAN_WRONG_REFERENCE = "QURAN_WRONG_REFERENCE"  # BR-03
    QURAN_NOT_IN_MUSHAF = "QURAN_NOT_IN_MUSHAF"  # BR-04
    HADITH_KNOWN_WEAK = "HADITH_KNOWN_WEAK"  # BR-05
    HADITH_AUTHENTIC_MATCH = "HADITH_AUTHENTIC_MATCH"  # BR-06
    HADITH_PARAPHRASE_AS_WORDING = "HADITH_PARAPHRASE_AS_WORDING"  # BR-07
    HADITH_PARAPHRASE_DECLARED = "HADITH_PARAPHRASE_DECLARED"  # BR-08
    HADITH_MISATTRIBUTED = "HADITH_MISATTRIBUTED"  # BR-09
    HADITH_LOCATE_ONLY = "HADITH_LOCATE_ONLY"  # BR-10
    HADITH_NOT_FOUND = "HADITH_NOT_FOUND"  # BR-11
    SOURCING_NO_SOURCE = "SOURCING_NO_SOURCE"  # BR-12
    SOURCING_CITED_OUT_OF_COVERAGE = "SOURCING_CITED_OUT_OF_COVERAGE"  # BR-13
    CONSENSUS = "CONSENSUS"  # BR-14
    GENERALIZATION = "GENERALIZATION"  # BR-15
    GROUP_JUDGMENT = "GROUP_JUDGMENT"  # BR-16
    SPECIALIST_REQUIRED = "SPECIALIST_REQUIRED"  # BR-17
    FATWA_REQUIRED = "FATWA_REQUIRED"  # BR-18
    CONCLUSION_EXCEEDS = "CONCLUSION_EXCEEDS"  # BR-19
    SYSTEM_UNAVAILABLE = "SYSTEM_UNAVAILABLE"  # BR-20
    QURAN_MERGED = "QURAN_MERGED"  # BR-21
    QURAN_AS_HADITH = "QURAN_AS_HADITH"  # BR-22
    HADITH_NOT_FOUND_WITH_SIGNS = "HADITH_NOT_FOUND_WITH_SIGNS"  # BR-23


@dataclass(frozen=True)
class Rule:
    rule_id: str
    status: EvidenceStatus
    reason: Reason | None
    severity: Severity
    action: Action


_S = EvidenceStatus
_R = Reason
_V = Severity
_A = Action

# الجدول نفسه. كل سطر = صف في المتطلبات §٥.١.
RULES: dict[Signal, Rule] = {
    Signal.QURAN_MATCH: Rule("BR-01", _S.SUPPORTED, None, _V.NONE, _A.NONE),
    Signal.QURAN_TEXT_MISMATCH: Rule(
        "BR-02", _S.CONTRADICTED, _R.TEXT_MISMATCH, _V.CRITICAL, _A.CORRECT_FROM_SOURCE
    ),
    Signal.QURAN_WRONG_REFERENCE: Rule(
        "BR-03", _S.PARTIALLY_SUPPORTED, _R.WRONG_REFERENCE, _V.HIGH, _A.CORRECT_FROM_SOURCE
    ),
    Signal.QURAN_NOT_IN_MUSHAF: Rule(
        "BR-04", _S.CONTRADICTED, _R.NOT_QURAN, _V.CRITICAL, _A.RECONSIDER
    ),
    Signal.HADITH_KNOWN_WEAK: Rule(
        "BR-05", _S.CONTRADICTED, _R.KNOWN_WEAK, _V.CRITICAL, _A.RECONSIDER
    ),
    Signal.HADITH_AUTHENTIC_MATCH: Rule("BR-06", _S.SUPPORTED, None, _V.NONE, _A.NONE),
    Signal.HADITH_PARAPHRASE_AS_WORDING: Rule(
        "BR-07", _S.PARTIALLY_SUPPORTED, _R.PARAPHRASED_AS_WORDING, _V.HIGH, _A.CORRECT_FROM_SOURCE
    ),
    Signal.HADITH_PARAPHRASE_DECLARED: Rule("BR-08", _S.SUPPORTED, None, _V.NONE, _A.NONE),
    Signal.HADITH_MISATTRIBUTED: Rule(
        "BR-09", _S.PARTIALLY_SUPPORTED, _R.MISATTRIBUTED, _V.HIGH, _A.CORRECT_FROM_SOURCE
    ),
    Signal.HADITH_LOCATE_ONLY: Rule(
        "BR-10", _S.FOUND_NO_RULING, _R.FOUND_OUTSIDE_RULING_SCOPE, _V.HIGH, _A.VERIFY
    ),
    Signal.HADITH_NOT_FOUND: Rule("BR-11", _S.NOT_FOUND, _R.NOT_FOUND, _V.HIGH, _A.VERIFY),
    Signal.SOURCING_NO_SOURCE: Rule("BR-12", _S.OUT_OF_SCOPE, _R.NO_SOURCE, _V.MEDIUM, _A.VERIFY),
    Signal.SOURCING_CITED_OUT_OF_COVERAGE: Rule(
        "BR-13", _S.OUT_OF_SCOPE, _R.CITED_OUT_OF_COVERAGE, _V.LOW, _A.VERIFY
    ),
    Signal.CONSENSUS: Rule("BR-14", _S.OUT_OF_SCOPE, _R.UNVERIFIED_CONSENSUS, _V.HIGH, _A.REPHRASE),
    Signal.GENERALIZATION: Rule(
        "BR-15", _S.OUT_OF_SCOPE, _R.OVERGENERALIZATION, _V.LOW, _A.REPHRASE
    ),
    Signal.GROUP_JUDGMENT: Rule("BR-16", _S.OUT_OF_SCOPE, _R.GROUP_JUDGMENT, _V.HIGH, _A.REFER),
    Signal.SPECIALIST_REQUIRED: Rule(
        "BR-17", _S.OUT_OF_SCOPE, _R.SPECIALIST_REQUIRED, _V.MEDIUM, _A.REFER
    ),
    Signal.FATWA_REQUIRED: Rule("BR-18", _S.OUT_OF_SCOPE, _R.FATWA_REQUIRED, _V.HIGH, _A.REFER),
    Signal.CONCLUSION_EXCEEDS: Rule(
        "BR-19", _S.EXCEEDS_SOURCE, _R.EXCEEDS_TEXT, _V.MEDIUM, _A.REPHRASE
    ),
    Signal.SYSTEM_UNAVAILABLE: Rule(
        "BR-20", _S.NOT_CHECKED, _R.SYSTEM_UNAVAILABLE, _V.NONE, _A.NONE
    ),
    # v2.5 (ADR-0014): الفحص المتقاطع وقرائن المتن.
    Signal.QURAN_MERGED: Rule(
        "BR-21", _S.PARTIALLY_SUPPORTED, _R.MERGED_AYAT, _V.HIGH, _A.CORRECT_FROM_SOURCE
    ),
    Signal.QURAN_AS_HADITH: Rule(
        "BR-22", _S.PARTIALLY_SUPPORTED, _R.QURAN_AS_HADITH, _V.HIGH, _A.CORRECT_FROM_SOURCE
    ),
    Signal.HADITH_NOT_FOUND_WITH_SIGNS: Rule(
        "BR-23", _S.NOT_FOUND, _R.NOT_FOUND, _V.CRITICAL, _A.VERIFY
    ),
}

# التركيبة غير المغطاة (المتطلبات §٥.٢ بند 4): خارج نطاق الفحص + متوسط + تحقّق.
FALLBACK_RULE = Rule("BR-00", _S.OUT_OF_SCOPE, _R.NO_SOURCE, _V.MEDIUM, _A.VERIFY)


def apply(signal: Signal) -> Rule:
    """يطبّق الجدول. حتمي: الإشارة نفسها تعطي القاعدة نفسها دائمًا."""
    return RULES.get(signal, FALLBACK_RULE)
