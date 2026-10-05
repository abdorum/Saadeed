"""وصلة الموسوعة القرآنية (quranpedia.net): المصدر الذي تسمّيه الحزمة العلمية للمسابقة للقرآن.

- **للبحث والمطابقة:** «مصحف حفص» (`mushafs-1`)، موافق لطبعة مجمع الملك فهد، بالرسم الإملائي المشكول.
- **للعرض:** «مصحف حفص نسخة نصية» (`mushafs-2`)، بالرسم العثماني من إصدار مجمع الملك فهد.
- **الرخصة** (من ملف الموسوعة): الاستعمال داخل التطبيقات وأدوات البحث مجاني بلا شرط نسبة،
  وإعادة النشر قاعدةَ بيانات تتطلب ذكر المصدر. ونحن لا نعيد نشرها، ونذكرها مع ذلك.
- **ينفّذ منفذ `QuranRepo` نفسه** الذي ينفّذه محوّل Tanzil، فالتبديل بينهما سطر في ملف المرجعية.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from saadeed.domain.enums import SourceRole
from saadeed.domain.ports import Ayah, SourceInfo
from saadeed.domain.quran_meta import AYA_COUNTS, sura_name

DUMPS_URL = "https://quranpedia.net/dumps/{name}"
FILES = ("mushafs-1.json.gz", "mushafs-2.json.gz")
_BOM = chr(0xFEFF)  # بعض الآيات في الملف تبدأ بعلامة ترتيب البايت


def _read(path: Path) -> dict[tuple[int, int], str]:
    data = json.loads(gzip.decompress(path.read_bytes()))
    out: dict[tuple[int, int], str] = {}
    for s in data["data"]["surahs"]:
        for a in s["ayahs"]:
            out[(int(s["id"]), int(a["number"]))] = a["text"].replace(_BOM, "").strip()
    return out


class QuranpediaQuranRepo:
    def __init__(
        self, simple_path: Path, uthmani_path: Path, version: str = "quranpedia.net"
    ) -> None:
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
                text_simple=text,
                text_uthmani=uthmani[(s, a)],
            )
        for s, count in enumerate(AYA_COUNTS, start=1):
            if (s, count) not in self._ayat:
                raise ValueError(f"السورة {s} ناقصة")
        self._info = SourceInfo(
            id="quran",
            name_ar="المصحف (الموسوعة القرآنية، رواية حفص، موافق لطبعة مجمع الملك فهد)",
            role=SourceRole.REFERENCE_TEXT,
            count=6236,
            version=version,
            license="quranpedia.net — استعمال حر داخل التطبيقات، مع ذكر المصدر",
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
        return f"https://quranpedia.net/ayahs/{sura}/{aya}"
