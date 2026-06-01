from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from .config import settings

router = APIRouter()
_model: Any | None = None
_model_error: str = ""
_loaded_model_name = ""


class EmbedRequest(BaseModel):
    texts: list[str] = Field(default_factory=list, min_length=1, max_length=128)
    workspace_id: str | None = None
    purpose: str = "query"


class ReloadArtifactRequest(BaseModel):
    artifact_id: str | None = None
    storage_url: str | None = None
    model: str | None = None


def require_agent_token(authorization: str | None) -> None:
    expected = settings.jims_render_agent_token.strip()
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="agent token not configured")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid agent token")


def _target_dim() -> int:
    return max(int(settings.jims_embedding_dimensions or 768), 1)


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [round(value / norm, 8) for value in values]


def _fit(values: list[float]) -> list[float]:
    target = _target_dim()
    if len(values) == target:
        return _normalize(values)
    if len(values) > target:
        return _normalize(values[:target])
    return _normalize([*values, *([0.0] * (target - len(values)))])


def _hash_embedding(text: str) -> list[float]:
    vector = [0.0] * _target_dim()
    for token in re.findall(r"[A-Za-z0-9_\.]+", text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % len(vector)
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[idx] += sign
    return _normalize(vector)


def _prefixed(text: str, purpose: str) -> str:
    if settings.jims_embedding_model.endswith("e5-small") or "/e5-" in settings.jims_embedding_model:
        prefix = "query" if purpose == "query" else "passage"
        return f"{prefix}: {text}"
    return text


def _load_model() -> Any | None:
    global _model, _model_error, _loaded_model_name
    if _model is not None:
        return _model
    model_name = settings.jims_active_artifact_path.strip() or settings.jims_embedding_model
    try:
        from sentence_transformers import SentenceTransformer
        import torch

        model_kwargs: dict[str, Any] = {}
        if settings.jims_embedding_torch_dtype == "float16":
            model_kwargs["torch_dtype"] = torch.float16
        elif settings.jims_embedding_torch_dtype == "bfloat16":
            model_kwargs["torch_dtype"] = torch.bfloat16
        if model_kwargs:
            try:
                _model = SentenceTransformer(model_name, device=settings.jims_embedding_device, model_kwargs=model_kwargs)
            except TypeError:
                _model = SentenceTransformer(model_name, device=settings.jims_embedding_device)
        else:
            _model = SentenceTransformer(model_name, device=settings.jims_embedding_device)
        _loaded_model_name = model_name
        _model_error = ""
        return _model
    except Exception as exc:
        _model = None
        _loaded_model_name = "hash_fallback"
        _model_error = str(exc)
        return None


def preload_model() -> None:
    _load_model()


def model_status() -> dict[str, Any]:
    return {
        "loaded": _model is not None,
        "model": _loaded_model_name or settings.jims_embedding_model,
        "error": _model_error,
    }


def _embed_texts(texts: list[str], purpose: str) -> tuple[str, list[list[float]], str]:
    model = _load_model()
    if model is None:
        if not settings.jims_embedding_hash_fallback_enabled:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"embedding model unavailable: {_model_error}")
        return "hash_fallback", [_hash_embedding(text) for text in texts], _model_error
    try:
        encoded = model.encode(
            [_prefixed(text, purpose) for text in texts],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    except Exception as exc:
        if not settings.jims_embedding_hash_fallback_enabled:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"embedding failed: {exc}") from exc
        return "hash_fallback", [_hash_embedding(text) for text in texts], str(exc)
    vectors = [_fit([float(value) for value in row]) for row in encoded]
    return _loaded_model_name or settings.jims_embedding_model, vectors, ""


@router.post("/v1/embed")
async def embed(request: EmbedRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_agent_token(authorization)
    texts = [text[:16000] for text in request.texts]
    model, vectors, error = _embed_texts(texts, request.purpose)
    return {
        "model": model,
        "artifact_id": settings.jims_active_artifact_id,
        "dimension": _target_dim(),
        "vectors": vectors,
        "fallback": model == "hash_fallback",
        "error": error,
    }


@router.post("/v1/embed-batch")
async def embed_batch(request: EmbedRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return await embed(request, authorization)


@router.post("/v1/encode")
async def encode_compat(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_agent_token(authorization)
    content = str(payload.get("content") or payload.get("text") or "")
    purpose = str(payload.get("purpose") or "document")
    model, vectors, error = _embed_texts([content[:16000]], purpose)
    return {
        "model": model,
        "artifact_id": settings.jims_active_artifact_id,
        "dimension": _target_dim(),
        "embedding": vectors[0],
        "fallback": model == "hash_fallback",
        "error": error,
    }


@router.get("/v1/artifact/current")
async def current_artifact() -> dict[str, Any]:
    return {
        "artifact_id": settings.jims_active_artifact_id,
        "model": _loaded_model_name or settings.jims_embedding_model,
        "base_model": settings.jims_embedding_model,
        "dimension": _target_dim(),
        "loaded": _model is not None,
        "fallback_error": _model_error,
    }


@router.post("/v1/reload-artifact")
async def reload_artifact(request: ReloadArtifactRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_agent_token(authorization)
    global _model, _model_error, _loaded_model_name
    _model = None
    _model_error = ""
    _loaded_model_name = ""
    if request.artifact_id:
        settings.jims_active_artifact_id = request.artifact_id
    if request.model:
        settings.jims_embedding_model = request.model
    _load_model()
    return await current_artifact()
