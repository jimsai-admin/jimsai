from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from prototype.jimsai.encoder import DualRepresentationEncoder
from prototype.jimsai.graph import CausalGraphEngine

router = APIRouter()
graph = CausalGraphEngine()
encoder = DualRepresentationEncoder()

class SignatureText(BaseModel):
    text: str

@router.post("/v1/graph/signature")
async def add_signature(request: SignatureText):
    signature = encoder.encode_text(request.text)
    graph.add_signature(signature)
    return {"signature": signature, "edge_count": sum(len(v) for v in graph.edges.values())}

@router.get("/v1/graph/traverse")
async def traverse(entity: str, depth: int = 3):
    return {"entity": entity, "paths": graph.traverse(entity, depth)}

@router.get("/v1/causal/trace")
async def causal_trace(entity: str, depth: int = 3):
    return {"entity": entity, "paths": graph.traverse(entity, depth)}
