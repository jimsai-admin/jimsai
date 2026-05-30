from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

SERVICE_CONTRACT = {
    "name": "hypothesis-resolver",
    "layer": "Multi-Hypothesis Resolver",
    "purpose": "Rank compound intents, preserve primary goals, overlays, and background warnings.",
    "deterministic": True,
    "endpoints": ['/v1/hypotheses/resolve', '/v1/hypotheses/trace'],
}

class DeterministicTask(BaseModel):
    trace_id: str | None = None
    payload: dict = {}

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
