"""تقطيع المسودة إلى جمل بمواضعها (FR-10).

لا يُقطع داخل الأقواس القرآنية ﴿﴾ ولا علامات التنصيص «»، حتى لا تنقسم آية أو حديث.
"""

from __future__ import annotations

from saadeed.domain.models import Sentence, Span

_OPEN = {"﴿": "﴾", "«": "»", "“": "”"}
_CLOSE = {v: k for k, v in _OPEN.items()}
_ENDERS = set(".!؟?…\n")


def split_sentences(text: str) -> list[Sentence]:
    sentences: list[Sentence] = []
    depth: list[str] = []
    start = 0

    def flush(end: int) -> None:
        nonlocal start
        raw = text[start:end]
        lead = len(raw) - len(raw.lstrip())
        trail = len(raw.rstrip())
        s, e = start + lead, start + trail
        if e > s and any(ch.isalpha() for ch in text[s:e]):
            sentences.append(
                Sentence(index=len(sentences), text=text[s:e], span=Span(start=s, end=e))
            )
        start = end

    for i, ch in enumerate(text):
        if ch in _OPEN:
            depth.append(_OPEN[ch])
        elif ch in _CLOSE and depth and depth[-1] == ch:
            depth.pop()
        elif ch in _ENDERS and not depth:
            flush(i + 1)
        elif ch == "\n":
            # سطر جديد داخل قوس لم يُغلق: نعدّه خطأ تنسيق ونُغلق الأقواس.
            depth.clear()
            flush(i + 1)
    flush(len(text))
    return sentences


def word_count(text: str) -> int:
    return len(text.split())
