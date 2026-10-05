"""بنك الاختبار (البروتوكول §٣): الحالات، والنصوص الحاملة، والتقسيم الطبقي ببذرة 70."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, Field

SEED = 70
CRITICAL = {"Q3", "Q4", "Q5", "Q7", "H6", "H7", "O6"}

# التصنيف المتوقع لكل فئة: (حالة الدليل، السبب، الإجراء). والسليم إجراؤه NONE.
EXPECTED: dict[str, tuple[str, str | None, str]] = {
    "Q1": ("SUPPORTED", None, "NONE"),
    "Q2": ("SUPPORTED", None, "NONE"),
    "Q3": ("CONTRADICTED", "TEXT_MISMATCH", "CORRECT_FROM_SOURCE"),
    "Q4": ("CONTRADICTED", "TEXT_MISMATCH", "CORRECT_FROM_SOURCE"),
    "Q5": ("CONTRADICTED", "TEXT_MISMATCH", "CORRECT_FROM_SOURCE"),
    "Q6": ("PARTIALLY_SUPPORTED", "WRONG_REFERENCE", "CORRECT_FROM_SOURCE"),
    "Q7": ("CONTRADICTED", "NOT_QURAN", "RECONSIDER"),
    # v2.5 (البروتوكول §١٢ بند 9): في نصوص حاملة جديدة لا تمس القديمة.
    "Q8": ("PARTIALLY_SUPPORTED", "QURAN_AS_HADITH", "CORRECT_FROM_SOURCE"),
    "Q9": ("PARTIALLY_SUPPORTED", "MERGED_AYAT", "CORRECT_FROM_SOURCE"),
    "H1": ("SUPPORTED", None, "NONE"),
    "H2": ("SUPPORTED", None, "NONE"),
    "H3": ("PARTIALLY_SUPPORTED", "PARAPHRASED_AS_WORDING", "CORRECT_FROM_SOURCE"),
    "H4": ("SUPPORTED", None, "NONE"),
    "H5": ("PARTIALLY_SUPPORTED", "MISATTRIBUTED", "CORRECT_FROM_SOURCE"),
    "H6": ("CONTRADICTED", "KNOWN_WEAK", "RECONSIDER"),
    "H7": ("NOT_FOUND", "NOT_FOUND", "VERIFY"),
    "H8a": ("FOUND_NO_RULING", "FOUND_OUTSIDE_RULING_SCOPE", "VERIFY"),
    "H8b": ("NOT_FOUND", "NOT_FOUND", "VERIFY"),
    "H9": ("EXCEEDS_SOURCE", "EXCEEDS_TEXT", "REPHRASE"),
    "H10": ("SUPPORTED", None, "NONE"),
    "O1": ("OUT_OF_SCOPE", "NO_SOURCE", "VERIFY"),
    "O2": ("OUT_OF_SCOPE", "NO_SOURCE", "VERIFY"),
    "O3": ("OUT_OF_SCOPE", "UNVERIFIED_CONSENSUS", "REPHRASE"),
    "O4": ("OUT_OF_SCOPE", "OVERGENERALIZATION", "REPHRASE"),
    "O5": ("OUT_OF_SCOPE", "SPECIALIST_REQUIRED", "REFER"),
    "O6": ("OUT_OF_SCOPE", "FATWA_REQUIRED", "REFER"),
    "O7": ("OUT_OF_SCOPE", "GROUP_JUDGMENT", "REFER"),
    "C0": ("NONE", None, "NONE"),
}

GROUP_OF = {
    **{c: "آيات" for c in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9")},
    **{c: "أحاديث" for c in ("H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8a", "H8b", "H9", "H10")},
    "O1": "أقوال منسوبة",
    "O2": "أرقام وإحصاءات",
    "O3": "إجماع وتعميم",
    "O4": "إجماع وتعميم",
    "O5": "إحالات",
    "O6": "إحالات",
    "O7": "إحالات",
    "C0": "جمل سليمة",
    "OF": "أمثلة الحزمة",
}


class Expected(BaseModel):
    evidence_status: str
    reason: str | None
    action: str


class TestCase(BaseModel):
    case_id: str
    category: str
    critical: bool = False
    surface: str
    """الجملة كما تظهر في النص الحامل."""
    claim_text: str
    """الجزء الذي هو الادعاء (موضعه = span)."""
    expected: Expected
    split: str = ""
    carrier_id: str = ""
    span: tuple[int, int] = (0, 0)
    label_source: str = "generated"  # generated | drafted | official
    reviewer: str | None = None
    notes: str | None = None
    meta: dict = Field(default_factory=dict)

    @property
    def defective(self) -> bool:
        return self.expected.action != "NONE"


class Carrier(BaseModel):
    carrier_id: str
    split: str
    text: str
    case_ids: list[str]
    kind: str = "carrier"  # carrier | composite


def expected_for(category: str) -> Expected:
    s, r, a = EXPECTED[category]
    return Expected(evidence_status=s, reason=r, action=a)


_OPENERS = [
    "أيها الإخوة الكرام،",
    "عباد الله،",
    "أيها المؤمنون،",
    "معاشر المسلمين،",
    "أحبتي في الله،",
]
_LINKS = ["ثم اعلموا رحمكم الله", "ومن ذلك", "وتأملوا معي", "وفي هذا المعنى", "ولنقف هنا قليلًا"]


def split_cases(cases: list[TestCase], dev_ratio: float = 0.4) -> None:
    """تقسيم طبقي بحسب الفئة، ببذرة ثابتة (البروتوكول §٣.٣)."""
    rng = random.Random(SEED)
    by_cat: dict[str, list[TestCase]] = defaultdict(list)
    for c in cases:
        by_cat[c.category].append(c)
    for cat in sorted(by_cat):
        group = sorted(by_cat[cat], key=lambda c: c.case_id)
        rng.shuffle(group)
        n_dev = max(1, round(len(group) * dev_ratio)) if len(group) > 1 else 1
        for i, c in enumerate(group):
            c.split = "dev" if i < n_dev else "test"


def build_carriers(cases: list[TestCase], per_carrier: int = 6) -> list[Carrier]:
    """يجمع الحالات في نصوص حاملة تشبه فقرات خطبة (البروتوكول §٣.٢)، ويحسب موضع كل ادعاء."""
    rng = random.Random(SEED + 1)
    carriers: list[Carrier] = []
    for split in ("dev", "test"):
        pool = sorted((c for c in cases if c.split == split), key=lambda c: c.case_id)
        rng.shuffle(pool)
        # لا نضع حالتين من الفئة نفسها متجاورتين قدر الإمكان.
        for k in range(0, len(pool), per_carrier):
            group = pool[k : k + per_carrier]
            cid = f"{split}-{len(carriers) + 1:03d}"
            parts: list[str] = [rng.choice(_OPENERS)]
            text = parts[0]
            for j, case in enumerate(group):
                link = (" " + rng.choice(_LINKS) + "، ") if j else " "
                start_surface = len(text) + len(link)
                text = text + link + case.surface
                off = case.surface.find(case.claim_text)
                if off < 0:
                    raise ValueError(f"{case.case_id}: claim_text ليس في surface")
                case.span = (start_surface + off, start_surface + off + len(case.claim_text))
                case.carrier_id = cid
            carriers.append(
                Carrier(carrier_id=cid, split=split, text=text, case_ids=[c.case_id for c in group])
            )
    return carriers


def save_bank(dir_: Path, cases: list[TestCase], carriers: list[Carrier]) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    with (dir_ / "cases.jsonl").open("w", encoding="utf-8") as f:
        for c in sorted(cases, key=lambda c: c.case_id):
            f.write(json.dumps(c.model_dump(), ensure_ascii=False) + "\n")
    with (dir_ / "carriers.jsonl").open("w", encoding="utf-8") as f:
        for k in carriers:
            f.write(json.dumps(k.model_dump(), ensure_ascii=False) + "\n")


def load_bank(dir_: Path) -> tuple[list[TestCase], list[Carrier]]:
    cases = [
        TestCase(**json.loads(x))
        for x in (dir_ / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        if x
    ]
    carriers = [
        Carrier(**json.loads(x))
        for x in (dir_ / "carriers.jsonl").read_text(encoding="utf-8").splitlines()
        if x
    ]
    return cases, carriers
