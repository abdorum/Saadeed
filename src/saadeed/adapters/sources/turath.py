"""وصلة حية إلى مكتبة «تراث» (app.turath.io): بحث في نصوص الكتب وقت المراجعة.

للأقوال المنسوبة إلى العلماء (تفسير، فقه، عقيدة…) حيث لا يمكن تنزيل المكتبة كلها.
- البحث بعبارات متتابعة من القول نفسه («بين علامتي تنصيص» = عبارة حرفية)، ثم بكلماته إن لم تُطابق عبارة.
- النص المعروض للمستخدم هو نص الصفحة كما أعادته المكتبة، ويحفظه المحوّل لحارس الإسناد.
- لا يحكم بشيء: يعيد مواضع مرشحة فقط، والحكم للحَكَم ثم لجدول القواعد.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from saadeed.domain.ports import LibraryHit, Passage
from saadeed.text.normalize import strip_diacritics

API = "https://api.turath.io/search"
BOOK_URL = "https://app.turath.io/book/{book_id}?page={page_id}"
_TAG = re.compile(r"<[^>]+>")
_HEADERS = {"User-Agent": "Mozilla/5.0 (Saadeed pre-publication reviewer)"}


class TurathLibrary:
    source_id = "turath"
    name_ar = "مكتبة تراث (app.turath.io)"

    def __init__(self, timeout: float = 8.0, per_query: int = 5) -> None:
        self.timeout = timeout
        self.per_query = per_query
        self._seen: dict[str, LibraryHit] = {}

    # ── البحث ──
    def _query(self, q: str) -> list[LibraryHit]:
        url = API + "?" + urllib.parse.urlencode({"q": q})
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.load(r)
        hits: list[LibraryHit] = []
        for h in data.get("data", [])[: self.per_query]:
            try:
                m = json.loads(h.get("meta") or "{}")
            except ValueError:
                continue
            page_text = _TAG.sub("", h.get("text") or "").strip()
            snip = _TAG.sub("", h.get("snip") or "").strip()
            hit = LibraryHit(
                item_id=f"{h.get('book_id')}:{m.get('page_id')}",
                book_name=str(m.get("book_name") or ""),
                author_name=str(m.get("author_name") or ""),
                vol=str(m.get("vol") or ""),
                page=str(m.get("page") or ""),
                url=BOOK_URL.format(book_id=h.get("book_id"), page_id=m.get("page_id")),
                text=_window(page_text, snip),
            )
            hits.append(hit)
        return hits

    def search(self, quote: str, speaker: str | None = None) -> list[LibraryHit]:
        """مواضع مرشحة للقول: عبارات حرفية من أوله ووسطه وآخره، ثم كلماته. بلا تكرار."""
        # بلا تشكيل فقط: المكتبة تطبّع الهمزات بنفسها، وتطبيعنا («دلايل») يُفسد العبارة.
        words = re.sub(r"[^\w\s]", " ", strip_diacritics(quote)).split()
        if len(words) < 3:
            return []
        n = min(6, len(words))
        starts = sorted({0, max(0, len(words) // 2 - n // 2), len(words) - n})
        queries = [f'"{" ".join(words[s : s + n])}"' for s in starts]
        queries.append(" ".join(words[:12]))
        out: dict[str, LibraryHit] = {}
        with ThreadPoolExecutor(max_workers=len(queries)) as pool:
            for res in pool.map(self._safe, queries):
                for h in res:
                    out.setdefault(h.item_id, h)
        hits = sorted(out.values(), key=lambda h: not same_author(speaker, h.author_name))[:6]
        for h in hits:
            self._seen[h.item_id] = h
        return hits

    def _safe(self, q: str) -> list[LibraryHit]:
        try:
            return self._query(q)
        except Exception:  # شبكة أو حد معدل: موضع أقل، لا انهيار
            return []

    def same_author(self, speaker: str | None, author: str) -> bool:
        return same_author(speaker, author)

    # ── لحارس الإسناد: النص المعروض هو ما أعادته المكتبة نفسها ──
    def get(self, item_id: str) -> Passage | None:
        h = self._seen.get(item_id)
        if h is None:
            return None
        return Passage(
            source_id=self.source_id,
            item_id=item_id,
            number=h.page,
            text_display=h.text,
            text_plain=h.text,
        )


def _window(page: str, snip: str, width: int = 700) -> str:
    """مقطع من الصفحة حول الموضع المطابق، لا الصفحة كلها."""
    page = re.sub(r"\s+", " ", page)
    if len(page) <= width:
        return page
    key = re.sub(r"\s+", " ", snip)[:40]
    i = page.find(key) if key else -1
    if i < 0:
        return page[:width] + "…"
    a = max(0, i - width // 3)
    return ("…" if a else "") + page[a : a + width] + "…"


_NAME_STOP = {
    "الامام",
    "ابو",
    "ابي",
    "بن",
    "ابن",
    "الشيخ",
    "العلامه",
    "الحافظ",
    "رحمه",
    "الله",
    "تعالي",
    "شيخ",
    "الاسلام",
    "القاضي",
}


def same_author(speaker: str | None, author: str) -> bool:
    """هل المؤلف هو المنسوب إليه؟ بكلمة مميزة مشتركة من الاسمين («أبو جعفر الطبري» و«ابن جرير الطبري»)."""
    from saadeed.text.normalize import normalize

    if not speaker:
        return False
    sp = {w for w in normalize(speaker).split() if w not in _NAME_STOP and len(w) >= 3}
    au = {w for w in normalize(author).split() if w not in _NAME_STOP and len(w) >= 3}
    return bool(sp & au)
