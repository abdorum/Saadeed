"""عقد وصلات المصحف (ADR-0015): Tanzil والموسوعة القرآنية تنفّذان المنفذ نفسه، ونصّاهما متكافئان.

التبديل بينهما سطر في ملف المرجعية، وهذا الاختبار يثبت أن التبديل لا يغيّر الحكم إلا في الفروق المعلنة.
"""

from pathlib import Path

import pytest

from saadeed.text.normalize import normalize

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
TANZIL = (RAW / "tanzil" / "quran-simple.txt", RAW / "tanzil" / "quran-uthmani.txt")
VENDOR = ROOT / "data" / "vendor" / "quranpedia"
QURANPEDIA = (VENDOR / "mushafs-1.json.gz", VENDOR / "mushafs-2.json.gz")

pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in (*TANZIL, *QURANPEDIA)),
    reason="البيانات غير مبنية: saadeed data build",
)

# الفروق الثمانية المعلنة (docs/research/quran-text-check.md): 3 فصل ووصل، و3 إملائية، و2 بسملة.
KNOWN_DIFFS = {(2, 181), (8, 6), (13, 37), (5, 31), (17, 32), (39, 56)}


def _repos():
    from saadeed.adapters.sources.quranpedia import QuranpediaQuranRepo
    from saadeed.adapters.sources.tanzil import TanzilQuranRepo

    return TanzilQuranRepo(*TANZIL), QuranpediaQuranRepo(*QURANPEDIA)


def test_both_connectors_implement_the_port_with_6236_ayat():
    for repo in _repos():
        ayat = repo.all_ayat()
        assert len(ayat) == 6236
        assert repo.get(2, 255) is not None and repo.get(114, 6) is not None
        assert repo.sura_names()[1]
        assert repo.ayah_url(2, 255).startswith("https://")


def test_texts_are_equivalent_except_declared_differences():
    t, q = _repos()
    diffs = {
        (a.sura, a.aya)
        for a in t.all_ayat()
        if normalize(a.text_simple).split() != normalize(q.get(a.sura, a.aya).text_simple).split()
    }
    assert diffs <= KNOWN_DIFFS, f"فروق غير معلنة: {sorted(diffs - KNOWN_DIFFS)}"


def test_basmala_is_not_glued_to_first_ayah():
    for repo in _repos():
        assert normalize(repo.get(95, 1).text_simple) == "والتين والزيتون"
        assert normalize(repo.get(97, 1).text_simple).startswith("انا انزلناه")
