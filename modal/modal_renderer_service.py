"""
modal_renderer_service.py — Renderer Service: Qwen3-4B on GPU for T2 VCO generation.

GPU preference: L4 → A10G → T4. Always warm (min_containers=1).
Supports SSE streaming, asyncio-safe lock serialisation, and cost-aware routing.

Tasks: 7.1, 7.2, 7.3, 7.4
Requirements: 8.1–8.10, 14.7, 15.3, 21.2, 22.4, 23.4, 24.4–24.6,
              26.1–26.6, 27.1, 27.5, 28.1–28.6, 29.4, 29.6–29.7, 30.2, 30.4
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
app = modal.App("jimsai-renderer-service")
volume = modal.Volume.from_name("jimsai-models", create_if_missing=True)
secret = modal.Secret.from_name("modal-jimsai-secrets")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands([
        "apt-get update -qq && apt-get install -y --no-install-recommends "
        "build-essential cmake git wget gnupg",
        "wget -qO /tmp/cuda-keyring.deb "
        "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb "
        "&& dpkg -i /tmp/cuda-keyring.deb "
        "&& apt-get update -qq "
        "&& apt-get install -y cuda-toolkit-12-3 --no-install-recommends",
        # Persist stub symlink and register with ldconfig so all link steps find libcuda.so.1
        "ln -sf /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1 "
        "&& echo '/usr/local/cuda/lib64/stubs' > /etc/ld.so.conf.d/cuda-stubs.conf "
        "&& ldconfig",
        # Build llama-cpp-python 0.3.9 from source — Qwen3 GGUF supported from 0.3.5+
        # cache-bust: llama-cpp-python-0.3.9-qwen3-fix
        "export PATH=/usr/local/cuda/bin:$PATH && "
        "export CUDACXX=/usr/local/cuda/bin/nvcc && "
        "CMAKE_ARGS='-DGGML_CUDA=on -DGGML_AVX=off -DGGML_AVX2=off "
        "-DGGML_F16C=off -DGGML_FMA=off' "
        "pip install 'llama-cpp-python==0.3.9' --no-cache-dir --no-binary llama-cpp-python && "
        "echo 'llama-cpp-python-0.3.9-qwen3-fix'",
    ])
    .pip_install([
        "modal>=1.0", "fastapi>=0.111", "uvicorn>=0.30",
        "huggingface-hub>=0.23", "pydantic>=2.7",
        "python-dotenv>=1.0", "torch>=2.3",
    ])
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
    model: str = "qwen-4b"
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
    # Qwen3 outputs think...done or </think>...</think> blocks
    text = re.sub(r"think.*?done", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"think.*?done", "", text, flags=re.DOTALL).strip()
    return text.strip()

def _extract_json(text: str) -> str:
    s, e = text.find("{"), text.rfind("}")
    return text[s:e + 1] if s != -1 and e > s else text

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
_svc_metrics = create_metrics("renderer", is_gpu_service=True)

# ---------------------------------------------------------------------------
# Modal class
# ---------------------------------------------------------------------------
@app.cls(
    image=image,
    volumes={"/vol/models": volume},
    secrets=[secret],
    gpu="l4",
    min_containers=0,
    max_containers=2,
    memory=16384,
)
class RendererService:
    """Qwen3-4B on GPU — T2 rendering/streaming service."""

    _llm = None
    _lock: threading.Lock | None = None
    _model_loaded: bool = False
    _volume_mounted: bool = False
    _container_start_time: float = 0.0
    _queue_depth: int = 0

    @modal.enter()
    def enter(self) -> None:
        """Load Qwen3-4B from volume; validate GPU. Reqs: 7.4,7.7,22.4,22.6,23.4,30.2,30.4"""
        import torch
        from llama_cpp import Llama
        from shared.modal_common import ensure_model_on_volume, ARTIFACT_REGISTRY

        self._container_start_time = time.time()
        try:
            if not torch.cuda.is_available():
                raise RuntimeError("GPU not available — Renderer_Service requires CUDA")
            if not os.path.isdir("/vol/models"):
                raise RuntimeError("Volume not mounted: /vol/models")
            self._volume_mounted = True

            ensure_model_on_volume(ARTIFACT_REGISTRY["qwen-4b"])

            result: list = []
            error: list = []

            def _load():
                try:
                    result.append(Llama(
                        model_path="/vol/models/generation/Qwen3-4B-Q4_K_M.gguf",
                        n_ctx=8192, n_gpu_layers=-1, verbose=False,
                    ))
                except Exception as exc:
                    error.append(exc)

            t = threading.Thread(target=_load, daemon=True)
            t0 = time.time()
            t.start()
            t.join(120)
            if t.is_alive():
                raise RuntimeError("Qwen3-4B load timed out after 120 s")
            if error:
                raise RuntimeError(f"Qwen3-4B load failed: {error[0]}")

            self._llm = result[0]
            self._lock = threading.Lock()
            _svc_metrics.record_model_load("qwen-4b", (time.time() - t0) * 1000)
            self._model_loaded = True
            logger.info("Model ready: qwen-4b")
        except Exception as exc:
            raise RuntimeError(f"Renderer_Service startup failed: {exc}") from exc
        logger.info("Container ready — accepting requests")

    @modal.method()
    def generate(self, request: GenerateRequest):
        """Streaming or non-streaming generation. Reqs: 8.1–8.10,26.1–26.6,27.1,27.5"""
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
                                logger.error("GGUF hard failure (renderer): %s", exc, exc_info=True)
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
                            logger.error("GGUF hard failure (renderer): %s", exc, exc_info=True)
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
                        response=content, model="qwen-4b",
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
        """Extended health. Reqs: 24.6,28.1–28.6,29.4"""
        import torch
        from shared.modal_common import build_health_payload
        gpu_ok = torch.cuda.is_available() and self._llm is not None
        return build_health_payload(
            service_name="renderer",
            models_loaded=self._model_loaded and gpu_ok,
            gpu_available=torch.cuda.is_available(),
            volume_mounted=self._volume_mounted,
            container_start_time=self._container_start_time,
        )

    @modal.method()
    def metrics(self) -> str:
        """Prometheus metrics. Reqs: 29.4,29.6,29.7"""
        from shared.metrics import render_prometheus_text
        return render_prometheus_text(_svc_metrics)


# ---------------------------------------------------------------------------
# FastAPI web app
# ---------------------------------------------------------------------------
web_app = FastAPI(title="JIMS-AI Renderer Service")

@web_app.post("/generate")
async def route_generate(request: GenerateRequest, _token: str = Depends(require_bearer_token)):
    svc = RendererService()
    return await svc.generate.remote.aio(request)

@web_app.get("/health")
async def route_health():
    svc = RendererService()
    return await svc.health.remote.aio()

@web_app.get("/metrics")
async def route_metrics():
    svc = RendererService()
    return Response(content=await svc.metrics.remote.aio(), media_type="text/plain; version=0.0.4")

@app.function(image=image, volumes={"/vol/models": volume}, secrets=[secret],
              gpu="l4")
@modal.asgi_app()
def fastapi_app():
    return web_app
