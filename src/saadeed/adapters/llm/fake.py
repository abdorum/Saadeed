"""محوّل مزيف للاختبارات: سريع ومجاني وحتمي. ومحوّل معطّل لاختبار الفشل الآمن."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from saadeed.domain.ports import LLMError, LLMResponse


class FakeLLM:
    def __init__(self, handler: Callable[[str, str], dict[str, Any]]) -> None:
        self._handler = handler
        self.requests: list[tuple[str, str]] = []

    @property
    def model_id(self) -> str:
        return "fake"

    def generate_json(self, *, system: str, user: str, max_tokens: int = 4096) -> LLMResponse:
        self.requests.append((system, user))
        return LLMResponse(data=self._handler(system, user), model="fake")


class BrokenLLM:
    """يرمي استثناءً دائمًا (اختبار م١٦: الفشل الآمن)."""

    @property
    def model_id(self) -> str:
        return "broken"

    def generate_json(self, *, system: str, user: str, max_tokens: int = 4096) -> LLMResponse:
        raise LLMError("النموذج معطّل عمدًا")
