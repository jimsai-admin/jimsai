"""
modal_intent_service.py — Modal app definition for JIMS-AI Intent Service.

Serves Qwen3-1.7B (T1 intent/understanding tier) via llama-cpp-python on GPU.
The model is small, but L1/T1 is on the user-facing critical path, so CPU
inference is too slow for real-time ingestion and query routing.

Task: 6.1 — App definition and container image scaffold.
Model loading (6.2), inference (6.3), health/metrics (6.4) are TODO stubs.

Requirements: 21.1, 21.4, 22.3, 23.3
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

# Make shared/ importable at runtime inside the Modal container
sys.path.insert(0, str(Path(__file__).parent))

import modal
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from shared.auth_middleware import require_bearer_token
from shared.metrics import create_metrics, render_prometheus_text
from shared.modal_common import build_health_payload

# ---------------------------------------------------------------------------
# Modal primitives
# ---------------------------------------------------------------------------

app = modal.App("jimsai-intent-service")

volume = modal.Volume.from_name("jimsai-models", create_if_missing=True)

secret = modal.Secret.from_name("modal-jimsai-secrets")

image = modal.Image.debian_slim(python_version="3.11").run_commands([
    "apt-get update -qq && apt-get install -y --no-install-recommends build-essential cmake git wget gnupg",
    "wget -qO /tmp/cuda-keyring.deb "
    "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb "
    "&& dpkg -i /tmp/cuda-keyring.deb "
    "&& apt-get update -qq "
    "&& apt-get install -y cuda-toolkit-12-3 --no-install-recommends",
    # Persist stub symlink + ldconfig so all link steps find libcuda.so.1
    "ln -sf /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1 "
    "&& echo '/usr/local/cuda/lib64/stubs' > /etc/ld.so.conf.d/cuda-stubs.conf "
    "&& ldconfig",
    # GPU build — T1 is on the critical path, so CPU llama-cpp is not acceptable.
    "export PATH=/usr/local/cuda/bin:$PATH && "
    "export CUDACXX=/usr/local/cuda/bin/nvcc && "
    "CMAKE_ARGS='-DGGML_CUDA=on -DGGML_AVX=off -DGGML_AVX2=off "
    "-DGGML_F16C=off -DGGML_FMA=off' "
    "pip install 'llama-cpp-python==0.3.9' --no-cache-dir --no-binary llama-cpp-python",
]).pip_install(
    [
        "modal>=1.0",
        "fastapi>=0.111",
        "uvicorn>=0.30",
        "huggingface-hub>=0.23",
        "pydantic>=2.7",
        "python-dotenv>=1.0",
        "torch>=2.3",
    ]
).add_local_dir(
    str(Path(__file__).parent / "shared"),
    remote_path="/root/shared",
)

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str
    content: str


class GenerateRequest(BaseModel):
    model: str = "qwen-1.7b"
    prompt: str | None = None
    messages: list[ChatMessage] | None = None
    temperature: float = 0.0
    max_tokens: int = 256
    stream: bool = False
    response_format: dict | None = None


class GenerateResponse(BaseModel):
    response: str
    model: str
    usage: dict
    finish_reason: str


# ---------------------------------------------------------------------------
# Modal class — IntentService
# ---------------------------------------------------------------------------

_svc_metrics = create_metrics("intent")


@app.cls(
    image=image,
    volumes={"/vol/models": volume},
    secrets=[secret],
    gpu="l4",
    min_containers=1,
    max_containers=3,
    memory=8192,
    timeout=600,
)
class IntentService:
    """Modal class that hosts Qwen3-1.7B on GPU for intent/T1 inference."""

    # ------------------------------------------------------------------
    # Class-level state stubs — set during container __enter__
    # ------------------------------------------------------------------
    _llm = None
    _lock = None
    _model_loaded: bool = False
    _volume_mounted: bool = False
    _container_start_time: float = 0.0

    @modal.enter()
    def enter(self) -> None:
        """Container lifecycle hook — load Qwen3-1.7B GGUF from the Modal Volume.

        Steps:
          1. Import runtime dependencies.
          2. Record container start time.
          3. Verify /vol/models is mounted.
          4. Ensure qwen-1.7b GGUF is present on the volume (download if needed).
          5. Load Llama instance with a 60-second timeout.
          6. Initialise asyncio.Lock.
          7. Record model-load duration metric.
          8. Mark model as loaded and log readiness.

        Requirements: 7.1, 7.2, 7.3, 7.6, 11.5, 14.8, 23.7, 30.2, 30.4
        """
        import time
        import logging
        import asyncio
        import threading
        import torch
        from llama_cpp import Llama
        from shared.modal_common import ensure_model_on_volume, ARTIFACT_REGISTRY

        logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)

        # Step 2 — record container start time
        self._container_start_time = time.time()

        if not torch.cuda.is_available():
            raise RuntimeError("GPU not available — Intent_Service requires CUDA for interactive T1 latency")

        # Step 3 — verify volume mount
        if not os.path.isdir("/vol/models"):
            raise RuntimeError("Volume not mounted: /vol/models")
        self._volume_mounted = True

        try:
            # Step 4 — ensure model file is on the volume (idempotent download)
            ensure_model_on_volume(ARTIFACT_REGISTRY["qwen-1.7b"])

            # Step 5 — load model with 60-second timeout via a daemon thread
            result: list = []
            error: list = []

            def _load():
                result.append(
                    Llama(
                        model_path="/vol/models/generation/Qwen3-1.7B-Q4_K_M.gguf",
                        n_ctx=4096,
                        n_gpu_layers=-1,
                        n_threads=4,
                        verbose=False,
                    )
                )

            t = threading.Thread(target=_load, daemon=True)
            t0 = time.time()
            t.start()
            t.join(60)  # 60-second per-model load timeout

            if t.is_alive():
                raise RuntimeError("Qwen3-1.7B load timed out after 60 seconds")
            if error:
                raise RuntimeError(f"Qwen3-1.7B load failed: {error[0]}")

            self._llm = result[0]

            # Step 6 — per-model asyncio.Lock (keeps interface consistent)
            self._lock = asyncio.Lock()

            # Step 7 — record load duration metric
            duration_ms = (time.time() - t0) * 1000
            _svc_metrics.record_model_load("qwen-1.7b", duration_ms)

            # Step 9 — mark model loaded
            self._model_loaded = True

            # Step 10 — log model ready
            logger.info("Model ready: qwen-1.7b")

        except Exception as exc:
            raise RuntimeError(f"Failed to load qwen-1.7b: {exc}") from exc

        # Step 12 — log container ready
        logger.info("Container ready — accepting requests")

    @modal.method()
    def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Run synchronous text generation with Qwen3-1.7B.

        Requirements: 8.1–8.10, 15.3, 21.1, 27.6
        """
        import re
        import time

        # 1. Validate prompt or messages
        if request.prompt is None and request.messages is None:
            raise HTTPException(status_code=422, detail="prompt or messages required")

        # 2. Validate model field (service is single-model)
        effective_model = "qwen-1.7b"

        # 3. Build messages list
        if request.messages:
            messages = [{"role": m.role, "content": m.content} for m in request.messages]
        else:
            messages = [{"role": "user", "content": request.prompt}]

        wants_json = bool(request.response_format and request.response_format.get("type") == "json_object")
        if wants_json:
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] = (
                    f"{messages[0]['content']}\n"
                    "Do not think step by step. Do not explain. Output only one valid compact JSON object."
                )
            else:
                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": "Do not think step by step. Do not explain. Output only one valid compact JSON object.",
                    },
                )
            for index in range(len(messages) - 1, -1, -1):
                if messages[index].get("role") == "user":
                    messages[index]["content"] = (
                        f"/no_think\n{messages[index]['content']}\n\n"
                        "Return only valid JSON. Do not include markdown, prose, or <think> tags."
                    )
                    break

        # 4. Time start
        t0 = time.time()

        # 5. Run inference
        try:
            completion = self._llm.create_chat_completion(
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens or 256,
                response_format=request.response_format if wants_json else None,
            )
        except Exception as exc:
            err_str = str(exc)
            if "ggml_assert" in err_str or "repack" in err_str:
                self._llm = None
                self._model_loaded = False
                raise HTTPException(
                    status_code=503,
                    detail="Generation failed — model reset. Please retry.",
                    headers={"Retry-After": "30"},
                )
            raise

        # 6. Extract content
        content = completion["choices"][0]["message"]["content"]

        # 7. Handle json_object response format
        if wants_json:
            # Strip think tags - Qwen3 outputs think...done
            content = re.sub(r"think.*?done", "", content, flags=re.DOTALL).strip()
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            # Extract JSON object
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                content = content[start:end + 1]
            else:
                repair_messages = [
                    *messages,
                    {"role": "assistant", "content": content[:3000]},
                    {
                        "role": "user",
                        "content": (
                            "/no_think\n"
                            "The previous response was not valid JSON. Using the original task and the previous response, "
                            "return the required result as exactly one compact JSON object. If an item is absent, use an empty list. "
                            "Do not include reasoning, markdown, prose, or <think> tags."
                        ),
                    },
                ]
                repair = self._llm.create_chat_completion(
                    messages=repair_messages,
                    temperature=0.0,
                    max_tokens=min(max(request.max_tokens or 256, 256), 512),
                    response_format=request.response_format,
                )
                content = repair["choices"][0]["message"]["content"]
                content = re.sub(r"think.*?done", "", content, flags=re.DOTALL).strip()
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end != -1 and end > start:
                    content = content[start:end + 1]

        # 8. Build usage
        usage = {
            "prompt_tokens": completion["usage"]["prompt_tokens"],
            "completion_tokens": completion["usage"]["completion_tokens"],
        }

        # 9. Finish reason
        finish_reason = completion["choices"][0]["finish_reason"] or "stop"

        # 10. Record metrics
        _svc_metrics.record_request((time.time() - t0) * 1000)

        # 11. Return
        return GenerateResponse(
            response=content,
            model="qwen-1.7b",
            usage=usage,
            finish_reason=finish_reason,
        )

    @modal.method()
    def health(self) -> dict:
        """Return extended health-check payload.

        Requirements: 21.4, 28.1–28.5, 29.3, 29.6
        """
        return build_health_payload(
            service_name="intent",
            models_loaded=self._model_loaded,
            gpu_available=True,
            volume_mounted=self._volume_mounted,
            container_start_time=self._container_start_time,
        )

    @modal.method()
    def metrics(self) -> str:
        """Return Prometheus text-format metrics.

        Requirements: 29.3, 29.6
        """
        return render_prometheus_text(_svc_metrics)


# ---------------------------------------------------------------------------
# FastAPI web application — HTTP entry point
# ---------------------------------------------------------------------------

web_app = FastAPI(title="JIMS-AI Intent Service")


@web_app.post("/generate", response_model=GenerateResponse)
async def route_generate(
    request: GenerateRequest,
    _token: str = Depends(require_bearer_token),
) -> GenerateResponse:
    """POST /generate — synchronous T1 intent generation."""
    svc = IntentService()
    return await svc.generate.remote.aio(request)


@web_app.get("/health")
async def route_health() -> dict:
    """GET /health — service health check."""
    svc = IntentService()
    return await svc.health.remote.aio()


@web_app.get("/metrics")
async def route_metrics():
    """GET /metrics — Prometheus text-format metrics."""
    svc = IntentService()
    content = await svc.metrics.remote.aio()
    return Response(content=content, media_type="text/plain; version=0.0.4")


# ---------------------------------------------------------------------------
# Modal web endpoint — wraps the FastAPI app as an ASGI app
# ---------------------------------------------------------------------------


@app.function(
    image=image,
    volumes={"/vol/models": volume},
    secrets=[secret],
    gpu="l4",
)
@modal.asgi_app()
def fastapi_app():
    """Serve the FastAPI web_app as a Modal ASGI endpoint."""
    return web_app
