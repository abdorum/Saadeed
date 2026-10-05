# سديد — حاوية واحدة (ADR-0012): النواة + FastAPI (/v1) + الواجهة الثابتة (/).
# البيانات تُبنى داخل الصورة من مصادرها الرسمية (Tanzil وOpen-Hadith-Data) بأمر واحد.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

RUN pip install "uv==0.12.1"

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra api

COPY prompts ./prompts
COPY data/manifest.toml data/manifest.tanzil.toml data/known_weak.json ./data/
COPY data/vendor ./data/vendor
COPY web ./web
COPY eval/reports/dev_v4c_saadeed-B0.json ./eval/reports/dev_v4c_saadeed-B0.json

# المصحف والكتب الستة: تنزيل وبناء، ثم حذف الخام الكبير (يبقى المعالَج وحده).
RUN uv run --no-sync saadeed data build && \
    rm -rf data/raw/open_hadith && \
    chmod -R a+rX /app

# Hugging Face Spaces يشغّل الحاوية بمستخدم غير جذري على المنفذ 7860.
EXPOSE 7860
CMD ["uv", "run", "--no-sync", "uvicorn", "saadeed.adapters.api.app:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers"]
