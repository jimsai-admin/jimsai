"""
modal_embedding_service.py — Modal app definition for JIMS-AI Embedding Service.

Serves three embedding models on CPU:
  - multilingual-e5-small  (SentenceTransformer, 768-d)
  - jina-v3                (SentenceTransformer, 768-d, trust_remote_code=True)
  - codebert               (AutoModel + AutoTokenizer, mean-pool + L2-norm, 768-d)

Task: 4.1 — App definition and container image scaffold.
Task: 4.2 — Container __enter__: model loading and integrity validation.
Inference (4.3), health/metrics (4.4) are TODO stubs.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 11.5, 13.1, 13.5,
              14.5, 14.6, 14.8, 22.1, 23.1, 30.1, 30.2, 30.3, 30.4
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

# Make shared/ importable at runtime inside the Modal container
sys.path.insert(0, str(Path(__file__).parent))

import modal
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoTokenizer

from shared.auth_middleware import require_bearer_token
from shared.metrics import create_metrics, render_prometheus_text
from shared.modal_common import ARTIFACT_REGISTRY, build_health_payload, ensure_model_on_volume

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Modal primitives
# ---------------------------------------------------------------------------

app = modal.App("jimsai-embedding-service")

volume = modal.Volume.from_name("jimsai-models", create_if_missing=True)

secret = modal.Secret.from_name("modal-jimsai-secrets")

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    [
        "modal>=1.0",
        "fastapi>=0.111",
        "uvicorn>=0.30",
        "sentence-transformers>=2.7",
        "transformers>=4.41",
        "torch>=2.3",
        "einops>=0.7",
        "huggingface-hub>=0.23",
        "numpy>=1.26",
        "pydantic>=2.7",
        "python-dotenv>=1.0",
    ]
).add_local_dir(
    str(Path(__file__).parent / "shared"),
    remote_path="/root/shared",
)

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class EmbedRequest(BaseModel):
    texts: list[str]
    model: str = "multilingual-e5-small"
    purpose: str = "query"


class EmbedResponse(BaseModel):
    vectors: list[list[float]]
    model: str
    dimension: int
    fallback: bool = False


class CodeEmbedRequest(BaseModel):
    texts: list[str]
    purpose: str = "document"


# ---------------------------------------------------------------------------
# Modal class — EmbeddingService
# ---------------------------------------------------------------------------

_svc_metrics = create_metrics("embedding", is_embedding_service=True)


@app.cls(
    image=image,
    volumes={"/vol/models": volume},
    secrets=[secret],
    min_containers=1,
    max_containers=5,
    memory=2560,
)
class EmbeddingService:
    """Modal class that hosts all three embedding models on CPU."""

    # ------------------------------------------------------------------
    # Class-level attribute declarations (initialised to sentinel values;
    # actual instances are set inside enter() at container startup).
    # ------------------------------------------------------------------
    _e5_model: SentenceTransformer | None = None
    _jina_model: SentenceTransformer | None = None
    _codebert_tokenizer: AutoTokenizer | None = None
    _codebert_model: AutoModel | None = None
    _models_loaded: dict = {}
    _volume_mounted: bool = False
    _container_start_time: float = 0.0

    # ------------------------------------------------------------------
    # Container lifecycle — model loading and integrity validation
    # Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7,
    #               11.5, 14.5, 14.6, 14.8, 30.2, 30.3, 30.4
    # ------------------------------------------------------------------

    @modal.enter()
    def enter(self) -> None:
        """Container lifecycle hook — load all three embedding models from the
        Modal Volume.

        Steps
        -----
        1. Record container start time.
        2. Verify the volume is mounted and non-empty.
        3. For each model: call ensure_model_on_volume (download + integrity),
           then load into memory, record load duration, and emit INFO log.
        4. Mark volume mounted and models loaded.
        5. Warn if total startup exceeds 90 s; fail container if > 120 s.
        6. Emit final "Container ready" log.
        """
        self._container_start_time = time.time()

        # ---- 1. Volume presence check (Req 3.1, 10.6) ------------------
        vol_root = "/vol/models"
        if not os.path.isdir(vol_root) or not os.listdir(vol_root):
            raise RuntimeError(f"Volume not mounted or empty: {vol_root}")

        # ---- 2. Model load sequence ------------------------------------
        # (model_key, loader_callable_that_returns_loaded_object)
        _STARTUP_TIMEOUT_S = 120
        _WARN_THRESHOLD_S = 90

        model_configs = [
            ("multilingual-e5-small", self._load_e5),
            ("jina-v3", self._load_jina),
            ("codebert", self._load_codebert),
        ]

        for model_key, loader in model_configs:
            # Ensure the artifact is on the volume (download if missing,
            # validate integrity).  Req 3.2, 3.3, 30.2, 30.3
            try:
                ensure_model_on_volume(ARTIFACT_REGISTRY[model_key])
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to load model {model_key}: {exc}"
                ) from exc

            # Load the model into memory and time it.
            model_start = time.time()
            try:
                loader()
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to load model {model_key}: {exc}"
                ) from exc

            duration_ms = (time.time() - model_start) * 1000.0
            logger.info("Model ready: %s", model_key)
            _svc_metrics.record_model_load(model_key, duration_ms)

            # ---- Startup timeout guard (Req 3.4) -----------------------
            elapsed = time.time() - self._container_start_time
            if elapsed > _STARTUP_TIMEOUT_S:
                raise RuntimeError(
                    f"Failed to load model {model_key}: "
                    f"startup exceeded {_STARTUP_TIMEOUT_S} s timeout "
                    f"(elapsed {elapsed:.1f} s)"
                )
            if elapsed > _WARN_THRESHOLD_S:
                logger.warning(
                    "Container startup is taking longer than %d s (elapsed %.1f s); "
                    "120 s hard limit not yet reached",
                    _WARN_THRESHOLD_S,
                    elapsed,
                )

        # ---- 3. Mark service as ready (Req 14.5, 14.8, 30.4) ----------
        self._models_loaded = {
            "multilingual-e5-small": True,
            "jina-v3": True,
            "codebert": True,
        }
        self._volume_mounted = True

        logger.info("Container ready — accepting requests")

    # ------------------------------------------------------------------
    # Private per-model loaders
    # ------------------------------------------------------------------

    def _load_e5(self) -> None:
        """Load multilingual-e5-small from the volume."""
        self._e5_model = SentenceTransformer(
            "/vol/models/embedding/multilingual-e5-small"
        )

    def _load_jina(self) -> None:
        """Load jina-embeddings-v3 from the volume (trust_remote_code=True)."""
        self._jina_model = SentenceTransformer(
            "/vol/models/embedding/jina-embeddings-v3",
            trust_remote_code=True,
        )

    def _load_codebert(self) -> None:
        """Load codebert-base tokenizer + model from the volume."""
        self._codebert_tokenizer = AutoTokenizer.from_pretrained(
            "/vol/models/embedding/codebert-base"
        )
        self._codebert_model = AutoModel.from_pretrained(
            "/vol/models/embedding/codebert-base"
        )

    @modal.method()
    def embed(self, request: EmbedRequest) -> EmbedResponse:
        """Embed a batch of texts using the requested model.

        Requirements: 4.1–4.10, 15.1
        """
        # 1. Validate batch size
        if len(request.texts) < 1 or len(request.texts) > 128:
            raise HTTPException(status_code=422, detail="texts must have 1–128 items")

        # 2. Truncate texts to 16000 chars
        texts = [t[:16000] for t in request.texts]

        # 3. Time start
        t0 = time.time()

        # 4. Route by model
        if request.model == "multilingual-e5-small":
            prefix = "query: " if request.purpose == "query" else "passage: "
            prefixed = [prefix + t for t in texts]
            raw = self._e5_model.encode(prefixed, normalize_embeddings=True)
            vectors = [np.array(v, dtype=float) for v in raw]

        elif request.model == "jina-v3":
            raw = self._jina_model.encode(texts, normalize_embeddings=True)
            vectors = [np.array(v, dtype=float) for v in raw]

        elif request.model == "codebert":
            vectors = []
            for text in texts:
                tokens = self._codebert_tokenizer(
                    text[:512],
                    return_tensors="pt",
                    truncation=True,
                    max_length=512,
                )
                output = self._codebert_model(**tokens)
                # Mean-pool over sequence dimension
                vec = output.last_hidden_state.mean(dim=1).squeeze().detach().numpy().astype(float)
                vectors.append(np.array(vec, dtype=float))

        else:
            raise HTTPException(status_code=422, detail=f"Unknown model: {request.model}")

        # 5. Ensure all vectors are exactly 768-d
        result_vecs = []
        for vec in vectors:
            vec = np.array(vec, dtype=float).flatten()
            if len(vec) < 768:
                vec = np.pad(vec, (0, 768 - len(vec)))
            elif len(vec) > 768:
                vec = vec[:768]

            # 6. Verify and enforce L2 norm ≈ 1.0
            norm = np.linalg.norm(vec)
            if norm < 1e-9 or abs(norm - 1.0) >= 1e-3:
                vec = vec / (norm if norm > 1e-9 else 1.0)

            result_vecs.append(vec)

        # 7. Record metrics
        _svc_metrics.record_request((time.time() - t0) * 1000)
        _svc_metrics.batch_size_histogram.record(len(texts))

        # 8. Return response
        return EmbedResponse(
            vectors=[v.tolist() for v in result_vecs],
            model=request.model,
            dimension=768,
        )

    @modal.method()
    def embed_code(self, request: CodeEmbedRequest) -> EmbedResponse:
        """Embed code snippets using codebert-base.

        Requirements: 4.6
        """
        # Delegate to embed() with model forced to "codebert"
        embed_request = EmbedRequest(
            texts=request.texts,
            model="codebert",
            purpose=request.purpose,
        )
        result = self.embed(embed_request)
        # Force model field to "codebert" in response
        return EmbedResponse(
            vectors=result.vectors,
            model="codebert",
            dimension=result.dimension,
            fallback=result.fallback,
        )

    @modal.method()
    def health(self) -> dict:
        """Return extended health-check payload.

        Requirements: 14.1, 28.1–28.6, 29.1, 29.6
        """
        return build_health_payload(
            service_name="embedding",
            models_loaded=self._models_loaded if self._models_loaded else False,
            gpu_available=False,
            volume_mounted=self._volume_mounted,
            container_start_time=self._container_start_time,
        )

    @modal.method()
    def metrics(self) -> str:
        """Return Prometheus text-format metrics.

        Requirements: 29.1, 29.6
        """
        return render_prometheus_text(_svc_metrics)


# ---------------------------------------------------------------------------
# FastAPI web application — HTTP entry point
# ---------------------------------------------------------------------------

web_app = FastAPI(title="JIMS-AI Embedding Service")


@web_app.post("/embed", response_model=EmbedResponse)
async def route_embed(
    request: EmbedRequest,
    _token: str = Depends(require_bearer_token),
) -> EmbedResponse:
    """POST /embed — embed a batch of texts."""
    svc = EmbeddingService()
    return svc.embed.remote(request)


@web_app.post("/embed/code", response_model=EmbedResponse)
async def route_embed_code(
    request: CodeEmbedRequest,
    _token: str = Depends(require_bearer_token),
) -> EmbedResponse:
    """POST /embed/code — embed code snippets via codebert."""
    svc = EmbeddingService()
    return svc.embed_code.remote(request)


@web_app.get("/health")
async def route_health() -> dict:
    """GET /health — service health check."""
    svc = EmbeddingService()
    return svc.health.remote()


@web_app.get("/metrics")
async def route_metrics():
    """GET /metrics — Prometheus text-format metrics."""
    svc = EmbeddingService()
    content = svc.metrics.remote()
    return Response(content=content, media_type="text/plain; version=0.0.4")


# ---------------------------------------------------------------------------
# Modal web endpoint — wraps the FastAPI app as an ASGI app
# ---------------------------------------------------------------------------


@app.function(
    image=image,
    volumes={"/vol/models": volume},
    secrets=[secret],
)
@modal.asgi_app()
def fastapi_app():
    """Serve the FastAPI web_app as a Modal ASGI endpoint."""
    return web_app
