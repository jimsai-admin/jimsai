from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

SERVICE_CONTRACT = {
    "name": "lexical-frontier",
    "layer": "Semantic Expansion Graph / ontology staging",
    "purpose": "Manage synonym expansion, lexical frontier candidates, staging promotion, and edge decay.",
    "deterministic": True,
    "endpoints": ['/v1/frontier/candidates', '/v1/frontier/promote'],
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
