"""محوّل OpenRouter (واجهة متوافقة مع OpenAI): النموذج الاحتياطي إن تعذّر Gemini.

نماذج مجانية، ومعها قائمة بدائل يوجّه إليها OpenRouter نفسه إن ازدحم الأول.
"""

from __future__ import annotations

from saadeed.adapters.llm.groq import GroqLLM

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
FALLBACK_MODELS = ["google/gemma-4-31b-it:free", "nvidia/nemotron-3-ultra-550b-a55b:free"]


class OpenRouterLLM(GroqLLM):
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 90.0) -> None:
        super().__init__(api_key, model, timeout=timeout, max_retries=4)
        self._url = OPENROUTER_URL

    @property
    def model_id(self) -> str:
        return f"openrouter:{self._model}"

    def _payload(self, system: str, user: str, max_tokens: int) -> dict:
        return {
            "model": self._model,
            "models": [self._model, *FALLBACK_MODELS],
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
