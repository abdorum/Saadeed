"""محوّل قائمة «المشتهر الذي لا يصح» (ملف JSON يعتمده محمد)."""

from __future__ import annotations

import json
from pathlib import Path

from saadeed.domain.ports import KnownWeak, SourceInfo


class JsonKnownWeakRepo:
    def __init__(self, info: SourceInfo, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        self._items = {d["id"]: KnownWeak(**d) for d in data["items"]}
        verified = sum(1 for k in self._items.values() if k.verified)
        status = (
            "approved"
            if verified == len(self._items)
            else f"draft ({verified}/{len(self._items)} معتمد)"
        )
        self._info = info.model_copy(update={"count": len(self._items), "review_status": status})

    @property
    def info(self) -> SourceInfo:
        return self._info

    def all(self) -> list[KnownWeak]:
        return list(self._items.values())

    def get(self, item_id: str) -> KnownWeak | None:
        return self._items.get(item_id)


class DorarLinker:
    """رابط بحث في الدرر السنية. لا استدعاء آلي (Q-02)."""

    def hadith_search_url(self, text: str) -> str:
        from urllib.parse import quote

        words = text.split()
        snippet = " ".join(words[:8])
        return f"https://dorar.net/hadith/search?q={quote(snippet)}"
