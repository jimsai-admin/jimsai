from __future__ import annotations

import base64
import io
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field


app = FastAPI(title="JIMS-AI Multimodal Encoder", version="0.1.0")


class EncodeRequest(BaseModel):
    content: str
    modality: str = Field(pattern="^(text|code|data|image|audio|video)$")
    dimensions: int = Field(default=768, ge=1, le=4096)


class EncodeResponse(BaseModel):
    embedding: list[float]
    modality: str
    dimensions: int
    model: str


class EncoderSettings(BaseModel):
    api_key: str = os.getenv("JIMS_MULTIMODAL_ENCODER_API_KEY", "")
    text_model: str = os.getenv("ENCODER_TEXT_MODEL", "nomic-ai/nomic-embed-text-v1.5")
    code_model: str = os.getenv("ENCODER_CODE_MODEL", "nomic-ai/nomic-embed-code")
    image_model: str = os.getenv("ENCODER_IMAGE_MODEL", "google/siglip-so400m-patch14-384")
    whisper_model: str = os.getenv("ENCODER_WHISPER_MODEL", "base")


settings = EncoderSettings()
sentence_models: dict[str, Any] = {}
hf_models: dict[str, tuple[Any, Any]] = {}
whisper_models: dict[str, Any] = {}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "jimsai-multimodal-encoder"}


@app.post("/v1/encode", response_model=EncodeResponse)
async def encode(request: EncodeRequest, authorization: str | None = Header(default=None)) -> EncodeResponse:
    require_bearer(authorization)
    model_name = model_for_modality(request.modality)
    if request.modality in {"text", "code", "data"}:
        vector = encode_sentence(request.content, model_name)
    elif request.modality == "image":
        vector = encode_image(request.content)
    elif request.modality == "audio":
        vector = encode_audio(request.content)
    elif request.modality == "video":
        vector = encode_video(request.content)
    else:
        raise HTTPException(status_code=400, detail=f"unsupported modality: {request.modality}")
    embedding = fit_dimensions(normalize(vector), request.dimensions)
    return EncodeResponse(
        embedding=embedding,
        modality=request.modality,
        dimensions=len(embedding),
        model=model_name,
    )


def require_bearer(authorization: str | None) -> None:
    if not settings.api_key:
        return
    expected = f"Bearer {settings.api_key}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid encoder bearer token")


def model_for_modality(modality: str) -> str:
    if modality == "code":
        return settings.code_model
    if modality == "image":
        return settings.image_model
    if modality in {"audio", "video"}:
        return f"{settings.whisper_model}+{settings.text_model}"
    return settings.text_model


def encode_sentence(content: str, model_name: str) -> list[float]:
    if model_name not in sentence_models:
        from sentence_transformers import SentenceTransformer

        sentence_models[model_name] = SentenceTransformer(model_name, trust_remote_code=True)
    vector = sentence_models[model_name].encode(content, normalize_embeddings=True)
    return tolist(vector)


def load_hf_model(model_name: str) -> tuple[Any, Any]:
    if model_name not in hf_models:
        from transformers import AutoModel, AutoProcessor

        processor = AutoProcessor.from_pretrained(model_name)
        model = AutoModel.from_pretrained(model_name)
        model.eval()
        hf_models[model_name] = (processor, model)
    return hf_models[model_name]


def encode_image(content: str) -> list[float]:
    import torch

    image = open_image(content)
    processor, model = load_hf_model(settings.image_model)
    inputs = processor(images=image, return_tensors="pt")
    with torch.no_grad():
        if hasattr(model, "get_image_features"):
            vector = model.get_image_features(**inputs)[0]
        else:
            output = model(**inputs)
            vector = output.pooler_output[0] if hasattr(output, "pooler_output") else output.last_hidden_state.mean(dim=1)[0]
    return tolist(vector)


def encode_audio(content: str) -> list[float]:
    path = content_to_path(content, suffix=".wav")
    try:
        import whisper

        if settings.whisper_model not in whisper_models:
            whisper_models[settings.whisper_model] = whisper.load_model(settings.whisper_model)
        transcript = whisper_models[settings.whisper_model].transcribe(str(path))["text"]
        return encode_sentence(transcript, settings.text_model)
    finally:
        remove_temp(path)


def encode_video(content: str) -> list[float]:
    import cv2
    from PIL import Image

    path = content_to_path(content, suffix=".mp4")
    cap = cv2.VideoCapture(str(path))
    vectors: list[list[float]] = []
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        step = max(total // 6, 1)
        frame_index = 0
        while cap.isOpened() and len(vectors) < 6:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = cap.read()
            if not ok:
                break
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame_rgb)
            with tempfile.NamedTemporaryFile(prefix="jimsai-frame-", suffix=".png", delete=False) as handle:
                image.save(handle, format="PNG")
                frame_path = Path(handle.name)
            try:
                vectors.append(encode_image(str(frame_path)))
            finally:
                remove_temp(frame_path)
            frame_index += step
    finally:
        cap.release()
        remove_temp(path)
    if not vectors:
        return []
    width = max(len(vector) for vector in vectors)
    return [sum(vector[i] if i < len(vector) else 0.0 for vector in vectors) / len(vectors) for i in range(width)]


def open_image(content: str) -> Any:
    from PIL import Image

    if looks_like_path(content) and Path(content).exists():
        return Image.open(content).convert("RGB")
    if content.startswith("data:"):
        content = content.split(",", 1)[1]
    try:
        return Image.open(io.BytesIO(base64.b64decode(content))).convert("RGB")
    except Exception:
        response = httpx.get(content, timeout=30)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")


def content_to_path(content: str, suffix: str) -> Path:
    path = Path(content) if looks_like_path(content) else None
    if path and path.exists():
        return path
    if content.startswith("data:"):
        content = content.split(",", 1)[1]
    data = base64.b64decode(content)
    with tempfile.NamedTemporaryFile(prefix="jimsai-media-", suffix=suffix, delete=False) as handle:
        handle.write(data)
        return Path(handle.name)


def looks_like_path(content: str) -> bool:
    return len(content) < 1024 and not content.startswith(("data:", "http://", "https://", "r2://", "s3://"))


def remove_temp(path: Path) -> None:
    if path.name.startswith(("jimsai-media-", "jimsai-frame-")):
        path.unlink(missing_ok=True)


def tolist(vector: Any) -> list[float]:
    if hasattr(vector, "detach"):
        vector = vector.detach().cpu()
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    if vector and isinstance(vector[0], list):
        vector = vector[0]
    return [float(value) for value in vector]


def normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [float(value) / norm for value in values]


def fit_dimensions(values: list[float], dimensions: int) -> list[float]:
    if len(values) == dimensions:
        return [round(value, 6) for value in values]
    if len(values) > dimensions:
        return [round(value, 6) for value in normalize(values[:dimensions])]
    return [round(value, 6) for value in normalize([*values, *([0.0] * (dimensions - len(values)))])]
