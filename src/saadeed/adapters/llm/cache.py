"""ذاكرة النداءات: التخزين المؤقت، والتسجيل، والإعادة دون مفتاح (ADR-0003، FR-83، م١٥).

المفتاح = بصمة (النموذج + التعليمات + المدخل + الملح). فالمدخل نفسه يعطي الاستجابة نفسها حرفيًا.
والملح يُستعمل في تشغيلات الاتساق (k) لنطلب استجابات جديدة عمدًا.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from saadeed.domain.ports import LLMError, LLMPort, LLMResponse, LLMUsage


class CachedLLM:
    """يلفّ أي محوّل نموذج. الأوضاع: use (قراءة وكتابة) · replay (قراءة فقط) · off."""

    def __init__(
        self,
        inner: LLMPort | None,
        cache_dir: Path,
        mode: str = "use",
        salt: str = "",
        model_id: str | None = None,
    ) -> None:
        if mode not in ("use", "replay", "off"):
            raise ValueError(mode)
        if inner is None and mode != "replay":
            raise ValueError("لا محوّل نموذج، والوضع ليس replay")
        self.inner = inner
        self.dir = cache_dir
        self.mode = mode
        self.salt = salt
        self._model_id = model_id or (inner.model_id if inner else "replay")
        self.calls = 0
        self.hits = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    def _key(self, system: str, user: str, max_tokens: int) -> str:
        blob = json.dumps([self._model_id, system, user, max_tokens, self.salt], ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def generate_json(self, *, system: str, user: str, max_tokens: int = 4096) -> LLMResponse:
        key = self._key(system, user, max_tokens)
        path = self.dir / key[:2] / f"{key}.json"
        if self.mode in ("use", "replay") and path.exists():
            self.hits += 1
            rec = json.loads(path.read_text(encoding="utf-8"))
            resp = LLMResponse(**rec["response"])
            return resp.model_copy(
                update={"usage": LLMUsage(**{**resp.usage.model_dump(), "cached": True})}
            )
        if self.mode == "replay":
            raise LLMError(f"وضع الإعادة: لا تسجيل لهذا المدخل ({key[:12]})")
        assert self.inner is not None
        self.calls += 1
        resp = self.inner.generate_json(system=system, user=user, max_tokens=max_tokens)
        if self.mode == "use":
            path.parent.mkdir(parents=True, exist_ok=True)
            rec = {
                "model": self._model_id,
                "salt": self.salt,
                "user_sha256": hashlib.sha256(user.encode()).hexdigest(),
                "response": resp.model_dump(),
            }
            path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        return resp
