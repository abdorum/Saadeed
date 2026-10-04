from saadeed.text.normalize import find_span, normalize, tokens


def test_diacritics_and_alef_forms_are_ignored():
    assert normalize("إِنَّ اللَّهَ مَعَ الصَّابِرِينَ") == normalize("ان الله مع الصابرين")
    assert normalize("آمَنُوا") == normalize("امنوا")
    assert normalize("ٱلرَّحْمَٰنِ") == "الرحمن"  # ألف وصل وألف خنجرية


def test_ta_marbuta_ya_and_hamza_seats():
    assert normalize("الصلاة") == normalize("الصلاه")
    assert normalize("على") == normalize("علي")
    assert normalize("مسؤول") == normalize("مسوول")


def test_honorifics_expand_so_hadith_text_matches():
    assert normalize("صلى الله عليه وسلم") in normalize("قال رسول الله ﷺ")


def test_punctuation_and_tatweel_removed():
    assert tokens("الحمــد لله، رب العالمين!") == ["الحمد", "لله", "رب", "العالمين"]


def test_find_span_maps_back_to_original_positions():
    text = "قال تعالى: ﴿إِنَّ اللَّهَ مَعَ الصَّابِرِينَ﴾ والحمد لله."
    span = find_span(text, "ان الله مع الصابرين")
    assert span is not None
    assert text[span[0] : span[1]] == "إِنَّ اللَّهَ مَعَ الصَّابِرِينَ"
