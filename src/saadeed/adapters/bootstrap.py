"""جذر التركيب (Composition Root): هنا فقط تُربط المحوّلات بالنواة.

يقرأ ملف المرجعية، ويبني محوّلًا لكل مصدر بدوره المعلن، ويختار محوّل النموذج من الإعداد.
تبديل Groq بـ Gemini = تغيير متغير بيئة واحد (SAADEED_LLM_PROVIDER).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saadeed.adapters.sources.known_weak import DorarLinker, JsonKnownWeakRepo
from saadeed.adapters.sources.open_hadith import OpenHadithSource
from saadeed.adapters.sources.quranpedia import QuranpediaQuranRepo
from saadeed.adapters.sources.tanzil import TanzilQuranRepo
from saadeed.application.manifest import SourceManifest, load_manifest
from saadeed.domain.enums import SourceRole
from saadeed.domain.models import Coverage, CoverageSource
from saadeed.domain.ports import SourceInfo

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.environ.get("SAADEED_DATA_DIR", ROOT / "data"))
PROMPTS_DIR = Path(os.environ.get("SAADEED_PROMPTS_DIR", ROOT / "prompts"))


def load_env(path: Path | None = None) -> None:
    """يقرأ `.env` إن وُجد (دون مكتبة إضافية). المتغيرات الموجودة في البيئة لها الأولوية."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class SourceBundle:
    manifest: SourceManifest
    quran: TanzilQuranRepo | QuranpediaQuranRepo
    hadith_sources: list[OpenHadithSource]
    known_weak: JsonKnownWeakRepo | None
    linker: DorarLinker

    @property
    def coverage(self) -> Coverage:
        infos: list[SourceInfo] = [self.quran.info, *(s.info for s in self.hadith_sources)]
        if self.known_weak:
            infos.append(self.known_weak.info)
        out = [
            CoverageSource(
                id=i.id,
                name_ar=i.name_ar,
                role=i.role,
                count=i.count,
                version=i.version,
                license=i.license,
                review_status=i.review_status,
            )
            for i in infos
        ]
        for e in self.manifest.by_role(SourceRole.LINK):
            out.append(
                CoverageSource(
                    id=e.id,
                    name_ar=e.name_ar,
                    role=e.role,
                    count=0,
                    version=e.version,
                    license=e.license,
                )
            )
        return Coverage(sources=out)


@lru_cache(maxsize=2)
def load_sources(data_dir: Path = DATA_DIR) -> SourceBundle:
    # ملف مرجعية بديل للتجربة دون تعديل الأصلي: SAADEED_MANIFEST=data/manifest.quranpedia.toml
    manifest = load_manifest(Path(os.environ.get("SAADEED_MANIFEST", data_dir / "manifest.toml")))
    quran: TanzilQuranRepo | QuranpediaQuranRepo | None = None
    hadith: list[OpenHadithSource] = []
    known_weak: JsonKnownWeakRepo | None = None
    for e in manifest.sources:
        info = SourceInfo(
            id=e.id, name_ar=e.name_ar, role=e.role, count=0, version=e.version, license=e.license
        )
        if e.adapter == "tanzil":
            quran = TanzilQuranRepo(data_dir / e.files[0], data_dir / e.files[1], version=e.version)
        elif e.adapter == "quranpedia":
            quran = QuranpediaQuranRepo(
                data_dir / e.files[0], data_dir / e.files[1], version=e.version
            )
        elif e.adapter == "open_hadith":
            if e.role not in (SourceRole.AUTHENTIC, SourceRole.LOCATE):
                raise ValueError(f"{e.id}: دور غير صالح لكتاب حديث: {e.role}")
            hadith.append(OpenHadithSource(info, data_dir / e.files[0]))
        elif e.adapter == "known_weak":
            known_weak = JsonKnownWeakRepo(info, data_dir / e.files[0])
        elif e.adapter == "dorar_link":
            continue
        else:
            raise ValueError(f"محوّل غير معروف في ملف المرجعية: {e.adapter}")
    if quran is None:
        raise ValueError("ملف المرجعية بلا مصحف")
    return SourceBundle(manifest, quran, hadith, known_weak, DorarLinker())
