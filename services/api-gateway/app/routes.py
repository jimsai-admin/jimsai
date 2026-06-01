from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from prototype.jimsai.auth import (
    AuthSettings,
    require_scope,
    supabase_auth_configured,
    supabase_password_auth,
    supabase_refresh_auth,
)
from prototype.jimsai.models import (
    CanvasRunRequest,
    FeedbackRequest,
    InventionRunRequest,
    KaggleTrainingRequest,
    MathSolveRequest,
    MemoryDeleteRequest,
    MemoryUpdateRequest,
    PipelineRequest,
    ReviewActionRequest,
    SandboxRunRequest,
    TrainingIngestRequest,
)
from prototype.jimsai.pipeline import JimsAIPipeline

router = APIRouter()
pipeline = JimsAIPipeline()


class AuthEmailPasswordRequest(BaseModel):
    email: str
    password: str


class AuthRefreshRequest(BaseModel):
    refresh_token: str


class ChatThreadDeleteRequest(BaseModel):
    user_id: str


@router.get("/v1/auth/config")
async def auth_config():
    settings = AuthSettings.from_env()
    return {
        "provider": settings.provider,
        "required": settings.required,
        "configured": supabase_auth_configured(settings),
        "default_scopes": settings.supabase_default_scopes,
    }


@router.post("/v1/auth/signin")
async def auth_signin(request: AuthEmailPasswordRequest):
    return await supabase_password_auth(request.email, request.password, "signin")


@router.post("/v1/auth/signup")
async def auth_signup(request: AuthEmailPasswordRequest):
    return await supabase_password_auth(request.email, request.password, "signup")


@router.post("/v1/auth/refresh")
async def auth_refresh(request: AuthRefreshRequest):
    return await supabase_refresh_auth(request.refresh_token)


@router.post("/v1/query", dependencies=[Depends(require_scope("runtime:query"))])
async def query(request: PipelineRequest):
    return await pipeline.run(request)

@router.post("/v1/training/ingest", dependencies=[Depends(require_scope("training:write"))])
async def training_ingest(request: TrainingIngestRequest):
    return await pipeline.ingest_training(request)

@router.post("/v1/feedback", dependencies=[Depends(require_scope("feedback:write"))])
async def feedback(request: FeedbackRequest):
    return await pipeline.record_feedback(request)

@router.get("/v1/training/dashboard", dependencies=[Depends(require_scope("training:read"))])
async def training_dashboard():
    return await pipeline.training_dashboard()

@router.get("/v1/training/panels/{panel}/items", dependencies=[Depends(require_scope("training:read"))])
async def training_panel_items(panel: str, cursor: str | None = None, limit: int = 25):
    return await pipeline.training_panel_page(panel, cursor=cursor, limit=limit)

@router.get("/v1/providers/readiness", dependencies=[Depends(require_scope("training:read"))])
async def provider_readiness():
    return pipeline.production.readiness()

@router.get("/v1/chat/threads", dependencies=[Depends(require_scope("runtime:query"))])
async def chat_threads(user_id: str, workspace_id: str | None = None, limit: int = 50):
    threads = pipeline.production.list_chat_threads(user_id=user_id, workspace_id=workspace_id, limit=limit)
    return {"threads": threads}

@router.get("/v1/chat/threads/{thread_id}/messages", dependencies=[Depends(require_scope("runtime:query"))])
async def chat_thread_messages(thread_id: str, user_id: str, limit: int = 200):
    messages = pipeline.production.list_chat_messages(thread_id=thread_id, user_id=user_id, limit=limit)
    return {"thread_id": thread_id, "messages": messages}

@router.delete("/v1/chat/threads/{thread_id}", dependencies=[Depends(require_scope("runtime:query"))])
async def chat_thread_delete(thread_id: str, request: ChatThreadDeleteRequest):
    deleted_messages = pipeline.production.delete_chat_thread(thread_id=thread_id, user_id=request.user_id)
    return {"accepted": True, "thread_id": thread_id, "deleted_messages": deleted_messages}

@router.post("/v1/review/action", dependencies=[Depends(require_scope("training:write"))])
async def review_action(request: ReviewActionRequest):
    return await pipeline.review_action(request)

@router.post("/v1/sandbox/run", dependencies=[Depends(require_scope("runtime:query"))])
async def sandbox_run(request: SandboxRunRequest):
    return await pipeline.run_sandbox(request)

@router.post("/v1/math/solve", dependencies=[Depends(require_scope("runtime:query"))])
async def math_solve(request: MathSolveRequest):
    return await pipeline.solve_math(request)

@router.post("/v1/memory/update", dependencies=[Depends(require_scope("training:write"))])
async def memory_update(request: MemoryUpdateRequest):
    return await pipeline.update_memory(request)

@router.post("/v1/memory/delete", dependencies=[Depends(require_scope("training:write"))])
async def memory_delete(request: MemoryDeleteRequest):
    return await pipeline.delete_memory(request)

@router.post("/v1/canvas/run", dependencies=[Depends(require_scope("training:write"))])
async def canvas_run(request: CanvasRunRequest):
    return await pipeline.schedule_canvas(request)

@router.get("/v1/canvas/status/{session_id}")
async def canvas_status(session_id: str):
    status = await pipeline.canvas_status(session_id)
    if status is None:
        raise HTTPException(status_code=404, detail="canvas session not found")
    return status

@router.post("/v1/invention/run", dependencies=[Depends(require_scope("training:write"))])
async def invention_run(request: InventionRunRequest):
    return await pipeline.schedule_invention(request)

@router.post("/v1/training/kaggle/run", dependencies=[Depends(require_scope("training:write"))])
async def kaggle_training_run(request: KaggleTrainingRequest):
    return await pipeline.schedule_kaggle_training(request)

@router.post("/v1/training/kaggle/{run_id}/sync", dependencies=[Depends(require_scope("training:write"))])
async def kaggle_training_sync(run_id: str):
    response = await pipeline.sync_kaggle_training(run_id)
    if response is None:
        raise HTTPException(status_code=404, detail="kaggle run not found")
    return response

@router.get("/v1/invention/status/{session_id}")
async def invention_status(session_id: str):
    status = await pipeline.invention_status(session_id)
    if status is None:
        raise HTTPException(status_code=404, detail="invention session not found")
    return status

@router.post("/v1/memory/insert", dependencies=[Depends(require_scope("training:write"))])
async def memory_insert(request: TrainingIngestRequest):
    return await pipeline.ingest_training(request)

@router.get("/v1/memory/stats", dependencies=[Depends(require_scope("training:read"))])
async def memory_stats():
    return pipeline.memory.stats()

@router.get("/v1/audit/events", dependencies=[Depends(require_scope("training:read"))])
async def audit_events(limit: int = 100):
    return await pipeline.audit_events(limit=limit)

@router.post("/v1/query/stream", dependencies=[Depends(require_scope("runtime:query"))])
async def query_stream(request: PipelineRequest):
    result = await pipeline.run(request)
    return {"events": [event.model_dump(mode="json") for event in result.trace], "final": result.response}

@router.get("/v1/memory/search", dependencies=[Depends(require_scope("training:read"))])
async def memory_search(user_id: str, q: str, provenance: str | None = None):
    compiled = pipeline.compiler.compile(q)
    results = pipeline.retrieval.retrieve(compiled, q)
    return {"user_id": user_id, "query": q, "results": [r.model_dump(mode="json") for r in results]}
