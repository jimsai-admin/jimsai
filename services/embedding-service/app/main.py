from __future__ import annotations

import asyncio

from fastapi import FastAPI

from .config import settings
from .routes import model_status, preload_model, router

app = FastAPI(title="JIMS-AI embedding-service", version="0.1.0")
app.include_router(router)


@app.on_event("startup")
async def startup() -> None:
    if settings.jims_embedding_preload_on_startup:
        asyncio.create_task(asyncio.to_thread(preload_model))


@app.get("/health")
async def health() -> dict[str, str | bool | int]:
    status = model_status()
    return {
        "status": "ok",
        "service": settings.service_name,
        "model_loaded": status["loaded"],
        "model": status["model"],
        "fallback_enabled": settings.jims_embedding_hash_fallback_enabled,
        "dimension": settings.jims_embedding_dimensions,
    }


@app.get("/ready")
async def ready() -> dict[str, str | bool | int]:
    status = model_status()
    return {
        "ready": bool(status["loaded"]),
        "service": settings.service_name,
        "model": status["model"],
        "dimension": settings.jims_embedding_dimensions,
        "error": status["error"],
    }
