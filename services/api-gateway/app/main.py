from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from .config import settings
from .routes import router
from .telemetry import configure_logger, trace_middleware

logger = configure_logger(settings.service_name, settings.log_level)
app = FastAPI(title="JIMS-AI api-gateway", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(trace_middleware)
app.include_router(router)


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
