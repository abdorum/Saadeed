"""بناء البيانات: تنزيل المصادر الخام، ومعالجتها، وحساب بصماتها (المعمارية §١٠).

`saadeed data build` يعيد بناء كل شيء من الصفر، فلا تُرفع الملفات الكبيرة إلى المستودع.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

from saadeed.adapters.sources.open_hadith import BOOK_FILES, build_book

TANZIL_URL = "https://tanzil.net/pub/download/index.php?quranType={kind}&outType=txt-2&agree=true"
OHD_URL = (
    "https://raw.githubusercontent.com/mhashim6/Open-Hadith-Data/master/{folder}/{stem}{suffix}"
)
OHD_FOLDERS = {
    "bukhari": "Sahih_Al-Bukhari",
    "muslim": "Sahih_Muslim",
    "abudawud": "Sunan_Abu-Dawud",
    "tirmidhi": "Sunan_Al-Tirmidhi",
    "nasai": "Sunan_Al-Nasai",
    "ibnmajah": "Sunan_Ibn-Maja",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "saadeed-data-build/0.1"})
    with urllib.request.urlopen(req, timeout=300) as r, dest.open("wb") as f:
        f.write(r.read())


def fetch_raw(data_dir: Path, force: bool = False) -> list[str]:
    done: list[str] = []
    for kind in ("simple", "uthmani"):
        dest = data_dir / "raw" / "tanzil" / f"quran-{kind}.txt"
        if force or not dest.exists():
            _download(TANZIL_URL.format(kind=kind), dest)
            done.append(str(dest))
    # وصلة الموسوعة القرآنية (المسمّاة في الحزمة): ملفان صغيران، ليكون التبديل إليها سطرًا في ملف المرجعية.
    from saadeed.adapters.sources.quranpedia import DUMPS_URL, FILES

    for name in FILES:
        # النسخة مثبّتة في المستودع (data/vendor) لإعادة الإنتاج، ولا تُنزَّل إلا إن غابت.
        dest = data_dir / "vendor" / "quranpedia" / name
        if force or not dest.exists():
            _download(DUMPS_URL.format(name=name), dest)
            done.append(str(dest))
    for book, stem in BOOK_FILES.items():
        for suffix in ("_ahadith.utf8.csv", "_ahadith_mushakkala_mufassala.utf8.csv"):
            dest = data_dir / "raw" / "open_hadith" / f"{stem}{suffix}"
            if force or not dest.exists():
                _download(OHD_URL.format(folder=OHD_FOLDERS[book], stem=stem, suffix=suffix), dest)
                done.append(str(dest))
    return done


def build_processed(data_dir: Path) -> dict[str, tuple[int, str]]:
    """يبني ملفات الكتب المعالجة، ويعيد لكل ملف عدده وبصمته."""
    out: dict[str, tuple[int, str]] = {}
    raw = data_dir / "raw" / "open_hadith"
    for book in BOOK_FILES:
        dest = data_dir / "processed" / f"{book}.json"
        n = build_book(raw, book, dest)
        out[book] = (n, sha256_file(dest))
    for kind in ("simple", "uthmani"):
        p = data_dir / "raw" / "tanzil" / f"quran-{kind}.txt"
        out[f"quran-{kind}"] = (6236, sha256_file(p))
    return out
