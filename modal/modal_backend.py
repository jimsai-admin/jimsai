"""
modal_backend.py — Modal ASGI wrapper for the JIMS-AI FastAPI backend.

Replaces the AWS Lambda + api-gateway deployment. Wraps prototype/app.py as
a Modal ASGI endpoint with Modal Secrets, scaling config, and cost-aware
routing to the five Modal AI services.

Tasks: 10.1, 10.2 (call-site wiring), 10.3 (routing), 10.4 (timeouts), 10.6 (health/metrics)
Requirements: 2.2, 9.1, 9.6, 13.4, 13.8, 14.4, 24.6, 28.1, 29.6, 29.8

# ── Timeout environment variables (picked up from modal-jimsai-secrets) ──────
#
# JIMS_EMBEDDING_TIMEOUT    (default 8 s)  — wraps all Embedding_Service calls.
#                           Used in provider_adapters.py ExternalMultimodalEncoderAdapter.
# JIMS_GENERATION_TIMEOUT   (default 120 s) — wraps all Intent/Renderer/Reasoning calls.
#                           Used in model_bridge.py _local_chat_json and _render_chat_json.
# JIMS_PROVIDER_HTTP_TIMEOUT (default 8 s) — general HTTP timeout for provider adapters.
# JIMS_LOCAL_INFERENCE_TIMEOUT (default 120 s) — legacy fallback for model_bridge.py.
#
# ── Health / Metrics note ─────────────────────────────────────────────────────
#
# The backend does NOT mount a Modal Volume and does NOT have a GPU.
# /health and /metrics are served directly by prototype/app.py:
#   GET /health  → returns {"status": "ok", "service": ..., "deterministic": true}
#   GET /metrics → returns Prometheus text format with basic service_up counter
#
# The backend is CPU-only, stateless (no volume), and horizontally scalable.
# GPU metrics (first-token latency, TPS) are exposed by Renderer/Reasoning services
# at their own /metrics endpoints.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure prototype/ and modal/ are importable inside the container
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "prototype"))
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(Path(__file__).parent))

import modal

app = modal.App("jimsai-backend")
secret = modal.Secret.from_name("modal-jimsai-secrets")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install([
        "modal>=1.0",
        "fastapi>=0.111",
        "uvicorn>=0.30",
        "httpx>=0.27",
        "pydantic>=2.7",
        "python-dotenv>=1.0",
        "supabase>=2.0",
        "neo4j>=5.0",
        "numpy>=1.26",
        "sentence-transformers>=2.7",
        "transformers>=4.41",
        "torch>=2.3",
        "huggingface-hub>=0.23",
        "sympy>=1.12",
        "z3-solver>=4.12",
    ])
)


@app.function(
    image=image,
    secrets=[secret],
    min_containers=1,
    max_containers=10,
    memory=1024,
)
@modal.asgi_app()
def fastapi_app():
    """Serve the existing prototype FastAPI app as a Modal ASGI endpoint.

    All /v1/... routes remain identical — no frontend changes required.
    Requirements: 2.1, 2.2, 2.3, 9.1
    """
    from app import app as prototype_app  # prototype/app.py
    return prototype_app
