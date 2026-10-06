"""جدول ميزان السداد يُنفَّذ حرفيًا (المتطلبات §٥.١)، والقوالب تحترم معجم الواجهة (المسرد §٨.٢)."""

import pytest

from saadeed.domain.enums import (
    Action,
    ClaimType,
    EvidenceStatus,
    Severity,
    SourceRole,
    TrackBucket,
    bucket_for,
)
from saadeed.domain.policy import RULES, Signal, apply
from saadeed.domain.templates import EXPLANATIONS, NEXT_STEPS

# الجدول كما في المتطلبات: (قاعدة، حالة، أثر، إجراء)
EXPECTED = {
    Signal.QURAN_MATCH: ("BR-01", "SUPPORTED", "NONE", "NONE"),
    Signal.QURAN_TEXT_MISMATCH: ("BR-02", "CONTRADICTED", "CRITICAL", "CORRECT_FROM_SOURCE"),
    Signal.QURAN_WRONG_REFERENCE: ("BR-03", "PARTIALLY_SUPPORTED", "HIGH", "CORRECT_FROM_SOURCE"),
    Signal.QURAN_NOT_IN_MUSHAF: ("BR-04", "CONTRADICTED", "CRITICAL", "RECONSIDER"),
    Signal.HADITH_KNOWN_WEAK: ("BR-05", "CONTRADICTED", "CRITICAL", "RECONSIDER"),
    Signal.HADITH_AUTHENTIC_MATCH: ("BR-06", "SUPPORTED", "NONE", "NONE"),
    Signal.HADITH_PARAPHRASE_AS_WORDING: (
        "BR-07",
        "PARTIALLY_SUPPORTED",
        "HIGH",
        "CORRECT_FROM_SOURCE",
    ),
    Signal.HADITH_PARAPHRASE_DECLARED: ("BR-08", "SUPPORTED", "NONE", "NONE"),
    Signal.HADITH_MISATTRIBUTED: ("BR-09", "PARTIALLY_SUPPORTED", "HIGH", "CORRECT_FROM_SOURCE"),
    Signal.HADITH_LOCATE_ONLY: ("BR-10", "FOUND_NO_RULING", "HIGH", "VERIFY"),
    Signal.HADITH_NOT_FOUND: ("BR-11", "NOT_FOUND", "HIGH", "VERIFY"),
    Signal.SOURCING_NO_SOURCE: ("BR-12", "OUT_OF_SCOPE", "MEDIUM", "VERIFY"),
    Signal.SOURCING_CITED_OUT_OF_COVERAGE: ("BR-13", "OUT_OF_SCOPE", "LOW", "VERIFY"),
    Signal.CONSENSUS: ("BR-14", "OUT_OF_SCOPE", "HIGH", "REPHRASE"),
    Signal.GENERALIZATION: ("BR-15", "OUT_OF_SCOPE", "LOW", "REPHRASE"),
    Signal.GROUP_JUDGMENT: ("BR-16", "OUT_OF_SCOPE", "HIGH", "REFER"),
    Signal.SPECIALIST_REQUIRED: ("BR-17", "OUT_OF_SCOPE", "MEDIUM", "REFER"),
    Signal.FATWA_REQUIRED: ("BR-18", "OUT_OF_SCOPE", "HIGH", "REFER"),
    Signal.CONCLUSION_EXCEEDS: ("BR-19", "EXCEEDS_SOURCE", "MEDIUM", "REPHRASE"),
    Signal.SYSTEM_UNAVAILABLE: ("BR-20", "NOT_CHECKED", "NONE", "NONE"),
    # v2.5 (ADR-0014)
    Signal.QURAN_MERGED: ("BR-21", "PARTIALLY_SUPPORTED", "HIGH", "CORRECT_FROM_SOURCE"),
    Signal.QURAN_AS_HADITH: ("BR-22", "PARTIALLY_SUPPORTED", "HIGH", "CORRECT_FROM_SOURCE"),
    Signal.HADITH_NOT_FOUND_WITH_SIGNS: ("BR-23", "NOT_FOUND", "CRITICAL", "VERIFY"),
    # v2.6: الأقوال المنسوبة تُطابق بمكتبة كتب العلماء (وصلة حية).
    Signal.SAYING_FOUND: ("BR-24", "SUPPORTED", "NONE", "NONE"),
    Signal.SAYING_FOUND_PARAPHRASE: ("BR-25", "PARTIALLY_SUPPORTED", "LOW", "CORRECT_FROM_SOURCE"),
    Signal.SAYING_OTHER_AUTHOR: ("BR-26", "PARTIALLY_SUPPORTED", "MEDIUM", "CORRECT_FROM_SOURCE"),
    Signal.SAYING_NOT_FOUND: ("BR-27", "NOT_FOUND", "MEDIUM", "VERIFY"),
}


@pytest.mark.parametrize("signal", list(Signal))
def test_every_rule_matches_requirements_table(signal):
    rule = apply(signal)
    assert (rule.rule_id, rule.status.value, rule.severity.value, rule.action.value) == EXPECTED[
        signal
    ]


def test_rule_ids_unique_and_complete():
    ids = [r.rule_id for r in RULES.values()]
    assert len(ids) == len(set(ids)) == 27


def test_policy_is_deterministic():
    assert all(apply(s) == apply(s) for s in Signal)


def test_bucket_derived_from_action_only():
    assert bucket_for(Action.NONE, EvidenceStatus.SUPPORTED) is TrackBucket.SUPPORTED_BY_SOURCES
    assert bucket_for(Action.REFER, EvidenceStatus.OUT_OF_SCOPE) is TrackBucket.REFER
    assert (
        bucket_for(Action.REPHRASE, EvidenceStatus.OUT_OF_SCOPE) is TrackBucket.NEEDS_VERIFICATION
    )
    assert bucket_for(Action.NONE, EvidenceStatus.NOT_CHECKED) is TrackBucket.NOT_CHECKED


FORBIDDEN = [
    "سليمة",
    "معتمدة",
    "صحيحة 100",
    "خطأ فادح",
    "كذب",
    "مكذوب",
    "موضوع",
    "باطل",
    "مرجعية",
    "طوائف",
]


@pytest.mark.parametrize("word", FORBIDDEN)
def test_templates_never_use_forbidden_words(word):
    for text in [*EXPLANATIONS.values(), *NEXT_STEPS.values()]:
        assert word not in text, f"«{word}» في قالب: {text}"


def test_every_rule_has_templates():
    for rule in RULES.values():
        assert rule.rule_id in EXPLANATIONS and rule.rule_id in NEXT_STEPS


def test_every_labeled_enum_member_has_arabic_label():
    for enum in (EvidenceStatus, Severity, Action, TrackBucket, ClaimType, SourceRole):
        for m in enum:
            assert m.label_ar
