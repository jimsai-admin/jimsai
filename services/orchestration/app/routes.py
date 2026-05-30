from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

SERVICE_CONTRACT = {
    "name": "orchestration",
    "layer": "L4 Sparse Activation and Meta-Controller",
    "purpose": "Route IR objects to retrieval, canvas, invention, simulation, and deterministic execution paths.",
    "deterministic": True,
    "endpoints": ['/v1/orchestrate', '/v1/activation/decision'],
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
