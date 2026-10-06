"""محوّل Groq (واجهة متوافقة مع OpenAI) عبر httpx.

- درجة حرارة 0، وبذرة ثابتة، ومخرجات JSON إلزامية.
- احترام حدود المعدل: عند 429 ننتظر بحسب ترويسات Groq ثم نعيد.
- نماذج الاستدلال (gpt-oss وqwen3): نخفض جهد الاستدلال لأن مهامنا استخراج لا تأمل، ولأن الرموز محدودة.
"""

from __future__ import annotations

import json
import re
import time

import httpx

from saadeed.domain.ports import LLMError, LLMResponse, LLMUsage

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def _parse_reset(value: str | None) -> float:
    """«1m26.4s» أو «13.56s» أو «250ms» ← ثوانٍ."""
    if not value:
        return 0.0
    total = 0.0
    for num, unit in re.findall(r"([\d.]+)(ms|s|m|h)", value):
        total += float(num) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return total


def parse_json_content(content: str) -> dict:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        m = _JSON_BLOCK.search(content or "")
        if not m:
            raise LLMError("الاستجابة ليست JSON") from None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise LLMError(f"JSON معطوب: {e}") from e
    if isinstance(data, list):
        data = {"items": data}
    if not isinstance(data, dict):
        raise LLMError("JSON ليس كائنًا")
    return data


class GroqLLM:
    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        timeout: float = 120.0,
        max_retries: int = 6,
    ) -> None:
        if not api_key:
            raise LLMError("GROQ_API_KEY غير موجود في البيئة أو .env")
        self._key = api_key
        self._model = model
        self._client = httpx.Client(timeout=timeout)
        self._retries = max_retries
        self._url = GROQ_URL

    @property
    def model_id(self) -> str:
        return f"groq:{self._model}"

    def _payload(self, system: str, user: str, max_tokens: int) -> dict:
        body: dict = {
            "model": self._model,
            "temperature": 0,
            "seed": 70,
            "max_completion_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self._model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
            body["include_reasoning"] = False
        elif self._model.startswith("qwen/"):
            body["reasoning_effort"] = "none"
        return body

    def generate_json(self, *, system: str, user: str, max_tokens: int = 4096) -> LLMResponse:
        body = self._payload(system, user, max_tokens)
        last_err = ""
        for attempt in range(self._retries):
            try:
                r = self._client.post(
                    self._url, json=body, headers={"Authorization": f"Bearer {self._key}"}
                )
            except httpx.HTTPError as e:
                last_err = f"شبكة: {e}"
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 429:
                wait = max(
                    _parse_reset(r.headers.get("retry-after") and f"{r.headers['retry-after']}s"),
                    _parse_reset(r.headers.get("x-ratelimit-reset-tokens")),
                    2.0,
                )
                if "day" in r.text.lower() and wait > 120:
                    raise LLMError(f"نفدت الحصة اليومية لـ {self._model}")
                time.sleep(min(wait + 0.5, 90))
                continue
            if r.status_code >= 500:
                last_err = f"خادم {r.status_code}"
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code != 200:
                # json_validate_failed وأمثاله: نعيد المحاولة مرة، فالنموذج قد يُصلح مخرجه.
                last_err = f"{r.status_code}: {r.text[:300]}"
                if r.status_code == 400 and "json" in r.text.lower() and attempt < 2:
                    continue
                raise LLMError(last_err)
            data = r.json()
            content = data["choices"][0]["message"].get("content") or ""
            usage = data.get("usage", {})
            return LLMResponse(
                data=parse_json_content(content),
                model=self.model_id,
                usage=LLMUsage(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                ),
            )
        raise LLMError(f"فشل النداء بعد {self._retries} محاولات: {last_err}")
