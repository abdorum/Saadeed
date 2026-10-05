"""مولّدات الحالات البرمجية (البروتوكول §٣.١): التصنيف مضمون رياضيًا لأننا صنعنا العيب بأنفسنا من نص المصدر.

الآيات: Q1–Q6 من مصحف Tanzil. والأحاديث: H1، H2، H5 من الصحيحين، وH8a من السنن الأربع.
كل اختيار ببذرة ثابتة (70)، فالبنك نفسه يُعاد بناؤه حرفيًا.
"""

from __future__ import annotations

import random
import re

from saadeed.adapters.eval.bank import CRITICAL, TestCase, expected_for
from saadeed.adapters.factory import Engine
from saadeed.domain.quran_meta import SURA_NAMES
from saadeed.text.normalize import normalize, strip_diacritics

SEED = 70
# كلمات شائعة للاستبدال في Q3 (يُشترط ألّا تكون الكلمة الأصلية نفسها).
COMMON_WORDS = [
    "الناس",
    "الحق",
    "الخير",
    "قلوبهم",
    "عظيم",
    "كريم",
    "الأرض",
    "الدنيا",
    "يعملون",
    "رحيم",
    "أنفسهم",
    "الصالحات",
]


def _case(cat: str, n: int, surface: str, claim: str, **meta) -> TestCase:
    return TestCase(
        case_id=f"{cat}-{n:02d}",
        category=cat,
        critical=cat in CRITICAL,
        surface=surface,
        claim_text=claim,
        expected=expected_for(cat),
        label_source="generated",
        meta=meta,
    )


def _quran_surface(
    text: str, sura: int, aya: int, with_ref: bool, ref_override: str | None = None
) -> tuple[str, str]:
    ref = ref_override or f"{SURA_NAMES[sura - 1]}: {aya}"
    surface = f"قال الله تعالى: ﴿{text}﴾" + (f" [{ref}]." if with_ref else ".")
    return surface, text


def quran_cases(engine: Engine, per_cat: int = 10) -> list[TestCase]:
    rng = random.Random(SEED)
    repo = engine.sources.quran
    idx = engine.quran.index
    ayat = [a for a in repo.all_ayat() if 7 <= len(a.text_simple.split()) <= 18]
    # نختار آيات لا يتكرر نصها في المصحف، حتى يكون التصنيف قاطعًا.
    unique = []
    for a in ayat:
        q = [w for w in normalize(a.text_simple).split()]
        if len(idx.anchors(q)) == 1:
            unique.append(a)
    rng.shuffle(unique)
    pool = iter(unique)
    out: list[TestCase] = []

    for i in range(per_cat):  # Q1
        a = next(pool)
        s, c = _quran_surface(a.text_simple, a.sura, a.aya, with_ref=i % 2 == 0)
        out.append(_case("Q1", i + 1, s, c, ref=f"{a.sura}:{a.aya}"))
    for i in range(per_cat):  # Q2: بلا تشكيل أو بتشكيل ناقص
        a = next(pool)
        txt = strip_diacritics(a.text_simple)
        s, c = _quran_surface(txt, a.sura, a.aya, with_ref=i % 2 == 1)
        out.append(_case("Q2", i + 1, s, c, ref=f"{a.sura}:{a.aya}"))
    for i in range(per_cat):  # Q3: كلمة مبدلة
        a = next(pool)
        words = strip_diacritics(a.text_simple).split()
        k = rng.randrange(1, len(words) - 1)
        repl = next(
            w
            for w in rng.sample(COMMON_WORDS, len(COMMON_WORDS))
            if normalize(w) != normalize(words[k])
        )
        mutated = " ".join(words[:k] + [repl] + words[k + 1 :])
        s, c = _quran_surface(mutated, a.sura, a.aya, with_ref=i % 2 == 0)
        out.append(_case("Q3", i + 1, s, c, ref=f"{a.sura}:{a.aya}", changed=f"{words[k]}→{repl}"))
    for i in range(per_cat):  # Q4: كلمة ناقصة أو زائدة
        a = next(pool)
        words = strip_diacritics(a.text_simple).split()
        k = rng.randrange(1, len(words) - 1)
        if i % 2 == 0:
            mutated = " ".join(words[:k] + words[k + 1 :])
            change = f"حذف {words[k]}"
        else:
            extra = rng.choice(["حقا", "جميعا", "دائما", "كلهم"])
            mutated = " ".join(words[:k] + [extra] + words[k:])
            change = f"زيادة {extra}"
        s, c = _quran_surface(mutated, a.sura, a.aya, with_ref=False)
        out.append(_case("Q4", i + 1, s, c, ref=f"{a.sura}:{a.aya}", changed=change))
    for i in range(per_cat):  # Q5: ترتيب مقلوب
        a = next(pool)
        words = strip_diacritics(a.text_simple).split()
        k = rng.randrange(1, len(words) - 2)
        while normalize(words[k]) == normalize(words[k + 1]):
            k = (k + 1) % (len(words) - 2) or 1
        words[k], words[k + 1] = words[k + 1], words[k]
        s, c = _quran_surface(" ".join(words), a.sura, a.aya, with_ref=i % 2 == 1)
        out.append(
            _case("Q5", i + 1, s, c, ref=f"{a.sura}:{a.aya}", changed=f"تبديل الكلمتين {k}/{k + 1}")
        )
    for i in range(per_cat):  # Q6: نص صحيح بإحالة خاطئة
        a = next(pool)
        wrong_sura = (a.sura % 114) + 1 if i % 2 == 0 else a.sura
        wrong_aya = a.aya if wrong_sura != a.sura else a.aya + 3
        ref = f"{SURA_NAMES[wrong_sura - 1]}: {wrong_aya}"
        s, c = _quran_surface(
            strip_diacritics(a.text_simple), a.sura, a.aya, with_ref=True, ref_override=ref
        )
        out.append(_case("Q6", i + 1, s, c, ref=f"{a.sura}:{a.aya}", cited=ref))
    return out


_SAID = re.compile(r"صلى الله عليه وسلم\s+(?:قال|يقول)\s+")
_NARRATION = {
    normalize(w)
    for w in (
        "حدثنا",
        "أخبرنا",
        "حدثني",
        "أخبرني",
        "عن",
        "رضي",
        "قالت",
        "فقال",
        "قال",
        "سمعت",
        "يعني",
        "حديث",
        "بهذا",
        "الإسناد",
        "نحوه",
        "مثله",
    )
}


def _matn(plain: str, n_words: int) -> str | None:
    """قول النبي ﷺ: الكلمات بعد «صلى الله عليه وسلم قال/يقول»، بلا كلام الرواة."""
    if len(plain) > 700:  # الأحاديث القصيرة أغلبها أقوال خالصة
        return None
    ms = list(_SAID.finditer(plain))
    if not ms:
        return None
    words = [w for w in plain[ms[-1].end() :].split() if any(ch.isalpha() for ch in w)]
    if len(words) < n_words + 1:
        return None
    frag = words[:n_words]
    if (
        any(
            normalize(w) in _NARRATION or normalize(w).lstrip("وف").startswith(("حدث", "اخبر"))
            for w in frag
        )
        or "صلى" in frag
        or "قوله" in frag
    ):
        return None
    return " ".join(frag).strip(" ،,.")


BOOK_TAKHRIJ = {"bukhari": "رواه البخاري", "muslim": "رواه مسلم"}


def hadith_cases(engine: Engine, per_cat: int = 8) -> list[TestCase]:
    rng = random.Random(SEED + 2)
    hidx = engine.hadith.index
    out: list[TestCase] = []

    def pick(sources: set[str], n_words: int, tries: int = 30000):
        docs = [d for d in hidx.docs if d.source_id in sources]
        rng.shuffle(docs)
        for d in docs[:tries]:
            p = hidx.sources[d.source_id].get(d.item_id)
            m = _matn(p.text_plain, n_words) if p else None
            if not m or len(hidx.exact_hits(normalize(m))) == 0:
                continue
            yield d, m

    gen = pick({"bukhari", "muslim"}, 10)
    for i in range(per_cat):  # H1: بلفظه مع نسبة صحيحة أو بلا نسبة
        d, m = next(gen)
        tak = f" {BOOK_TAKHRIJ[d.source_id]}." if i % 2 == 0 else "."
        surface = f"وقال رسول الله ﷺ: «{m}»{tak}"
        out.append(_case("H1", i + 1, surface, m, source=f"{d.source_id}:{d.item_id}"))
    gen2 = pick({"bukhari", "muslim"}, 6)
    for i in range(per_cat):  # H2: جزء من حديث
        d, m = next(gen2)
        surface = f"وفي الحديث أن النبي ﷺ قال: «{m}»."
        out.append(_case("H2", i + 1, surface, m, source=f"{d.source_id}:{d.item_id}"))
    gen3 = pick({"bukhari", "muslim"}, 10)
    made = 0
    for d, m in gen3:  # H5: منسوب إلى غير كتابه
        other = "muslim" if d.source_id == "bukhari" else "bukhari"
        if hidx.book_contains(other, normalize(m)):
            continue
        made += 1
        surface = f"وقال رسول الله ﷺ: «{m}» {BOOK_TAKHRIJ[other]}."
        out.append(_case("H5", made, surface, m, source=f"{d.source_id}:{d.item_id}", cited=other))
        if made == per_cat:
            break
    gen4 = pick({"abudawud", "tirmidhi", "nasai", "ibnmajah"}, 10)
    made = 0
    for d, m in gen4:  # H8a: في السنن الأربع وحدها
        q = normalize(m)
        if hidx.book_contains("bukhari", q) or hidx.book_contains("muslim", q):
            continue
        made += 1
        surface = f"وقد قال النبي ﷺ: «{m}»."
        out.append(_case("H8a", made, surface, m, source=f"{d.source_id}:{d.item_id}"))
        if made == per_cat:
            break
    return out


def quran_v25_cases(engine: Engine, per_cat: int = 8) -> list[TestCase]:
    """Q8 (آية نُسبت حديثًا) وQ9 (آيتان مدموجتان) — البروتوكول §١٢ بند 9.

    ببذرة مستقلة (70 + 25) حتى لا تتأثر حالات v1. ونختار مقاطع نصها فريد في المصحف،
    ولا يوجد حرفيًا في كتب الحديث (فلا تكون آية رواها النبي ﷺ في حديث)."""
    from saadeed.text.align import rasm_key

    rng = random.Random(SEED + 25)
    repo = engine.sources.quran
    idx = engine.quran.index
    hadith = engine.hadith.index

    def unique_ayah(a) -> str | None:
        """آية كاملة قصيرة (طبيعية في الخطبة)، نصها فريد في المصحف وليس في كتب الحديث."""
        norm = normalize(a.text_simple)
        keys = [rasm_key(w) for w in norm.split()]
        if len(idx.occurrences(keys)) != 1 or hadith.exact_hits(norm):
            return None
        return strip_diacritics(a.text_simple)

    q8_pool = [a for a in repo.all_ayat() if 5 <= len(a.text_simple.split()) <= 12]
    q9_pool = [a for a in repo.all_ayat() if 4 <= len(a.text_simple.split()) <= 8]
    rng.shuffle(q8_pool)
    rng.shuffle(q9_pool)
    out: list[TestCase] = []
    i = 0
    for a in q8_pool:  # Q8
        if i >= per_cat:
            break
        t = unique_ayah(a)
        if t is None:
            continue
        i += 1
        s = f"قال رسول الله صلى الله عليه وسلم: «{t}»."
        out.append(_case("Q8", i, s, t, ref=f"{a.sura}:{a.aya}"))
    i = 0
    it = iter(q9_pool)
    for a in it:  # Q9
        if i >= per_cat:
            break
        b = next(it, None)
        if b is None or b.sura == a.sura:
            continue
        t1, t2 = unique_ayah(a), unique_ayah(b)
        if t1 is None or t2 is None:
            continue
        i += 1
        merged = f"{t1} {t2}"
        s = f"قال الله تعالى: ﴿{merged}﴾."
        out.append(_case("Q9", i, s, merged, ref=f"{a.sura}:{a.aya}+{b.sura}:{b.aya}"))
    return out
