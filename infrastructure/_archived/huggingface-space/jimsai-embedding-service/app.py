from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import time
from typing import Any
from uuid import uuid4

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
QWEN_ENABLED = os.environ.get("JIMS_QWEN_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
QWEN_REPO_ID = os.environ.get("JIMS_QWEN_MODEL_REPO", "ggml-org/Qwen3-1.7B-GGUF")
QWEN_FILENAME = os.environ.get("JIMS_QWEN_MODEL_FILE", "Qwen3-1.7B-Q4_K_M.gguf")
if QWEN_REPO_ID == "Qwen/Qwen3-8B-GGUF" and QWEN_FILENAME.lower() == "qwen3-8b-q4_k_m.gguf":
    QWEN_FILENAME = "Qwen3-8B-Q4_K_M.gguf"
QWEN_MODEL_NAME = os.environ.get("JIMS_QWEN_MODEL", "qwen3-1.7b-instruct")
QWEN_CONTEXT = max(int(os.environ.get("JIMS_QWEN_CONTEXT", "4096") or "4096"), 512)
QWEN_MAX_TOKENS = max(int(os.environ.get("JIMS_QWEN_MAX_TOKENS", "256") or "256"), 16)
QWEN_THREADS = max(int(os.environ.get("JIMS_QWEN_THREADS", "2") or "2"), 1)
QWEN_BATCH = max(int(os.environ.get("JIMS_QWEN_BATCH", "64") or "64"), 1)
QWEN_CHAT_FORMAT = os.environ.get("JIMS_QWEN_CHAT_FORMAT", "chatml")
QWEN_GPU_LAYERS = int(os.environ.get("JIMS_QWEN_GPU_LAYERS", "0") or "0")
RENDER_MODEL_REPO = os.environ.get("JIMS_RENDER_MODEL_REPO", "Qwen/Qwen3-4B-GGUF")
RENDER_MODEL_FILE = os.environ.get("JIMS_RENDER_MODEL_FILE", "Qwen3-4B-Q4_K_M.gguf")
RENDER_MODEL_NAME = os.environ.get("JIMS_RENDER_MODEL_NAME", "qwen3-4b-instruct")
RENDER_CONTEXT = max(int(os.environ.get("JIMS_RENDER_CONTEXT", "8192") or "8192"), 512)
RENDER_MAX_TOKENS = max(int(os.environ.get("JIMS_RENDER_MAX_TOKENS", "1200") or "1200"), 16)
RENDER_BATCH = max(int(os.environ.get("JIMS_RENDER_BATCH", "128") or "128"), 1)
RENDER_THREADS = max(int(os.environ.get("JIMS_RENDER_THREADS", "2") or "2"), 1)
RENDER_GPU_LAYERS = int(os.environ.get("JIMS_RENDER_GPU_LAYERS", "0") or "0")
ROUTER_MODEL_NAME = os.environ.get("JIMS_ROUTER_MODEL", "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli")
HF_ACCESS_TOKEN = (
    os.environ.get("HF_TOKEN")
    or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    or os.environ.get("HUGGING_ACCESS_TOKEN")
    or os.environ.get("HUGGING_ACESS_TOKEN")
)

model = None
model_error = ""
qwen_model = None
qwen_error = ""
router_model = None
router_error = ""
render_model = None
render_error = ""
qwen_lock = asyncio.Lock()
render_lock = asyncio.Lock()

models_cache = {}
models_lock = asyncio.Lock()

CAPABILITY_LABELS = {
    "memory_chat": "memory recall",
    "world_knowledge": "current world knowledge",
    "coding": "software coding",
    "math_science": "mathematics",
    "creative_text": "creative writing",
    "image_generation": "image generation",
    "audio_generation": "audio generation",
    "video_generation": "video generation",
    "agentic_task": "tool automation",
}


class EmbedRequest(BaseModel):
    texts: list[str] | None = None
    input: str | list[str] | None = None
    model: str | None = None
    workspace_id: str | None = None
    purpose: str = "query"


class ReloadArtifactRequest(BaseModel):
    artifact_id: str | None = None
    model: str | None = None


class WarmRequest(BaseModel):
    load_embedding: bool = True
    load_qwen: bool = False
    load_router: bool = False
    load_render: bool = False


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list, min_length=1, max_length=64)
    temperature: float = 0.0
    max_tokens: int | None = None
    response_format: dict[str, Any] | None = None


class CapabilityClassifyRequest(BaseModel):
    text: str
    candidate_kinds: list[str] | None = None


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


def fit_dimensions_for_model(values: list[float], model_id: str) -> list[float]:
    if model_id == "intfloat/multilingual-e5-small":
        if len(values) == TARGET_DIMENSIONS:
            return normalize(values)
        if len(values) > TARGET_DIMENSIONS:
            return normalize(values[:TARGET_DIMENSIONS])
        return normalize([*values, *([0.0] * (TARGET_DIMENSIONS - len(values)))])
    return normalize(values)


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


def get_model(model_name: str):
    if model_name in models_cache:
        return models_cache[model_name]
    
    if model_name == "intfloat/multilingual-e5-small":
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(model_name)
    elif model_name == "jinaai/jina-embeddings-v3":
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(model_name, trust_remote_code=True)
    elif model_name == "microsoft/codebert-base":
        from transformers import AutoModel, AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model_obj = AutoModel.from_pretrained(model_name)
        m = (model_obj, tokenizer)
    else:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(model_name)
        
    models_cache[model_name] = m
    return m


def load_model():
    global model, model_error
    if model is not None:
        return model
    try:
        model = get_model(MODEL_NAME)
        model_error = ""
        return model
    except Exception as exc:
        model_error = str(exc)
        if not HASH_FALLBACK:
            raise HTTPException(status_code=503, detail=f"embedding model unavailable: {exc}") from exc
        return None


def load_qwen():
    global qwen_model, qwen_error
    if not QWEN_ENABLED:
        qwen_error = "qwen disabled"
        return None
    if qwen_model is not None:
        return qwen_model
    try:
        from huggingface_hub import hf_hub_download
        from llama_cpp import Llama

        model_path = hf_hub_download(
            repo_id=QWEN_REPO_ID,
            filename=QWEN_FILENAME,
            token=HF_ACCESS_TOKEN or None,
        )
        qwen_model = Llama(
            model_path=model_path,
            n_ctx=QWEN_CONTEXT,
            n_threads=QWEN_THREADS,
            n_batch=QWEN_BATCH,
            n_gpu_layers=QWEN_GPU_LAYERS,
            chat_format=QWEN_CHAT_FORMAT,
            verbose=False,
        )
        qwen_error = ""
        return qwen_model
    except Exception as exc:
        qwen_error = str(exc)
        return None


def load_render_model():
    global render_model, render_error
    if not QWEN_ENABLED:
        render_error = "qwen disabled"
        return None
    if render_model is not None:
        return render_model
    try:
        from huggingface_hub import hf_hub_download
        from llama_cpp import Llama

        model_path = hf_hub_download(
            repo_id=RENDER_MODEL_REPO,
            filename=RENDER_MODEL_FILE,
            token=HF_ACCESS_TOKEN or None,
        )
        render_model = Llama(
            model_path=model_path,
            n_ctx=RENDER_CONTEXT,
            n_threads=RENDER_THREADS,
            n_batch=RENDER_BATCH,
            n_gpu_layers=RENDER_GPU_LAYERS,
            chat_format="chatml",
            verbose=False,
        )
        render_error = ""
        return render_model
    except Exception as exc:
        render_error = str(exc)
        return None


def load_router():
    global router_model, router_error
    if router_model is not None:
        return router_model
    try:
        from transformers import pipeline

        router_model = pipeline(
            "zero-shot-classification",
            model=ROUTER_MODEL_NAME,
            device=-1,
        )
        router_error = ""
        return router_model
    except Exception as exc:
        router_error = str(exc)
        return None


def strip_thinking_for_json(content: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        candidate = cleaned[start : end + 1]
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            return cleaned
    return cleaned


def inference_failed_hard(exc: Exception) -> bool:
    text = str(exc)
    lowered = text.lower()
    return "ggml_assert" in lowered or "assert" in lowered or "failed" in lowered or "repack" in lowered


def encode_codebert(text: str, model_obj, tokenizer_obj) -> list[float]:
    import torch
    inputs = tokenizer_obj(text, return_tensors="pt", max_length=512, truncation=True)
    with torch.no_grad():
        outputs = model_obj(**inputs)
    embeddings = outputs[0].mean(dim=1).squeeze(0)
    norm = torch.norm(embeddings, p=2)
    if norm > 1e-9:
        embeddings = embeddings / norm
    return embeddings.cpu().tolist()


def encode_sentence_transformer(text: str, model_obj, purpose: str, model_name: str) -> list[float]:
    text_to_encode = text
    if model_name.endswith("e5-small") or "/e5-" in model_name:
        text_to_encode = f"{'query' if purpose == 'query' else 'passage'}: {text}"
    vector = model_obj.encode(text_to_encode, normalize_embeddings=True).tolist()
    return vector


def embed_texts(texts: list[str], purpose: str, model_name: str | None = None) -> tuple[list[list[float]], bool, str]:
    target_model = model_name or MODEL_NAME
    try:
        m = get_model(target_model)
    except Exception as exc:
        if not HASH_FALLBACK:
            raise HTTPException(status_code=503, detail=f"embedding model unavailable: {exc}") from exc
        return [hash_embed(text) for text in texts], True, "hash_fallback"

    try:
        vectors = []
        for text in texts:
            if target_model == "microsoft/codebert-base":
                model_obj, tokenizer_obj = m
                vec = encode_codebert(text[:16000], model_obj, tokenizer_obj)
            else:
                vec = encode_sentence_transformer(text[:16000], m, purpose, target_model)
            vec = fit_dimensions_for_model(vec, target_model)
            vectors.append(vec)
        return vectors, False, target_model
    except Exception as exc:
        if not HASH_FALLBACK:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return [hash_embed(text) for text in texts], True, "hash_fallback"


@app.on_event("startup")
def startup_warm_embedding() -> None:
    load_model()
    load_router()


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
        "qwen_enabled": QWEN_ENABLED,
        "qwen_model": QWEN_MODEL_NAME,
        "qwen_loaded": qwen_model is not None,
        "qwen_context": QWEN_CONTEXT,
        "qwen_batch": QWEN_BATCH,
        "router_model": ROUTER_MODEL_NAME,
        "router_loaded": router_model is not None,
        "render_model_loaded": render_model is not None,
        "render_model": RENDER_MODEL_NAME,
        "render_context": RENDER_CONTEXT,
    }


@app.get("/ready")
def ready() -> dict[str, Any]:
    return {
        "ready": model is not None and router_model is not None,
        "model": MODEL_NAME,
        "error": model_error,
        "qwen_enabled": QWEN_ENABLED,
        "qwen_loaded": qwen_model is not None,
        "qwen_error": qwen_error,
        "router_model": ROUTER_MODEL_NAME,
        "router_loaded": router_model is not None,
        "router_error": router_error,
        "render_loaded": render_model is not None,
        "render_error": render_error,
    }


@app.get("/v1/warm", dependencies=[Depends(verify_token)])
def warm_get(load_qwen_model: bool = False, load_router_model: bool = False, load_render_model: bool = False) -> dict[str, Any]:
    return warm(
        WarmRequest(
            load_embedding=True,
            load_qwen=load_qwen_model,
            load_router=load_router_model,
            load_render=load_render_model,
        )
    )


@app.post("/v1/warm", dependencies=[Depends(verify_token)])
def warm(req: WarmRequest) -> dict[str, Any]:
    if req.load_embedding:
        load_model()
    if req.load_qwen:
        load_qwen()
    if req.load_router:
        load_router()
    if req.load_render:
        load_render_model()
    return {
        "status": "ok",
        "model_loaded": model is not None,
        "model_error": model_error,
        "qwen_loaded": qwen_model is not None,
        "qwen_error": qwen_error,
        "qwen_context": QWEN_CONTEXT,
        "qwen_batch": QWEN_BATCH,
        "router_loaded": router_model is not None,
        "router_error": router_error,
        "render_loaded": render_model is not None,
        "render_error": render_error,
    }


@app.post("/v1/embed", dependencies=[Depends(verify_token)])
async def embed(req: EmbedRequest) -> dict[str, Any]:
    texts = []
    if req.input is not None:
        if isinstance(req.input, list):
            texts = req.input
        else:
            texts = [req.input]
    elif req.texts is not None:
        texts = req.texts
    else:
        raise HTTPException(status_code=400, detail="Either 'input' or 'texts' must be provided.")

    model_id = req.model or MODEL_NAME
    async with models_lock:
        vectors, fallback, model_name = embed_texts(texts, req.purpose, model_id)
    dimension = len(vectors[0]) if vectors else 0
    return {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "index": idx,
                "embedding": vec
            }
            for idx, vec in enumerate(vectors)
        ],
        "model": model_name,
        "artifact_id": ARTIFACT_ID,
        "dimension": dimension,
        "vectors": vectors,
        "embeddings": vectors,
        "fallback": fallback,
        "error": model_error if fallback else "",
    }


@app.post("/v1/embed-batch", dependencies=[Depends(verify_token)])
async def embed_batch(req: EmbedRequest) -> dict[str, Any]:
    return await embed(req)


@app.post("/v1/encode", dependencies=[Depends(verify_token)])
async def encode(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("content") or payload.get("text") or "")
    model_id = payload.get("model") or MODEL_NAME
    async with models_lock:
        vectors, fallback, model_name = embed_texts([text], str(payload.get("purpose") or "document"), model_id)
    return {
        "model": model_name,
        "artifact_id": ARTIFACT_ID,
        "dimension": len(vectors[0]),
        "embedding": vectors[0],
        "vector": vectors[0],
        "fallback": fallback,
        "error": model_error if fallback else "",
    }


@app.post("/v1/chat/completions", dependencies=[Depends(verify_token)])
async def chat_completions(req: ChatCompletionRequest) -> dict[str, Any]:
    global qwen_model, qwen_error
    async with qwen_lock:
        loaded = load_qwen()
        if loaded is None:
            raise HTTPException(status_code=503, detail=f"qwen model unavailable: {qwen_error}")
        messages = [message.model_dump(mode="json") for message in req.messages]
        json_requested = bool(req.response_format and req.response_format.get("type") == "json_object")
        if json_requested:
            messages = [
                *messages[:-1],
                {
                    **messages[-1],
                    "content": (
                        f"/no_think\n{messages[-1]['content']}\n\n"
                        "Return one valid minified JSON object only. "
                        "Do not include markdown, prose, or <think> tags."
                    ),
                },
            ]
        requested_tokens = req.max_tokens or QWEN_MAX_TOKENS
        max_tokens = min(max(requested_tokens, 1), QWEN_MAX_TOKENS)
        try:
            completion = loaded.create_chat_completion(
                messages=messages,
                temperature=max(float(req.temperature), 0.0),
                max_tokens=max_tokens,
            )
        except Exception as exc:
            qwen_error = str(exc)
            if inference_failed_hard(exc):
                qwen_model = None
            raise HTTPException(status_code=500, detail=f"qwen inference failed: {exc}") from exc
    choice = (completion.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = str(message.get("content") or "")
    if json_requested:
        content = strip_thinking_for_json(content)
    return {
        "id": f"chatcmpl-{uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model or QWEN_MODEL_NAME,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": choice.get("finish_reason") or "stop",
            }
        ],
        "usage": completion.get("usage") or {},
    }


@app.post("/v1/chat/render", dependencies=[Depends(verify_token)])
async def chat_render(req: ChatCompletionRequest) -> dict[str, Any]:
    global render_model, render_error
    async with render_lock:
        loaded = load_render_model()
        if loaded is None:
            raise HTTPException(status_code=503, detail=f"render model unavailable: {render_error}")
        messages = [message.model_dump(mode="json") for message in req.messages]
        json_requested = bool(req.response_format and req.response_format.get("type") == "json_object")
        if json_requested:
            messages = [
                *messages[:-1],
                {
                    **messages[-1],
                    "content": (
                        f"/no_think\n{messages[-1]['content']}\n\n"
                        "Return one valid minified JSON object only. "
                        "Do not include markdown, prose, or <think> tags."
                    ),
                },
            ]
        requested_tokens = req.max_tokens or RENDER_MAX_TOKENS
        max_tokens = min(max(requested_tokens, 1), RENDER_MAX_TOKENS)
        try:
            completion = loaded.create_chat_completion(
                messages=messages,
                temperature=max(float(req.temperature), 0.0),
                max_tokens=max_tokens,
            )
        except Exception as exc:
            render_error = str(exc)
            if inference_failed_hard(exc):
                render_model = None
            raise HTTPException(status_code=500, detail=f"render inference failed: {exc}") from exc
    choice = (completion.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = str(message.get("content") or "")
    if json_requested:
        content = strip_thinking_for_json(content)
    return {
        "id": f"chatcmpl-{uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model or RENDER_MODEL_NAME,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": choice.get("finish_reason") or "stop",
            }
        ],
        "usage": completion.get("usage") or {},
    }


@app.post("/v1/classify/capability", dependencies=[Depends(verify_token)])
def classify_capability(req: CapabilityClassifyRequest) -> dict[str, Any]:
    loaded = load_router()
    if loaded is None:
        raise HTTPException(status_code=503, detail=f"router model unavailable: {router_error}")
    allowed = [kind for kind in (req.candidate_kinds or list(CAPABILITY_LABELS)) if kind in CAPABILITY_LABELS]
    if not allowed:
        allowed = list(CAPABILITY_LABELS)
    labels = [CAPABILITY_LABELS[kind] for kind in allowed]
    try:
        result = loaded(
            req.text[:4096],
            candidate_labels=labels,
            multi_label=False,
            hypothesis_template="This request is about {}.",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"router inference failed: {exc}") from exc
    label_to_kind = {CAPABILITY_LABELS[kind]: kind for kind in allowed}
    ranked = [
        {"kind": label_to_kind.get(str(label), "memory_chat"), "score": float(score)}
        for label, score in zip(result.get("labels", []), result.get("scores", []), strict=False)
    ]
    ranked.sort(key=lambda item: item["score"], reverse=True)
    primary = ranked[0] if ranked else {"kind": "memory_chat", "score": 0.0}
    return {
        "model": ROUTER_MODEL_NAME,
        "primary_kind": primary["kind"],
        "confidence": primary["score"],
        "secondary_kinds": [item["kind"] for item in ranked[1:4] if item["score"] >= 0.35],
        "scores": ranked,
    }


@app.get("/v1/artifact/current")
def current_artifact() -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "model": MODEL_NAME,
        "dimension": TARGET_DIMENSIONS,
        "loaded": model is not None,
        "error": model_error,
        "qwen_enabled": QWEN_ENABLED,
        "qwen_model": QWEN_MODEL_NAME,
        "qwen_repo": QWEN_REPO_ID,
        "qwen_file": QWEN_FILENAME,
        "qwen_context": QWEN_CONTEXT,
        "qwen_batch": QWEN_BATCH,
        "qwen_loaded": qwen_model is not None,
        "qwen_error": qwen_error,
        "router_model": ROUTER_MODEL_NAME,
        "router_loaded": router_model is not None,
        "router_error": router_error,
        "render_model": RENDER_MODEL_NAME,
        "render_repo": RENDER_MODEL_REPO,
        "render_file": RENDER_MODEL_FILE,
        "render_context": RENDER_CONTEXT,
        "render_loaded": render_model is not None,
        "render_error": render_error,
    }


@app.get("/v1/model/config")
def model_config() -> dict[str, Any]:
    """Return current model configuration — no auth required (public metadata)."""
    return {
        "t1_model": {
            "repo": QWEN_REPO_ID,
            "file": QWEN_FILENAME,
            "name": QWEN_MODEL_NAME,
            "loaded": qwen_model is not None,
            "context": QWEN_CONTEXT,
            "gpu_layers": QWEN_GPU_LAYERS,
        },
        "t2_model": {
            "repo": RENDER_MODEL_REPO,
            "file": RENDER_MODEL_FILE,
            "name": RENDER_MODEL_NAME,
            "loaded": render_model is not None,
            "context": RENDER_CONTEXT,
            "gpu_layers": RENDER_GPU_LAYERS,
        },
        "embedding_model": MODEL_NAME,
        "router_model": ROUTER_MODEL_NAME,
    }


@app.post("/v1/reload-artifact", dependencies=[Depends(verify_token)])
def reload_artifact(_: ReloadArtifactRequest) -> dict[str, Any]:
    global model
    model = None
    load_model()
    return current_artifact()
