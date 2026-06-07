"""
modal_reasoning_service.py — Reasoning Service: Qwen3-8B on GPU, scale-to-zero.

GPU preference: A100 → L4 → A10G. min_containers=0 (cost-efficient specialist).
Only activated for: invention engine, low confidence, deep planning, explicit qwen-8b.

Tasks: 9.1, 9.2, 9.3, 9.4
Requirements: 8.1–8.10, 15.3, 21.3, 22.5, 22.7, 23.5, 27.2, 27.5,
              28.1–28.4, 29.5–29.7, 30.2, 30.4
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import modal
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from shared.auth_middleware import require_bearer_token
from shared.metrics import create_metrics

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Modal primitives
# ---------------------------------------------------------------------------
app = modal.App("jimsai-reasoning-service")
volume = modal.Volume.from_name("jimsai-models", create_if_missing=True)
secret = modal.Secret.from_name("modal-jimsai-secrets")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands([
        "apt-get update && apt-get install -y --no-install-recommends build-essential cmake 2>/dev/null || true"
    ])
    .env({"CMAKE_ARGS": "-DGGML_CUDA=on", "FORCE_CMAKE": "1"})
    .pip_install([
        "modal>=1.0", "fastapi>=0.111", "uvicorn>=0.30",
        "huggingface-hub>=0.23", "pydantic>=2.7",
        "python-dotenv>=1.0", "torch>=2.3",
    ])
    .pip_install(["llama-cpp-python>=0.2.90"])
    .add_local_dir(
        str(Path(__file__).parent / "shared"),
        remote_path="/root/shared",
    )
)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str

class GenerateRequest(BaseModel):
    model: str = "qwen-8b"
    prompt: str | None = None
    messages: list[ChatMessage] | None = None
    temperature: float = 0.0
    max_tokens: int = 1200
    stream: bool = False
    response_format: dict | None = None

class GenerateResponse(BaseModel):
    response: str
    model: str
    usage: dict
    finish_reason: str

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

def _extract_json(text: str) -> str:
    s, e = text.find("{"), text.rfind("}")
    return text[s:e + 1] if s != -1 and e > s else text

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
_svc_metrics = create_metrics("reasoning", is_gpu_service=True)

# ---------------------------------------------------------------------------
# Modal class
# ---------------------------------------------------------------------------
@app.cls(
    image=image,
    volumes={"/vol/models": volume},
    secrets=[secret],
    gpu=modal.gpu.Any(ordered=["A100", "L4", "A10G"]),
    min_containers=0,
    max_containers=2,
    memory=24576,
)
class ReasoningService:
    """Qwen3-8B on GPU — specialist deep reasoning, scale-to-zero."""

    _llm = None
    _lock: threading.Lock | None = None
    _model_loaded: bool = False
    _volume_mounted: bool = False
    _container_start_time: float = 0.0
    _queue_depth: int = 0

    @modal.enter()
    def enter(self) -> None:
        """Load Qwen3-8B from volume; validate GPU. Reqs: 7.1,7.5,7.8,22.5,23.7,30.2,30.4"""
        import torch
        from llama_cpp import Llama
        from shared.modal_common import ensure_model_on_volume, ARTIFACT_REGISTRY

        self._container_start_time = time.time()
        try:
            if not torch.cuda.is_available():
                raise RuntimeError("GPU not available — Reasoning_Service requires CUDA")
            if not os.path.isdir("/vol/models"):
                raise RuntimeError("Volume not mounted: /vol/models")
            self._volume_mounted = True

            ensure_model_on_volume(ARTIFACT_REGISTRY["qwen-8b"])

            result: list = []
            error: list = []

            def _load():
                try:
                    result.append(Llama(
                        model_path="/vol/models/generation/Qwen3-8B-Q4_K_M.gguf",
                        n_ctx=8192, n_gpu_layers=-1, verbose=False,
                    ))
                except Exception as exc:
                    error.append(exc)

            t = threading.Thread(target=_load, daemon=True)
            t0 = time.time()
            t.start()
            t.join(120)
            if t.is_alive():
                raise RuntimeError("Qwen3-8B load timed out after 120 s")
            if error:
                raise RuntimeError(f"Qwen3-8B load failed: {error[0]}")

            self._llm = result[0]
            self._lock = threading.Lock()
            _svc_metrics.record_model_load("qwen-8b", (time.time() - t0) * 1000)
            self._model_loaded = True
            logger.info("Model ready: qwen-8b")
        except Exception as exc:
            raise RuntimeError(f"Reasoning_Service startup failed: {exc}") from exc
        logger.info("Container ready — accepting requests")

    @modal.method()
    def generate(self, request: GenerateRequest):
        """Streaming or non-streaming generation. Reqs: 8.1–8.10,27.2,27.5"""
        if request.prompt is None and request.messages is None:
            raise HTTPException(422, "prompt or messages required")
        if self._queue_depth >= 5:
            raise HTTPException(429, "Too many requests", headers={"Retry-After": "30"})

        messages = (
            [{"role": m.role, "content": m.content} for m in request.messages]
            if request.messages
            else [{"role": "user", "content": request.prompt}]
        )

        self._queue_depth += 1
        try:
            if request.stream:
                def _sse():
                    first_recorded = False
                    total_tok = 0
                    t0 = time.time()
                    with self._lock:
                        self._queue_depth = max(0, self._queue_depth - 1)
                        try:
                            stream = self._llm.create_chat_completion(
                                messages=messages,
                                temperature=request.temperature,
                                max_tokens=request.max_tokens or 1200,
                                stream=True,
                            )
                            for chunk in stream:
                                delta = chunk["choices"][0].get("delta", {})
                                tok = delta.get("content", "")
                                fr = chunk["choices"][0].get("finish_reason")
                                if tok:
                                    if not first_recorded:
                                        _svc_metrics.record_first_token((time.time() - t0) * 1000)
                                        first_recorded = True
                                    total_tok += 1
                                    yield f'data: {json.dumps({"token": tok, "finish_reason": None})}\n\n'
                                if fr:
                                    yield f'data: {json.dumps({"token": "", "finish_reason": fr})}\n\n'
                                    yield "data: [DONE]\n\n"
                                    ms = (time.time() - t0) * 1000
                                    _svc_metrics.record_generation(ms, total_tok)
                                    _svc_metrics.record_request(ms)
                                    break
                        except Exception as exc:
                            s = str(exc)
                            if "ggml_assert" in s or "repack" in s:
                                self._llm = None
                                self._model_loaded = False
                                logger.error("GGUF hard failure (reasoning): %s", exc, exc_info=True)
                            raise
                return StreamingResponse(_sse(), media_type="text/event-stream")
            else:
                with self._lock:
                    self._queue_depth = max(0, self._queue_depth - 1)
                    t0 = time.time()
                    try:
                        completion = self._llm.create_chat_completion(
                            messages=messages,
                            temperature=request.temperature,
                            max_tokens=request.max_tokens or 1200,
                        )
                    except Exception as exc:
                        s = str(exc)
                        if "ggml_assert" in s or "repack" in s:
                            self._llm = None
                            self._model_loaded = False
                            logger.error("GGUF hard failure (reasoning): %s", exc, exc_info=True)
                            raise HTTPException(503, "Generation failed", headers={"Retry-After": "30"})
                        raise
                    content = completion["choices"][0]["message"]["content"]
                    if request.response_format and request.response_format.get("type") == "json_object":
                        content = _extract_json(_strip_think(content))
                    ms = (time.time() - t0) * 1000
                    _svc_metrics.record_first_token(ms)
                    _svc_metrics.record_generation(ms, completion["usage"]["completion_tokens"])
                    _svc_metrics.record_request(ms)
                    return GenerateResponse(
                        response=content, model="qwen-8b",
                        usage={"prompt_tokens": completion["usage"]["prompt_tokens"],
                               "completion_tokens": completion["usage"]["completion_tokens"]},
                        finish_reason=completion["choices"][0]["finish_reason"] or "stop",
                    )
        except HTTPException:
            raise
        except Exception:
            self._queue_depth = max(0, self._queue_depth - 1)
            raise

    @modal.method()
    def health(self) -> dict:
        """Extended health. Reqs: 28.1–28.4"""
        import torch
        from shared.modal_common import build_health_payload
        gpu_ok = torch.cuda.is_available() and self._llm is not None
        return build_health_payload(
            service_name="reasoning",
            models_loaded=self._model_loaded and gpu_ok,
            gpu_available=torch.cuda.is_available(),
            volume_mounted=self._volume_mounted,
            container_start_time=self._container_start_time,
        )

    @modal.method()
    def metrics(self) -> str:
        """Prometheus metrics. Reqs: 29.5,29.6,29.7"""
        from shared.metrics import render_prometheus_text
        return render_prometheus_text(_svc_metrics)


# ---------------------------------------------------------------------------
# FastAPI web app
# ---------------------------------------------------------------------------
web_app = FastAPI(title="JIMS-AI Reasoning Service")

@web_app.post("/generate")
async def route_generate(request: GenerateRequest, _token: str = Depends(require_bearer_token)):
    svc = ReasoningService()
    return svc.generate.remote(request)

@web_app.get("/health")
async def route_health():
    svc = ReasoningService()
    return svc.health.remote()

@web_app.get("/metrics")
async def route_metrics():
    svc = ReasoningService()
    return Response(content=svc.metrics.remote(), media_type="text/plain; version=0.0.4")

@app.function(image=image, volumes={"/vol/models": volume}, secrets=[secret],
              gpu=modal.gpu.Any(ordered=["A100", "L4", "A10G"]))
@modal.asgi_app()
def fastapi_app():
    return web_app
