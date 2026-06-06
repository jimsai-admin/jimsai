# infrastructure/fly/Dockerfile
# Production image for JimsAI API Gateway on Fly.io
#
# Build context = repo root (fly.toml is at repo root)
# All COPY paths are relative to the repo root.
#
# sentence-transformers / PyTorch intentionally excluded:
#   - Embeddings → HF Space (jimstechai-jimsai-embedding-service.hf.space)
#   - T1/T2 inference → HF Space
#   - No GPU needed on Fly — keeps image under 500 MB

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# ── System deps ───────────────────────────────────────────────────────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# ── Python deps ───────────────────────────────────────────────────────────────
COPY infrastructure/fly/requirements.fly.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.txt

# ── App code ──────────────────────────────────────────────────────────────────
COPY prototype /app/prototype
COPY services/api-gateway/app /app/app

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8080

# Fly.io injects $PORT (8080 default); 2 workers handles concurrent requests
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 2 --timeout-keep-alive 120"]
