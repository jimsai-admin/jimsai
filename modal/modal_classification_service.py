"""
modal_classification_service.py — Modal app definition for JIMS-AI Classification Service.

Serves the mDeBERTa zero-shot classifier on CPU:
  - MoritzLaurer/mDeBERTa-v3-base-mnli-xnli  (zero-shot-classification pipeline)

Task: 5.1 — App definition and container image scaffold.
Model loading (5.2), inference (5.3), health/metrics (5.4) are TODO stubs.

Requirements: 5.1, 13.2, 13.6, 22.2, 23.2
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

app = modal.App("jimsai-classification-service")

volume = modal.Volume.from_name("jimsai-models", create_if_missing=True)

secret = modal.Secret.from_name("modal-jimsai-secrets")

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    [
        "modal>=1.0",
        "fastapi>=0.111",
        "uvicorn>=0.30",
        "transformers>=4.41",
        "torch>=2.3",
        "huggingface-hub>=0.23",
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


class ClassifyRequest(BaseModel):
    text: str
    candidate_labels: list[str] | None = None
    hypothesis_template: str = "This request is about {}."


class ClassifyResponse(BaseModel):
    primary_kind: str
    confidence: float
    secondary_kinds: list[str]
    scores: list[dict]
    model: str


# ---------------------------------------------------------------------------
# Modal class — ClassificationService
# ---------------------------------------------------------------------------

_svc_metrics = create_metrics("classification")


@app.cls(
    image=image,
    volumes={"/vol/models": volume},
    secrets=[secret],
    min_containers=1,
    max_containers=3,
    memory=1536,
)
class ClassificationService:
    """Modal class that hosts the mDeBERTa zero-shot classifier on CPU."""

    # ------------------------------------------------------------------
    # Class-level attribute stubs (populated in enter())
    # ------------------------------------------------------------------
    _classifier = None
    _model_loaded: bool = False
    _volume_mounted: bool = False
    _container_start_time: float = 0.0

    @modal.enter()
    def enter(self) -> None:
        """Container lifecycle hook — load mDeBERTa from the Modal Volume.

        Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 11.5, 14.8, 30.2, 30.4
        """
        import time
        import logging
        from transformers import pipeline
        from shared.modal_common import ensure_model_on_volume, ARTIFACT_REGISTRY

        logger = logging.getLogger(__name__)

        self._container_start_time = time.time()

        try:
            # 1. Verify /vol/models is mounted (models will be downloaded if missing)
            vol_path = "/vol/models"
            if not os.path.isdir(vol_path):
                raise RuntimeError("Volume not mounted: /vol/models")
            os.makedirs("/vol/models/classification", exist_ok=True)
            self._volume_mounted = True

            # 2. Ensure mDeBERTa is present on the volume (download if missing)
            ensure_model_on_volume(ARTIFACT_REGISTRY["mDeBERTa"])

            # 3. Load the zero-shot-classification pipeline from the volume path
            t0 = time.time()
            self._classifier = pipeline(
                "zero-shot-classification",
                model="/vol/models/classification/mDeBERTa-v3-base-mnli-xnli",
                device=-1,  # CPU
            )
            duration_ms = (time.time() - t0) * 1000

            # 4. Record model load duration in metrics
            _svc_metrics.record_model_load("mDeBERTa", duration_ms)

            # 5. Mark model as loaded and log readiness
            self._model_loaded = True
            logger.info("Model ready: mDeBERTa")

        except Exception as exc:
            raise RuntimeError(f"Failed to load mDeBERTa: {exc}") from exc

        logger.info("Container ready — accepting requests")

    @modal.method()
    def classify(self, request: ClassifyRequest) -> ClassifyResponse:
        """Run zero-shot classification on the input text.

        Requirements: 6.1–6.7, 15.2
        """
        import time

        DEFAULT_LABELS = [
            "coding", "mathematics", "world_knowledge", "reasoning",
            "creative_writing", "data_analysis", "planning", "science", "conversation"
        ]

        # 1. Validate
        if not request.text or len(request.text) > 4096:
            raise HTTPException(
                status_code=422,
                detail="text must be between 1 and 4096 characters",
            )

        # 2. Resolve labels
        labels = request.candidate_labels if request.candidate_labels else DEFAULT_LABELS
        if not labels:
            labels = DEFAULT_LABELS

        # 3. Time start
        t0 = time.time()

        # 4. Run zero-shot classification
        result = self._classifier(
            request.text,
            labels,
            hypothesis_template=request.hypothesis_template,
            multi_label=False,
        )

        # 5. Build sorted scores
        scores = [
            {"kind": label, "score": round(score, 4)}
            for label, score in zip(result["labels"], result["scores"])
        ]

        # 6. Extract primary/secondary
        primary_kind = scores[0]["kind"]
        confidence = scores[0]["score"]
        secondary_kinds = [s["kind"] for s in scores[1:4] if s["score"] >= 0.1]

        # 7. Record metrics
        _svc_metrics.record_request((time.time() - t0) * 1000)

        # 8. Return
        return ClassifyResponse(
            primary_kind=primary_kind,
            confidence=confidence,
            secondary_kinds=secondary_kinds,
            scores=scores,
            model="mDeBERTa-v3-base-mnli-xnli",
        )

    @modal.method()
    def health(self) -> dict:
        """Return extended health-check payload.

        Requirements: 14.2, 28.1–28.5, 29.2, 29.6
        """
        return build_health_payload(
            service_name="classification",
            models_loaded=self._model_loaded,
            gpu_available=False,
            volume_mounted=self._volume_mounted,
            container_start_time=self._container_start_time,
        )

    @modal.method()
    def metrics(self) -> str:
        """Return Prometheus text-format metrics.

        Requirements: 29.2, 29.6
        """
        return render_prometheus_text(_svc_metrics)


# ---------------------------------------------------------------------------
# FastAPI web application — HTTP entry point
# ---------------------------------------------------------------------------

web_app = FastAPI(title="JIMS-AI Classification Service")


@web_app.post("/classify", response_model=ClassifyResponse)
async def route_classify(
    request: ClassifyRequest,
    _token: str = Depends(require_bearer_token),
) -> ClassifyResponse:
    """POST /classify — zero-shot capability classification."""
    svc = ClassificationService()
    return await svc.classify.remote.aio(request)


@web_app.get("/health")
async def route_health() -> dict:
    """GET /health — service health check."""
    svc = ClassificationService()
    return await svc.health.remote.aio()


@web_app.get("/metrics")
async def route_metrics():
    """GET /metrics — Prometheus text-format metrics."""
    svc = ClassificationService()
    content = await svc.metrics.remote.aio()
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
