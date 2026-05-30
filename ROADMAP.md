# JIMS-AI Roadmap

## Phase 1: Prototype

Goal: prove deterministic semantic execution.

- Semantic Compiler Runtime: sanitizer, deterministic intent matcher, multi-hypothesis resolver, typed IR.
- Shared semantic state objects and execution trace schema.
- Dual-representation text signatures with deterministic local embeddings.
- Four-layer in-memory store with entity, temporal, causal, semantic, and importance indexes.
- Bounded causal graph traversal and dependency tracing.
- Rule-based Meta-Controller and runtime router.
- Recursive planner and bounded simulation MVP.
- Constraint validator with schema, contradiction, gap, and source checks.
- CSSE/SRE deterministic renderer using semantic primitives and source citations.
- Benchmark harness for determinism, hallucination barrier, memory use, latency, and reproducibility.

## Phase 2: MVP

Goal: multi-service runtime aligned to the PDF's 24-week MVP.

- Redis session state, IR hot cache, ontology staging, and cache coherence.
- Neo4j graph runtime and concept lattice.
- PostgreSQL/Supabase metadata store and auth/workspace control plane.
- Cloudflare R2 raw asset layer and Vectorize-compatible vector cache.
- Active Canvas MVP for 100k-token datasets and async job orchestration.
- Invention Engine MVP with Recursive Planner, Simulation Engine, and invention signatures.
- Human review queues for confidence-gated world model candidates.
- Training UI panels and User Chat UI with memory, reasoning, simulation, and source trace controls.
- SDK, CLI, deployment pipeline, and agentic test harness.

## Phase 3: Production

Goal: scalable post-transformer cognitive infrastructure.

- Distributed graph runtime, graph contraction, A* namespace routing, bitmap intersection, and decay.
- Full five-module Invention Engine.
- Learned Meta-Controller trained from feedback while preserving deterministic execution gates.
- Mature abstraction engine, concept lattice, world models, and cross-domain analogy review.
- CSSE with Active Discourse State, CSP, Concept Lattice, SPPE, PIM, SSA, and SRE.
- Enterprise orchestration, per-user and workspace memory isolation, audit exports, and HA deployments.
- Energy and latency optimization with conditional T1/T2 invocation.

## Benchmarks

- Hallucination rate: claims must map to signatures or explicit gaps.
- Energy usage: proxy by module activations and transformer bypass rate.
- Memory usage: store/index growth per signature.
- Latency: compiler, retrieval, traversal, simulation, validation, CSSE.
- Determinism: same input and same memory produce same IR, plan, trace, and response.
- Reproducibility: seed-free deterministic outputs and stable trace hashes.
- Context scaling: retrieval over growing memory without full context recomputation.

## Deployment Milestones

- Local prototype with FastAPI and pytest.
- Docker compose for core services and local stores.
- Kubernetes manifests for service isolation.
- Terraform skeleton for managed stores.
- Render/Vast.ai deployment guides for CPU services and optional GPU jobs.
