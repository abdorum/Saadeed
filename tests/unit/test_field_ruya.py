"""نقطة المرجع الميدانية (E-019..E-021): خطبة «الرؤى والأحلام» المنشورة، مشكولة كاملة، 1202 كلمة.

ما ينبغي أن يظهر مكتوب في `eval/field/ruya_ahlam.md`. وهنا ما يثبت منه بالقواعد وحدها (بلا نموذج)،
وما يثبت مع نموذج مُبرمَج يعيد خريطة المسودة.
"""

from pathlib import Path

from saadeed.adapters.llm.fake import FakeLLM
from saadeed.application.extraction import CHUNK_MAX, chunk_sentences
from saadeed.application.safety_net import safety_net
from saadeed.domain.enums import ClaimType, SegmentKind
from saadeed.text.markers import canonical_books, has_prophetic_context
from saadeed.text.normalize import normalize
from saadeed.text.segment import split_sentences
from saadeed.verifiers.hadith import without_embedded_verses
from tests.conftest import needs_data

DRAFT = (Path(__file__).parents[2] / "eval" / "field" / "ruya_ahlam.txt").read_text()


def _find(report, needle, ctype=None):
    # المقارنة بعد التطبيع: ترتيب الحركات (الشدة والفتحة) يختلف بين لوحات المفاتيح.
    hits = [
        f
        for f in report.findings
        if normalize(needle) in normalize(f.claim.text) and ctype in (None, f.claim.type)
    ]
    assert hits, f"لم يُفحص: {needle}"
    return hits[0]


def test_long_draft_is_chunked_short_draft_is_not():
    sents = split_sentences(DRAFT)
    parts = chunk_sentences(sents)
    assert len(parts) > 1
    assert [s for p in parts for s in p] == sents  # لا جملة تسقط ولا تتكرر
    short = split_sentences("قال رسول الله ﷺ: «إنما الأعمال بالنيات».")
    assert chunk_sentences(short) == [short]
    assert CHUNK_MAX >= 118  # أطول حامل في بنك التقييم: لا يتغير نداؤه فتبقى الإعادة صالحة


def test_quote_attribution_stays_in_its_sentence():
    text = "سنة النبي صلى الله عليه وسلم.\n\nفدلت النصوص على أمور: «أن يحمد الله عليها وأن يستبشر بها»."
    i = text.index("أن يحمد")
    assert not has_prophetic_context(text, i, i + 10)
    text2 = "وعند الترمذي عن النبي صلى الله عليه وسلم قال: «في آخر الزمان لا تكاد رؤيا المؤمن تكذب»"
    j = text2.index("في آخر")
    assert has_prophetic_context(text2, j, j + 10)
    k = "وكان النبي صلى الله عليه وسلم إذا حزبه أمر صلى."
    assert has_prophetic_context(k, 0, len(k))


def test_kubra_is_out_of_coverage_and_embedded_verse_stripped():
    assert canonical_books("رواه النسائي في الكبرى") == {"other"}
    assert canonical_books("رواه النسائي") == {"nasai"}
    assert without_embedded_verses("فاقرأ آية الكرسي ﴿ الله لا إله إلا هو ﴾ حتى تختم") == (
        "فاقرأ آية الكرسي حتى تختم"
    )


def test_net_groups_story_and_asks_quote_speaker():
    text = (
        "كان الربيع بن خثيم من كبار التابعين. فنام صاحبه فأتاه آت في المنام. "
        "فقال له الربيع: «إنما هذا الشيطان فأعيذك بالله منه». "
        "وذلك «طردا للشيطان الذي حضر الرؤيا المكروهة تحقيرا له واستقذارا»."
    )
    sents = split_sentences(text)
    kinds = {0: SegmentKind.ATHAR, 1: SegmentKind.STORY, 2: SegmentKind.STORY}
    out = safety_net(text, [], sents, kinds)
    assert out[0].type is ClaimType.HISTORICAL_EVENT and out[0].origin == "net-map"
    assert "كان الربيع" in out[0].text and "أعيذك" in out[0].text  # القصة ادعاء واحد
    quote = [c for c in out if c.origin == "net-quote"]
    assert len(quote) == 1 and quote[0].text.startswith("طردا للشيطان")
    assert quote[0].type is ClaimType.ATTRIBUTED_SAYING


@needs_data
def test_field_sermon_deterministic(engine):
    """بلا نموذج: كل حديث في الخطبة يُفحص، والآية داخل الحديث تُفحص بالمصحف."""
    r = engine.reviewer(None).review(DRAFT)
    assert _find(r, "فَلْيَتَعَوَّذْ بِاللَّهِ مِنْ شَرِّهَا").rule_id == "BR-06"  # رواه الشيخان
    assert _find(r, "فَلْيَبْصُقْ عَنْ يَسَارِهِ ثَلَاثًا، وَلْيَسْتَعِذْ").rule_id == "BR-06"
    assert _find(r, "لَا تَكَادُ رُؤْيَا الْمُؤْمِنِ").rule_id == "BR-10"  # الترمذي
    assert _find(r, "رَأْسِي ضُرِبَ").rule_id == "BR-10"  # ابن ماجه، بلا «قال ﷺ» قبله
    assert _find(r, "لَقَدْ كُنْتُ أَرَى الرُّؤْيَا فَتُمْرِضُنِي").rule_id == "BR-06"  # أثر في البخاري
    verse = _find(r, "اللَّهُ لَا إِلَهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ", ClaimType.QURAN_QUOTE)
    assert verse.claim.type is ClaimType.QURAN_QUOTE and verse.rule_id == "BR-01"
    # اقتباس بلا قائل بعد «وفي رواية» في جملته: بلا نموذج يُعلن «لم يُفحص» ولا يُترك صامتًا.
    assert _find(r, "طَرْدًا لِلشَّيْطَانِ").rule_id in ("BR-12", "BR-20")
    khalid = _find(r, "كَانَ خَالِدُ بْنُ الْوَلِيدِ")
    assert canonical_books(khalid.claim.hints.cited_book) == {"other"}


@needs_data
def test_field_sermon_with_model_map(engine):
    """بنموذج لا يستخرج شيئًا سوى الخريطة: الشبكة تلتقط القصة و«بعض العلماء»،
    والاقتباس بلا نسبة لا يُعدّ «لفظ حديث» (لا BR-07)."""
    sents = split_sentences(DRAFT)

    def kind_of(s):
        n = normalize(s.text)
        if "الربيع" in n or "الهمداني" in n:
            return "STORY"
        if "بعض العلم" in n:
            return "SCHOLAR"
        return "EXHORTATION"

    def scripted(system, user):
        if "الاستخراج" in system:
            idx = [int(line[1 : line.index("]")]) for line in user.splitlines() if line[:1] == "["]
            return {"claims": [], "map": [[i, kind_of(sents[i])] for i in idx]}
        return {"items": []}

    r = engine.reviewer(FakeLLM(scripted)).review(DRAFT)
    story = _find(r, "الرَّبِيعُ بْنُ خُثَيْمٍ")
    assert story.claim.type is ClaimType.HISTORICAL_EVENT and story.rule_id == "BR-12"
    assert _find(r, "ذكر بعض العلم").rule_id == "BR-12"
    assert all(f.rule_id != "BR-07" for f in r.findings if "يستبشر" in normalize(f.claim.text))
