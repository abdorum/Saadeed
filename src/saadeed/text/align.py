"""المحاذاة كلمة بكلمة (المعمارية §٧.١): تُحسب على الكلمات المطبَّعة، وتُعرض بالكلمات الأصلية.

نستعمل `difflib.SequenceMatcher` من المكتبة القياسية: حتمي، ولا يعتمد على مكتبة خارجية.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from saadeed.domain.models import DiffOp
from saadeed.text.normalize import normalize


@dataclass
class Alignment:
    src_start: int
    """أول كلمة مطابقة في نافذة المصدر."""
    src_end: int
    """بعد آخر كلمة مطابقة في نافذة المصدر."""
    matched: int
    """عدد الكلمات المتطابقة."""
    score: float
    """matched / max(len(query), len(src_region))."""
    ops: list[DiffOp]


def align(
    query_norm: list[str],
    src_norm: list[str],
    query_disp: list[str] | None = None,
    src_disp: list[str] | None = None,
) -> Alignment | None:
    """يحاذي كلمات الاقتباس بأفضل منطقة في نافذة المصدر."""
    if not query_norm or not src_norm:
        return None
    query_disp = query_disp or query_norm
    src_disp = src_disp or src_norm
    sm = SequenceMatcher(None, query_norm, src_norm, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size]
    if not blocks:
        return None
    src_start = blocks[0].b - blocks[0].a  # امتداد إلى بداية الاقتباس إن نقصت كلماته الأولى
    src_start = max(0, min(src_start, blocks[0].b))
    last = blocks[-1]
    tail = len(query_norm) - (last.a + last.size)
    src_end = min(len(src_norm), last.b + last.size + tail)
    region = src_norm[src_start:src_end]
    sm2 = SequenceMatcher(None, query_norm, region, autojunk=False)
    matched = sum(b.size for b in sm2.get_matching_blocks())
    ops: list[DiffOp] = []
    for tag, i1, i2, j1, j2 in sm2.get_opcodes():
        ops.append(
            DiffOp(
                op=tag,
                draft=" ".join(query_disp[i1:i2]),
                source=" ".join(src_disp[src_start + j1 : src_start + j2]),
            )
        )
    score = matched / max(len(query_norm), len(region)) if region else 0.0
    return Alignment(src_start, src_end, matched, score, ops)


def _strip_alef(word: str) -> str:
    return word[0] + word[1:].replace("ا", "") if word else word


def rasm_key(word: str) -> str:
    """مفتاح فهرسة يتسامح مع فروق الرسم نفسها التي يقبلها `rasm_equivalent`."""
    if len(word) >= 5 and word.endswith("وه"):
        word = word[:-2] + "اه"
    return _strip_alef(word) if len(word) >= 6 else word


def rasm_equivalent(a: str, b: str) -> bool:
    """هل الفرق بين كلمتين فرق رسم لا فرق لفظ؟ (FR-23)

    حالتان فقط، بشروط طول تحمي من إخفاء خطأ حقيقي:
    - ألف وسطية محذوفة في الرسم العثماني: «السموات/السماوات»، «الرحمن/الرحمان». والكلمة الأقصر 6 أحرف فأكثر
      (فلا تتساوى «قل/قال» ولا «الكتب/الكتاب»).
    - الواو مكان الألف قبل التاء المربوطة: «الصلوة/الصلاة»، «الزكوة/الزكاة». والكلمة 5 أحرف فأكثر.
    """
    if a == b:
        return True
    if min(len(a), len(b)) >= 6 and _strip_alef(a) == _strip_alef(b):
        return True
    if min(len(a), len(b)) >= 5 and a.endswith(("وه", "اه")) and b.endswith(("وه", "اه")):
        return a[:-2] == b[:-2]
    return False


def relax_rasm(ops: list[DiffOp], q_norm: list[str], s_norm: list[str]) -> list[DiffOp]:
    """يحوّل عمليات «replace» التي هي فروق رسم فقط إلى «equal»."""
    out: list[DiffOp] = []
    for op in ops:
        if op.op == "replace":
            d, s = op.draft.split(), op.source.split()
            dn, sn = [normalize(w) for w in d], [normalize(w) for w in s]
            if len(dn) == len(sn) and all(
                rasm_equivalent(x, y) for x, y in zip(dn, sn, strict=True)
            ):
                out.append(DiffOp(op="equal", draft=op.draft, source=op.source))
                continue
        out.append(op)
    return out


def diff_summary(ops: list[DiffOp], limit: int = 3) -> tuple[int, str]:
    """ملخص الفروق للقالب: عددها، وأمثلة «X ← Y»."""
    changes = [o for o in ops if o.op != "equal"]
    parts: list[str] = []
    for o in changes[:limit]:
        if o.op == "replace":
            parts.append(f"«{o.draft}» والصواب «{o.source}»")
        elif o.op == "delete":
            parts.append(f"زيادة «{o.draft}» ليست في المصحف")
        elif o.op == "insert":
            parts.append(f"سقطت «{o.source}»")
    return len(changes), "؛ ".join(parts)
