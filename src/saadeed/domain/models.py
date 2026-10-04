"""نماذج النطاق: الكيانات الأساسية في المسرد §١ ومخطط التقرير في المتطلبات §٦.

كل النماذج pydantic v2. والنواة لا تعرف شيئًا عن HTTP أو مزود النموذج.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field

from saadeed.domain.enums import (
    Action,
    ClaimType,
    Confidence,
    ContentLevel,
    EvidenceStatus,
    MatchType,
    OverreachType,
    Reason,
    Relation,
    Severity,
    SourceRole,
    TrackBucket,
    bucket_for,
)

SCHEMA_VERSION = "1.0"


class Span(BaseModel):
    """موضع `[start, end)` بالحروف في نص المسودة الأصلي."""

    model_config = ConfigDict(frozen=True)

    start: int = Field(ge=0)
    end: int = Field(ge=0)

    def overlaps(self, other: Span) -> bool:
        return self.start < other.end and other.start < self.end

    def iou(self, other: Span) -> float:
        inter = max(0, min(self.end, other.end) - max(self.start, other.start))
        union = max(self.end, other.end) - min(self.start, other.start)
        return inter / union if union else 0.0


class Sentence(BaseModel):
    """جملة من المسودة بموضعها."""

    index: int
    text: str
    span: Span


class ClaimHints(BaseModel):
    """قرائن من نص المسودة نفسه، تُستعمل مدخلاتٍ للقواعد."""

    presented_as_verbatim: bool = True
    """هل يُقدَّم النص بلفظه (تنصيص، أو «قال ﷺ:»)؟ أم بالمعنى («ما معناه»)؟"""
    cited_ref: str | None = None
    """إحالة الآية كما كتبها الكاتب: «البقرة: 255»."""
    cited_book: str | None = None
    """نسبة التخريج كما كتبها الكاتب: «رواه البخاري»."""
    source_mentioned: str | None = None
    """مصدر يذكره الكاتب لقول أو رقم: «في زاد المعاد»."""
    speaker: str | None = None
    """القائل المنسوب إليه: «ابن القيم»."""


class Claim(BaseModel):
    """ادعاء قابل للفحص في المسودة."""

    id: str
    text: str
    span: Span
    type: ClaimType
    level: ContentLevel
    hints: ClaimHints = Field(default_factory=ClaimHints)
    linked_conclusion: Span | None = None
    """موضع الاستنتاج الذي يبنيه الكاتب على هذا الحديث (ADR-0011)."""
    origin: str = "llm"
    """من أين جاء: llm (الاستخراج) أو marker (المرور الحتمي) أو both."""


class SourceRef(BaseModel):
    """مرجع الشاهد في المخزن."""

    source_id: str
    item_id: str
    citation: str
    url: str | None = None


class DiffOp(BaseModel):
    """عملية فرق كلمة بكلمة بين نص المسودة ونص المصدر."""

    op: str  # equal | replace | insert | delete
    draft: str = ""
    source: str = ""


class Evidence(BaseModel):
    """شاهد من المخزن. نصه يُعاد جلبه دائمًا بحارس الإسناد."""

    ref: SourceRef
    role: SourceRole
    text: str
    match_type: MatchType
    match_reason: str
    diff: list[DiffOp] = Field(default_factory=list)
    highlight: list[Span] = Field(default_factory=list)
    """مواضع الجزء المطابق داخل `text` (لتظليله في الواجهة)."""


class RelationResult(BaseModel):
    """حكم العلاقة بين استنتاج المسودة ولفظ الحديث (FR-36)."""

    relation: Relation
    overreach_type: OverreachType | None = None
    excess_text: str | None = None
    """الجزء الزائد، **منسوخًا من نص المسودة** لا مكتوبًا من النموذج."""


class Finding(BaseModel):
    """ملاحظة: نتيجة فحص ادعاء واحد على الأبعاد الثلاثة."""

    id: str
    claim: Claim
    evidence_status: EvidenceStatus
    severity: Severity
    action: Action
    reason: Reason | None
    rule_id: str
    evidence: list[Evidence] = Field(default_factory=list)
    relation: RelationResult | None = None
    explanation: str = ""
    next_step: str = ""
    confidence: Confidence = Confidence.MEDIUM
    notes: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bucket(self) -> TrackBucket:
        return bucket_for(self.action, self.evidence_status)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def labels_ar(self) -> dict[str, str]:
        """التسميات العربية للأبعاد، كما في المسرد."""
        return {
            "evidence_status": self.evidence_status.label_ar,
            "severity": self.severity.label_ar,
            "action": self.action.label_ar,
            "bucket": self.bucket.label_ar,
            "claim_type": self.claim.type.label_ar,
        }


class DraftInfo(BaseModel):
    char_count: int
    word_count: int
    language: str = "ar"


class Summary(BaseModel):
    total_claims: int
    by_bucket: dict[str, int]
    by_severity: dict[str, int]
    not_checked: list[str] = Field(default_factory=list)


class CoverageSource(BaseModel):
    id: str
    name_ar: str
    role: SourceRole
    count: int
    version: str
    license: str
    review_status: str = "approved"


class Coverage(BaseModel):
    sources: list[CoverageSource] = Field(default_factory=list)


class ManifestStamp(BaseModel):
    id: str
    sha256: str


class Meta(BaseModel):
    saadeed_version: str
    llm: str
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    policy_version: str
    manifest: ManifestStamp
    duration_ms: int = 0
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    warnings: list[str] = Field(default_factory=list)


class ReviewReport(BaseModel):
    """تقرير المراجعة (Report 1.0)."""

    schema_version: str = SCHEMA_VERSION
    draft: DraftInfo
    summary: Summary
    top_risks: list[str]
    findings: list[Finding]
    coverage: Coverage
    meta: Meta
