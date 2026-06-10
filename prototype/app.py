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
from .jimsai.env_config import get_config
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


@app.on_event("startup")
async def startup_warm_classifier() -> None:
    """Pre-warm the intent classifier prototype embeddings at startup.

    Moves the 2 HF Space batch calls for prototype embeddings from
    per-query (cold) to startup (once). After this runs, classify_intent()
    uses cached embeddings and adds ~0ms overhead per query.

    The embedding service health check runs in the background so it never
    delays server readiness — the HF Space can take 60-90s to cold-start
    and blocking startup for that long is unacceptable.
    """
    import asyncio
    import logging
    _logger = logging.getLogger("jimsai.startup")
    # Validate all required env vars on startup — raises RuntimeError if any missing
    try:
        get_config()
    except RuntimeError as exc:
        _logger.error("Required environment variable missing at startup: %s", exc)
        # Re-raise so the process exits cleanly rather than silently serving bad requests
        raise
    try:
        # Access the classifier to trigger lazy init
        classifier = pipeline.compiler.classifier
        # Pre-warm the embedding classifier if it has the method (i.e. _FallbackClassifier
        # is available via _LLMClassifier._embed_cls). Non-fatal if not available.
        embed_cls = getattr(classifier, "_embed_cls", None) or getattr(classifier, "_embedding_classifier", None)
        if embed_cls is None and hasattr(classifier, "_get_prototype_embeddings"):
            embed_cls = classifier  # direct _FallbackClassifier
        if embed_cls is not None:
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, embed_cls._get_prototype_embeddings),
                    timeout=30.0
                )
                await asyncio.wait_for(
                    loop.run_in_executor(None, embed_cls._get_memory_recall_embedding),
                    timeout=15.0
                )
                _logger.info("Intent classifier prototype embeddings pre-warmed successfully.")
            except asyncio.TimeoutError:
                _logger.warning("Startup classifier warm timed out — will warm on first query (non-fatal).")
        else:
            _logger.info("Classifier pre-warm skipped (LLM-first mode, no prototype embeddings to cache).")
    except Exception as exc:
        _logger.warning("Startup classifier warm failed (non-fatal): %s", repr(exc))

    # Embedding service health is checked on first encode call — no blocking startup check needed.
    # Use POST /v1/autonomous/reembed-hash after startup if Vectorize needs refreshing.

    # Modal services are pre-warmed by the client (test scripts, benchmark runner).
    # Server startup is intentionally kept lightweight — no blocking Modal calls.


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


@app.post("/v1/autonomous/reembed-hash", dependencies=[Depends(require_scope("training:write"))])
async def reembed_hash():
    """Re-embed all signatures stored with hash-projection fallback vectors.

    Uses batch embedding (one Modal call for all texts) for speed.
    Call once after the embedding service cold-starts.
    """
    import asyncio
    import logging
    import httpx as _httpx
    _logger = logging.getLogger("jimsai.reembed")

    try:
        adapter = pipeline.production.multimodal
        if adapter is None or not hasattr(adapter, "embed_batch"):
            raise HTTPException(status_code=503, detail="Multimodal encoder adapter not configured.")

        store = pipeline.production.postgres
        if not store.configured:
            raise HTTPException(status_code=503, detail="Supabase credentials not configured.")

        # Fetch signatures
        async with _httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                store._rest_url("signatures"),
                headers=store._rest_headers(),
                params={"select": "id,provenance,payload", "limit": "500"},
            )
            resp.raise_for_status()
            rows = resp.json()

        to_reembed = [
            r for r in rows
            if isinstance(r.get("payload"), dict)
            and r["payload"].get("metadata", {}).get("reembedding_required") is True
        ]
        _logger.info("reembed-hash: %d / %d need re-embedding", len(to_reembed), len(rows))
        if not to_reembed:
            return {"status": "ok", "total_found": 0, "reembedded": 0, "failed": 0}

        # Batch-embed all texts in a single Modal call (up to 100 per batch)
        loop = asyncio.get_event_loop()
        texts = [str(r["payload"].get("provenance") or r.get("provenance") or "") for r in to_reembed]
        BATCH = 100
        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            chunk = texts[i:i + BATCH]
            vecs = await loop.run_in_executor(None, adapter.embed_batch, chunk, "document")
            all_vectors.extend(vecs)

        reembedded = 0
        failed = 0
        async with _httpx.AsyncClient(timeout=20.0) as client:
            for row, vector in zip(to_reembed, all_vectors):
                if not vector:
                    failed += 1
                    continue
                try:
                    payload = dict(row["payload"])
                    payload.setdefault("metadata", {})
                    payload["metadata"]["reembedding_required"] = False
                    payload["metadata"]["latent_embedding_source"] = "external_service"
                    payload["latent_embedding"] = vector
                    patch_resp = await client.patch(
                        store._rest_url("signatures"),
                        headers=store._rest_headers(prefer="return=minimal"),
                        params={"id": f"eq.{row['id']}"},
                        json={"payload": payload},
                    )
                    patch_resp.raise_for_status()
                    reembedded += 1
                except Exception as exc:
                    _logger.warning("reembed patch failed for %s: %s", row.get("id"), exc)
                    failed += 1

        _logger.info("reembed-hash done: %d ok, %d failed", reembedded, failed)
        return {"status": "ok", "total_found": len(to_reembed), "reembedded": reembedded, "failed": failed}

    except HTTPException:
        raise
    except Exception as exc:
        import logging as _log; _log.getLogger("jimsai.reembed").error("reembed-hash: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/v1/chat/threads", dependencies=[Depends(require_scope("runtime:query"))])
async def chat_threads(user_id: str, workspace_id: str | None = None, limit: int = 50):
    threads = pipeline.production.postgres.list_chat_threads(user_id, workspace_id=workspace_id, limit=limit)
    return {"threads": threads}


@app.get("/v1/chat/threads/{thread_id}/messages", dependencies=[Depends(require_scope("runtime:query"))])
async def chat_thread_messages(thread_id: str, user_id: str, limit: int = 200):
    messages = pipeline.production.postgres.list_chat_messages(thread_id, user_id, limit=limit)
    return {"messages": messages}


@app.delete("/v1/chat/threads/{thread_id}", dependencies=[Depends(require_scope("training:write"))])
async def delete_chat_thread(thread_id: str):
    import httpx as _httpx
    store = pipeline.production.postgres
    async with _httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.delete(
            store._rest_url("chat_threads"),
            headers=store._rest_headers(prefer="return=minimal"),
            params={"id": f"eq.{thread_id}"},
        )
        resp.raise_for_status()
    return {"deleted": thread_id}
