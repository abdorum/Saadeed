"""أعطال الاختبار الميداني على عشر خطب من الألوكة (T-138، E-023..E-027). حتمي، بلا نموذج."""

from saadeed.domain.enums import ClaimType
from saadeed.domain.policy import Signal
from saadeed.text.footnotes import find_footnotes, strip_ref
from saadeed.text.markers import canonical_books, scan
from tests.conftest import needs_data

_DRAFT_WITH_NOTES = (
    "قال رسول الله ﷺ: «أيما مسلم سقى مسلما على ظمأ سقاه الله من الرحيق المختوم»[1]. "
    "وقال الخطابي: «معناه ما فضل عن حاجته وحاجة عياله»[2].\n\n"
    "[1] أخرجه أبو داود (1682)، والترمذي (2449).\n\n"
    "[2] عون المعبود شرح سنن أبي داود (9/268).\n\n"
    "[3] [الأعراف: 31]."
)


def test_footnotes_zone_and_refs():
    notes = find_footnotes(_DRAFT_WITH_NOTES)
    assert notes.zone_start == _DRAFT_WITH_NOTES.index("[1] أخرجه")
    end = _DRAFT_WITH_NOTES.index("المختوم") + len("المختوم")
    assert notes.ref_after(_DRAFT_WITH_NOTES, end).startswith("أخرجه أبو داود")
    assert strip_ref("3") is None and strip_ref("[3]") is None and strip_ref("رواه مسلم")
    # سطر واحد يبدأ برقم ليس قسم حواشٍ
    assert find_footnotes("(1) أولًا: التقوى.\nثم الكلام.").zone_start is None


def test_commentary_is_not_the_book():
    assert canonical_books("عون المعبود شرح سنن أبي داود") == {"other"}
    assert canonical_books("شرح النووي على صحيح مسلم") == {"other"}
    assert canonical_books("أخرجه البخاري رقم (4563)") == {"bukhari"}


def test_qudsi_after_allah_said_is_hadith():
    t = (
        "وهو سبحانه القائل في الحديث القدسي: فيقول الله تعالى: ((وعزتي وجلالي لأنصرنك ولو بعد حين)) "
        "(رواه الترمذي). وقال تعالى: (إن الله مع الصابرين)."
    )
    kinds = [(m.kind, m.text) for m in scan(t)]
    assert kinds == [
        ("hadith", "وعزتي وجلالي لأنصرنك ولو بعد حين"),
        ("quran", "إن الله مع الصابرين"),
    ]


@needs_data
def test_rasm_vocative_and_assimilation(engine):
    v = engine.quran
    for ok in (
        "فَاعْتَبِرُوا يَاأُولِي الْأَبْصَارِ",
        "قُلْ يَاعِبَادِيَ الَّذِينَ أَسْرَفُوا عَلَى أَنْفُسِهِمْ",
        "وَأَلَّوِ اسْتَقَامُوا عَلَى الطَّرِيقَةِ لَأَسْقَيْنَاهُمْ مَاءً غَدَقًا",
    ):
        assert v.verify(ok).signal is Signal.QURAN_MATCH, ok
    # والخطأ الحقيقي يبقى خطأً (خطبة منشورة: «ولولو» مكررة)
    typo = "وَإِذَا جَاءَهُمْ أَمْرٌ مِنَ الْأَمْنِ أَوِ الْخَوْفِ أَذَاعُوا بِهِ وَلولوْ رَدُّوهُ"
    assert v.verify(typo).signal is Signal.QURAN_TEXT_MISMATCH
    assert engine.quran.index.split_vocative("ياتي") == ["ياتي"]


@needs_data
def test_footnotes_are_sources_not_claims(engine):
    r = engine.reviewer(None).review(_DRAFT_WITH_NOTES)
    assert all(f.claim.span.start < _DRAFT_WITH_NOTES.index("[1] أخرجه") for f in r.findings)
    assert all(f.rule_id != "BR-04" for f in r.findings)  # «[الأعراف: 31]» ليست آية محرّفة
    hadith = next(f for f in r.findings if f.claim.type is ClaimType.HADITH_QUOTE)
    assert canonical_books(hadith.claim.hints.cited_book) == {"abudawud", "tirmidhi"}
