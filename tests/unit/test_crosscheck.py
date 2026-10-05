"""الفحص المتقاطع وقرائن المتن والبديل الثابت (ADR-0014، v2.5). حتمي، بلا نموذج."""

from saadeed.adapters.llm.fake import FakeLLM
from saadeed.domain.enums import ClaimType, EvidenceStatus, Severity
from saadeed.domain.policy import Signal
from saadeed.text.matn_signs import matn_signs
from tests.conftest import needs_data

pytestmark = needs_data


def _review(engine, text, claims=None):
    def scripted(system, user):
        if "الاستخراج" in system:
            return {"claims": claims or []}
        return {"items": []}

    return engine.reviewer(FakeLLM(scripted)).review(text)


def _by_rule(report):
    return {f.rule_id: f for f in report.findings}


def test_verse_attributed_to_prophet(engine):
    r = _review(engine, "قال رسول الله ﷺ: «إن الله مع الصابرين».")
    f = _by_rule(r)["BR-22"]
    assert f.claim.type is ClaimType.QURAN_QUOTE
    assert f.claim.hints.presented_as is ClaimType.HADITH_QUOTE
    assert f.evidence[0].ref.source_id == "quran"


def test_verse_mislabeled_as_generalization_is_split(engine):
    text = "واعلموا أن إن الإنسان لفي خسر إلا الذين آمنوا وعملوا الصالحات، فكل من ترك العمل خاسر."
    claims = [
        {
            "s": 0,
            "quote": "إن الإنسان لفي خسر إلا الذين آمنوا وعملوا الصالحات، فكل من ترك العمل خاسر",
            "type": "GENERALIZATION",
            "level": "B",
        }
    ]
    r = _review(engine, text, claims)
    rules = _by_rule(r)
    verse = rules["BR-01"]
    assert verse.claim.text.endswith("الصالحات")  # بلا الفاصلة
    assert "العصر" in verse.evidence[0].ref.citation
    gen = rules["BR-15"]
    assert gen.claim.text == "فكل من ترك العمل خاسر"


def test_unmarked_verse_found_without_llm(engine):
    text = "ومن أعظم ما يعين على ذلك أن تتذكر قول ربك يا أيها الذين آمنوا اتقوا الله وقولوا قولا سديدا ثم تعمل."
    r = engine.reviewer(None).review(text)
    f = _by_rule(r)["BR-01"]
    assert f.claim.origin == "crosscheck"
    assert "الأحزاب" in f.evidence[0].ref.citation


def test_merged_verses(engine):
    from saadeed.verifiers.quran import QuranVerifier  # noqa: F401

    out = engine.reviewer(None).quran.verify("ومن يتوكل على الله فهو حسبه إن الله يحب المتوكلين")
    assert out.signal is Signal.QURAN_MERGED
    cits = [e.ref.citation for e in out.evidence]
    assert any("الطلاق" in c for c in cits) and any("آل عمران" in c for c in cits)


def test_single_wrong_word_is_mismatch_not_merge(engine):
    out = engine.reviewer(None).quran.verify("يا أيها الذين آمنوا اتقوا الله وقولوا قولا حسنا")
    assert out.signal is Signal.QURAN_TEXT_MISMATCH


def test_hadith_presented_as_verse_points_to_hadith(engine):
    r = _review(engine, "قال تعالى: «إنما الأعمال بالنيات».")
    f = _by_rule(r)["BR-04"]
    assert "حديثًا" in f.explanation
    assert any(e.ref.source_id in ("bukhari", "muslim") for e in f.evidence)


def test_known_weak_offers_authentic_alternative(engine):
    r = _review(engine, "قال رسول الله ﷺ: «النظافة من الإيمان».")
    f = _by_rule(r)["BR-05"]
    alt = [e for e in f.evidence if e.ref.source_id == "muslim"]
    assert alt and alt[0].highlight
    assert "ثبت في صحيح مسلم" in f.explanation


def test_matn_signs_raise_severity_only():
    assert matn_signs("من قرأ سورة الكهف يوم الأربعاء غفر له ذنب أربعين سنة")
    assert matn_signs("من صلى الضحى أعطي ثواب سبعين نبيا")
    assert not matn_signs("من قرأ سورة الكهف يوم الجمعة أضاء له من النور ما بين الجمعتين")
    assert not matn_signs("من صام رمضان إيمانا واحتسابا غفر له ما تقدم من ذنبه")


def test_not_found_with_signs_is_critical_but_still_not_found(engine):
    hv = engine.reviewer(None).hadith
    out = hv.not_found("من قرأ سورة الكهف يوم الأربعاء غفر له ذنب أربعين سنة")
    assert out.signal is Signal.HADITH_NOT_FOUND_WITH_SIGNS
    from saadeed.domain.policy import apply

    rule = apply(out.signal)
    assert rule.status is EvidenceStatus.NOT_FOUND and rule.severity is Severity.CRITICAL


def test_hadith_quoting_a_verse_stays_hadith(engine):
    # حديث يتضمن آية قصيرة: لا يُعاد تصنيفه آية
    text = "قال رسول الله ﷺ: «ما من مسلم تصيبه مصيبة فيقول ما أمره الله إنا لله وإنا إليه راجعون اللهم أجرني في مصيبتي وأخلف لي خيرا منها إلا أخلف الله له خيرا منها»."
    r = _review(engine, text)
    assert any(f.claim.type is ClaimType.HADITH_QUOTE for f in r.findings)
    assert not any(f.rule_id == "BR-22" for f in r.findings)


def test_suggestion_guard_rejects_sharia_text_and_numbers(engine):
    from saadeed.application.suggestion_guard import safe_suggestion

    rev = engine.reviewer(None)
    q, h = rev.quran.index, rev.hadith.index
    orig = "كل الناس اليوم لا يقرؤون"
    assert safe_suggestion("كثير من الناس اليوم لا يقرؤون", orig, q, h)
    assert safe_suggestion("قال تعالى إن الله مع الصابرين", orig, q, h) is None
    assert safe_suggestion("«كثير من الناس» لا يقرؤون", orig, q, h) is None
    assert safe_suggestion("90% من الناس لا يقرؤون", orig, q, h) is None
    assert safe_suggestion("يا أيها الذين آمنوا اتقوا الله", orig, q, h) is None
    assert safe_suggestion(orig, orig, q, h) is None
    assert safe_suggestion(
        "في هذه النهاية كثير من الناس لا يقرؤون", orig, q, h
    )  # «نهاية» ليست «آية»


def test_draft_map_and_guarded_suggestion(engine):
    text = (
        "الحمد لله. قال تعالى: ﴿إن الله مع الصابرين﴾. وكل الشباب اليوم لا يصلون الفجر. اللهم اهدنا."
    )

    def scripted(system, user):
        if "الاستخراج" in system:
            return {
                "claims": [
                    {
                        "s": 2,
                        "quote": "وكل الشباب اليوم لا يصلون الفجر",
                        "type": "GENERALIZATION",
                        "level": "B",
                        "rephrase": "وكثير من الشباب اليوم يفرّطون في صلاة الفجر",
                    }
                ],
                "map": [[0, "OTHER"], [1, "EXHORTATION"], [2, "FACT"], [3, "DUA"], [99, "QURAN"]],
            }
        return {"items": []}

    r = engine.reviewer(FakeLLM(scripted)).review(text)
    kinds = [e.kind.value for e in r.draft_map]
    assert kinds == ["OTHER", "QURAN", "FACT", "DUA"]  # الآية من الفحص لا من تصنيف النموذج
    assert r.draft_map[1].kind_source == "evidence"
    gen = next(f for f in r.findings if f.rule_id == "BR-15")
    assert gen.suggestion == "وكثير من الشباب اليوم يفرّطون في صلاة الفجر"
    assert gen.explanation and "مولَّد" not in gen.explanation  # الشرح من القالب


def test_light_stem_joins_verb_and_pronoun_forms():
    from saadeed.text.normalize import normalize
    from saadeed.text.stem import light_stem

    assert light_stem(normalize("ويعلمه")) == light_stem(normalize("وعلمه"))
    assert light_stem(normalize("يتعلم")) == light_stem(normalize("تعلم"))
    assert light_stem(normalize("القرآن")) == light_stem(normalize("قرآن"))
    assert light_stem("من") == "من"  # القصير لا يُمس


def test_paraphrase_reaches_bukhari_candidate(engine):
    # E-004: «أفضل الناس من يتعلم القرآن ويعلمه غيره» ← البخاري «إن أفضلكم من تعلم القرآن وعلمه»
    from saadeed.text.normalize import normalize

    hv = engine.reviewer(None).hadith
    pool = hv._candidate_pool(normalize("أفضل الناس من يتعلم القرآن ويعلمه غيره"))
    first = hv.index.docs[pool[0][0]]
    assert first.source_id == "bukhari"
    assert "تعلم القران وعلمه" in first.norm
