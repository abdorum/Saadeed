"""v2.6 (ADR-0016): مطابقة اسم المؤلف، وتنظيف الضجيج قبل الفحص، وروابط الدرر."""

from urllib.parse import unquote

from saadeed.adapters.sources.known_weak import DorarLinker
from saadeed.adapters.sources.turath import same_author
from saadeed.application.review_draft import _drop_noise
from saadeed.domain.enums import ClaimType, ContentLevel
from saadeed.domain.models import Claim, ClaimHints, Span


def test_same_author_matches_name_variants():
    assert same_author("الإمام أبو جعفر الطبري", "ابن جرير الطبري")
    assert same_author("الإمام ابن كثير", "ابن كثير")
    assert same_author("الإمام أحمد بن حنبل", "أحمد بن حنبل")
    assert not same_author("الإمام ابن كثير", "محمد رشيد رضا")
    assert not same_author(None, "ابن كثير")


def _claim(text, draft, ctype, cited_ref=None):
    i = draft.index(text)
    return Claim(
        id="x",
        text=text,
        span=Span(start=i, end=i + len(text)),
        type=ctype,
        level=ContentLevel.A,
        hints=ClaimHints(cited_ref=cited_ref),
    )


def test_single_word_echo_of_quoted_verse_is_not_a_claim():
    draft = "قال تعالى: ﴿ وَمَا آتَاكُمُ الرَّسُولُ فَخُذُوهُ ﴾ [الحشر: 7]. تأملوا: ﴿ فَخُذُوهُ ﴾، أي: تلقوه."
    full = _claim("وَمَا آتَاكُمُ الرَّسُولُ فَخُذُوهُ", draft, ClaimType.QURAN_QUOTE, "[الحشر: 7]")
    one = _claim("فَخُذُوهُ ﴾،", draft, ClaimType.QURAN_QUOTE)
    one = one.model_copy(update={"text": "فَخُذُوهُ"})
    kept = _drop_noise(draft, [full, one])
    assert [c.text for c in kept] == [full.text]


def test_book_title_inside_citation_is_not_a_hadith():
    draft = "قال أحمد: «السنة تفسر القرآن»؛ [ابن أبي يعلى، «طبقات الحنابلة»، المجلد الأول، ص 241]."
    book = _claim("طبقات الحنابلة", draft, ClaimType.HADITH_QUOTE)
    assert _drop_noise(draft, [book]) == []
    short = "قال رسول الله ﷺ: «تهادوا تحابوا»."
    hadith = _claim("تهادوا تحابوا", short, ClaimType.HADITH_QUOTE)
    assert _drop_noise(short, [hadith]) == [hadith]


def test_dorar_link_has_no_diacritics_or_punctuation():
    url = DorarLinker.hadith_search_url(None, "«وَإِذَا رَأَى مَا يَكْرَهُ فَلْيَتَعَوَّذْ بِاللَّهِ مِنْ شَرِّهَا»")
    assert unquote(url).endswith("q=وإذا رأى ما يكره فليتعوذ بالله")
