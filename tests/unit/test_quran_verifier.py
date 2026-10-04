"""متحقق الآيات على المصحف الحقيقي (Tanzil)."""

import pytest

from saadeed.domain.policy import Signal
from tests.conftest import needs_data

pytestmark = needs_data


@pytest.mark.parametrize(
    ("quote", "ref", "signal", "citation"),
    [
        ("إِنَّ اللَّهَ مَعَ الصَّابِرِينَ", "البقرة: 153", Signal.QURAN_MATCH, "البقرة: 153"),
        (
            "إن الله مع الصابرين",
            "الأنفال: 46",
            Signal.QURAN_MATCH,
            "الأنفال: 46",
        ),  # العبارة في موضعين
        (
            "يا أيها الذين آمنوا اتقوا الله وقولوا قولا سديدا",
            "[الأحزاب: 70]",
            Signal.QURAN_MATCH,
            "الأحزاب: 70",
        ),
        (
            "يا أيها الذين آمنوا اتقوا الله وقولوا قولا حسنا",
            None,
            Signal.QURAN_TEXT_MISMATCH,
            "الأحزاب: 70",
        ),
        ("قل هو الله واحد", None, Signal.QURAN_TEXT_MISMATCH, "الإخلاص: 1"),
        (
            "يا أيها الذين آمنوا اتقوا الله وقولوا قولا سديدا",
            "(البقرة: 70)",
            Signal.QURAN_WRONG_REFERENCE,
            "الأحزاب: 70",
        ),
        ("الجنة تحت أقدام الأمهات", None, Signal.QURAN_NOT_IN_MUSHAF, None),
        ("الله نور السموات والأرض", None, Signal.QURAN_MATCH, "النور: 35"),  # فرق رسم
        ("وأقيموا الصلوة وآتوا الزكوة", None, Signal.QURAN_MATCH, "البقرة: 43"),  # فرق رسم
    ],
)
def test_quran_cases(engine, quote, ref, signal, citation):
    out = engine.quran.verify(quote, ref)
    assert out.signal is signal
    if citation:
        assert out.evidence[0].ref.citation == citation


def test_diacritics_only_difference_is_not_flagged(engine):
    plain = engine.quran.verify("قل هو الله احد الله الصمد")
    voweled = engine.quran.verify("قُلْ هُوَ اللَّهُ أَحَدٌ اللَّهُ الصَّمَدُ")
    assert plain.signal is voweled.signal is Signal.QURAN_MATCH


def test_quote_spanning_two_ayat(engine):
    out = engine.quran.verify(
        "يا أيها الذين آمنوا اتقوا الله وقولوا قولا سديدا يصلح لكم أعمالكم ويغفر لكم ذنوبكم"
    )
    assert out.signal is Signal.QURAN_MATCH
    assert out.evidence[0].ref.citation == "الأحزاب: 70–71"


def test_evidence_text_is_uthmani_from_store(engine):
    out = engine.quran.verify("قل هو الله أحد")
    assert "\u0671" in out.evidence[0].text  # ألف الوصل علامة الرسم العثماني


def test_same_input_same_output(engine):
    a = engine.quran.verify("يا أيها الذين آمنوا اتقوا الله وقولوا قولا حسنا")
    b = engine.quran.verify("يا أيها الذين آمنوا اتقوا الله وقولوا قولا حسنا")
    assert a.signal == b.signal and a.evidence[0].diff == b.evidence[0].diff
