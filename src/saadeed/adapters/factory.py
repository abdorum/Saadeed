"""تركيب سديد كاملًا: المصادر + النموذج + المتحققات + حالة الاستخدام."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saadeed.adapters.bootstrap import (
    DATA_DIR,
    PROMPTS_DIR,
    ROOT,
    SourceBundle,
    load_env,
    load_sources,
)
from saadeed.adapters.llm.cache import CachedLLM
from saadeed.application.citation_guard import CitationGuard
from saadeed.application.prompts import PromptSet
from saadeed.application.review_draft import ReviewConfig, ReviewDraft
from saadeed.domain.ports import LLMError, LLMPort
from saadeed.verifiers.hadith import HadithIndex, HadithVerifier
from saadeed.verifiers.quran import QuranIndex, QuranVerifier

DEFAULT_MODELS = {"groq": "openai/gpt-oss-120b", "gemini": "gemini-3.5-flash-lite"}


def build_llm(
    provider: str | None = None, model: str | None = None, api_key: str | None = None
) -> LLMPort | None:
    """يختار محوّل النموذج من الإعداد. تبديل المزود = تغيير متغير بيئة.

    `api_key` مفتاح يمرّره المستخدم مع طلبه (صفحة الإعدادات)، فيُقدَّم على مفتاح الخادم ولا يُحفظ.
    """
    load_env()
    provider = (provider or os.environ.get("SAADEED_LLM_PROVIDER", "gemini")).lower()
    model = model or os.environ.get("SAADEED_LLM_MODEL") or DEFAULT_MODELS.get(provider)
    if provider == "none":
        return None
    if provider == "groq":
        from saadeed.adapters.llm.groq import GroqLLM

        return GroqLLM(
            api_key or os.environ.get("GROQ_API_KEY", ""), model or DEFAULT_MODELS["groq"]
        )
    if provider == "gemini":
        from saadeed.adapters.llm.gemini import GeminiLLM

        return GeminiLLM(
            api_key or os.environ.get("GEMINI_API_KEY", ""), model or DEFAULT_MODELS["gemini"]
        )
    raise LLMError(f"مزود غير معروف: {provider}")


@dataclass
class Engine:
    sources: SourceBundle
    quran: QuranVerifier
    hadith: HadithVerifier
    prompts: PromptSet

    def reviewer(
        self,
        llm: LLMPort | None,
        config: ReviewConfig | None = None,
        quran_llm_judge=None,
        live: bool = False,
    ) -> ReviewDraft:
        """`live`: وصلات حية وقت المراجعة (مكتبة تراث للأقوال المنسوبة). التقييم يعمل بدونها."""
        texts: dict = {s.info.id: s for s in self.sources.hadith_sources}
        library = None
        if live and os.environ.get("SAADEED_LIBRARY", "turath") != "off":
            from saadeed.adapters.sources.turath import TurathLibrary

            library = TurathLibrary()
            texts[library.source_id] = library
        guard = CitationGuard(self.sources.quran, texts, self.sources.known_weak)
        return ReviewDraft(
            llm=llm,
            quran=self.quran,
            hadith=self.hadith,
            guard=guard,
            prompts=self.prompts,
            coverage=self.sources.coverage,
            manifest=self.sources.manifest.stamp,
            config=config,
            quran_llm_judge=quran_llm_judge,
            library=library,
        )


@lru_cache(maxsize=1)
def build_engine(data_dir: Path = DATA_DIR, prompts_dir: Path = PROMPTS_DIR) -> Engine:
    """يبني الفهارس مرة واحدة (نحو ثانيتين)، ثم يُعاد استعمالها لكل مسودة."""
    sources = load_sources(data_dir)
    quran = QuranVerifier(sources.quran, QuranIndex(sources.quran))
    hadith = HadithVerifier(HadithIndex(sources.hadith_sources), sources.known_weak, sources.linker)
    return Engine(sources, quran, hadith, PromptSet.load(prompts_dir))


def configured_model_id(provider: str | None = None, model: str | None = None) -> str:
    """معرّف النموذج المضبوط في الإعداد، دون إنشاء اتصال (لوضع الإعادة بلا مفتاح)."""
    load_env()
    provider = (provider or os.environ.get("SAADEED_LLM_PROVIDER", "gemini")).lower()
    model = model or os.environ.get("SAADEED_LLM_MODEL") or DEFAULT_MODELS.get(provider, "")
    return f"{provider}:{model}"


def cached(
    llm: LLMPort | None, mode: str = "use", salt: str = "", cache_dir: Path | None = None
) -> LLMPort | None:
    if llm is None and mode != "replay":
        return None
    load_env()
    # متغير فارغ في .env («SAADEED_CACHE_DIR=») يعني الافتراضي، لا جذر المستودع.
    d = cache_dir or Path(os.environ.get("SAADEED_CACHE_DIR") or ROOT / ".cache" / "llm")
    if not d.is_absolute():
        d = ROOT / d
    model_id = llm.model_id if llm is not None else configured_model_id()
    return CachedLLM(llm, d, mode=mode, salt=salt, model_id=model_id)
