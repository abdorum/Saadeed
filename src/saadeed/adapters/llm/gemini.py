"""محوّل Gemini (google-genai). يُفعَّل بـ SAADEED_LLM_PROVIDER=gemini.

يتطلب: متغير GEMINI_API_KEY (المكتبة من التثبيت الأساسي).
"""

from __future__ import annotations

import time

from saadeed.adapters.llm.groq import parse_json_content
from saadeed.domain.ports import LLMError, LLMResponse, LLMUsage


class GeminiLLM:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", max_retries: int = 5) -> None:
        if not api_key:
            raise LLMError("GEMINI_API_KEY غير موجود في البيئة أو .env")
        try:
            from google import genai  # استيراد متأخر: النواة لا تعرف المزود
        except ImportError as e:  # pragma: no cover
            raise LLMError("ثبّت المزود: uv sync") from e
        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._retries = max_retries

    @property
    def model_id(self) -> str:
        return f"gemini:{self._model}"

    def generate_json(self, *, system: str, user: str, max_tokens: int = 4096) -> LLMResponse:
        types = self._genai.types
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            seed=70,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        )
        last = ""
        for attempt in range(self._retries):
            try:
                resp = self._client.models.generate_content(
                    model=self._model, contents=user, config=config
                )
                meta = resp.usage_metadata
                return LLMResponse(
                    data=parse_json_content(resp.text or ""),
                    model=self.model_id,
                    usage=LLMUsage(
                        prompt_tokens=getattr(meta, "prompt_token_count", 0) or 0,
                        completion_tokens=getattr(meta, "candidates_token_count", 0) or 0,
                    ),
                )
            except LLMError:
                raise
            except Exception as e:  # أخطاء المزود متنوعة؛ نعيد المحاولة ثم نعلن الفشل الآمن
                last = str(e)[:300]
                time.sleep(min(2 ** (attempt + 1), 30))
        raise LLMError(f"فشل Gemini: {last}")
