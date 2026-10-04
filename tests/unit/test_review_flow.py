"""المسار الكامل بنموذج مزيف: حتمي، ومجاني، ويختبر الفشل الآمن وحارس الإسناد."""

import json

from saadeed.adapters.llm.fake import BrokenLLM, FakeLLM
from saadeed.application.review_draft import ReviewConfig
from saadeed.domain.enums import (
    Action,
    ClaimType,
    EvidenceStatus,
    MatchType,
    SourceRole,
    TrackBucket,
)
from saadeed.domain.models import Evidence, SourceRef
from tests.conftest import needs_data

pytestmark = needs_data

DRAFT = (
    "قال الله تعالى: ﴿يَا أَيُّهَا الَّذِينَ آمَنُوا اتَّقُوا اللَّهَ وَقُولُوا قَوْلًا حسنا﴾ [الأحزاب: 70]. "
    "وقال رسول الله ﷺ: «اطلبوا العلم ولو بالصين». "
    "وقد أجمع العلماء على أن الصدق منجاة. "
    "وقال ابن القيم: العلم صيد والكتابة قيده."
)


def scripted(system: str, user: str) -> dict:
    if "الاستخراج" in system:
        return {
            "claims": [
                {
                    "s": 0,
                    "quote": "يَا أَيُّهَا الَّذِينَ آمَنُوا اتَّقُوا اللَّهَ وَقُولُوا قَوْلًا حسنا",
                    "type": "QURAN_QUOTE",
                    "level": "A",
                },
                {"s": 1, "quote": "اطلبوا العلم ولو بالصين", "type": "HADITH_QUOTE", "level": "A"},
                {
                    "s": 2,
                    "quote": "أجمع العلماء على أن الصدق منجاة",
                    "type": "CONSENSUS_CLAIM",
                    "level": "B",
                },
                {
                    "s": 3,
                    "quote": "العلم صيد والكتابة قيده",
                    "type": "ATTRIBUTED_SAYING",
                    "level": "B",
                    "speaker": "ابن القيم",
                },
                {"s": 3, "quote": "نص لا يوجد في المسودة أبدًا", "type": "STATISTIC", "level": "B"},
            ]
        }
    return {"items": []}


def test_full_flow_with_fake_llm(engine):
    report = engine.reviewer(FakeLLM(scripted)).review(DRAFT)
    by_type = {f.claim.type: f for f in report.findings}
    assert by_type[ClaimType.QURAN_QUOTE].rule_id == "BR-02"
    assert by_type[ClaimType.HADITH_QUOTE].rule_id == "BR-05"
    assert by_type[ClaimType.CONSENSUS_CLAIM].action is Action.REPHRASE
    assert by_type[ClaimType.ATTRIBUTED_SAYING].evidence_status is EvidenceStatus.OUT_OF_SCOPE
    # الادعاء الذي اخترعه النموذج ولا يوجد في المسودة أُسقط
    assert len(report.findings) == 4
    assert any("أُسقط ادعاء" in w for w in report.meta.warnings)
    # الأخطر أولًا: الحرج قبل غيره
    first = next(f for f in report.findings if f.id == report.top_risks[0])
    assert first.severity.value == "CRITICAL"
    json.dumps(report.model_dump(mode="json"), ensure_ascii=False)


def test_same_input_same_report(engine):
    r1 = engine.reviewer(FakeLLM(scripted)).review(DRAFT)
    r2 = engine.reviewer(FakeLLM(scripted)).review(DRAFT)

    def strip(r):
        return [(f.id, f.rule_id, f.evidence_status, f.action, f.explanation) for f in r.findings]

    assert strip(r1) == strip(r2)


def test_safe_failure_when_llm_is_down(engine):
    report = engine.reviewer(BrokenLLM()).review(DRAFT)
    types = {f.claim.type for f in report.findings}
    # المعلَّم ما زال يُفحص بلا نموذج
    assert ClaimType.QURAN_QUOTE in types and ClaimType.HADITH_QUOTE in types
    assert report.summary.not_checked
    assert any("تعذّر" in w for w in report.meta.warnings)


def test_citation_guard_drops_unknown_ids(engine):
    rev = engine.reviewer(FakeLLM(scripted))
    report = rev.review(DRAFT)
    f = next(x for x in report.findings if x.claim.type is ClaimType.QURAN_QUOTE)
    fake = Evidence(
        ref=SourceRef(source_id="bukhari", item_id="99999999", citation="مزيف"),
        role=SourceRole.AUTHENTIC,
        text="نص مختلق",
        match_type=MatchType.NORMALIZED,
        match_reason="—",
    )
    bad = f.model_copy(update={"evidence": [fake], "evidence_status": EvidenceStatus.SUPPORTED})
    (guarded,) = rev.guard.guard([bad])
    assert guarded.evidence == []
    assert guarded.evidence_status is EvidenceStatus.NOT_CHECKED


def test_guard_replaces_text_with_store_text(engine):
    rev = engine.reviewer(FakeLLM(scripted))
    report = rev.review(DRAFT)
    f = next(x for x in report.findings if x.claim.type is ClaimType.QURAN_QUOTE)
    tampered = f.model_copy(
        update={"evidence": [f.evidence[0].model_copy(update={"text": "نص عدّله أحد"})]}
    )
    (guarded,) = rev.guard.guard([tampered])
    assert guarded.evidence[0].text == f.evidence[0].text


def test_overreach_off_by_default(engine):
    assert ReviewConfig().enable_overreach is False


def test_buckets_add_up(engine):
    report = engine.reviewer(FakeLLM(scripted)).review(DRAFT)
    assert sum(report.summary.by_bucket.values()) == report.summary.total_claims
    assert report.summary.by_bucket[TrackBucket.NEEDS_VERIFICATION.value] == 4
