from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.requests import Request

from .config import settings
from .routes import router
from .telemetry import configure_logger, trace_middleware

logger = configure_logger(settings.service_name, settings.log_level)


async def _wake_hf_space() -> None:
    """Fire-and-forget background task: ping HF Space /health until it responds.
    This prevents the first real user request from blocking on cold-start.
    """
    url = os.getenv("JIMS_EMBEDDING_SERVICE_URL", "").rstrip("/")
    if not url:
        return
    health_url = f"{url}/health"
    for attempt in range(1, 16):          # up to ~4 minutes total
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(health_url)
                if r.status_code == 200:
                    logger.info("HF Space awake after %d ping(s): %s", attempt, r.json().get("status"))
                    return
                logger.debug("HF Space ping %d → HTTP %d", attempt, r.status_code)
        except Exception as exc:
            logger.debug("HF Space ping %d failed: %s", attempt, exc)
        await asyncio.sleep(15)
    logger.warning("HF Space did not respond within warm-up window — embeddings will use hash fallback until it wakes")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Kick off HF Space warm-up in the background — don't block startup
    asyncio.create_task(_wake_hf_space())
    yield


app = FastAPI(title="JIMS-AI api-gateway", version="0.1.0", lifespan=lifespan)
configured_cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
lambda_function_url_cors = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
if configured_cors_origins and not lambda_function_url_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.middleware("http")(trace_middleware)
app.include_router(router)


def _allowed_cors_origin(origin: str | None) -> str | None:
    if lambda_function_url_cors:
        return None
    if not origin:
        return None
    origins = [value.strip() for value in settings.cors_origins.split(",") if value.strip()]
    return origin if origin in origins or "*" in origins else None


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled API error")
    response = JSONResponse(
        status_code=500,
        content={"detail": "internal server error", "error_type": exc.__class__.__name__},
    )
    allowed_origin = _allowed_cors_origin(request.headers.get("origin"))
    if allowed_origin:
        response.headers["Access-Control-Allow-Origin"] = allowed_origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'")
    return response


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "deterministic": True,
        "layer": "External API layer",
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    return "jimsai_service_up{service='" + settings.service_name + "'} 1\n"


@app.get("/trace")
async def trace() -> dict[str, str]:
    return {"service": settings.service_name, "trace_policy": "all requests emit deterministic trace headers"}
