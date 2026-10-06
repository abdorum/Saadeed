"""عقد التوسعة (docs/EXTENDING.md): من أضاف نوعًا أو صنفًا أو قاعدة أو دورًا ونسي خطوة، فشل هذا الاختبار.

الفكرة: «مضمون» في الهندسة تعني «مفروض باختبار»، لا «موعود في وثيقة».
"""

import re
from pathlib import Path

import pytest

from saadeed.domain.enums import (
    Action,
    ClaimType,
    ContentLevel,
    EvidenceStatus,
    OverreachType,
    SegmentKind,
    Severity,
    SourceRole,
    TrackBucket,
    bucket_for,
)
from saadeed.domain.models import Claim, Span
from saadeed.domain.policy import RULES, Signal, apply
from saadeed.domain.templates import EXPLANATIONS, NEXT_STEPS
from saadeed.verifiers.base import Outcome
from saadeed.verifiers.hadith import HadithPending
from tests.conftest import needs_data

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "web" / "assets" / "app.css").read_text(encoding="utf-8")
JS = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")

# أنواع لا تُوجَّه من الاستخراج مباشرة، بل تُبنى في مسار خاص (فحص التجاوز).
ROUTE_EXEMPT = {ClaimType.HADITH_CONCLUSION}


@pytest.mark.parametrize(
    "enum",
    [
        EvidenceStatus,
        Severity,
        Action,
        TrackBucket,
        ClaimType,
        SegmentKind,
        OverreachType,
        SourceRole,
    ],
)
def test_every_enum_value_has_an_arabic_label(enum):
    for v in enum:
        assert v.label_ar.strip(), f"{enum.__name__}.{v.value} بلا تسمية عربية (enums._LABEL_PAIRS)"


def test_every_signal_has_rule_and_both_templates():
    for sig in Signal:
        rule = apply(sig)
        assert sig in RULES, f"{sig} بلا صف في جدول القواعد (policy.RULES)"
        assert rule.rule_id in EXPLANATIONS, f"{rule.rule_id} بلا قالب شرح (templates.EXPLANATIONS)"
        assert rule.rule_id in NEXT_STEPS, (
            f"{rule.rule_id} بلا قالب خطوة تالية (templates.NEXT_STEPS)"
        )


def test_every_action_maps_to_a_summary_bucket():
    for a in Action:
        for s in EvidenceStatus:
            assert isinstance(bucket_for(a, s), TrackBucket)


@needs_data
def test_every_claim_type_is_routed(engine):
    """كل نوع ادعاء له مسار صريح في `ReviewDraft._route`، لا يسقط في الاحتياط العام صامتًا."""
    rev = engine.reviewer(None)
    for t in ClaimType:
        if t in ROUTE_EXEMPT:
            continue
        cl = Claim(
            id="c1",
            text="نص تجريبي للاختبار",
            span=Span(start=0, end=18),
            type=t,
            level=ContentLevel.B,
        )
        out = rev._route(cl)
        assert isinstance(out, Outcome | HadithPending), t
        if isinstance(out, Outcome):
            silent_fallback = (
                out.signal is Signal.SOURCING_NO_SOURCE and out.confidence.value == "low"
            )
            assert not silent_fallback, f"{t} يسقط في الاحتياط العام: أضف له مسارًا في _route"


def test_every_segment_kind_has_a_color_in_the_interface():
    for k in SegmentKind:
        var = f"--k-{k.value.lower()}"
        assert var in CSS, f"صنف الخريطة {k} بلا لون في web/assets/app.css ({var})"
        assert re.search(rf"\b{k.value}\s*:", JS), f"صنف الخريطة {k} غير معرّف في KIND_VAR (app.js)"


def test_every_source_role_is_explained_in_the_interface():
    for r in SourceRole:
        assert re.search(rf"\b{r.value}\s*:", JS), f"الدور {r} بلا تسمية في ROLE_AR (app.js)"


def test_every_bucket_is_rendered_in_the_interface():
    for b in TrackBucket:
        assert re.search(rf"\b{b.value}\s*:", JS), f"الباب {b} غير معرّف في BUCKETS (app.js)"
