"""محوّل HTTP (FR-71، ADR-0012): FastAPI على `/v1`، ويخدم الواجهة الثابتة `web/` على `/`.

- **لا تُخزَّن المسودات ولا تُسجَّل نصوصها** (NFR-08): ذاكرة النداءات هنا في الذاكرة فقط، ومحدودة الحجم.
- **حد معدل لكل عنوان** (NFR-09).
- **«الفحص السريع»** (`mode=quick`): المسار الحتمي وحده، بلا نموذج، فوري. تعرضه الواجهة أولًا
  ثم تستبدل به التقرير الكامل حين يكتمل، فلا ينتظر الخطيب صامتًا.
- الواجهة نفسها تستهلك `/v1/reviews`، فالفصل السداسي محفوظ: المحوّل لا يعرف إلا حالة الاستخدام.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict, defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from saadeed import __version__
from saadeed.adapters.bootstrap import ROOT
from saadeed.adapters.factory import Engine, build_engine, build_llm
from saadeed.application.review_draft import MAX_WORDS, DraftError, ReviewConfig
from saadeed.domain.policy import POLICY_VERSION
from saadeed.domain.ports import LLMError, LLMPort, LLMResponse

WEB_DIR = Path(os.environ.get("SAADEED_WEB_DIR", ROOT / "web"))
RESULTS_FILE = Path(
    os.environ.get("SAADEED_RESULTS", ROOT / "eval" / "reports" / "dev_v4c_saadeed-B0.json")
)
RATE_LIMIT = int(os.environ.get("SAADEED_RATE_LIMIT", "12"))
"""عدد المراجعات الكاملة لكل عنوان في الدقيقة."""
MAX_CHARS = 40_000

POLICIES = [
    "لا يُولِّد سديد نص آية أو حديث: كل نص شرعي معروض مجلوب من المخزن بمعرّفه.",
    "لا يحكم سديد على حديث: الحكم منقول بلفظ مصدره ونسبته، و«لم يُعثر عليه» لا تعني «لا يصح».",
    "لا يُفتي سديد ولا يحكم على الأشخاص والجماعات: يحيل إلى المختص.",
    "لا يعيد سديد كتابة المسودة. واقتراح الصياغة للتعميم والإجماع وحدهما، موسوم «مولَّد»، وله حارس.",
    "لا تُخزَّن المسودات ولا تُسجَّل نصوصها.",
    "كل تقرير يحمل معرّف ملف المرجعية وبصمته: بماذا فُحصت المسودة بالضبط.",
]


class MemoryCachedLLM:
    """ذاكرة نداءات **في الذاكرة فقط** (لا قرص): المسودة نفسها تعطي التقرير نفسه، دون حفظ نصها."""

    def __init__(self, inner: LLMPort, maxsize: int = 128) -> None:
        self.inner = inner
        self.maxsize = maxsize
        self._store: OrderedDict[str, LLMResponse] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def model_id(self) -> str:
        return self.inner.model_id

    def generate_json(self, *, system: str, user: str, max_tokens: int = 4096) -> LLMResponse:
        key = hashlib.sha256(
            json.dumps([self.model_id, system, user, max_tokens], ensure_ascii=False).encode()
        ).hexdigest()
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                return self._store[key]
        resp = self.inner.generate_json(system=system, user=user, max_tokens=max_tokens)
        with self._lock:
            self._store[key] = resp
            while len(self._store) > self.maxsize:
                self._store.popitem(last=False)
        return resp


class RateLimiter:
    """نافذة منزلقة بسيطة لكل عنوان. تكفي لحماية الحصة المجانية من العبث."""

    def __init__(self, limit: int, window_s: float = 60.0) -> None:
        self.limit, self.window = limit, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


class ReviewRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_CHARS, description="نص المسودة")
    mode: Literal["full", "quick"] = Field(
        "full", description="full: التقرير الكامل · quick: المسار الحتمي وحده (فوري، بلا نموذج)"
    )
    overreach: bool = Field(False, description="فحص التجاوز (تجريبي، FR-36)")


class _State:
    engine: Engine | None = None
    llm: LLMPort | None = None
    llm_error: str | None = None
    limiter = RateLimiter(RATE_LIMIT)


state = _State()


def _init() -> None:
    if state.engine is not None:
        return
    state.engine = build_engine()
    try:
        inner = build_llm()
        state.llm = MemoryCachedLLM(inner) if inner is not None else None
    except LLMError as e:  # الفشل الآمن: يبقى المسار الحتمي يعمل
        state.llm, state.llm_error = None, str(e)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _init()
    yield


app = FastAPI(
    title="سديد — واجهة برمجية",
    version=__version__,
    description="مراجِع ما قبل النشر للمسودات الدعوية العربية. التقرير بمخطط Report 1.1.",
    docs_url="/v1/docs",
    openapi_url="/v1/openapi.json",
    redoc_url=None,
    lifespan=lifespan,
)


def _engine() -> Engine:
    _init()
    assert state.engine is not None
    return state.engine


@app.get("/v1/health", summary="حالة الخدمة")
def health() -> dict[str, Any]:
    eng = _engine()
    return {
        "ok": True,
        "name": "saadeed",
        "version": __version__,
        "policy_version": POLICY_VERSION,
        "manifest": eng.sources.manifest.stamp.model_dump(),
        "llm": state.llm.model_id if state.llm else "none",
        "llm_error": state.llm_error,
        "max_words": MAX_WORDS,
    }


@app.get("/v1/coverage", summary="ما يغطيه سديد (من ملف المرجعية)")
def coverage() -> dict[str, Any]:
    eng = _engine()
    m = eng.sources.manifest
    return {
        "manifest": m.stamp.model_dump(),
        "sources": [s.model_dump(mode="json") for s in eng.sources.coverage.sources],
        "connectors": [
            {
                "id": e.id,
                "adapter": e.adapter,
                "role": e.role.value,
                "role_ar": e.role.label_ar,
                "name_ar": e.name_ar,
                "version": e.version,
                "license": e.license,
            }
            for e in m.sources
        ],
        "policies": POLICIES,
    }


@app.get("/v1/results", summary="كيف نعرف أن سديد يعمل؟ (أحدث تقرير تقييم)")
def results() -> dict[str, Any]:
    if not RESULTS_FILE.exists():
        raise HTTPException(404, "لا تقرير تقييم في هذه النسخة")
    m = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))["metrics"]
    keep = (
        "detection",
        "detection_ci",
        "false_alarm",
        "false_alarm_ci",
        "precision",
        "critical_missed",
        "critical_total",
        "fabricated_citations",
        "false_accusation_H8",
        "mandatory_referral",
        "extraction_recall",
        "by_group",
        "latency_p50_ms",
        "tokens",
    )
    return {
        "split": m["split"],
        "n_cases": m["n_cases"],
        "carriers": m["carriers"],
        "model": m["model"],
        "prompt_versions": m["prompt_versions"],
        "generated_at": m["generated_at"],
        "systems": {name: {k: s.get(k) for k in keep} for name, s in m["systems"].items()},
        "mcnemar": m.get("mcnemar_saadeed_vs_B0"),
        "source_file": RESULTS_FILE.name,
    }


@app.post("/v1/reviews", summary="راجِع مسودة")
def review(req: ReviewRequest, request: Request) -> JSONResponse:
    client = request.headers.get("x-forwarded-for", request.client.host if request.client else "-")
    client = client.split(",")[0].strip()
    if req.mode == "full" and not state.limiter.allow(client):
        raise HTTPException(429, "طلبات كثيرة في دقيقة واحدة. انتظر قليلًا ثم أعد المحاولة.")
    eng = _engine()
    llm = state.llm if req.mode == "full" else None
    reviewer = eng.reviewer(llm, ReviewConfig(enable_overreach=req.overreach))
    try:
        report = reviewer.review(req.text)
    except DraftError as e:
        raise HTTPException(422, str(e)) from e
    payload = report.model_dump(mode="json")
    payload["mode"] = req.mode
    return JSONResponse(payload)


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
