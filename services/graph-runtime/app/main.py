from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from .config import settings
from .routes import router
from .telemetry import configure_logger, trace_middleware

logger = configure_logger(settings.service_name, settings.log_level)
app = FastAPI(title="JIMS-AI graph-runtime", version="0.1.0")
app.middleware("http")(trace_middleware)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "deterministic": True,
        "layer": "L6 retrieval and Neo4j-backed graph runtime",
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    return "jimsai_service_up{service='" + settings.service_name + "'} 1\n"


@app.get("/trace")
async def trace() -> dict[str, str]:
    return {"service": settings.service_name, "trace_policy": "all requests emit deterministic trace headers"}
