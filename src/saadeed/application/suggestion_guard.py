"""حارس الاقتراح (ADR-0014): الصياغة المولَّدة لا تمر إلا خالية من أي نص شرعي أو نسبة.

النموذج يقترح صياغة أدق للتعميم وادعاء الإجماع، لأن هذا من صميم قدرته (اللغة)، ولا يمس الدليل.
لكن الاقتراح نص مولَّد، فيُرفض إن:
- حمل علامة تنصيص أو اقتباس، أو صيغة نسبة («قال تعالى»، «ﷺ»، «رواه»، «حديث»).
- حمل رقمًا ليس في عبارة الكاتب.
- حمل مقطعًا من المصحف (4 كلمات فأكثر)، أو من الحديث في المخزن (6 كلمات فأكثر).
  والعتبتان أعلى من 3 لأن «كثير من الناس» و«أكثر أهل العلم» عبارات عادية تتكرر في المصادر.
- طال أكثر من ضعف عبارة الكاتب، أو طابقها.

والرفض صامت للمستخدم: لا اقتراح خير من اقتراح مريب. وهو حتمي بالكامل.
"""

from __future__ import annotations

import re

from saadeed.text.normalize import normalize
from saadeed.verifiers.hadith import HadithIndex
from saadeed.verifiers.quran import QuranIndex

_MARKS = re.compile(r"[﴿﴾«»\"“”]|\(\(|\)\)")
_ATTRIBUTION = re.compile(
    r"(?:^|\s)(?:قال تعالي|قال الله|يقول الله|رسول الله|النبي|صلي الله عليه وسلم|رواه|اخرجه"
    r"|حديث|الحديث|ايه|الايه|سوره)(?:\s|$)"
)
_DIGITS = re.compile(r"[0-9٠-٩]+")
QURAN_MIN = 4
HADITH_MIN = 6
MAX_RATIO = 2.0


def safe_suggestion(
    suggestion: str | None, original: str, quran: QuranIndex, hadith: HadithIndex
) -> str | None:
    if not suggestion:
        return None
    s = suggestion.strip()
    norm = normalize(s)
    if not norm or norm == normalize(original):
        return None
    if len(s) > MAX_RATIO * max(len(original), 20):
        return None
    if _MARKS.search(s) or _ATTRIBUTION.search(" " + norm + " "):
        return None
    if set(_DIGITS.findall(s)) - set(_DIGITS.findall(original)):
        return None
    words = norm.split()
    if quran.runs(words, QURAN_MIN):
        return None
    for i in range(len(words) - HADITH_MIN + 1):
        if hadith.exact_hits(" ".join(words[i : i + HADITH_MIN])):
            return None
    return s
