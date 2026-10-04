"""التطبيع العربي (المسرد §٤): للبحث والمطابقة فقط، ولا يُعرض النص مطبَّعًا أبدًا.

القواعد مستقاة من الممارسة المعتمدة في محركات البحث القرآني والحديثي:
- حذف التشكيل والتطويل وعلامات الوقف والعلامات القرآنية الصغيرة والألف الخنجرية.
- توحيد الألفات (أ إ آ ٱ ← ا)، والياء (ى ئ ← ي)، والواو (ؤ ← و)، والتاء المربوطة (ة ← ه)، وحذف الهمزة المفردة.
- توسيع الرموز (ﷺ ← صلى الله عليه وسلم).
والهدف: ألّا يُنبَّه على اختلاف التشكيل أو الرسم (FR-23)، وأن يبقى الحرف المختلف حقًا ظاهرًا.
"""

from __future__ import annotations

import re
import unicodedata

# التشكيل والعلامات: الحركات، والألف الخنجرية، وعلامات المصحف، والعلامات الممتدة.
_DROP_RANGES = [
    (0x0610, 0x061A),  # علامات صغيرة فوق الحروف
    (0x064B, 0x065F),  # الحركات والتنوين والشدة والسكون
    (0x0670, 0x0670),  # الألف الخنجرية
    (0x06D6, 0x06ED),  # علامات الوقف والعلامات القرآنية
    (0x08D3, 0x08FF),  # علامات عربية ممتدة
]
_DROP_CHARS = {
    "ـ",  # التطويل
    "‌",
    "‍",
    "‎",
    "‏",
    "؜",
    "﻿",  # محارف الاتجاه والوصل
    "ء",  # الهمزة المفردة
}
_MAP = {
    "أ": "ا",
    "إ": "ا",
    "آ": "ا",
    "ٱ": "ا",
    "ٲ": "ا",
    "ٳ": "ا",
    "ى": "ي",
    "ئ": "ي",
    "ی": "ي",
    "ؤ": "و",
    "ة": "ه",
    "ک": "ك",
}
_EXPAND = {
    "ﷺ": " صلى الله عليه وسلم ",  # ﷺ
    "ﷻ": " جل جلاله ",  # ﷻ
    "ﷲ": "الله",  # ﷲ
}
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _is_dropped(ch: str) -> bool:
    if ch in _DROP_CHARS:
        return True
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _DROP_RANGES)


def _is_word_char(ch: str) -> bool:
    cat = unicodedata.category(ch)
    return cat[0] in ("L", "N")


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """يطبّع النص ويعيد خريطة: لكل حرف في الناتج موضعه في الأصل.

    الخريطة تتيح تحويل موضع وُجد في النص المطبَّع إلى موضعه في المسودة الأصلية.
    """
    out: list[str] = []
    idx: list[int] = []
    prev_space = True
    for i, raw in enumerate(text):
        chunk = _EXPAND.get(raw)
        pieces = chunk if chunk is not None else raw
        for ch in pieces:
            if _is_dropped(ch):
                continue
            ch = _MAP.get(ch, ch)
            ch = ch.translate(_DIGITS)
            if _is_word_char(ch):
                out.append(ch.lower())
                idx.append(i)
                prev_space = False
            elif not prev_space:
                out.append(" ")
                idx.append(i)
                prev_space = True
    while out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def normalize(text: str) -> str:
    """التطبيع للبحث والمطابقة."""
    return normalize_with_map(text)[0]


def tokens(text: str) -> list[str]:
    """كلمات النص بعد التطبيع."""
    norm = normalize(text)
    return norm.split() if norm else []


def strip_diacritics(text: str) -> str:
    """يحذف التشكيل فقط ويُبقي الحروف كما هي (للعرض المبسّط)."""
    return "".join(ch for ch in text if not _is_dropped(ch) or ch == "ء")


def find_span(haystack: str, needle: str, start_hint: int = 0) -> tuple[int, int] | None:
    """يجد `needle` في `haystack` بعد التطبيع، ويعيد موضعه في الأصل `[start, end)`.

    يُستعمل لتحديد موضع الادعاء في المسودة من نص يعيده النموذج (قد يختلف تشكيلًا أو ترقيمًا).
    """
    norm_h, map_h = normalize_with_map(haystack)
    norm_n = normalize(needle)
    if not norm_n:
        return None
    pos = -1
    if start_hint:
        # ابحث أولًا بعد التلميح، فالادعاءات المتكررة تأخذ أقرب ظهور تالٍ.
        norm_hint = next((j for j, o in enumerate(map_h) if o >= start_hint), len(map_h))
        pos = norm_h.find(norm_n, norm_hint)
    if pos < 0:
        pos = norm_h.find(norm_n)
    if pos < 0:
        return None
    start = map_h[pos]
    end = map_h[pos + len(norm_n) - 1] + 1
    # الحركات بعد آخر حرف جزء من الكلمة، فلا تُقطع.
    while end < len(haystack) and _is_dropped(haystack[end]) and not haystack[end].isspace():
        end += 1
    return start, end


_WS = re.compile(r"\s+")


def squash_spaces(text: str) -> str:
    return _WS.sub(" ", text).strip()
