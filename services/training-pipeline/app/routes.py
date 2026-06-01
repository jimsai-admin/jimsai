from __future__ import annotations

import os

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from prototype.jimsai.models import KaggleTrainingRequest, TrainingIngestRequest
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
        "/v1/autonomous/cycle",
        "/v1/autonomous/kaggle/run",
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


def require_agent_token(authorization: str | None) -> None:
    expected = os.getenv("JIMS_RENDER_AGENT_TOKEN", "").strip()
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid agent token")


def get_pipeline() -> JimsAIPipeline:
    global pipeline
    if pipeline is None:
        pipeline = JimsAIPipeline()
    return pipeline

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
async def autonomous_cycle(request: AutonomousCycleRequest, authorization: str | None = Header(default=None)):
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
    return {
        "accepted": True,
        "cycle_completed": True,
        "ingestion_history": agent.ingestion_history[-1:] if agent.ingestion_history else [],
        "training_cycles": agent.training_cycles[-1:] if agent.training_cycles else [],
        "production_readiness": active_pipeline.production.readiness(),
    }


@router.post("/v1/autonomous/ingest-batch")
async def autonomous_ingest_batch(request: BatchIngestRequest, authorization: str | None = Header(default=None)):
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
    return {"accepted": True, "ingested": len(results), "results": results}


@router.post("/v1/autonomous/kaggle/run")
async def autonomous_kaggle_run(request: KaggleTrainingRequest, authorization: str | None = Header(default=None)):
    """Package persisted SPPE/signature history for Kaggle GPU training."""
    require_agent_token(authorization)
    active_pipeline = get_pipeline()
    response = await active_pipeline.schedule_kaggle_training(request)
    return response
