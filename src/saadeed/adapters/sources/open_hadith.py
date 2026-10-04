"""محوّل كتب الحديث من Open-Hadith-Data (ODbL 1.0)، كتاب لكل مثيل (ADR-0010).

الدور (احتجاج أو موضع) لا يقرره المحوّل، بل ملف المرجعية.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from saadeed.domain.ports import Passage, SourceInfo
from saadeed.text.normalize import normalize

csv.field_size_limit(10**9)

# أسماء الملفات في Open-Hadith-Data لكل كتاب
BOOK_FILES: dict[str, str] = {
    "bukhari": "sahih_al-bukhari",
    "muslim": "sahih_muslim",
    "abudawud": "sunan_abu-dawud",
    "tirmidhi": "sunan_al-tirmidhi",
    "nasai": "sunan_al-nasai",
    "ibnmajah": "sunan_ibn-maja",
}
BOOK_NAMES_AR: dict[str, str] = {
    "bukhari": "صحيح البخاري",
    "muslim": "صحيح مسلم",
    "abudawud": "سنن أبي داود",
    "tirmidhi": "جامع الترمذي",
    "nasai": "سنن النسائي",
    "ibnmajah": "سنن ابن ماجه",
}

_MARKS = re.compile("[‎‏‪-‮]")
_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WS.sub(" ", _MARKS.sub("", text)).strip()


def build_book(raw_dir: Path, book_id: str, out_path: Path) -> int:
    """يبني ملف الكتاب المعالج من الملفين الخام: المشكول (للعرض) وغير المشكول (للبحث)."""
    stem = BOOK_FILES[book_id]
    plain_rows = list(csv.reader((raw_dir / f"{stem}_ahadith.utf8.csv").open(encoding="utf-8")))
    disp_rows = list(
        csv.reader(
            (raw_dir / f"{stem}_ahadith_mushakkala_mufassala.utf8.csv").open(encoding="utf-8")
        )
    )
    if [r[0] for r in plain_rows] != [r[0] for r in disp_rows]:
        raise ValueError(f"{book_id}: المعرّفات لا تتطابق بين النسختين")
    items = [
        {
            "id": p[0],
            "n": p[0],
            "display": _clean(d[1]),
            "plain": _clean(p[1]),
            "norm": normalize(p[1]),
        }
        for p, d in zip(plain_rows, disp_rows, strict=True)
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return len(items)


class OpenHadithSource:
    def __init__(self, info: SourceInfo, path: Path) -> None:
        self._info = info
        data = json.loads(path.read_text(encoding="utf-8"))
        self._items = {
            str(d["id"]): Passage(
                source_id=info.id,
                item_id=str(d["id"]),
                number=str(d["n"]),
                text_display=d["display"],
                text_plain=d["plain"],
                text_norm=d.get("norm"),
            )
            for d in data
        }
        self._info = info.model_copy(update={"count": len(self._items)})

    @property
    def info(self) -> SourceInfo:
        return self._info

    def all_passages(self) -> list[Passage]:
        return list(self._items.values())

    def get(self, item_id: str) -> Passage | None:
        return self._items.get(item_id)
