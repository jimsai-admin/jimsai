from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from fastapi import Depends, FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .jimsai.auth import AuthSettings, require_scope, supabase_auth_configured, supabase_password_auth, supabase_refresh_auth
from .jimsai.models import (
    CanvasRunRequest,
    FeedbackRequest,
    InventionRunRequest,
    KaggleTrainingRequest,
    MathSolveRequest,
    MemoryDeleteRequest,
    MemoryRollbackRequest,
    MemoryUpdateRequest,
    PipelineRequest,
    ReviewActionRequest,
    SandboxRunRequest,
    TrainingIngestRequest,
)
from .jimsai.pipeline import JimsAIPipeline

app = FastAPI(title="JIMS-AI Phase 1 Prototype", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://127.0.0.1:3001,http://localhost:3001,http://127.0.0.1:3000,http://localhost:3000",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
pipeline = JimsAIPipeline()


class PasswordAuthRequest(BaseModel):
    email: str
    password: str


class RefreshAuthRequest(BaseModel):
    refresh_token: str


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
async def health() -> dict[str, str]:
    return {"status": "ok", "architecture": "hybrid transformer-interface cognitive runtime"}


@app.get("/v1/auth/config")
async def auth_config() -> dict[str, bool | str]:
    settings = AuthSettings.from_env()
    return {
        "configured": supabase_auth_configured(settings),
        "provider": settings.provider,
        "required": settings.required,
    }


@app.post("/v1/auth/signin")
async def auth_signin(request: PasswordAuthRequest):
    return await supabase_password_auth(request.email, request.password, "signin")


@app.post("/v1/auth/signup")
async def auth_signup(request: PasswordAuthRequest):
    return await supabase_password_auth(request.email, request.password, "signup")


@app.post("/v1/auth/refresh")
async def auth_refresh(request: RefreshAuthRequest):
    return await supabase_refresh_auth(request.refresh_token)


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    stats = pipeline.memory.stats()
    return "\n".join(f"jimsai_memory_{key} {value}" for key, value in stats.items()) + "\n"


@app.post("/v1/query", dependencies=[Depends(require_scope("runtime:query"))])
async def query(request: PipelineRequest):
    return await pipeline.run(request)


@app.post("/v1/training/ingest", dependencies=[Depends(require_scope("training:write"))])
async def training_ingest(request: TrainingIngestRequest):
    return await pipeline.ingest_training(request)


@app.post("/v1/feedback", dependencies=[Depends(require_scope("feedback:write"))])
async def feedback(request: FeedbackRequest):
    return await pipeline.record_feedback(request)


@app.post("/v1/review/action", dependencies=[Depends(require_scope("training:write"))])
async def review_action(request: ReviewActionRequest):
    return await pipeline.review_action(request)


@app.post("/v1/sandbox/run", dependencies=[Depends(require_scope("runtime:query"))])
async def sandbox_run(request: SandboxRunRequest):
    return await pipeline.run_sandbox(request)


@app.post("/v1/math/solve", dependencies=[Depends(require_scope("runtime:query"))])
async def math_solve(request: MathSolveRequest):
    return await pipeline.solve_math(request)


@app.get("/v1/training/dashboard", dependencies=[Depends(require_scope("training:read"))])
async def training_dashboard():
    return await pipeline.training_dashboard()


@app.get("/v1/training/panels/{panel}/items", dependencies=[Depends(require_scope("training:read"))])
async def training_panel_items(panel: str, cursor: str | None = None, limit: int = 25):
    return await pipeline.training_panel_page(panel, cursor=cursor, limit=limit)


@app.post("/v1/canvas/run", dependencies=[Depends(require_scope("training:write"))])
async def canvas_run(request: CanvasRunRequest):
    return await pipeline.schedule_canvas(request)


@app.get("/v1/canvas/status/{session_id}")
async def canvas_status(session_id: str):
    status = await pipeline.canvas_status(session_id)
    if status is None:
        raise HTTPException(status_code=404, detail="canvas session not found")
    return status


@app.post("/v1/invention/run", dependencies=[Depends(require_scope("training:write"))])
async def invention_run(request: InventionRunRequest):
    return await pipeline.schedule_invention(request)


@app.post("/v1/training/kaggle/run", dependencies=[Depends(require_scope("training:write"))])
async def kaggle_training_run(request: KaggleTrainingRequest):
    return await pipeline.schedule_kaggle_training(request)


@app.post("/v1/training/kaggle/{run_id}/sync", dependencies=[Depends(require_scope("training:write"))])
async def kaggle_training_sync(run_id: str):
    response = await pipeline.sync_kaggle_training(run_id)
    if response is None:
        raise HTTPException(status_code=404, detail="kaggle run not found")
    return response


@app.get("/v1/invention/status/{session_id}")
async def invention_status(session_id: str):
    status = await pipeline.invention_status(session_id)
    if status is None:
        raise HTTPException(status_code=404, detail="invention session not found")
    return status


@app.post("/v1/memory/insert", dependencies=[Depends(require_scope("training:write"))])
async def memory_insert(request: TrainingIngestRequest):
    return await pipeline.ingest_training(request)


@app.post("/v1/memory/update", dependencies=[Depends(require_scope("training:write"))])
async def memory_update(request: MemoryUpdateRequest):
    return await pipeline.update_memory(request)


@app.post("/v1/memory/delete", dependencies=[Depends(require_scope("training:write"))])
async def memory_delete(request: MemoryDeleteRequest):
    return await pipeline.delete_memory(request)


@app.post("/v1/memory/rollback", dependencies=[Depends(require_scope("training:write"))])
async def memory_rollback(request: MemoryRollbackRequest):
    return await pipeline.rollback_memory(request)


@app.get("/v1/memory/stats")
async def memory_stats() -> dict[str, int]:
    return pipeline.memory.stats()


@app.get("/v1/audit/events", dependencies=[Depends(require_scope("training:read"))])
async def audit_events(limit: int = 100):
    return await pipeline.audit_events(limit=limit)
