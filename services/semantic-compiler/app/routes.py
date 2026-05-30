from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime

router = APIRouter()
compiler = SemanticCompilerRuntime()

class CompileRequest(BaseModel):
    text: str
    namespace: str = "TECHNICAL"
    session: dict = {}

@router.post("/v1/compile")
async def compile_request(request: CompileRequest):
    return compiler.compile(request.text, request.namespace, request.session)

@router.post("/v1/resolve")
async def resolve_request(request: CompileRequest):
    tokens = compiler.compile(request.text, request.namespace, request.session).tokens
    return {"tokens": tokens, "hypotheses": compiler.score_intents(tokens)}
