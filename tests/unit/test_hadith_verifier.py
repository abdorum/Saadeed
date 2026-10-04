"""متحقق الأحاديث على الكتب الستة الحقيقية."""

import pytest

from saadeed.domain.policy import Signal
from saadeed.verifiers.hadith import HadithPending
from tests.conftest import needs_data

pytestmark = needs_data


@pytest.mark.parametrize(
    ("quote", "book", "signal"),
    [
        (
            "إنما الأعمال بالنيات وإنما لكل امرئ ما نوى",
            "متفق عليه",
            Signal.HADITH_AUTHENTIC_MATCH,
        ),  # «بالنية» عند مسلم
        ("الدين النصيحة", "رواه مسلم", Signal.HADITH_AUTHENTIC_MATCH),
        ("الطهور شطر الإيمان", "رواه البخاري", Signal.HADITH_MISATTRIBUTED),  # هو في مسلم
        ("تبسمك في وجه أخيك لك صدقة", None, Signal.HADITH_LOCATE_ONLY),  # في الترمذي وحده
        ("اطلبوا العلم ولو في الصين", None, Signal.HADITH_KNOWN_WEAK),  # صيغة غير صيغة القائمة
        ("حب الأوطان من الإيمان", None, Signal.HADITH_KNOWN_WEAK),
    ],
)
def test_hadith_cases(engine, quote, book, signal):
    out = engine.hadith.verify_deterministic(quote, True, book)
    assert not isinstance(out, HadithPending)
    assert out.signal is signal


def test_locate_only_never_says_supported(engine):
    out = engine.hadith.verify_deterministic("تبسمك في وجه أخيك لك صدقة", True, None)
    assert out.signal is Signal.HADITH_LOCATE_ONLY
    assert any(e.ref.source_id == "dorar" for e in out.evidence)


def test_sahih_hadith_not_confused_with_known_weak(engine):
    out = engine.hadith.verify_deterministic("الدين النصيحة", True, None)
    assert out.signal is not Signal.HADITH_KNOWN_WEAK


def test_unknown_text_goes_to_judge_with_store_candidates(engine):
    out = engine.hadith.verify_deterministic("خير الناس أنفعهم للناس", True, None)
    assert isinstance(out, HadithPending)
    assert 0 < len(out.candidates) <= 5
    assert all(":" in c.key for c in out.candidates)


def test_judge_cannot_inject_unknown_id(engine):
    pend = engine.hadith.verify_deterministic("خير الناس أنفعهم للناس", True, None)
    out = engine.hadith.resolve_with_judgment(
        "خير الناس أنفعهم للناس", True, None, pend, "VERBATIM", "bukhari:999999"
    )
    assert out.signal is Signal.HADITH_NOT_FOUND
    assert any("حارس الإسناد" in n for n in out.notes)
