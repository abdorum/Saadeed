"""مُجذّع عربي خفيف للاسترجاع فقط (E-004، v2.5).

ليس تجذيرًا صرفيًا: يحذف سابقة واحدة ولاحقة واحدة شائعتين، ليلتقي «ويعلمه» و«وعلمه» و«يتعلم» و«تعلم».
يُطبَّق على الطرفين (المسودة والمخزن) بالقاعدة نفسها، فالتصادم الزائد لا يضر إلا بترتيب المرشحين،
والحكم بعده للحَكَم على مرشحين من المخزن. ولا يُستعمل في المطابقة الحرفية ولا في الآيات أبدًا.
"""

from __future__ import annotations

from functools import lru_cache

_PREFIXES = (
    "وبال",
    "وكال",
    "فبال",
    "فال",
    "وال",
    "بال",
    "كال",
    "لل",
    "ال",
    "و",
    "ف",
    "ب",
    "ل",
    "ك",
)
_VERB = ("ي", "ت", "ن")
_SUFFIXES = (
    "هما",
    "كما",
    "ها",
    "هم",
    "هن",
    "كم",
    "كن",
    "نا",
    "ون",
    "ين",
    "ات",
    "ان",
    "وا",
    "ه",
    "ي",
)
MIN_STEM = 3


@lru_cache(maxsize=200_000)
def light_stem(word: str) -> str:
    w = word
    for p in _PREFIXES:
        if w.startswith(p) and len(w) - len(p) >= MIN_STEM:
            w = w[len(p) :]
            break
    if len(w) >= 5 and w[0] in _VERB:
        w = w[1:]
    for s in _SUFFIXES:
        if w.endswith(s) and len(w) - len(s) >= MIN_STEM:
            w = w[: -len(s)]
            break
    return w


def stems(text_norm: str) -> set[str]:
    return {light_stem(t) for t in text_norm.split()}
