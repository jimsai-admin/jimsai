from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

SERVICE_CONTRACT = {
    "name": "auth-service",
    "layer": "User and workspace control plane",
    "purpose": "Integrate Supabase Auth identities, workspaces, API access boundaries, and cloud-only authorization policy.",
    "deterministic": True,
    "endpoints": ['/v1/users', '/v1/workspaces'],
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
