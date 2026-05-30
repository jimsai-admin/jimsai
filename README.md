# JIMS-AI

JIMS-AI is a memory-centric intelligence architecture built from the PDF specification in
`docs/JimsAI_Complete_Specification_v8.pdf`. The implementation follows the document's core separation:
language is interpreted by a bounded transformer interface, converted into typed Semantic IR, processed through
structured memory, graph, simulation, validation, planning, and CSSE layers, then rendered from verified state.
The v9 expansion plan is captured in `docs/Jims_AI_v9.md`; it adds typed capability routing for world knowledge,
coding, math/science, creative text, media generation, and approved agentic tasks without replacing the v8 core.

This repository is not an LLM-only wrapper, and it is not deterministic-only rigidity. It is a hybrid cognitive
runtime: transformers interpret and render; the middle layers remember, retrieve, route, simulate, validate,
invent, and explain. The public surface can still be a chat interface because the transformer is used efficiently
at the boundary instead of owning the whole reasoning stack.

## Architecture Summary

The source document defines 10 cognitive layers plus two bounded transformer interfaces:

1. T1 intent interface: optional bounded conversion of human language chaos into a Semantic Intent Graph.
2. L1 encoder: dual symbolic and latent signatures.
3. L2 real-time learning: source trust, conflict checks, memory integration, indexes.
4. L3 Active Canvas: one-shot synthesis for large unstructured corpora.
5. L4 sparse activation and Meta-Controller: bounded routing with feedback-trained activation patterns.
6. L5 Invention Engine: planner, simulation, reflection, controlled novelty for novel tasks.
7. L6 multi-index retrieval: entity, semantic, temporal, causal, importance indexes.
8. L7 abstraction engine and concept lattice.
9. L8 latent world model and causal constraints.
10. L9 reasoning bridge: conflict resolution, gaps, confidence, reasoning chain.
11. L10 CSSE/SRE: meaning-first rendering from verified cognitive objects.
12. T2 render interface: optional bounded style/fluency renderer, never memory or reasoning.

## Local Development

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[providers,dev]"
pytest
uvicorn prototype.app:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev -- --port 3001
```

Open `http://localhost:3001/training` for the training console. Each operator panel is a separate route under
`/training/{panel}` with cursor-paged stored-data reads, and `http://localhost:3001/user` or
`http://localhost:3001/chat` opens the persistent chat runtime.

Query the Phase 1 runtime:

```bash
curl -X POST http://localhost:8000/v1/query ^
  -H "Content-Type: application/json" ^
  -d "{\"user_id\":\"local\",\"query\":\"What services are affected if UserModel.id changes?\"}"
```

Enable Groq bounded interfaces with `GROQ_API_KEY` and `JIMS_ENABLE_GROQ_T1/T2/CANVAS/INVENTION=true`.
Groq is used where the PDF places transformers: T1 intent interpretation, T2 fluent rendering, one-shot Canvas
synthesis, and bounded invention candidate generation. Memory, graph traversal, simulation, validation, planning,
and confidence scoring stay in the structured runtime.

## Docker Usage

The compose stack starts Redis, Neo4j, PostgreSQL, API Gateway, a Celery training worker, Semantic Compiler,
Graph Runtime, and the frontend:

```bash
docker compose up --build
```

## Infrastructure Overview

- Redis: distributed session state, IR hot cache, ontology staging.
- Neo4j Aura: causal graph, concept lattice, relationship traversal.
- PostgreSQL/Supabase: signature metadata, users, workspaces, review queues.
- Vector cache/Vectorize: embeddings and metadata for O(log n)-style retrieval paths.
- R2/S3-compatible storage: raw files, never queried directly.
- Prometheus/Grafana/OpenTelemetry: logs, metrics, traces.

Set `JIMS_STORAGE_BACKEND=production` to activate the real provider adapters for R2, Vectorize,
Supabase REST/Auth, Neo4j Aura, Redis/Celery, and external multimodal encoders. See `production/README.md` and
`.env.production.example`.

Run `python scripts/check_providers.py` after changing `.env`. The script performs redacted readiness checks for
R2, Vectorize, Supabase, Neo4j Aura, Redis/Celery, the external encoder service, and Kaggle orchestration.

For media training at public scale, the default path is now KaggleHub batch handoff:
`JIMS_MULTIMODAL_ENCODER_MODE=kaggle_batch`, `KAGGLE_API_TOKEN`, and `KAGGLE_DATASET_OWNER`. This uploads
training payloads as private Kaggle datasets for GPU notebooks and downloads notebook outputs as artifacts.
For low-latency media inference, deploy `services/multimodal-encoder` on a GPU host and switch
`JIMS_MULTIMODAL_ENCODER_MODE=external` with `JIMS_MULTIMODAL_ENCODER_URL`.
See `infrastructure/deployment/kagglehub_training.md`.

## Roadmap

See `ROADMAP.md`, `docs/implementation_notes/prototype_stack_verification.md`, and `docs/implementation_notes/deploy_to_test.md`.

## Contribution Guide

Contributions must preserve the PDF's architecture. Do not collapse JIMS-AI into an LLM-only flow, and do not
remove the bounded transformer interfaces the PDF explicitly defines. Every new module must expose logs, metrics,
traces, typed outputs, tests, and local setup.
