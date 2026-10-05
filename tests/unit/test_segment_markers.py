from saadeed.text.markers import canonical_books, parse_ref, scan
from saadeed.text.segment import split_sentences


def test_no_split_inside_quran_brackets_or_quotes():
    text = "قال تعالى: ﴿قُلْ هُوَ اللَّهُ أَحَدٌ. اللَّهُ الصَّمَدُ﴾. وقال ﷺ: «الدين النصيحة. قلنا لمن؟». انتهى."
    sents = split_sentences(text)
    assert any("أَحَدٌ. اللَّهُ" in s.text for s in sents)
    assert any("النصيحة. قلنا" in s.text for s in sents)


def test_quran_marker_with_reference():
    text = "قال تعالى: ﴿وَقُولُوا قَوْلًا سَدِيدًا﴾ [الأحزاب: ٧٠]."
    (m,) = scan(text)
    assert m.kind == "quran"
    assert m.ref_parsed == (33, 70, 70)


def test_hadith_marker_with_takhrij_and_meaning():
    text = "وقال ﷺ: «الدين النصيحة» رواه مسلم. وعنه ﷺ ما معناه: «من غشنا فليس منا»."
    marks = scan(text)
    assert [m.kind for m in marks] == ["hadith", "hadith"]
    assert marks[0].cited_book and "مسلم" in marks[0].cited_book
    assert marks[0].verbatim is True
    assert marks[1].verbatim is False


def test_parse_ref_variants():
    assert parse_ref("البقرة: 255") == (2, 255, 255)
    assert parse_ref("(سورة آل عمران: 102)") == (3, 102, 102)
    assert parse_ref("[الأحزاب: ٧٠–٧١]") == (33, 70, 71)
    assert parse_ref("[بني إسرائيل: 36]") == (17, 36, 36)
    assert parse_ref("[كتاب مجهول: 3]") is None


def test_canonical_books():
    assert canonical_books("متفق عليه") == {"bukhari", "muslim"}
    assert canonical_books("رواه البخاري ومسلم") == {"bukhari", "muslim"}
    assert canonical_books("في الصحيحين") == {"bukhari", "muslim"}
    assert canonical_books("رواه أبو داود") == {"abudawud"}
    assert canonical_books("رواه أحمد") == {"other"}


def test_double_parentheses_hadith_and_comma_range():
    """فجوة كشفتها خطبة حقيقية (الألوكة): (( )) للحديث، و[فصلت: 34، 35] للإحالة."""
    text = (
        "أن رسول الله صلى الله عليه وسلم قال: ((لا يستقيم إيمان عبد حتى يستقيم قلبه)). "
        "وقال سبحانه: ﴿ ادْفَعْ بِالَّتِي هِيَ أَحْسَنُ ﴾ [فصلت: 34، 35]."
    )
    marks = scan(text)
    assert [m.kind for m in marks] == ["hadith", "quran"]
    assert marks[0].text.startswith("لا يستقيم")
    assert marks[1].ref_parsed == (41, 34, 35)
    assert parse_ref("[المؤمنون: 1 - 3]") == (23, 1, 3)


def test_scan_fully_vocalized_hadith():
    # الخطب المنشورة تُشكَّل كاملة: الأنماط تعمل على الهيكل، والنص المعروض من الأصل بحركاته.
    text = (
        "فَقَالَ صَلَّى اللَّهُ عَلَيْهِ وَسَلَّمَ: «إِذَا رَأَى أَحَدُكُمُ الرُّؤْيَا يَكْرَهُهَا فَلْيَبْصُقْ عَنْ يَسَارِهِ ثَلَاثًا» "
        "رَوَاهُ مُسْلِمٌ، وَقَالَ النَّبِيُّ ‌صَلَّى اللَّهُ عَلَيْهِ وَسَلَّمَ: «وَلَا يُحَدِّثْ بِهَا أَحَدًا» رَوَاهُ الشَّيْخَانِ."
    )
    found = [m for m in scan(text) if m.kind == "hadith"]
    assert len(found) == 2
    assert found[0].text.startswith("إِذَا رَأَى") and found[0].text.endswith("ثَلَاثًا")
    assert text[found[0].start : found[0].end] == found[0].text
    assert found[0].cited_book == "مسلم"
    assert canonical_books(found[1].cited_book) == {"bukhari", "muslim"}


def test_scan_keeps_hadith_that_contains_a_verse():
    text = (
        "قَوْلُ النَّبِيِّ صَلَّى اللَّهُ عَلَيْهِ وَسَلَّمَ: «إِذَا أَوَيْتَ إِلَى فِرَاشِكَ فَاقْرَأْ آيَةَ الْكُرْسِيِّ "
        "﴿ اللَّهُ لَا إِلَهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ ﴾ حَتَّى تَخْتِمَ الْآيَةَ» رَوَاهُ الْبُخَارِيُّ."
    )
    kinds = sorted(m.kind for m in scan(text))
    assert kinds == ["hadith", "quran"]
