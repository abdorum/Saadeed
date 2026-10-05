"""محوّل المصحف من ملفات Tanzil كما نُزّلت (CC BY 3.0، دون تعديل).

الملف لا يُعدَّل. والبسملة التي يضيفها Tanzil في أول الآية الأولى من كل سورة (عدا الفاتحة والتوبة)
تُفصل عند التحميل في الذاكرة فقط، لأنها ليست من الآية في عدّ مصحف المدينة.
"""

from __future__ import annotations

from pathlib import Path

from saadeed.domain.enums import SourceRole
from saadeed.domain.ports import Ayah, SourceInfo
from saadeed.domain.quran_meta import AYA_COUNTS, sura_name
from saadeed.text.normalize import normalize

_BASMALA_WORDS = 4


def _read(path: Path) -> dict[tuple[int, int], str]:
    out: dict[tuple[int, int], str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        s, a, text = line.split("|", 2)
        out[(int(s), int(a))] = text.strip()
    return out


def _strip_basmala(sura: int, aya: int, text: str) -> str:
    if aya != 1 or sura in (1, 9):
        return text
    words = text.split()
    # بالتطبيع لا بالحروف: في التين والقدر تأتي «بِّسْمِ» بشدة (كشفته المطابقة بالموسوعة القرآنية، v2.5).
    if len(words) > _BASMALA_WORDS and normalize(" ".join(words[:2])) == "بسم الله":
        return " ".join(words[_BASMALA_WORDS:])
    return text


class TanzilQuranRepo:
    def __init__(self, simple_path: Path, uthmani_path: Path, version: str = "Tanzil 1.1") -> None:
        simple = _read(simple_path)
        uthmani = _read(uthmani_path)
        if len(simple) != 6236 or len(uthmani) != 6236:
            raise ValueError(f"عدد الآيات غير صحيح: {len(simple)} / {len(uthmani)}")
        self._ayat: dict[tuple[int, int], Ayah] = {}
        for (s, a), text in simple.items():
            self._ayat[(s, a)] = Ayah(
                sura=s,
                aya=a,
                sura_name=sura_name(s),
                text_simple=_strip_basmala(s, a, text),
                text_uthmani=_strip_basmala(s, a, uthmani[(s, a)]),
            )
        for s, count in enumerate(AYA_COUNTS, start=1):
            if (s, count) not in self._ayat:
                raise ValueError(f"السورة {s} ناقصة")
        self._info = SourceInfo(
            id="quran",
            name_ar="المصحف (مصحف المدينة، رواية حفص عن عاصم)",
            role=SourceRole.REFERENCE_TEXT,
            count=6236,
            version=version,
            license="CC BY 3.0, verbatim (tanzil.net)",
        )

    @property
    def info(self) -> SourceInfo:
        return self._info

    def all_ayat(self) -> list[Ayah]:
        return [self._ayat[k] for k in sorted(self._ayat)]

    def get(self, sura: int, aya: int) -> Ayah | None:
        return self._ayat.get((sura, aya))

    def sura_names(self) -> dict[int, str]:
        return {s: sura_name(s) for s in range(1, 115)}

    def ayah_url(self, sura: int, aya: int) -> str:
        return f"https://tanzil.net/#{sura}:{aya}"
