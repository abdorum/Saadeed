"""التعدادات: منقولة حرفيًا من المسرد (docs/planning/10-glossary.md §٢–§٥).

كل قيمة لها اسم عربي فصيح يظهر في الواجهة (`label_ar`). لا يُضاف هنا شيء قبل إضافته إلى المسرد.
"""

from __future__ import annotations

from enum import StrEnum


class _Labeled(StrEnum):
    """تعداد له تسمية عربية للواجهة."""

    @property
    def label_ar(self) -> str:
        return _LABELS[(type(self).__name__, self.value)]


class EvidenceStatus(_Labeled):
    """حالة الدليل: ماذا وجدنا؟"""

    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    EXCEEDS_SOURCE = "EXCEEDS_SOURCE"
    CONTRADICTED = "CONTRADICTED"
    FOUND_NO_RULING = "FOUND_NO_RULING"
    NOT_FOUND = "NOT_FOUND"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    NOT_CHECKED = "NOT_CHECKED"


class Severity(_Labeled):
    """أثر الخطأ: كم يضر لو كان الادعاء خطأً؟ (ليس احتمال الخطأ)."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"

    @property
    def rank(self) -> int:
        """للترتيب: الأخطر أولًا."""
        return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "NONE": 4}[self.value]


class Action(_Labeled):
    """الإجراء: ماذا يفعل الكاتب الآن؟"""

    NONE = "NONE"
    VERIFY = "VERIFY"
    CORRECT_FROM_SOURCE = "CORRECT_FROM_SOURCE"
    RECONSIDER = "RECONSIDER"
    REPHRASE = "REPHRASE"
    REFER = "REFER"


class TrackBucket(_Labeled):
    """أبواب الملخص بلغة معيار المسار. تُشتق من الإجراء ولا تُخزَّن."""

    SUPPORTED_BY_SOURCES = "SUPPORTED_BY_SOURCES"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    REFER = "REFER"
    NOT_CHECKED = "NOT_CHECKED"


class Reason(StrEnum):
    """السبب: أي قاعدة أنتجت الملاحظة؟ (المسرد §٢.٥)."""

    TEXT_MISMATCH = "TEXT_MISMATCH"
    WRONG_REFERENCE = "WRONG_REFERENCE"
    NOT_QURAN = "NOT_QURAN"
    KNOWN_WEAK = "KNOWN_WEAK"
    PARAPHRASED_AS_WORDING = "PARAPHRASED_AS_WORDING"
    MISATTRIBUTED = "MISATTRIBUTED"
    FOUND_OUTSIDE_RULING_SCOPE = "FOUND_OUTSIDE_RULING_SCOPE"
    NOT_FOUND = "NOT_FOUND"
    NO_SOURCE = "NO_SOURCE"
    CITED_OUT_OF_COVERAGE = "CITED_OUT_OF_COVERAGE"
    UNVERIFIED_CONSENSUS = "UNVERIFIED_CONSENSUS"
    OVERGENERALIZATION = "OVERGENERALIZATION"
    GROUP_JUDGMENT = "GROUP_JUDGMENT"
    SPECIALIST_REQUIRED = "SPECIALIST_REQUIRED"
    FATWA_REQUIRED = "FATWA_REQUIRED"
    EXCEEDS_TEXT = "EXCEEDS_TEXT"
    SYSTEM_UNAVAILABLE = "SYSTEM_UNAVAILABLE"


class ClaimType(_Labeled):
    """أنواع الادعاءات (المسرد §٣)."""

    QURAN_QUOTE = "QURAN_QUOTE"
    HADITH_QUOTE = "HADITH_QUOTE"
    TAKHRIJ = "TAKHRIJ"
    ATTRIBUTED_SAYING = "ATTRIBUTED_SAYING"
    STATISTIC = "STATISTIC"
    HISTORICAL_EVENT = "HISTORICAL_EVENT"
    CONSENSUS_CLAIM = "CONSENSUS_CLAIM"
    GENERALIZATION = "GENERALIZATION"
    GROUP_JUDGMENT = "GROUP_JUDGMENT"
    RULING = "RULING"
    PERSONAL_CASE = "PERSONAL_CASE"
    HADITH_CONCLUSION = "HADITH_CONCLUSION"


class ContentLevel(StrEnum):
    """مستويات المحتوى في الحزمة العلمية: أ/ب/ج/د."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


class Confidence(StrEnum):
    """الثقة وصفًا لا رقمًا (Q-06)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MatchType(StrEnum):
    """نوع المطابقة: مدخل للقواعد، لا حالة."""

    EXACT = "EXACT"
    NORMALIZED = "NORMALIZED"
    PARTIAL = "PARTIAL"
    PARAPHRASE = "PARAPHRASE"
    MISMATCH = "MISMATCH"
    NONE = "NONE"


class Relation(StrEnum):
    """علاقة الاستنتاج بلفظ الحديث (ADR-0011)."""

    SUPPORTS = "SUPPORTS"
    PARTIAL = "PARTIAL"
    EXCEEDS = "EXCEEDS"
    CONTRADICTS = "CONTRADICTS"


class OverreachType(_Labeled):
    """أنواع التجاوز (قائمة مغلقة، ADR-0011 §٢)."""

    DROPPED_CONDITION = "DROPPED_CONDITION"
    ADDITION = "ADDITION"
    OVERGENERALIZED = "OVERGENERALIZED"
    ESCALATED = "ESCALATED"


class SourceRole(_Labeled):
    """دور المصدر: ما يجوز له أن يقرره (ADR-0010 §٣)."""

    REFERENCE_TEXT = "REFERENCE_TEXT"
    AUTHENTIC = "AUTHENTIC"
    RULING = "RULING"
    LOCATE = "LOCATE"
    LINK = "LINK"


# قائمة أزواج لا قاموس: مفاتيح StrEnum المتساوية القيمة (NONE، REFER) تتصادم في القاموس.
_LABEL_PAIRS: list[tuple[StrEnum, str]] = [
    (EvidenceStatus.SUPPORTED, "مؤيَّد بالمصدر"),
    (EvidenceStatus.PARTIALLY_SUPPORTED, "مؤيَّد جزئيًا"),
    (EvidenceStatus.EXCEEDS_SOURCE, "يتجاوز المصدر"),
    (EvidenceStatus.CONTRADICTED, "يخالف المصدر"),
    (EvidenceStatus.FOUND_NO_RULING, "وُجد دون حكم"),
    (EvidenceStatus.NOT_FOUND, "لم يُعثر عليه في النطاق"),
    (EvidenceStatus.OUT_OF_SCOPE, "خارج نطاق الفحص"),
    (EvidenceStatus.NOT_CHECKED, "لم يُفحص"),
    (Severity.CRITICAL, "حرج"),
    (Severity.HIGH, "مرتفع"),
    (Severity.MEDIUM, "متوسط"),
    (Severity.LOW, "منخفض"),
    (Severity.NONE, "—"),
    (Action.NONE, "لا إجراء"),
    (Action.VERIFY, "تحقّق ووثّق"),
    (Action.CORRECT_FROM_SOURCE, "صحّح من المصدر"),
    (Action.RECONSIDER, "أعِد النظر في الاستشهاد"),
    (Action.REPHRASE, "أعِد الصياغة"),
    (Action.REFER, "أحِل إلى مختص"),
    (TrackBucket.SUPPORTED_BY_SOURCES, "تؤيده المصادر"),
    (TrackBucket.NEEDS_VERIFICATION, "يتطلب تحققًا"),
    (TrackBucket.REFER, "إحالة إلى مختص"),
    (TrackBucket.NOT_CHECKED, "لم يُفحص"),
    (ClaimType.QURAN_QUOTE, "آية قرآنية"),
    (ClaimType.HADITH_QUOTE, "حديث نبوي"),
    (ClaimType.TAKHRIJ, "نسبة تخريج"),
    (ClaimType.ATTRIBUTED_SAYING, "قول منسوب"),
    (ClaimType.STATISTIC, "رقم أو إحصاء"),
    (ClaimType.HISTORICAL_EVENT, "واقعة سيرة أو تاريخ"),
    (ClaimType.CONSENSUS_CLAIM, "ادعاء إجماع"),
    (ClaimType.GENERALIZATION, "تعميم"),
    (ClaimType.GROUP_JUDGMENT, "حكم على جماعة"),
    (ClaimType.RULING, "حكم فقهي أو عقدي تفصيلي"),
    (ClaimType.PERSONAL_CASE, "حالة شخصية"),
    (ClaimType.HADITH_CONCLUSION, "استنتاج مبني على حديث"),
    (OverreachType.DROPPED_CONDITION, "إطلاق المقيَّد"),
    (OverreachType.ADDITION, "الزيادة على النص"),
    (OverreachType.OVERGENERALIZED, "تعميم الخاص"),
    (OverreachType.ESCALATED, "رفع درجة الخبر"),
    (SourceRole.REFERENCE_TEXT, "نص معتمد"),
    (SourceRole.AUTHENTIC, "مصدر احتجاج"),
    (SourceRole.RULING, "مصدر حكم منقول"),
    (SourceRole.LOCATE, "مصدر موضع"),
    (SourceRole.LINK, "إحالة"),
]


# المفتاح (اسم التعداد، القيمة): لأن قيمًا مثل NONE وREFER مشتركة بين أكثر من تعداد.
_LABELS: dict[tuple[str, str], str] = {(type(k).__name__, k.value): v for k, v in _LABEL_PAIRS}


def bucket_for(action: Action, status: EvidenceStatus) -> TrackBucket:
    """يشتق باب الملخص من الإجراء (ADR-0009 §٢). لا يُخزَّن الباب حقلًا مستقلًا."""
    if status is EvidenceStatus.NOT_CHECKED:
        return TrackBucket.NOT_CHECKED
    if action is Action.NONE:
        return TrackBucket.SUPPORTED_BY_SOURCES
    if action is Action.REFER:
        return TrackBucket.REFER
    return TrackBucket.NEEDS_VERIFICATION
