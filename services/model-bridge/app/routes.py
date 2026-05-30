from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

SERVICE_CONTRACT = {
    "name": "model-bridge",
    "layer": "Bounded transformer interfaces",
    "purpose": "Provide controlled adapters for T1/T2, canvas, invention, cloud model providers, and strict bypass.",
    "deterministic": True,
    "endpoints": ['/v1/model/render', '/v1/model/intent'],
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

