"""نموذج أساسي ونموذج احتياطي: إن فشل الأساسي (مفتاح، أو حصة، أو شبكة) أُعيد النداء على الاحتياطي.

المعرّف (model_id) معرّف الأساسي، فتبقى التسجيلات كما هي. والنموذج الذي أجاب فعلًا في `LLMResponse.model`.
"""

from __future__ import annotations

import sys
import threading
import time

from saadeed.domain.ports import LLMError, LLMPort, LLMResponse


class FallbackLLM:
    # بعد فشل الأساسي يُتجاوز مدةً (قاطع الدائرة)، فلا يدفع كل نداء ثمن انتظار نموذج معطّل.
    _down_until: float = 0.0
    _lock = threading.Lock()
    COOLDOWN = 300.0

    def __init__(self, primary: LLMPort, backup: LLMPort) -> None:
        self.primary = primary
        self.backup = backup

    @property
    def model_id(self) -> str:
        return self.primary.model_id

    def generate_json(self, *, system: str, user: str, max_tokens: int = 4096) -> LLMResponse:
        if time.monotonic() >= FallbackLLM._down_until:
            try:
                return self.primary.generate_json(system=system, user=user, max_tokens=max_tokens)
            except LLMError as e:
                with FallbackLLM._lock:
                    FallbackLLM._down_until = time.monotonic() + self.COOLDOWN
                print(
                    f"fallback: {self.primary.model_id} فشل ({str(e)[:80]})، والنداء على {self.backup.model_id}",
                    file=sys.stderr,
                )
        return self.backup.generate_json(system=system, user=user, max_tokens=max_tokens)
