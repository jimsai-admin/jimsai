# Architecture Analysis

Source of truth: `docs/JimsAI Complete Specification v9.pdf` plus current deployment/spec notes.

## Extracted Intent

The PDF defines JIMS-AI as persistent structured cognition, not a stateless chatbot. The key architectural
move is the Intelligence Separation Principle: memory, retrieval, synthesis, routing, invention, reasoning,
and generation are distinct mechanisms. Transformers may interpret and render at bounded interfaces, but
they must not retrieve, reason, plan, simulate, validate, or remember.

## Layer Mapping

| PDF Layer | Implementation Module | Phase 1 Status |
| --- | --- | --- |
| T1 Intent Interface | `prototype.jimsai.semantic_compiler` plus `services/semantic-compiler` | Deterministic compiler implemented; transformer hook is optional and bypassed. |
| L1 Encoder | `prototype.jimsai.encoder`, `services/semantic-parser` | Text signatures implemented with deterministic local embedding proxy. |
| L2 Real-Time Learning | `prototype.jimsai.memory`, `services/memory-runtime` | Four-layer in-memory store and indexes implemented. |
| L3 Active Canvas | `services/orchestration`, `services/model-bridge` | API scaffold and job contracts; full canvas is MVP/Phase 2. |
| L4 Sparse Activation | `prototype.jimsai.semantic_compiler`, `prototype.jimsai.pipeline` | Rule-based deterministic routing implemented. |
| L5 Invention Engine | `prototype.jimsai.planner`, `prototype.jimsai.simulation` | Recursive planner and bounded simulation MVP implemented. |
| L6 Multi-Index Retrieval | `prototype.jimsai.retrieval` | Entity, semantic, temporal, causal, importance ranking implemented locally. |
| L7 Abstraction Engine | `services/graph-runtime`, `prototype.jimsai.graph` | Concept lattice hooks scaffolded. |
| L8 World Model | `prototype.jimsai.graph`, `prototype.jimsai.constraints` | Causal rules and contradiction/gap checks implemented locally. |
| L9 Reasoning Bridge | `prototype.jimsai.constraints`, `prototype.jimsai.pipeline` | Verified Cognitive Object assembled with chain, sources, confidence, gaps. |
| L10 CSSE/SRE | `prototype.jimsai.csse` | Template and semantic primitive rendering implemented. |

## Mandatory Constraints Preserved

- Raw language never directly executes application logic.
- The IR object is the execution source of truth.
- Output rendering is constrained to verified claims, explicit gaps, and traceable sources.
- Graph traversal and memory retrieval are separate from language generation.
- Every service scaffold exposes health, metrics, traces, README, Dockerfile, tests, config, and API spec.

## Conservative Assumptions

- The Phase 1 prototype uses deterministic hash vectors instead of heavyweight encoders to preserve local
  development and low compute. The model names from the PDF remain in configuration for MVP replacement.
- External LLM/Groq calls are represented as optional adapters only. They are not in the deterministic runtime
  path and are not required to run tests.
- Neo4j, Redis, PostgreSQL, Vectorize, R2, and Supabase are scaffolded for Phase 2. Phase 1 uses in-memory
  adapters with the same contracts.

## v9 Additions To Preserve

- Memory, feedback, review, execution, and training state should move toward Event Sourcing/CQRS.
- Canvas, Invention, training, and sandbox execution need Saga-style orchestration with compensation steps.
- The Invention Engine should keep its planner boundary but use MCTS for large search spaces.
- Formal constraints should use SAT/SMT verification, with Z3 as the first practical target.
- Sandbox/code execution and symbolic math solving must write verified cached result signatures before returning.
- Admin UI should show a System Health Score and the limiting factor blocking the next maturity step.
