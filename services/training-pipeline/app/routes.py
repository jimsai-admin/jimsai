from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, Body, Header, HTTPException, status
from pydantic import BaseModel, Field

from prototype.jimsai.models import KaggleTrainingRequest, TrainingIngestRequest, TrainingPanelItem
from prototype.jimsai.pipeline import JimsAIPipeline
from prototype.jimsai.autonomous_training_agent import AutonomousAgentConfig, AutonomousTrainingAgent

router = APIRouter()
pipeline: JimsAIPipeline | None = None

SERVICE_CONTRACT = {
    "name": "training-pipeline",
    "layer": "Unified Training Pipeline",
    "purpose": "Coordinate encoder signals, world model candidates, SPPE pairs, review queues, and feedback.",
    "deterministic": True,
    "endpoints": [
        "/v1/autonomous/ingest-batch",
        "/v1/autonomous/discover",
        "/v1/autonomous/evaluate",
        "/v1/autonomous/plan",
        "/v1/autonomous/reembed-hash",
        "/v1/autonomous/report",
        "/v1/autonomous/kaggle/package",
        "/v1/contract",
    ],
}

class DeterministicTask(BaseModel):
    trace_id: str | None = None
    payload: dict = {}


class AutonomousCycleRequest(BaseModel):
    user_id: str = "render:autonomous-agent"
    workspace_id: str | None = None
    max_documents: int = Field(default=100, ge=1, le=1000)
    batch_size: int = Field(default=25, ge=1, le=100)
    parallel_workers: int = Field(default=2, ge=1, le=8)
    data_sources: list[str] = Field(default_factory=lambda: ["user_interactions", "synthetic_generation"])


class BatchIngestRequest(BaseModel):
    user_id: str = "render:autonomous-agent"
    workspace_id: str | None = None
    domain_hint: str = "autonomous_render_ingest"
    source_trust: float = Field(default=0.82, ge=0.0, le=1.0)
    documents: list[str] = Field(default_factory=list, max_length=100)


class AutonomousGenericRequest(BaseModel):
    user_id: str = "render:autonomous-agent"
    workspace_id: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    payload: dict = Field(default_factory=dict)


class KagglePackageRequest(BaseModel):
    user_id: str = "render:autonomous-agent"
    workspace_id: str | None = None
    task_type: Literal["encoder_finetune", "reranker_finetune", "world_model_extractor", "sppe_refiner", "sppe_renderer_finetune"] = "encoder_finetune"
    title: str = "JIMS-AI encoder fine-tune"
    notes: str = "autonomous package"
    gpu: bool = True

    def to_training_request(self) -> KaggleTrainingRequest:
        return KaggleTrainingRequest(
            user_id=self.user_id,
            workspace_id=self.workspace_id,
            task_type=self.task_type,
            title=self.title,
            notes=self.notes,
            gpu=self.gpu,
        )


def require_agent_token(authorization: str | None) -> None:
    expected = os.getenv("JIMS_RENDER_AGENT_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="agent token not configured")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid agent token")


def get_pipeline() -> JimsAIPipeline:
    global pipeline
    if pipeline is None:
        pipeline = JimsAIPipeline()
    return pipeline


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_id(kind: str) -> str:
    return f"{kind}_{uuid4().hex[:16]}"


def save_run_state(table: str, row: dict) -> None:
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not supabase_url or not service_key:
        return
    try:
        httpx.post(
            f"{supabase_url}/rest/v1/{table}",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json=row,
            timeout=20,
        ).raise_for_status()
    except Exception:
        return


def save_panel_item(active_pipeline: JimsAIPipeline, item: TrainingPanelItem) -> None:
    active_pipeline.production.save_panel_items([item])


def autonomous_item(kind: str, title: str, payload: dict, panel: str = "autonomous") -> TrainingPanelItem:
    item_id = str(payload.get("id") or payload.get("run_id") or run_id(kind))
    return TrainingPanelItem(
        id=f"{panel}:{item_id}",
        panel=panel,
        kind=kind,
        title=title,
        subtitle=str(payload.get("status") or payload.get("summary") or ""),
        data=payload,
    )


def record_autonomous_run(active_pipeline: JimsAIPipeline, kind: str, status_value: str, metrics: dict, error: str | None = None) -> dict:
    now = utc_now_iso()
    row = {
        "id": run_id(kind),
        "run_type": kind,
        "status": status_value,
        "started_at": now,
        "finished_at": now if status_value in {"completed", "failed"} else None,
        "metrics": metrics,
        "error": error,
    }
    save_run_state("autonomous_runs", row)
    save_panel_item(active_pipeline, autonomous_item("autonomous_run", f"Autonomous {kind}", row))
    return row

@router.get("/v1/contract")
async def contract():
    return SERVICE_CONTRACT

@router.post("/v1/execute")
async def execute(task: DeterministicTask):
    return {
        "service": SERVICE_CONTRACT["name"],
        "trace_id": task.trace_id,
        "accepted": True,
        "deterministic": True,
        "payload_keys": sorted(task.payload.keys()),
    }


@router.post("/v1/autonomous/cycle")
async def autonomous_cycle(request: AutonomousCycleRequest = Body(default_factory=AutonomousCycleRequest), authorization: str | None = Header(default=None)):
    """Run one bounded autonomous cycle from a pingable Render web service."""
    require_agent_token(authorization)
    active_pipeline = get_pipeline()
    config = AutonomousAgentConfig(
        data_sources=request.data_sources,
        parallel_workers=request.parallel_workers,
        batch_size=request.batch_size,
        max_documents_per_cycle=request.max_documents,
    )
    agent = AutonomousTrainingAgent(active_pipeline, config)
    await agent._execute_cycle()
    record_autonomous_run(
        active_pipeline,
        "cycle",
        "completed",
        {
            "ingestion_history": agent.ingestion_history[-1:] if agent.ingestion_history else [],
            "training_cycles": agent.training_cycles[-1:] if agent.training_cycles else [],
        },
    )
    return {
        "accepted": True,
        "cycle_completed": True,
        "ingestion_history": agent.ingestion_history[-1:] if agent.ingestion_history else [],
        "training_cycles": agent.training_cycles[-1:] if agent.training_cycles else [],
        "production_readiness": active_pipeline.production.readiness(),
    }


@router.post("/v1/autonomous/discover")
async def autonomous_discover(request: AutonomousGenericRequest = Body(default_factory=AutonomousGenericRequest), authorization: str | None = Header(default=None)):
    """Create bounded autonomous discovery jobs without doing long-running work inline."""
    require_agent_token(authorization)
    active_pipeline = get_pipeline()
    job = {
        "id": run_id("job"),
        "job_type": "discover",
        "status": "queued",
        "priority": 100,
        "payload": {"workspace_id": request.workspace_id, "limit": request.limit, **request.payload},
        "scheduled_at": utc_now_iso(),
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    save_run_state("autonomous_jobs", job)
    save_panel_item(active_pipeline, autonomous_item("autonomous_job", "Discovery job queued", job))
    record_autonomous_run(active_pipeline, "discover", "completed", {"jobs_created": 1, "limit": request.limit})
    return {"accepted": True, "job": job}


@router.post("/v1/autonomous/ingest-batch")
async def autonomous_ingest_batch(request: BatchIngestRequest = Body(default_factory=BatchIngestRequest), authorization: str | None = Header(default=None)):
    """Ingest a bounded document batch into the same production stores Lambda reads."""
    require_agent_token(authorization)
    active_pipeline = get_pipeline()
    results = []
    for content in request.documents:
        if not content.strip():
            continue
        response = await active_pipeline.ingest_training(
            TrainingIngestRequest(
                user_id=request.user_id,
                workspace_id=request.workspace_id,
                content=content,
                domain_hint=request.domain_hint,
                source_trust=request.source_trust,
            )
        )
        results.append(
            {
                "signature_id": response.signature.id,
                "confidence": response.signature.confidence.score,
                "sppe_accepted": response.sppe_training_pair.accepted,
                "world_model_candidates": len(response.world_model_candidates),
            }
        )
    run = record_autonomous_run(active_pipeline, "ingest-batch", "completed", {"ingested": len(results), "requested": len(request.documents)})
    return {"accepted": True, "run": run, "ingested": len(results), "results": results}


@router.post("/v1/autonomous/kaggle/run")
@router.post("/v1/autonomous/kaggle/package")
async def autonomous_kaggle_run(request: KagglePackageRequest = Body(default_factory=KagglePackageRequest), authorization: str | None = Header(default=None)):
    """Package persisted SPPE/signature history for Kaggle GPU training."""
    require_agent_token(authorization)
    active_pipeline = get_pipeline()
    training_request = request.to_training_request()
    response = await active_pipeline.schedule_kaggle_training(training_request)
    batch = {
        "id": response.run_id,
        "workspace_id": training_request.workspace_id or "default",
        "task_type": training_request.task_type,
        "status": response.status,
        "item_count": len(active_pipeline.training_history),
        "storage_url": response.local_path,
        "manifest": response.model_dump(mode="json"),
        "created_at": response.submitted_at.isoformat(),
        "updated_at": utc_now_iso(),
    }
    save_run_state("training_batches", batch)
    save_panel_item(active_pipeline, autonomous_item("training_batch", f"Kaggle package {response.status}", batch, panel="artifacts"))
    record_autonomous_run(active_pipeline, "kaggle-package", "completed", {"run_id": response.run_id, "status": response.status})
    return response


@router.post("/v1/autonomous/evaluate")
async def autonomous_evaluate(request: AutonomousGenericRequest = Body(default_factory=AutonomousGenericRequest), authorization: str | None = Header(default=None)):
    require_agent_token(authorization)
    active_pipeline = get_pipeline()
    dashboard = await active_pipeline.training_dashboard()
    metrics = {
        "memory_stats": dashboard.memory_stats,
        "pipeline_monitor": dashboard.pipeline_monitor,
        "production_readiness": dashboard.production_readiness,
    }
    report = {
        "id": run_id("eval"),
        "artifact_id": request.payload.get("artifact_id"),
        "workspace_id": request.workspace_id,
        "report_type": "autonomous_evaluation",
        "metrics": metrics,
        "summary": "Bounded evaluation completed from current training dashboard state.",
        "created_at": utc_now_iso(),
    }
    save_run_state("evaluation_reports", report)
    save_panel_item(active_pipeline, autonomous_item("evaluation_report", "Autonomous evaluation", report, panel="evaluation"))
    run = record_autonomous_run(active_pipeline, "evaluate", "completed", {"report_id": report["id"]})
    return {"accepted": True, "run": run, "report": report}


@router.post("/v1/autonomous/reembed-hash")
async def autonomous_reembed_hash(request: AutonomousGenericRequest = Body(default_factory=AutonomousGenericRequest), authorization: str | None = Header(default=None)):
    """Replace recoverable hash vectors with sentence-transformer vectors when the embedding service is healthy."""
    require_agent_token(authorization)
    active_pipeline = get_pipeline()
    candidates = []
    seen: set[str] = set()
    for signature in [*active_pipeline.memory.all_signatures(), *active_pipeline.production.load_recent_signatures(limit=max(request.limit * 4, 100))]:
        if signature.id in seen:
            continue
        seen.add(signature.id)
        metadata = signature.metadata or {}
        if metadata.get("reembedding_required") or metadata.get("latent_embedding_source") == "hash_projection":
            candidates.append(signature)
        if len(candidates) >= request.limit:
            break

    updated = []
    skipped = []
    for signature in candidates:
        vector = active_pipeline.encoder._external_embedding(signature.raw_excerpt, signature.modality)
        if not vector:
            skipped.append(signature.id)
            continue
        signature.latent_embedding = vector
        signature.metadata["latent_embedding_source"] = "external_service"
        signature.metadata["reembedding_required"] = False
        signature.metadata["reembedded_at"] = utc_now_iso()
        active_pipeline.memory.update(signature)
        active_pipeline.production.save_training_ingest(
            signature,
            signature.raw_excerpt,
            [active_pipeline._signature_item(signature, panel="memory")],
        )
        updated.append(signature.id)

    metrics = {"candidates": len(candidates), "updated": len(updated), "skipped": len(skipped)}
    run = record_autonomous_run(active_pipeline, "reembed-hash", "completed", metrics)
    save_panel_item(
        active_pipeline,
        autonomous_item(
            "reembedding_run",
            "Hash fallback re-embedding",
            {"id": run["id"], "status": "completed", "updated": updated, "skipped": skipped, "metrics": metrics},
        ),
    )
    return {"accepted": True, "run": run, "updated": updated, "skipped": skipped}


@router.post("/v1/autonomous/plan")
async def autonomous_plan(request: AutonomousGenericRequest = Body(default_factory=AutonomousGenericRequest), authorization: str | None = Header(default=None)):
    require_agent_token(authorization)
    active_pipeline = get_pipeline()
    dashboard = await active_pipeline.training_dashboard()
    decision = dashboard.auto_training_decision.model_dump(mode="json") if dashboard.auto_training_decision else {}
    plan = {
        "id": run_id("plan"),
        "job_type": "training_plan",
        "status": "queued" if decision.get("should_schedule") else "completed",
        "priority": 80,
        "payload": {"workspace_id": request.workspace_id, "decision": decision, **request.payload},
        "scheduled_at": utc_now_iso(),
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    save_run_state("autonomous_jobs", plan)
    save_panel_item(active_pipeline, autonomous_item("autonomous_plan", "Training plan refreshed", plan))
    run = record_autonomous_run(active_pipeline, "plan", "completed", {"should_schedule": bool(decision.get("should_schedule"))})
    return {"accepted": True, "run": run, "plan": plan}


@router.post("/v1/autonomous/report")
async def autonomous_report(request: AutonomousGenericRequest = Body(default_factory=AutonomousGenericRequest), authorization: str | None = Header(default=None)):
    require_agent_token(authorization)
    active_pipeline = get_pipeline()
    dashboard = await active_pipeline.training_dashboard()
    summary = {
        "id": run_id("report"),
        "workspace_id": request.workspace_id or "default",
        "status": "completed",
        "summary": "Autonomous training report generated.",
        "memory_stats": dashboard.memory_stats,
        "pipeline_monitor": dashboard.pipeline_monitor,
        "created_at": utc_now_iso(),
    }
    save_panel_item(active_pipeline, autonomous_item("autonomous_report", "Autonomous training report", summary))
    run = record_autonomous_run(active_pipeline, "report", "completed", {"memory_stats": dashboard.memory_stats})
    return {"accepted": True, "run": run, "report": summary}
