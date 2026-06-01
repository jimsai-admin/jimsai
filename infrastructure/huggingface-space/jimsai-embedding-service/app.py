from __future__ import annotations

import hashlib
import math
import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

app = FastAPI(title="JIMS-AI Hugging Face Embedding Service")
security = HTTPBearer()

AGENT_TOKEN = os.environ.get("JIMS_RENDER_AGENT_TOKEN") or os.environ.get("JIMS_EMBEDDING_SERVICE_TOKEN", "")
MODEL_NAME = os.environ.get("JIMS_EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
ARTIFACT_ID = os.environ.get("JIMS_ACTIVE_ARTIFACT_ID", "hf_space_encoder")
HASH_FALLBACK = os.environ.get("JIMS_EMBEDDING_HASH_FALLBACK_ENABLED", "true").lower() == "true"
TARGET_DIMENSIONS = max(int(os.environ.get("JIMS_EMBEDDING_DIMENSIONS", "768") or "768"), 1)

model = None
model_error = ""


class EmbedRequest(BaseModel):
    texts: list[str] = Field(default_factory=list, min_length=1, max_length=128)
    workspace_id: str | None = None
    purpose: str = "query"


class ReloadArtifactRequest(BaseModel):
    artifact_id: str | None = None
    model: str | None = None


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if not AGENT_TOKEN:
        raise HTTPException(status_code=503, detail="agent token not configured")
    if credentials.credentials != AGENT_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")
    return credentials.credentials


def normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [round(value / norm, 8) for value in values]


def fit_dimensions(values: list[float]) -> list[float]:
    if len(values) == TARGET_DIMENSIONS:
        return normalize(values)
    if len(values) > TARGET_DIMENSIONS:
        return normalize(values[:TARGET_DIMENSIONS])
    return normalize([*values, *([0.0] * (TARGET_DIMENSIONS - len(values)))])


def hash_embed(text: str) -> list[float]:
    dimensions = TARGET_DIMENSIONS
    vector = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % dimensions
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[idx] += sign
    return fit_dimensions(vector)


def prefixed(text: str, purpose: str) -> str:
    if MODEL_NAME.endswith("e5-small") or "/e5-" in MODEL_NAME:
        return f"{'query' if purpose == 'query' else 'passage'}: {text}"
    return text


def load_model():
    global model, model_error
    if model is not None:
        return model
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(MODEL_NAME)
        model_error = ""
        return model
    except Exception as exc:
        model_error = str(exc)
        if not HASH_FALLBACK:
            raise HTTPException(status_code=503, detail=f"embedding model unavailable: {exc}") from exc
        return None


def embed_texts(texts: list[str], purpose: str) -> tuple[list[list[float]], bool, str]:
    loaded = load_model()
    if loaded is None:
        return [hash_embed(text) for text in texts], True, "hash_fallback"
    try:
        vectors = loaded.encode([prefixed(text[:16000], purpose) for text in texts], normalize_embeddings=True).tolist()
        return [fit_dimensions([float(value) for value in vector]) for vector in vectors], False, MODEL_NAME
    except Exception as exc:
        if not HASH_FALLBACK:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return [hash_embed(text) for text in texts], True, "hash_fallback"


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "jimsai-embedding-service", "status": "ok"}


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "embedding-service",
        "model": MODEL_NAME,
        "dimension": TARGET_DIMENSIONS,
        "model_loaded": model is not None,
    }


@app.get("/ready")
def ready() -> dict[str, Any]:
    return {"ready": model is not None, "model": MODEL_NAME, "error": model_error}


@app.post("/v1/embed", dependencies=[Depends(verify_token)])
def embed(req: EmbedRequest) -> dict[str, Any]:
    vectors, fallback, model_name = embed_texts(req.texts, req.purpose)
    dimension = len(vectors[0]) if vectors else 0
    return {
        "model": model_name,
        "artifact_id": ARTIFACT_ID,
        "dimension": dimension,
        "vectors": vectors,
        "embeddings": vectors,
        "fallback": fallback,
        "error": model_error if fallback else "",
    }


@app.post("/v1/embed-batch", dependencies=[Depends(verify_token)])
def embed_batch(req: EmbedRequest) -> dict[str, Any]:
    return embed(req)


@app.post("/v1/encode", dependencies=[Depends(verify_token)])
def encode(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("content") or payload.get("text") or "")
    vectors, fallback, model_name = embed_texts([text], str(payload.get("purpose") or "document"))
    return {
        "model": model_name,
        "artifact_id": ARTIFACT_ID,
        "dimension": len(vectors[0]),
        "embedding": vectors[0],
        "vector": vectors[0],
        "fallback": fallback,
        "error": model_error if fallback else "",
    }


@app.get("/v1/artifact/current")
def current_artifact() -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "model": MODEL_NAME,
        "dimension": TARGET_DIMENSIONS,
        "loaded": model is not None,
        "error": model_error,
    }


@app.post("/v1/reload-artifact", dependencies=[Depends(verify_token)])
def reload_artifact(_: ReloadArtifactRequest) -> dict[str, Any]:
    global model
    model = None
    load_model()
    return current_artifact()
