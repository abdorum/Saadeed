"""الحواشي (E-023): مصادر الكاتب، لا ادعاءاته.

الخطب المنشورة كثيرًا ما تنتهي بحواشٍ مرقّمة:

    …«أيما مسلم سقى مسلمًا على ظمأ…»[4].
    [4] أخرجه أبو داود (1682)، والترمذي (2449).

فالحاشية لا تُستخرج منها ادعاءات (سطر «الأعراف: 31» ليس آية محرّفة، و«أخرجه مسلم (1565)» ليس حديثًا)،
بل تُلحق بالادعاء الذي أشار إليها رقمها: نسبة تخريج للحديث، ومصدرًا مذكورًا للقول.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# سطر حاشية: يبدأ برقم بين معقوفين أو قوسين، في أول السطر.
_NOTE_LINE = re.compile(r"^[ \t]*[\[(]([0-9٠-٩]{1,3})[\])][ \t]*(\S.*)$", re.M)
# إشارة الحاشية في المتن: [4] أو (4) ملاصقة لما قبلها أو بعد مسافة.
_NOTE_REF = re.compile(r"\s?[\[(]([0-9٠-٩]{1,3})[\])]")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
MIN_NOTES = 2
"""أقل عدد من أسطر الحواشي المتتالية في آخر النص لنعدّها قسم حواشٍ (لا سطرًا عابرًا يبدأ برقم)."""


@dataclass(frozen=True)
class Footnotes:
    zone_start: int | None
    """أول موضع في قسم الحواشي، أو None إن لم يكن."""
    notes: dict[int, str]

    def in_zone(self, pos: int) -> bool:
        return self.zone_start is not None and pos >= self.zone_start

    def ref_after(self, text: str, end: int, window: int = 12) -> str | None:
        """نص الحاشية التي يشير إليها رقم بعد الادعاء مباشرة («…»[4]).

        النافذة قصيرة: الرقم يلي الادعاء أو علامة إغلاقه، فلا يُلحق بالادعاء رقم حاشية جملة أخرى.
        """
        if not self.notes:
            return None
        frag = text[end : end + window]
        m = _NOTE_REF.search(frag)
        if not m or frag[: m.start()].strip(' »"”)﴾.،؛:'):
            return None
        return self.notes.get(int(m.group(1).translate(_DIGITS)))


def find_footnotes(text: str) -> Footnotes:
    """قسم الحواشي = أسطر الحواشي المتتالية في آخر النص (يُسمح بينها بأسطر فارغة أو تكملة)."""
    lines = list(_NOTE_LINE.finditer(text))
    if len(lines) < MIN_NOTES:
        return Footnotes(None, {})
    # نبدأ من آخر سطر حاشية ونرجع ما دامت الأسطر متقاربة (لا يفصلها متن طويل).
    group = [lines[-1]]
    for m in reversed(lines[:-1]):
        gap = text[m.end() : group[0].start()]
        if len(gap.strip()) > 400:
            break
        group.insert(0, m)
    if len(group) < MIN_NOTES:
        return Footnotes(None, {})
    notes = {int(m.group(1).translate(_DIGITS)): m.group(2).strip() for m in group}
    return Footnotes(group[0].start(), notes)


def strip_ref(value: str | None) -> str | None:
    """قيمة نسبة أعادها النموذج وهي رقم حاشية فقط («3»، «[3]») ليست كتابًا."""
    if value is None:
        return None
    v = value.strip().strip("[]() ")
    return None if not v or v.translate(_DIGITS).isdigit() else value
