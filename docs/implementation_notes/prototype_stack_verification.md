# Prototype Stack Verification

Date: 2026-05-27

## Verified Runnable Loop

The local Phase 1 prototype currently supports:

1. Training ingestion via `POST /v1/training/ingest`.
2. Signature creation with symbolic entities, relations, causal links, deterministic hash embedding, confidence, and provenance.
3. Memory insertion into the local four-layer memory store.
4. Causal graph insertion and bounded traversal.
5. World-model candidate extraction from causal links.
6. SPPE training-pair generation from the structured signature and original text.
7. Prompting via `POST /v1/query`.
8. Strict pipeline execution through input, T1 intent interface, L1 full encoder, L2 real-time learning, L3 Active Canvas, L4 sparse activation/meta-controller, L5 invention, L6 multi-index retrieval, L7 abstraction, L8 latent world model, L9 reasoning bridge, T2 render interface, output, and feedback.
9. Optional Groq bounded interfaces for T1, T2, Active Canvas, and Invention Engine, disabled by default to preserve deterministic local execution.
10. Separate browser UIs: `/training` for ingestion/SPPE/world-model review and `/user` for prompting, traces, sources, simulation, abstraction, and feedback.

## PDF Prototype Stack Status

| PDF stack item | Current status | Notes |
| --- | --- | --- |
| Python + FastAPI backend | Implemented locally | `prototype/app.py` and service scaffolds. |
| Next.js frontend | Implemented locally | App Router UI on port `3001`; Playwright smoke test passes. |
| Redis + Celery async queues | Scaffolded | Compose/config present; local runtime uses in-process state. |
| Neo4j Aura / graph DB | Local graph implemented, provider scaffolded | Causal graph engine is in memory; Neo4j adapter is not wired yet. |
| Supabase/PostgreSQL metadata | Scaffolded | PostgreSQL compose/init present; runtime metadata still in memory. |
| Cloudflare R2 raw storage | Scaffolded | Setup guide/env placeholders present; raw file storage adapter not wired. |
| Cloudflare Vectorize | Local deterministic vector adapter implemented, provider scaffolded | Hash vectors prove retrieval contract; Vectorize adapter not wired. |
| Groq canvas/invention/render models | Optional bounded adapter implemented | Enable with `GROQ_API_KEY` and `JIMS_ENABLE_GROQ_*`; deterministic runtime remains authoritative. |
| Nomic/SigLIP/HuBERT/Whisper encoders | Configured as target stack, local deterministic text encoder implemented | Heavy encoders are not installed/wired in Phase 1. |
| Playwright | Implemented | UI smoke test catches browser runtime errors and verifies ingest -> query. |
| Docker Compose | File present | Could not verify with `docker compose config` because Docker is not installed on this machine. |

## Verification Commands

```bash
python -m pytest
python benchmarks/determinism_benchmark.py
python benchmarks/hallucination_barrier.py
cd frontend && npm run build
cd frontend && npm run test:e2e
```

## Current Limitation

This is now a runnable local prototype for the strict 10-layer architecture loop. Groq is wired as a bounded interface, not as a replacement for the cognitive runtime. Redis, Neo4j Aura, Supabase, Cloudflare R2/Vectorize, and heavyweight local encoders are still represented by service/config/deployment boundaries rather than active production adapters inside the Phase 1 in-process runtime.
