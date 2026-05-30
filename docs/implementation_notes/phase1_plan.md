# Phase 1 Prototype Plan

## Objective

Prove the PDF's deterministic semantic execution path:

Input -> Semantic Compiler -> IR -> Signature -> Memory -> Retrieval -> Graph traversal -> Simulation ->
Constraint Validator -> Symbolic Planner -> CSSE -> auditable response.

## Implemented in This Scaffold

- Typed Pydantic data structures for IR, signatures, traces, plans, simulations, constraints, and verified
  cognitive objects.
- Semantic Compiler with sanitizer, deterministic matcher, multi-hypothesis resolver, and context inheritance.
- Deterministic local encoder with symbolic extraction and hash-vector embeddings.
- In-memory four-layer memory store with indexes.
- Bounded causal graph engine with reinforcement and edge decay hooks.
- Retrieval engine merging entity, semantic, temporal, causal, and importance signals.
- Bounded simulation engine and symbolic planner.
- Constraint validator that blocks unsupported claims and surfaces gaps.
- CSSE renderer using semantic primitives, confidence markers, source citations, and gap formatting.
- FastAPI app and service scaffolds.

## Definition of Done

- `pytest` passes.
- Repeated identical queries return identical IR and response.
- Responses include sources or explicit knowledge gaps.
- No service requires an LLM API key for core execution.
