"""المنافذ (Ports): واجهات تعرّفها النواة، وتنفذها المحوّلات (المعمارية §٨).

النواة لا تعرف من ينفذها: Groq أو Gemini أو Fake، ملفات JSON أو MCP لاحقًا.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from saadeed.domain.enums import SourceRole


class LLMUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached: bool = False


class LLMResponse(BaseModel):
    """استجابة JSON من النموذج. لا نص حر."""

    data: dict[str, Any]
    model: str
    usage: LLMUsage = Field(default_factory=LLMUsage)


class LLMError(RuntimeError):
    """تعذّر الحصول على استجابة صالحة من النموذج (يقود إلى الفشل الآمن)."""


class LLMPort(Protocol):
    """منفذ النموذج اللغوي: يعيد JSON فقط، بدرجة حرارة 0."""

    @property
    def model_id(self) -> str: ...

    def generate_json(self, *, system: str, user: str, max_tokens: int = 4096) -> LLMResponse: ...


class Ayah(BaseModel):
    sura: int
    aya: int
    sura_name: str
    text_simple: str
    """الرسم الإملائي (Tanzil simple) بلا بسملة مضافة."""
    text_uthmani: str
    """الرسم العثماني للعرض."""


class QuranRepo(Protocol):
    def all_ayat(self) -> list[Ayah]: ...

    def get(self, sura: int, aya: int) -> Ayah | None: ...

    def sura_names(self) -> dict[int, str]: ...


class SourceInfo(BaseModel):
    id: str
    name_ar: str
    role: SourceRole
    count: int
    version: str
    license: str
    review_status: str = "approved"


class Passage(BaseModel):
    """نص من مصدر نصي (حديث مثلًا)."""

    source_id: str
    item_id: str
    number: str
    text_display: str
    """النص المشكول للعرض (من المخزن)."""
    text_plain: str
    """النص بلا تشكيل (للبحث)."""
    text_norm: str | None = None
    """النص مطبَّعًا مسبقًا عند بناء البيانات (لتسريع الفهرسة). يُحسب إن غاب."""


class TextSourcePort(Protocol):
    """منفذ موحّد للمصادر النصية (ADR-0010). محوّل لكل كتاب."""

    @property
    def info(self) -> SourceInfo: ...

    def all_passages(self) -> list[Passage]: ...

    def get(self, item_id: str) -> Passage | None: ...


class StoreRef(BaseModel):
    """إشارة إلى نص في المخزن بمعرّفه. النص نفسه يُجلب من المخزن دائمًا."""

    source_id: str
    item_id: str
    anchor: str | None = None
    """عبارة من نص المخزن لتظليل موضع الشاهد فقط، ولا تُعرض من هذا الحقل."""


class KnownWeak(BaseModel):
    """حديث من «المشتهر الذي لا يصح»: حكمه منقول بلفظ مصدره (يعتمده محمد)."""

    id: str
    text: str
    variants: list[str] = Field(default_factory=list)
    ruling_ar: str
    ruling_source: str
    url: str | None = None
    verified: bool = False
    note: str | None = None
    alternative: StoreRef | None = None
    """حديث في المخزن يؤدي المعنى بلفظ ثابت أو مروي (v2.5): «ما الذي أقوله بدلًا منه؟»."""


class KnownWeakRepo(Protocol):
    @property
    def info(self) -> SourceInfo: ...

    def all(self) -> list[KnownWeak]: ...

    def get(self, item_id: str) -> KnownWeak | None: ...


class ReferenceLinker(Protocol):
    def hadith_search_url(self, text: str) -> str: ...

    def fiqh_search_url(self, text: str) -> str: ...
