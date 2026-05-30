from __future__ import annotations

import shutil
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]


SERVICES = {
    "semantic-compiler": {
        "layer": "Semantic Compiler Runtime / T1 deterministic fallback",
        "purpose": "Compile human input into typed Semantic IR without allowing raw language to control execution.",
        "endpoints": ["/v1/compile", "/v1/resolve"],
    },
    "lexical-frontier": {
        "layer": "Semantic Expansion Graph / ontology staging",
        "purpose": "Manage synonym expansion, lexical frontier candidates, staging promotion, and edge decay.",
        "endpoints": ["/v1/frontier/candidates", "/v1/frontier/promote"],
    },
    "causal-graph-engine": {
        "layer": "L8 World Model and causal graph",
        "purpose": "Maintain causal links, dependency traces, reinforcement, and bounded causal traversal.",
        "endpoints": ["/v1/causal/trace", "/v1/causal/reinforce"],
    },
    "graph-runtime": {
        "layer": "L6 retrieval and Neo4j-backed graph runtime",
        "purpose": "Expose graph traversal, relationship lookup, concept lattice reads, and traceable graph writes.",
        "endpoints": ["/v1/graph/traverse", "/v1/graph/signature"],
    },
    "orchestration": {
        "layer": "L4 Sparse Activation and Meta-Controller",
        "purpose": "Route IR objects to retrieval, canvas, invention, simulation, and deterministic execution paths.",
        "endpoints": ["/v1/orchestrate", "/v1/activation/decision"],
    },
    "memory-runtime": {
        "layer": "L2 real-time learning and four-layer memory",
        "purpose": "Store signatures across sensory, working, episodic, and semantic memory with promotion rules.",
        "endpoints": ["/v1/memory/insert", "/v1/memory/search"],
    },
    "deterministic-executor": {
        "layer": "Immutable execution pass",
        "purpose": "Execute validated IR against parameterized handlers, never raw user language.",
        "endpoints": ["/v1/execute", "/v1/execution/trace"],
    },
    "api-gateway": {
        "layer": "External API layer",
        "purpose": "Expose query, memory, canvas, invention, reasoning, world model, and feedback endpoints.",
        "endpoints": ["/v1/query", "/v1/query/stream", "/v1/memory/search"],
    },
    "auth-service": {
        "layer": "User and workspace control plane",
        "purpose": "Integrate Supabase Auth identities, workspaces, API access boundaries, and cloud-only authorization policy.",
        "endpoints": ["/v1/users", "/v1/workspaces"],
    },
    "telemetry": {
        "layer": "Logs, metrics, execution traces",
        "purpose": "Collect deterministic trace events, Prometheus metrics, and audit logs from every service.",
        "endpoints": ["/v1/traces", "/v1/metrics/snapshot"],
    },
    "training-pipeline": {
        "layer": "Unified Training Pipeline",
        "purpose": "Coordinate encoder signals, world model candidates, SPPE pairs, review queues, and feedback.",
        "endpoints": ["/v1/training/ingest", "/v1/training/review-queue"],
    },
    "graph-decay-engine": {
        "layer": "Graph optimization",
        "purpose": "Run contraction shortcuts, A* frontier optimization, bitmap refresh, and generational edge decay.",
        "endpoints": ["/v1/decay/run", "/v1/decay/report"],
    },
    "hypothesis-resolver": {
        "layer": "Multi-Hypothesis Resolver",
        "purpose": "Rank compound intents, preserve primary goals, overlays, and background warnings.",
        "endpoints": ["/v1/hypotheses/resolve", "/v1/hypotheses/trace"],
    },
    "semantic-parser": {
        "layer": "L1 structured extraction",
        "purpose": "Extract entities, relations, causal chains, modality metadata, and source trust from inputs.",
        "endpoints": ["/v1/parse/text", "/v1/parse/signature"],
    },
    "system-ir": {
        "layer": "Typed IR schema registry",
        "purpose": "Version Semantic IR, Verified Cognitive Object, and shared semantic state schemas.",
        "endpoints": ["/v1/ir/schema", "/v1/ir/validate"],
    },
    "runtime-router": {
        "layer": "Conditional transformer and module invocation",
        "purpose": "Decide when to bypass T1/T2 and which deterministic modules must activate.",
        "endpoints": ["/v1/runtime/route", "/v1/runtime/transformer-decision"],
    },
    "workspace-connectors": {
        "layer": "Workspace and data ingestion",
        "purpose": "Connect local files, codebases, object storage, and workspace assets to the ingestion pipeline.",
        "endpoints": ["/v1/connectors/register", "/v1/connectors/ingest"],
    },
    "model-bridge": {
        "layer": "Bounded transformer interfaces",
        "purpose": "Provide controlled adapters for T1/T2, canvas, invention, cloud model providers, and strict bypass.",
        "endpoints": ["/v1/model/render", "/v1/model/intent"],
    },
}


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dedent(content).lstrip(), encoding="utf-8")


def touch(path: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()


def copy_pdf() -> None:
    src = ROOT / "Jims_AI_v8.pdf"
    dst = ROOT / "docs" / "JimsAI_Complete_Specification_v8.pdf"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copy2(src, dst)


def root_files() -> None:
    write(
        "README.md",
        """
        # JIMS-AI

        JIMS-AI is a memory-centric intelligence architecture built from the PDF specification in
        `docs/JimsAI_Complete_Specification_v8.pdf`. The implementation follows the document's core separation:
        language is interpreted at the boundary, converted into typed Semantic IR, processed through deterministic
        memory, graph, simulation, validation, planning, and CSSE layers, then rendered from verified state.

        This repository is not a chatbot wrapper. The runtime is organized as inspectable services and a runnable
        Phase 1 prototype that proves deterministic semantic execution.

        ## Architecture Summary

        The source document defines 10 cognitive layers plus two bounded transformer interfaces:

        1. T1 intent interface: optional bounded conversion of human language chaos into a Semantic Intent Graph.
        2. L1 encoder: dual symbolic and latent signatures.
        3. L2 real-time learning: source trust, conflict checks, memory integration, indexes.
        4. L3 Active Canvas: one-shot synthesis for large unstructured corpora.
        5. L4 sparse activation and Meta-Controller: deterministic routing.
        6. L5 Invention Engine: planner, simulation, reflection, controlled novelty for novel tasks.
        7. L6 multi-index retrieval: entity, semantic, temporal, causal, importance indexes.
        8. L7 abstraction engine and concept lattice.
        9. L8 latent world model and causal constraints.
        10. L9 reasoning bridge: conflict resolution, gaps, confidence, reasoning chain.
        11. L10 CSSE/SRE: deterministic rendering from verified cognitive objects.
        12. T2 render interface: optional bounded style/fluency renderer, never memory or reasoning.

        ## Local Development

        ```bash
        python -m venv .venv
        .venv\\Scripts\\activate
        python -m pip install -e ".[dev]"
        pytest
        uvicorn prototype.app:app --reload --port 8000
        ```

        Query the Phase 1 runtime:

        ```bash
        curl -X POST http://localhost:8000/v1/query ^
          -H "Content-Type: application/json" ^
          -d "{\\"user_id\\":\\"local\\",\\"query\\":\\"What services are affected if UserModel.id changes?\\"}"
        ```

        ## Docker Usage

        The compose stack starts Redis, Neo4j, PostgreSQL, API Gateway, Semantic Compiler, Graph Runtime, and the
        frontend:

        ```bash
        docker compose up --build
        ```

        ## Infrastructure Overview

        - Redis: distributed session state, IR hot cache, ontology staging.
        - Neo4j: causal graph, concept lattice, relationship traversal.
        - PostgreSQL/Supabase: signature metadata, users, workspaces, review queues.
        - Vector cache/Vectorize: embeddings and metadata for O(log n)-style retrieval paths.
        - R2/S3-compatible storage: raw files, never queried directly.
        - Prometheus/Grafana/OpenTelemetry: logs, metrics, traces.

        ## Roadmap

        See `ROADMAP.md` and `docs/implementation_notes/phase1_plan.md`.

        ## Contribution Guide

        Contributions must preserve the PDF's architecture. Do not replace deterministic execution with an LLM-only
        flow. Every new module must expose logs, metrics, traces, deterministic outputs, tests, and local setup.
        """,
    )
    write(
        "ROADMAP.md",
        """
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
        """,
    )
    write(
        ".env.example",
        """
        # Bounded model interfaces and optional external APIs
        OPENAI_API_KEY=
        ANTHROPIC_API_KEY=
        GOOGLE_API_KEY=
        GROQ_API_KEY=
        GROQ_CANVAS_MODEL=llama-3.1-70b-versatile
        GROQ_GENERATOR_MODEL=llama-3.1-8b-instant

        # Redis state runtime
        REDIS_URL=rediss://default:password@host:port/0
        # Neo4j graph runtime
        NEO4J_URI=neo4j+s://instance.databases.neo4j.io
        NEO4J_USER=neo4j
        NEO4J_USERNAME=neo4j
        NEO4J_PASSWORD=password

        # Structured storage
        SUPABASE_URL=https://project-ref.supabase.co
        SUPABASE_URL=
        SUPABASE_KEY=
        SUPABASE_ANON_KEY=
        SUPABASE_SERVICE_KEY=

        # Object and vector storage
        AWS_ACCESS_KEY_ID=
        AWS_SECRET_ACCESS_KEY=
        S3_BUCKET=jimsai-files
        CLOUDFLARE_ACCOUNT_ID=
        CLOUDFLARE_API_TOKEN=
        CF_ACCOUNT_ID=
        CF_R2_BUCKET=jimsai-files
        CF_R2_ACCESS_KEY=
        CF_R2_SECRET_KEY=
        CF_VECTORIZE_INDEX=jimsai-embeddings
        CF_VECTORIZE_API_TOKEN=
        # External multimodal encoder service
        JIMS_ENABLE_MULTIMODAL_ENCODERS=true
        JIMS_MULTIMODAL_ENCODER_MODE=external
        JIMS_MULTIMODAL_ENCODER_URL=https://encoder.example.com
        JIMS_MULTIMODAL_ENCODER_API_KEY=replace-with-encoder-service-key

        # Observability
        GRAFANA_PASSWORD=admin
        PROMETHEUS_ENDPOINT=http://localhost:9090
        OTEL_EXPORTER_OTLP_ENDPOINT=https://otel.example.com
        LOG_LEVEL=INFO

        # GPU and batch jobs
        VAST_API_KEY=
        VAST_TEMPLATE_ID=
        CANVAS_MAX_TOKENS=100000
        SIMULATION_TIME_BUDGET_MS=200
        """,
    )
    write(
        "docker-compose.yml",
        """
        services:
          redis:
            image: redis:7-alpine
            ports:
              - "6379:6379"

          neo4j:
            image: neo4j:5-community
            environment:
              NEO4J_AUTH: neo4j/password
            ports:
              - "7474:7474"
              - "7687:7687"
            volumes:
              - neo4j-data:/data

          postgres:
            image: postgres:16-alpine
            environment:
              POSTGRES_DB: jimsai
              POSTGRES_USER: jimsai
              POSTGRES_PASSWORD: jimsai
            ports:
              - "5432:5432"
            volumes:
              - postgres-data:/var/lib/postgresql/data
              - ./infrastructure/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro

          api-gateway:
            build:
              context: .
              dockerfile: services/api-gateway/Dockerfile
            env_file: .env.example
            environment:
              SERVICE_NAME: api-gateway
              REDIS_URL: redis://redis:6379/0
              NEO4J_URI: bolt://neo4j:7687
            ports:
              - "8000:8000"
            depends_on:
              - redis
              - neo4j
              - postgres

          semantic-compiler:
            build:
              context: .
              dockerfile: services/semantic-compiler/Dockerfile
            env_file: .env.example
            environment:
              SERVICE_NAME: semantic-compiler
              REDIS_URL: redis://redis:6379/0
            ports:
              - "8010:8000"
            depends_on:
              - redis

          graph-runtime:
            build:
              context: .
              dockerfile: services/graph-runtime/Dockerfile
            env_file: .env.example
            environment:
              SERVICE_NAME: graph-runtime
              NEO4J_URI: bolt://neo4j:7687
            ports:
              - "8020:8000"
            depends_on:
              - neo4j

          frontend:
            build:
              context: .
              dockerfile: frontend/Dockerfile
            environment:
              NEXT_PUBLIC_API_BASE_URL: http://localhost:8000
            ports:
              - "3000:3000"
            depends_on:
              - api-gateway

        volumes:
          neo4j-data:
          postgres-data:
        """,
    )
    write(
        "pyproject.toml",
        """
        [build-system]
        requires = ["setuptools>=68"]
        build-backend = "setuptools.build_meta"

        [project]
        name = "jims-ai"
        version = "0.1.0"
        description = "Deterministic memory-centric AI runtime based on the JIMS-AI v8 specification"
        requires-python = ">=3.11"
        dependencies = [
          "fastapi>=0.111",
          "uvicorn>=0.30",
          "pydantic>=2.7",
          "pydantic-settings>=2.3",
          "python-multipart>=0.0.9",
          "prometheus-client>=0.20",
          "httpx>=0.27"
        ]

        [project.optional-dependencies]
        dev = ["pytest>=8.2", "pytest-asyncio>=0.23"]

        [tool.setuptools.packages.find]
        where = ["."]
        include = ["prototype*"]

        [tool.pytest.ini_options]
        testpaths = ["tests"]
        asyncio_mode = "auto"
        """,
    )
    write(
        ".gitignore",
        """
        .venv/
        __pycache__/
        *.pyc
        .pytest_cache/
        .mypy_cache/
        node_modules/
        .next/
        .env
        *.db
        datasets/lancedb/
        logs/
        """,
    )


def docs() -> None:
    write(
        "docs/architecture/architecture_analysis.md",
        """
        # Architecture Analysis

        Source of truth: `docs/JimsAI_Complete_Specification_v8.pdf`.

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
        """,
    )
    write(
        "docs/architecture/dependency_graph.md",
        """
        # Dependency Graph

        ```mermaid
        graph TD
          Input[Input: text/code/image/audio/files] --> T1[T1 Intent Interface / Semantic Compiler]
          T1 --> IR[Typed Semantic IR]
          IR --> L1[L1 Encoder]
          L1 --> Sig[Dual Representation Signature]
          Sig --> L2[L2 Real-Time Learning]
          L2 --> Memory[Four-Layer Memory Store]
          L2 --> Graph[Neo4j / Causal Graph]
          L2 --> Vector[Vector Cache]
          IR --> L4[L4 Sparse Activation / Meta-Controller]
          L4 --> L3[L3 Active Canvas if global synthesis]
          L4 --> L5[L5 Invention Engine if novel]
          Memory --> L6[L6 Multi-Index Retrieval]
          Graph --> L6
          Vector --> L6
          L6 --> L7[L7 Abstraction / Concept Lattice]
          L7 --> L8[L8 World Model]
          L5 --> L8
          L8 --> L9[L9 Reasoning Bridge]
          L9 --> VCO[Verified Cognitive Object]
          VCO --> L10[L10 CSSE / SRE]
          L10 --> T2[T2 Optional Render Interface]
          T2 --> Output[Response + confidence + gaps + sources + trace]
          L10 --> Output
          Output --> Feedback[Feedback / Human Review]
          Feedback --> L2
          Feedback --> Graph
        ```

        ## Service Dependencies

        ```mermaid
        graph LR
          APIGW[api-gateway] --> SC[semantic-compiler]
          APIGW --> MR[memory-runtime]
          APIGW --> GR[graph-runtime]
          APIGW --> ORCH[orchestration]
          ORCH --> RR[runtime-router]
          ORCH --> HR[hypothesis-resolver]
          ORCH --> DE[deterministic-executor]
          MR --> SP[semantic-parser]
          GR --> CG[causal-graph-engine]
          GR --> GDE[graph-decay-engine]
          TP[training-pipeline] --> MR
          TP --> GR
          TP --> LF[lexical-frontier]
          MB[model-bridge] --> ORCH
          TEL[telemetry] --> APIGW
          TEL --> SC
          TEL --> GR
          TEL --> MR
          AUTH[auth-service] --> APIGW
          WC[workspace-connectors] --> TP
          SIR[system-ir] --> SC
          SIR --> DE
        ```
        """,
    )
    write(
        "docs/diagrams/runtime_pipeline.mmd",
        """
        sequenceDiagram
          participant U as User
          participant API as API Gateway
          participant SC as Semantic Compiler
          participant MEM as Memory Runtime
          participant G as Graph Runtime
          participant OR as Orchestration
          participant EX as Deterministic Executor
          participant CS as CSSE

          U->>API: POST /v1/query
          API->>SC: compile raw input
          SC-->>API: typed Semantic IR + hypotheses
          API->>MEM: encode and retrieve signatures
          API->>G: bounded causal traversal
          API->>OR: activation decision
          OR->>EX: execute deterministic plan
          EX-->>API: verified plan + simulation + constraints
          API->>CS: render Verified Cognitive Object
          CS-->>API: response + gaps + citations
          API-->>U: auditable response
        """,
    )
    write(
        "docs/implementation_notes/assumptions.md",
        """
        # Implementation Assumptions

        1. The PDF is authoritative. When the repo request used names not literally present in the PDF, the nearest
           PDF-aligned interpretation was used.
        2. Phase 1 must be local-first, so heavyweight encoders are represented by deterministic local adapters.
           This keeps bounded execution and testability while preserving the dual-representation contract.
        3. The deterministic compiler path is primary. Transformer adapters are optional boundary interfaces and are
           never required for runtime correctness.
        4. Production stores are represented by service contracts and Docker services. In-memory implementations
           prove behavior before Redis/Neo4j/PostgreSQL adapters are wired.
        5. The benchmark suite reports local deterministic metrics now and leaves external LLM comparisons behind
           explicit API-key-controlled adapters.
        """,
    )
    write(
        "docs/implementation_notes/phase1_plan.md",
        """
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
        """,
    )
    write(
        "docs/research/benchmarking_methodology.md",
        """
        # Benchmarking Methodology

        Phase 1 benchmarks are deterministic local measurements. External GPT-style, transformer pipeline, and
        agentic runtime comparisons are adapter-based and must not be called unless keys are configured.

        Metrics:

        - Hallucination rate: count unsupported claims not backed by a source signature or explicit gap.
        - Energy proxy: module activations, transformer bypass count, and wall-clock runtime.
        - Memory usage: Python process RSS where available plus signature/index counts.
        - Latency: compiler, retrieval, graph traversal, simulation, validation, planner, CSSE.
        - Determinism: same input and memory must produce identical trace hash.
        - Reproducibility: benchmark config and data are versioned under `benchmarks/` and `datasets/`.
        - Context scaling: grow signatures and ensure retrieval does not reprocess all raw source text.
        """,
    )


def prototype_files() -> None:
    touch("prototype/__init__.py")
    write(
        "prototype/README.md",
        """
        # Phase 1 Prototype

        The prototype is a local deterministic runtime for the PDF pipeline. It does not call a transformer or remote
        API. It compiles input into Semantic IR, builds signatures, updates memory, traverses a graph, simulates
        bounded consequences, validates constraints, plans execution, and renders through CSSE.

        ```bash
        uvicorn prototype.app:app --reload --port 8000
        pytest tests
        ```
        """,
    )
    write(
        "prototype/jimsai/__init__.py",
        """
        from .pipeline import JimsAIPipeline

        __all__ = ["JimsAIPipeline"]
        """,
    )
    write(
        "prototype/jimsai/models.py",
        r'''
        from __future__ import annotations

        from datetime import datetime, timezone
        from enum import Enum
        from typing import Any, Literal
        from uuid import uuid4

        from pydantic import BaseModel, Field


        def utc_now() -> datetime:
            return datetime.now(timezone.utc)


        class ExecutionMode(str, Enum):
            DETERMINISTIC_CORE = "DETERMINISTIC_CORE"
            AIR_GAPPED_CONTAINER = "AIR_GAPPED_CONTAINER"
            TEMPLATE_RENDER = "TEMPLATE_RENDER"


        class Modality(str, Enum):
            TEXT = "text"
            CODE = "code"
            IMAGE = "image"
            AUDIO = "audio"
            VIDEO = "video"
            DATA = "data"


        class IntentDomain(str, Enum):
            WORKSPACE_OPERATION = "WORKSPACE_OPERATION"
            GENERAL_KNOWLEDGE = "GENERAL_KNOWLEDGE"
            EMOTIONAL_SOCIAL = "EMOTIONAL_SOCIAL"
            META_SYSTEM = "META_SYSTEM"
            UNKNOWN = "UNKNOWN"


        class TraceEvent(BaseModel):
            stage: str
            message: str
            data: dict[str, Any] = Field(default_factory=dict)
            timestamp: datetime = Field(default_factory=utc_now)


        class Hypothesis(BaseModel):
            target_ir: str
            score: float
            role: Literal["primary", "overlay", "secondary", "candidate"] = "candidate"
            reason: str = ""


        class SemanticIR(BaseModel):
            trace_id: str = Field(default_factory=lambda: uuid4().hex)
            target_ir: str
            system_action: str
            confidence: float
            scope_constraints: dict[str, Any] = Field(default_factory=dict)
            execution_mode: ExecutionMode = ExecutionMode.DETERMINISTIC_CORE
            domain_namespace: str = "TECHNICAL"
            intent_domain: IntentDomain = IntentDomain.WORKSPACE_OPERATION
            tokens: list[str] = Field(default_factory=list)
            hypotheses: list[Hypothesis] = Field(default_factory=list)
            context_inherited: bool = False
            context_boosted: bool = False


        class Entity(BaseModel):
            id: str
            name: str
            type: str = "concept"


        class Relation(BaseModel):
            subject: str
            predicate: str
            object: str
            confidence: float = 0.8


        class CausalLink(BaseModel):
            cause: str
            effect: str
            confidence: float = 0.8


        class TemporalInfo(BaseModel):
            tense: str = "present"
            timestamp: datetime = Field(default_factory=utc_now)


        class SignatureIntent(BaseModel):
            type: str
            certainty: str = "confirmed"


        class StructuredSignature(BaseModel):
            entities: list[Entity] = Field(default_factory=list)
            relations: list[Relation] = Field(default_factory=list)
            causal_chain: list[CausalLink] = Field(default_factory=list)
            temporal: TemporalInfo = Field(default_factory=TemporalInfo)
            intent: SignatureIntent = Field(default_factory=lambda: SignatureIntent(type="unknown"))


        class Confidence(BaseModel):
            score: float = 0.0
            source: str = "unknown"


        class Importance(BaseModel):
            retrieval_count: int = 0
            current_score: float = 0.5


        class MemorySignature(BaseModel):
            id: str
            provenance: str
            structured: StructuredSignature
            latent_embedding: list[float]
            abstraction_tags: list[str] = Field(default_factory=list)
            confidence: Confidence = Field(default_factory=Confidence)
            importance: Importance = Field(default_factory=Importance)
            modality: Modality = Modality.TEXT
            linked_signatures: list[str] = Field(default_factory=list)
            raw_excerpt: str = ""
            created_at: datetime = Field(default_factory=utc_now)


        class RetrievalResult(BaseModel):
            signature: MemorySignature
            score: float
            reasons: list[str] = Field(default_factory=list)


        class SimulationScope(BaseModel):
            entities: list[str] = Field(default_factory=list)
            depth: int = 3
            time_budget_ms: int = 200
            strategy: Literal["NEAREST_CAUSE", "CRITICAL_PATH", "FULL"] = "NEAREST_CAUSE"


        class SimulationResult(BaseModel):
            scenario: str
            passed: bool
            confidence: float
            outcomes: list[str] = Field(default_factory=list)
            scope: SimulationScope = Field(default_factory=SimulationScope)


        class ConstraintCheck(BaseModel):
            name: str
            passed: bool
            confidence: float
            detail: str


        class PlanStep(BaseModel):
            order: int
            action: str
            inputs: dict[str, Any] = Field(default_factory=dict)
            expected_output: str = ""


        class ExecutionPlan(BaseModel):
            goal: str
            steps: list[PlanStep]
            deterministic: bool = True


        class ReasoningStep(BaseModel):
            claim: str
            confidence: float
            sources: list[str] = Field(default_factory=list)
            relation: str = "ASSERT"


        class VerifiedCognitiveObject(BaseModel):
            trace_id: str
            intent: str
            verified_plan: ExecutionPlan
            simulation_results: list[SimulationResult] = Field(default_factory=list)
            constraint_checks: list[ConstraintCheck] = Field(default_factory=list)
            semantic_graph: dict[str, Any] = Field(default_factory=dict)
            reasoning_chain: list[ReasoningStep] = Field(default_factory=list)
            knowledge_gaps: list[str] = Field(default_factory=list)
            sources: list[str] = Field(default_factory=list)
            confidence: float = 0.0
            style_signature: dict[str, Any] = Field(default_factory=lambda: {"tone": "technical", "format": "answer"})
            generation_mode: Literal["FACT", "CREATIVE", "HYBRID", "TEMPLATE"] = "FACT"


        class PipelineRequest(BaseModel):
            user_id: str
            query: str
            modality: Modality = Modality.TEXT
            workspace_id: str | None = None
            canvas_hint: bool = False
            invention_hint: bool = False
            return_trace: bool = True


        class PipelineResponse(BaseModel):
            response: str
            ir: SemanticIR
            reasoning_chain: list[ReasoningStep]
            confidence: float
            gaps: list[str]
            sources: list[str]
            simulation_results: list[SimulationResult]
            trace: list[TraceEvent]


        class TrainingIngestRequest(BaseModel):
            user_id: str
            content: str
            modality: Modality = Modality.TEXT
            source_trust: float = Field(default=0.8, ge=0.0, le=1.0)
            domain_hint: str | None = None


        class WorldModelCandidate(BaseModel):
            rule: str
            confidence: float
            provenance: str
            review_required: bool


        class SPPETrainingPair(BaseModel):
            signature_id: str
            semantic_intention_graph: dict[str, Any]
            original_text: str
            confidence: float
            accepted: bool


        class TrainingIngestResponse(BaseModel):
            signature: MemorySignature
            world_model_candidates: list[WorldModelCandidate]
            sppe_training_pair: SPPETrainingPair
            memory_stats: dict[str, int]
            trace: list[TraceEvent]
        ''',
    )
    write(
        "prototype/jimsai/observability.py",
        """
        from __future__ import annotations

        import hashlib
        import json
        import logging
        from typing import Any

        from .models import TraceEvent


        def configure_logging(service_name: str, level: str = "INFO") -> logging.Logger:
            logging.basicConfig(
                level=getattr(logging, level.upper(), logging.INFO),
                format="%(asctime)s %(levelname)s %(name)s %(message)s",
            )
            return logging.getLogger(service_name)


        class ExecutionTracer:
            def __init__(self) -> None:
                self.events: list[TraceEvent] = []

            def add(self, stage: str, message: str, **data: Any) -> None:
                self.events.append(TraceEvent(stage=stage, message=message, data=data))

            def hash(self) -> str:
                payload = [
                    {"stage": e.stage, "message": e.message, "data": e.data}
                    for e in self.events
                ]
                encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
                return hashlib.sha256(encoded).hexdigest()
        """,
    )
    write(
        "prototype/jimsai/semantic_compiler.py",
        r'''
        from __future__ import annotations

        import math
        import re
        from collections import Counter
        from typing import Any

        from .models import ExecutionMode, Hypothesis, IntentDomain, SemanticIR


        STOP_WORDS = {
            "a", "an", "the", "yo", "please", "just", "over", "that", "we", "back", "in", "for",
            "to", "of", "and", "or", "on", "with", "can", "you", "i", "me", "my", "is", "are",
        }
        QUESTION_WORDS = {"What", "Why", "How", "When", "Where", "Who", "Which"}
        IMPACT_TOKENS = {"affect", "impact", "chang", "change", "happen", "break", "depend", "downstream", "upstream"}

        INTENT_TEMPLATES: dict[str, str] = {
            "FETCH_DOCUMENT": "pull layout document manifest file pdf page download view open retrieve",
            "SYSTEM_DIAGNOSTIC": "error broken status crash failure bug log deployment timeout diagnostic",
            "WORKSPACE_QUERY": "metrics analysis progress overview stats tracking services dependencies affected happen impact change downstream upstream",
            "CODE_GENERATE": "create build scaffold generate api route function class code implementation",
            "RUN_CANVAS": "analyse analyze deep scan full codebase corpus dataset synthesis everything uploaded",
            "RUN_INVENTION": "invent design novel architecture theorem hypothesis protocol plan new solution",
            "GENERAL_FACT": "what explain define describe capital concept general knowledge",
            "EMOTIONAL_CATCH": "stressed overwhelmed anxious confused giving up frustrated hard worried",
            "META_INQUIRY": "why answer confidence memory trace sources reasoning gaps explain yourself",
        }

        INTENT_DOMAINS: dict[str, IntentDomain] = {
            "GENERAL_FACT": IntentDomain.GENERAL_KNOWLEDGE,
            "EMOTIONAL_CATCH": IntentDomain.EMOTIONAL_SOCIAL,
            "META_INQUIRY": IntentDomain.META_SYSTEM,
        }


        def _stem(token: str) -> str:
            for suffix in ("ing", "ingly", "edly", "ed", "es", "s"):
                if len(token) > len(suffix) + 3 and token.endswith(suffix):
                    return token[: -len(suffix)]
            return token


        def sanitize(raw: str) -> list[str]:
            cleaned = re.sub(r"[^A-Za-z0-9_\-.\s]", " ", raw.lower())
            tokens = [_stem(t) for t in cleaned.split() if t and t not in STOP_WORDS]
            return tokens


        def _vectorize(tokens: list[str]) -> Counter[str]:
            return Counter(tokens)


        def _cosine(left: Counter[str], right: Counter[str]) -> float:
            if not left or not right:
                return 0.0
            dot = sum(left[t] * right.get(t, 0) for t in left)
            lnorm = math.sqrt(sum(v * v for v in left.values()))
            rnorm = math.sqrt(sum(v * v for v in right.values()))
            if lnorm == 0 or rnorm == 0:
                return 0.0
            return dot / (lnorm * rnorm)


        class SemanticCompilerRuntime:
            def __init__(self, confidence_threshold: float = 0.18) -> None:
                self.confidence_threshold = confidence_threshold
                self.template_vectors = {
                    intent: _vectorize(sanitize(template))
                    for intent, template in INTENT_TEMPLATES.items()
                }

            def score_intents(self, tokens: list[str]) -> list[Hypothesis]:
                user_vec = _vectorize(tokens)
                hypotheses = [
                    Hypothesis(target_ir=intent, score=round(_cosine(user_vec, vec), 4))
                    for intent, vec in self.template_vectors.items()
                ]
                hypotheses.sort(key=lambda h: (-h.score, h.target_ir))
                return hypotheses

            def resolve_hypotheses(self, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
                positive = [h for h in hypotheses if h.score > 0.0]
                if not positive:
                    return [Hypothesis(target_ir="OP_ESCAPE_TO_SANDBOX", score=0.0, role="primary", reason="No ontology match")]
                roles = ["primary", "overlay", "secondary"]
                resolved: list[Hypothesis] = []
                for idx, hyp in enumerate(positive[:3]):
                    role = roles[idx] if idx < len(roles) else "candidate"
                    resolved.append(hyp.model_copy(update={"role": role, "reason": "deterministic lexical score"}))
                return resolved

            def _scope_from_tokens(self, tokens: list[str], raw_input: str) -> dict[str, Any]:
                scope: dict[str, Any] = {"raw_length": len(raw_input), "token_count": len(tokens)}
                for token in tokens:
                    if re.fullmatch(r"\d+", token):
                        scope.setdefault("numbers", []).append(int(token))
                    if token.endswith(".pdf"):
                        scope["document_type"] = "PDF"
                    if token in {"april", "may", "june", "july"}:
                        scope["temporal_hint"] = token
                camel_entities = [
                    entity.strip(".,:;!?")
                    for entity in re.findall(r"\b[A-Z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)?\b", raw_input)
                    if entity not in QUESTION_WORDS
                ]
                if any(token.startswith("chang") for token in tokens):
                    camel_entities.extend(f"{entity}_change" for entity in list(camel_entities) if "." in entity)
                if camel_entities:
                    scope["entities"] = sorted(set(camel_entities))
                return scope

            def compile(self, raw_input: str, namespace: str = "TECHNICAL", session: dict[str, Any] | None = None) -> SemanticIR:
                session = session or {}
                tokens = sanitize(raw_input)
                hypotheses = self.resolve_hypotheses(self.score_intents(tokens))
                primary = hypotheses[0]
                target_ir = primary.target_ir
                confidence = primary.score
                scope = self._scope_from_tokens(tokens, raw_input)
                if scope.get("entities") and (set(tokens) & IMPACT_TOKENS):
                    target_ir = "WORKSPACE_QUERY"
                    confidence = max(confidence, 0.22)
                execution_mode = ExecutionMode.DETERMINISTIC_CORE
                if target_ir == "OP_ESCAPE_TO_SANDBOX" or confidence < self.confidence_threshold:
                    target_ir = "OP_ESCAPE_TO_SANDBOX"
                    execution_mode = ExecutionMode.AIR_GAPPED_CONTAINER
                context_inherited = False
                context_boosted = False
                if "entities" not in scope and session.get("ACTIVE_OBJECT"):
                    scope["entities"] = [session["ACTIVE_OBJECT"]]
                    context_inherited = True
                if confidence < 0.8 and session.get("ACTIVE_INTENT") == target_ir:
                    confidence = min(confidence + 0.15, 1.0)
                    context_boosted = True
                domain = INTENT_DOMAINS.get(target_ir, IntentDomain.WORKSPACE_OPERATION)
                return SemanticIR(
                    target_ir=target_ir,
                    system_action=target_ir,
                    confidence=round(confidence, 4),
                    scope_constraints=scope,
                    execution_mode=execution_mode,
                    domain_namespace=namespace,
                    intent_domain=domain,
                    tokens=tokens,
                    hypotheses=hypotheses,
                    context_inherited=context_inherited,
                    context_boosted=context_boosted,
                )
        ''',
    )
    write(
        "prototype/jimsai/encoder.py",
        r'''
        from __future__ import annotations

        import hashlib
        import math
        import re

        from .models import CausalLink, Confidence, Entity, MemorySignature, Modality, Relation, SignatureIntent, StructuredSignature


        RELATION_PATTERNS: list[tuple[str, str]] = [
            (r"(?P<subject>[A-Za-z][\w\.]+)\s+(depends on|requires|uses)\s+(?P<object>[A-Za-z][\w\.]+)", "depends_on"),
            (r"(?P<subject>[A-Za-z][\w\.]+)\s+(causes|triggers|invalidates|breaks)\s+(?P<object>[A-Za-z][\w\.]+)", "causes"),
            (r"if\s+(?P<subject>[A-Za-z][\w\.]+)\s+.*\s+then\s+(?P<object>[A-Za-z][\w\.]+)", "causes"),
        ]


        def clean_ref(value: str) -> str:
            return value.strip(".,:;!?")


        def stable_id(prefix: str, text: str) -> str:
            return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"


        def hash_embedding(text: str, dimensions: int = 64) -> list[float]:
            vector = [0.0] * dimensions
            for token in re.findall(r"[A-Za-z0-9_\.]+", text.lower()):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                idx = int.from_bytes(digest[:2], "big") % dimensions
                sign = 1.0 if digest[2] % 2 == 0 else -1.0
                vector[idx] += sign
            norm = math.sqrt(sum(v * v for v in vector)) or 1.0
            return [round(v / norm, 6) for v in vector]


        class DualRepresentationEncoder:
            def encode_text(self, text: str, intent_type: str = "workspace_query", provenance: str = "local_extraction") -> MemorySignature:
                entity_names = sorted({clean_ref(name) for name in re.findall(r"\b[A-Z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)?\b", text)})
                if not entity_names:
                    entity_names = sorted(set(re.findall(r"\b[a-z][a-z0-9_]{4,}\b", text.lower())))[:8]
                entities = [Entity(id=stable_id("ent", name), name=name, type="entity") for name in entity_names]
                relations: list[Relation] = []
                causal: list[CausalLink] = []
                for pattern, predicate in RELATION_PATTERNS:
                    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                        subject = clean_ref(match.group("subject"))
                        obj = clean_ref(match.group("object"))
                        relations.append(Relation(subject=subject, predicate=predicate, object=obj, confidence=0.82))
                        if predicate == "causes":
                            causal.append(CausalLink(cause=subject, effect=obj, confidence=0.82))
                structured = StructuredSignature(
                    entities=entities,
                    relations=relations,
                    causal_chain=causal,
                    intent=SignatureIntent(type=intent_type, certainty="confirmed"),
                )
                sig_id = stable_id("sig", f"{provenance}:{intent_type}:{text}")
                tags = sorted({intent_type, *[r.predicate for r in relations], *[e.name.lower() for e in entities[:4]]})
                return MemorySignature(
                    id=sig_id,
                    provenance=provenance,
                    structured=structured,
                    latent_embedding=hash_embedding(text),
                    abstraction_tags=tags,
                    confidence=Confidence(score=0.86 if text.strip() else 0.0, source="deterministic_encoder"),
                    modality=Modality.TEXT,
                    raw_excerpt=text[:500],
                )
        ''',
    )
    write(
        "prototype/jimsai/memory.py",
        """
        from __future__ import annotations

        from collections import defaultdict

        from .models import MemorySignature


        class FourLayerMemoryStore:
            def __init__(self) -> None:
                self.sensory: dict[str, MemorySignature] = {}
                self.working: dict[str, MemorySignature] = {}
                self.episodic: dict[str, MemorySignature] = {}
                self.semantic: dict[str, MemorySignature] = {}
                self.entity_index: dict[str, set[str]] = defaultdict(set)
                self.temporal_index: dict[str, set[str]] = defaultdict(set)
                self.causal_index: dict[str, set[str]] = defaultdict(set)
                self.importance_index: dict[str, float] = {}

            def insert(self, signature: MemorySignature) -> MemorySignature:
                self.sensory[signature.id] = signature
                if signature.confidence.score >= 0.75:
                    self.working[signature.id] = signature
                    self.episodic[signature.id] = signature
                if signature.confidence.score >= 0.85:
                    self.semantic[signature.id] = signature
                for entity in signature.structured.entities:
                    self.entity_index[entity.name.lower()].add(signature.id)
                month_key = signature.structured.temporal.timestamp.strftime("%Y-%m")
                self.temporal_index[month_key].add(signature.id)
                for link in signature.structured.causal_chain:
                    self.causal_index[link.cause.lower()].add(signature.id)
                    self.causal_index[link.effect.lower()].add(signature.id)
                self.importance_index[signature.id] = signature.importance.current_score
                return signature

            def all_signatures(self) -> list[MemorySignature]:
                merged = {**self.sensory, **self.working, **self.episodic, **self.semantic}
                return list(merged.values())

            def get(self, signature_id: str) -> MemorySignature | None:
                return self.semantic.get(signature_id) or self.episodic.get(signature_id) or self.working.get(signature_id) or self.sensory.get(signature_id)

            def by_entity(self, entity: str) -> list[MemorySignature]:
                return [self.get(sid) for sid in self.entity_index.get(entity.lower(), set()) if self.get(sid)]

            def stats(self) -> dict[str, int]:
                return {
                    "sensory": len(self.sensory),
                    "working": len(self.working),
                    "episodic": len(self.episodic),
                    "semantic": len(self.semantic),
                    "entity_terms": len(self.entity_index),
                    "causal_terms": len(self.causal_index),
                }
        """,
    )
    write(
        "prototype/jimsai/graph.py",
        """
        from __future__ import annotations

        import time
        from collections import defaultdict, deque
        from dataclasses import dataclass

        from .models import MemorySignature


        @dataclass
        class Edge:
            target: str
            predicate: str
            weight: float
            source_signature: str
            last_used: float


        class CausalGraphEngine:
            def __init__(self) -> None:
                self.edges: dict[str, list[Edge]] = defaultdict(list)

            def _add_edge(self, source: str, edge: Edge) -> None:
                source_key = source.lower()
                for existing in self.edges.get(source_key, []):
                    if (
                        existing.target == edge.target
                        and existing.predicate == edge.predicate
                        and existing.source_signature == edge.source_signature
                    ):
                        existing.weight = max(existing.weight, edge.weight)
                        existing.last_used = max(existing.last_used, edge.last_used)
                        return
                self.edges[source_key].append(edge)

            def add_signature(self, signature: MemorySignature) -> None:
                now = time.time()
                for relation in signature.structured.relations:
                    self._add_edge(
                        relation.subject,
                        Edge(relation.object.lower(), relation.predicate, relation.confidence, signature.id, now),
                    )
                for link in signature.structured.causal_chain:
                    self._add_edge(
                        link.cause,
                        Edge(link.effect.lower(), "causes", link.confidence, signature.id, now),
                    )

            def traverse(self, start: str, depth: int = 3) -> dict[str, list[dict[str, str | float]]]:
                start_key = start.lower()
                visited = {start_key}
                queue: deque[tuple[str, int]] = deque([(start_key, 0)])
                paths: dict[str, list[dict[str, str | float]]] = defaultdict(list)
                while queue:
                    node, level = queue.popleft()
                    if level >= depth:
                        continue
                    for edge in self.edges.get(node, []):
                        edge.last_used = time.time()
                        paths[node].append(
                            {
                                "target": edge.target,
                                "predicate": edge.predicate,
                                "weight": round(edge.weight, 4),
                                "source": edge.source_signature,
                            }
                        )
                        if edge.target not in visited:
                            visited.add(edge.target)
                            queue.append((edge.target, level + 1))
                return dict(paths)

            def reinforce(self, source: str, target: str, delta: float = 0.03) -> bool:
                for edge in self.edges.get(source.lower(), []):
                    if edge.target == target.lower():
                        edge.weight = min(1.0, edge.weight + delta)
                        edge.last_used = time.time()
                        return True
                return False

            def decay(self, decay_rate: float = 0.05, prune_threshold: float = 0.15) -> int:
                now = time.time()
                pruned = 0
                for node, edges in list(self.edges.items()):
                    live: list[Edge] = []
                    for edge in edges:
                        days_stale = (now - edge.last_used) / 86400
                        edge.weight = round(edge.weight - (decay_rate * days_stale), 4)
                        if edge.weight >= prune_threshold:
                            live.append(edge)
                        else:
                            pruned += 1
                    if live:
                        self.edges[node] = live
                    else:
                        self.edges.pop(node, None)
                return pruned
        """,
    )
    write(
        "prototype/jimsai/retrieval.py",
        """
        from __future__ import annotations

        import math

        from .encoder import hash_embedding
        from .memory import FourLayerMemoryStore
        from .models import RetrievalResult, SemanticIR


        def cosine(left: list[float], right: list[float]) -> float:
            dot = sum(a * b for a, b in zip(left, right))
            lnorm = math.sqrt(sum(a * a for a in left)) or 1.0
            rnorm = math.sqrt(sum(b * b for b in right)) or 1.0
            return dot / (lnorm * rnorm)


        class MultiIndexRetrievalEngine:
            def __init__(self, memory: FourLayerMemoryStore) -> None:
                self.memory = memory

            def retrieve(self, ir: SemanticIR, query: str, limit: int = 8, exclude_ids: set[str] | None = None) -> list[RetrievalResult]:
                exclude_ids = exclude_ids or set()
                query_vec = hash_embedding(query)
                query_terms = set(ir.tokens) | {str(entity).lower() for entity in ir.scope_constraints.get("entities", [])}
                results: dict[str, RetrievalResult] = {}
                for sig in self.memory.all_signatures():
                    if sig.id in exclude_ids:
                        continue
                    reasons: list[str] = []
                    score = 0.0
                    entity_names = {e.name.lower() for e in sig.structured.entities}
                    if entity_names & query_terms:
                        score += 0.35
                        reasons.append("entity_index")
                    semantic = max(cosine(query_vec, sig.latent_embedding), 0.0)
                    if semantic > 0:
                        score += 0.35 * semantic
                        reasons.append("semantic_index")
                    if sig.structured.causal_chain:
                        causal_terms = {c.cause.lower() for c in sig.structured.causal_chain} | {c.effect.lower() for c in sig.structured.causal_chain}
                        if causal_terms & query_terms:
                            score += 0.2
                            reasons.append("causal_index")
                    score += 0.1 * sig.importance.current_score
                    if score >= 0.12:
                        results[sig.id] = RetrievalResult(signature=sig, score=round(score, 4), reasons=reasons or ["importance_index"])
                ranked = sorted(results.values(), key=lambda r: (-r.score, r.signature.id))
                for result in ranked[:limit]:
                    result.signature.importance.retrieval_count += 1
                    result.signature.importance.current_score = min(1.0, result.signature.importance.current_score + 0.01)
                return ranked[:limit]
        """,
    )
    write(
        "prototype/jimsai/simulation.py",
        """
        from __future__ import annotations

        from .graph import CausalGraphEngine
        from .models import SemanticIR, SimulationResult, SimulationScope


        class BoundedSimulationEngine:
            def __init__(self, graph: CausalGraphEngine) -> None:
                self.graph = graph

            def run(self, ir: SemanticIR) -> list[SimulationResult]:
                entities = [str(e) for e in ir.scope_constraints.get("entities", [])]
                scope = SimulationScope(entities=entities, depth=3, time_budget_ms=200)
                if not entities:
                    return [
                        SimulationResult(
                            scenario="bounded_local_simulation",
                            passed=True,
                            confidence=0.55,
                            outcomes=["No explicit entity scope was provided; simulation limited to IR-level checks."],
                            scope=scope,
                        )
                    ]
                outcomes: list[str] = []
                for entity in entities[:3]:
                    traversal = self.graph.traverse(entity, depth=scope.depth)
                    if traversal:
                        outcomes.append(f"{entity} has causal/dependency paths: {sorted(traversal.keys())}")
                    else:
                        outcomes.append(f"{entity} has no known causal expansion in local graph.")
                return [
                    SimulationResult(
                        scenario="bounded_local_simulation",
                        passed=True,
                        confidence=0.74 if any("paths" in o for o in outcomes) else 0.6,
                        outcomes=outcomes,
                        scope=scope,
                    )
                ]
        """,
    )
    write(
        "prototype/jimsai/constraints.py",
        """
        from __future__ import annotations

        from .models import ConstraintCheck, RetrievalResult, SemanticIR, SimulationResult


        class ConstraintValidator:
            def validate(
                self,
                ir: SemanticIR,
                retrieval_results: list[RetrievalResult],
                simulations: list[SimulationResult],
            ) -> tuple[list[ConstraintCheck], list[str]]:
                checks: list[ConstraintCheck] = []
                gaps: list[str] = []
                checks.append(
                    ConstraintCheck(
                        name="ir_confidence_threshold",
                        passed=ir.confidence >= 0.18,
                        confidence=ir.confidence,
                        detail="IR confidence is above deterministic execution threshold." if ir.confidence >= 0.18 else "IR routed to sandbox due to low confidence.",
                    )
                )
                source_count = len(retrieval_results)
                checks.append(
                    ConstraintCheck(
                        name="source_grounding",
                        passed=source_count > 0,
                        confidence=min(1.0, source_count / 3),
                        detail=f"{source_count} source signatures retrieved.",
                    )
                )
                if source_count == 0:
                    gaps.append("No source signatures matched the query; factual claims are withheld.")
                if not all(sim.passed for sim in simulations):
                    gaps.append("At least one bounded simulation failed.")
                checks.append(
                    ConstraintCheck(
                        name="simulation_bounds",
                        passed=all(sim.scope.time_budget_ms <= 200 for sim in simulations),
                        confidence=1.0,
                        detail="Simulation is bounded to local causal neighbourhood by default.",
                    )
                )
                return checks, gaps
        """,
    )
    write(
        "prototype/jimsai/planner.py",
        """
        from __future__ import annotations

        from .models import ExecutionPlan, PlanStep, SemanticIR


        class SymbolicPlanner:
            def plan(self, ir: SemanticIR) -> ExecutionPlan:
                steps: list[PlanStep] = [
                    PlanStep(order=1, action="compile_ir", inputs={"target_ir": ir.target_ir}, expected_output="typed Semantic IR"),
                    PlanStep(order=2, action="retrieve_signatures", inputs={"tokens": ir.tokens}, expected_output="ranked source signatures"),
                ]
                if ir.target_ir in {"RUN_CANVAS"}:
                    steps.append(PlanStep(order=3, action="schedule_canvas", inputs=ir.scope_constraints, expected_output="canvas job or existing signatures"))
                elif ir.target_ir in {"RUN_INVENTION", "CODE_GENERATE"}:
                    steps.append(PlanStep(order=3, action="run_recursive_planner", inputs=ir.scope_constraints, expected_output="candidate plan"))
                    steps.append(PlanStep(order=4, action="simulate_candidates", inputs=ir.scope_constraints, expected_output="bounded simulation result"))
                else:
                    steps.append(PlanStep(order=3, action="compose_reasoning_chain", inputs=ir.scope_constraints, expected_output="verified chain"))
                steps.append(PlanStep(order=len(steps) + 1, action="render_csse", inputs={"mode": "FACT"}, expected_output="grounded response"))
                return ExecutionPlan(goal=ir.target_ir, steps=steps)
        """,
    )
    write(
        "prototype/jimsai/csse.py",
        """
        from __future__ import annotations

        from .models import VerifiedCognitiveObject


        class ConstrainedSemanticSynthesisEngine:
            def render(self, obj: VerifiedCognitiveObject) -> str:
                lines: list[str] = []
                if obj.reasoning_chain:
                    lines.append("Verified response:")
                    for step in obj.reasoning_chain:
                        source_note = f" sources={','.join(step.sources)}" if step.sources else " sources=none"
                        lines.append(f"- {step.claim} (confidence {step.confidence:.2f};{source_note})")
                else:
                    lines.append("I do not have verified source signatures for a factual answer.")
                if obj.simulation_results:
                    lines.append("")
                    lines.append("Simulation:")
                    for sim in obj.simulation_results:
                        status = "passed" if sim.passed else "failed"
                        lines.append(f"- {sim.scenario} {status} at confidence {sim.confidence:.2f}.")
                        for outcome in sim.outcomes:
                            lines.append(f"  - {outcome}")
                if obj.knowledge_gaps:
                    lines.append("")
                    lines.append("Explicit gaps:")
                    for gap in obj.knowledge_gaps:
                        lines.append(f"- {gap}")
                if obj.sources:
                    lines.append("")
                    lines.append("Source signatures:")
                    for source in obj.sources:
                        lines.append(f"- {source}")
                return "\\n".join(lines)
        """,
    )
    write(
        "prototype/jimsai/pipeline.py",
        """
        from __future__ import annotations

        from .constraints import ConstraintValidator
        from .csse import ConstrainedSemanticSynthesisEngine
        from .encoder import DualRepresentationEncoder
        from .graph import CausalGraphEngine
        from .memory import FourLayerMemoryStore
        from .models import (
            ExecutionMode,
            PipelineRequest,
            PipelineResponse,
            ReasoningStep,
            SPPETrainingPair,
            TrainingIngestRequest,
            TrainingIngestResponse,
            VerifiedCognitiveObject,
            WorldModelCandidate,
        )
        from .observability import ExecutionTracer
        from .planner import SymbolicPlanner
        from .retrieval import MultiIndexRetrievalEngine
        from .semantic_compiler import SemanticCompilerRuntime
        from .simulation import BoundedSimulationEngine


        class JimsAIPipeline:
            def __init__(self) -> None:
                self.compiler = SemanticCompilerRuntime()
                self.encoder = DualRepresentationEncoder()
                self.memory = FourLayerMemoryStore()
                self.graph = CausalGraphEngine()
                self.retrieval = MultiIndexRetrievalEngine(self.memory)
                self.simulation = BoundedSimulationEngine(self.graph)
                self.validator = ConstraintValidator()
                self.planner = SymbolicPlanner()
                self.csse = ConstrainedSemanticSynthesisEngine()
                self.sessions: dict[str, dict[str, str]] = {}
                self._seed_memory()

            def _seed_memory(self) -> None:
                seeds = [
                    "AuthService depends on UserModel. UserModel.id_change causes AuthService.token_invalidation.",
                    "PaymentService depends on AuthService. AuthService.token_invalidation causes PaymentService.session_refresh.",
                    "A bounded queue prevents backpressure deadlock when producer throughput exceeds consumer throughput.",
                    "Semantic Compiler converts human language into typed IR before deterministic execution.",
                ]
                for text in seeds:
                    sig = self.encoder.encode_text(text, provenance="seed_spec_alignment")
                    self.memory.insert(sig)
                    self.graph.add_signature(sig)

            async def run(self, request: PipelineRequest) -> PipelineResponse:
                tracer = ExecutionTracer()
                session = self.sessions.setdefault(request.user_id, {})
                ir = self.compiler.compile(request.query, namespace="TECHNICAL", session=session)
                session["ACTIVE_INTENT"] = ir.target_ir
                if ir.scope_constraints.get("entities"):
                    session["ACTIVE_OBJECT"] = str(ir.scope_constraints["entities"][0])
                tracer.add("semantic_compiler", "Compiled raw input to Semantic IR", target_ir=ir.target_ir, confidence=ir.confidence)

                input_signature = self.encoder.encode_text(request.query, intent_type=ir.target_ir.lower(), provenance="local_extraction")
                self.memory.insert(input_signature)
                self.graph.add_signature(input_signature)
                tracer.add("encoder_learning", "Encoded input and inserted signature", signature_id=input_signature.id, memory=self.memory.stats())

                if ir.execution_mode == ExecutionMode.AIR_GAPPED_CONTAINER:
                    retrieved = []
                    tracer.add(
                        "runtime_router",
                        "Bypassed factual retrieval for sandbox-routed input",
                        reason="unmatched ontology",
                    )
                else:
                    retrieved = self.retrieval.retrieve(ir, request.query, exclude_ids={input_signature.id})
                tracer.add("retrieval", "Retrieved signatures from local multi-index store", count=len(retrieved), ids=[r.signature.id for r in retrieved])

                graph_view: dict[str, object] = {}
                for entity in ir.scope_constraints.get("entities", [])[:3]:
                    graph_view[str(entity)] = self.graph.traverse(str(entity), depth=3)
                tracer.add("graph_runtime", "Completed bounded causal graph traversal", graph=graph_view)

                simulations = self.simulation.run(ir)
                tracer.add("simulation", "Ran bounded local simulation", count=len(simulations))

                checks, gaps = self.validator.validate(ir, retrieved, simulations)
                if ir.execution_mode == ExecutionMode.AIR_GAPPED_CONTAINER:
                    gaps.append("Input did not match the deterministic ontology; no factual claims were emitted from core memory.")
                tracer.add("constraint_validator", "Validated IR, sources, and simulation bounds", passed=[c.name for c in checks if c.passed], gaps=gaps)

                plan = self.planner.plan(ir)
                tracer.add("symbolic_planner", "Built deterministic execution plan", steps=len(plan.steps))

                reasoning_chain = [
                    ReasoningStep(
                        claim=f"Retrieved signature {result.signature.id} supports intent {ir.target_ir}",
                        confidence=min(0.99, result.score),
                        sources=[result.signature.id],
                        relation="ASSERT",
                    )
                    for result in retrieved[:5]
                ]
                if not reasoning_chain:
                    reasoning_chain = [
                        ReasoningStep(
                            claim="No verified claim emitted because retrieval returned no source signatures.",
                            confidence=0.3,
                            sources=[],
                            relation="HEDGE",
                        )
                    ]
                confidence_values = [ir.confidence, *[r.confidence for r in reasoning_chain], *[c.confidence for c in checks]]
                confidence = round(sum(confidence_values) / len(confidence_values), 4)
                sources = sorted({source for step in reasoning_chain for source in step.sources})
                obj = VerifiedCognitiveObject(
                    trace_id=ir.trace_id,
                    intent=ir.target_ir,
                    verified_plan=plan,
                    simulation_results=simulations,
                    constraint_checks=checks,
                    semantic_graph=graph_view,
                    reasoning_chain=reasoning_chain,
                    knowledge_gaps=gaps,
                    sources=sources,
                    confidence=confidence,
                )
                response = self.csse.render(obj)
                tracer.add("csse", "Rendered response from Verified Cognitive Object", sources=sources, confidence=confidence)
                return PipelineResponse(
                    response=response,
                    ir=ir,
                    reasoning_chain=reasoning_chain,
                    confidence=confidence,
                    gaps=gaps,
                    sources=sources,
                    simulation_results=simulations,
                    trace=tracer.events if request.return_trace else [],
                )

            async def ingest_training(self, request: TrainingIngestRequest) -> TrainingIngestResponse:
                tracer = ExecutionTracer()
                intent_type = request.domain_hint or "training_ingestion"
                signature = self.encoder.encode_text(
                    request.content,
                    intent_type=intent_type,
                    provenance="training_pipeline",
                )
                signature.confidence.score = round(min(signature.confidence.score, request.source_trust), 4)
                signature.confidence.source = "training_ingestion_source_trust"
                self.memory.insert(signature)
                self.graph.add_signature(signature)
                tracer.add(
                    "training_ingest",
                    "Encoded training input and inserted memory signature",
                    signature_id=signature.id,
                    modality=request.modality,
                    source_trust=request.source_trust,
                )

                world_model_candidates = [
                    WorldModelCandidate(
                        rule=f"{link.cause} causes {link.effect}",
                        confidence=round(min(link.confidence, request.source_trust), 4),
                        provenance=signature.id,
                        review_required=min(link.confidence, request.source_trust) < 0.9,
                    )
                    for link in signature.structured.causal_chain
                ]
                tracer.add(
                    "world_model_candidates",
                    "Extracted causal world model candidates from signature",
                    count=len(world_model_candidates),
                )

                semantic_intention_graph = {
                    "entities": [entity.model_dump() for entity in signature.structured.entities],
                    "relations": [relation.model_dump() for relation in signature.structured.relations],
                    "causal_chain": [link.model_dump() for link in signature.structured.causal_chain],
                    "intent": signature.structured.intent.model_dump(),
                }
                sppe_pair = SPPETrainingPair(
                    signature_id=signature.id,
                    semantic_intention_graph=semantic_intention_graph,
                    original_text=request.content,
                    confidence=signature.confidence.score,
                    accepted=signature.confidence.score >= 0.75,
                )
                tracer.add(
                    "sppe_pair",
                    "Generated confidence-scored SPPE training pair",
                    accepted=sppe_pair.accepted,
                    confidence=sppe_pair.confidence,
                )
                return TrainingIngestResponse(
                    signature=signature,
                    world_model_candidates=world_model_candidates,
                    sppe_training_pair=sppe_pair,
                    memory_stats=self.memory.stats(),
                    trace=tracer.events,
                )
        """,
    )
    write(
        "prototype/app.py",
        """
        from __future__ import annotations

        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import PlainTextResponse

        from .jimsai.models import PipelineRequest, TrainingIngestRequest
        from .jimsai.pipeline import JimsAIPipeline

        app = FastAPI(title="JIMS-AI Phase 1 Prototype", version="0.1.0")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://127.0.0.1:3001", "http://localhost:3001", "http://127.0.0.1:3000", "http://localhost:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        pipeline = JimsAIPipeline()


        @app.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok", "architecture": "deterministic semantic execution"}


        @app.get("/metrics", response_class=PlainTextResponse)
        async def metrics() -> str:
            stats = pipeline.memory.stats()
            return "\\n".join(f"jimsai_memory_{key} {value}" for key, value in stats.items()) + "\\n"


        @app.post("/v1/query")
        async def query(request: PipelineRequest):
            return await pipeline.run(request)


        @app.post("/v1/training/ingest")
        async def training_ingest(request: TrainingIngestRequest):
            return await pipeline.ingest_training(request)


        @app.post("/v1/memory/insert")
        async def memory_insert(request: TrainingIngestRequest):
            return await pipeline.ingest_training(request)


        @app.get("/v1/memory/stats")
        async def memory_stats() -> dict[str, int]:
            return pipeline.memory.stats()
        """,
    )


def service_route_code(service_name: str, meta: dict[str, object]) -> str:
    if service_name == "api-gateway":
        return """
        from __future__ import annotations

        from fastapi import APIRouter

        from prototype.jimsai.models import PipelineRequest, TrainingIngestRequest
        from prototype.jimsai.pipeline import JimsAIPipeline

        router = APIRouter()
        pipeline = JimsAIPipeline()

        @router.post("/v1/query")
        async def query(request: PipelineRequest):
            return await pipeline.run(request)

        @router.post("/v1/training/ingest")
        async def training_ingest(request: TrainingIngestRequest):
            return await pipeline.ingest_training(request)

        @router.post("/v1/memory/insert")
        async def memory_insert(request: TrainingIngestRequest):
            return await pipeline.ingest_training(request)

        @router.post("/v1/query/stream")
        async def query_stream(request: PipelineRequest):
            result = await pipeline.run(request)
            return {"events": [event.model_dump(mode="json") for event in result.trace], "final": result.response}

        @router.get("/v1/memory/search")
        async def memory_search(user_id: str, q: str, provenance: str | None = None):
            compiled = pipeline.compiler.compile(q)
            results = pipeline.retrieval.retrieve(compiled, q)
            return {"user_id": user_id, "query": q, "results": [r.model_dump(mode="json") for r in results]}
        """
    if service_name == "semantic-compiler":
        return """
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
        """
    if service_name in {"graph-runtime", "causal-graph-engine"}:
        return """
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
        """
    return f'''
        from __future__ import annotations

        from fastapi import APIRouter
        from pydantic import BaseModel

        router = APIRouter()

        SERVICE_CONTRACT = {{
            "name": "{service_name}",
            "layer": "{meta["layer"]}",
            "purpose": "{meta["purpose"]}",
            "deterministic": True,
            "endpoints": {meta["endpoints"]!r},
        }}

        class DeterministicTask(BaseModel):
            trace_id: str | None = None
            payload: dict = {{}}

        @router.get("/v1/contract")
        async def contract():
            return SERVICE_CONTRACT

        @router.post("/v1/execute")
        async def execute(task: DeterministicTask):
            return {{
                "service": SERVICE_CONTRACT["name"],
                "trace_id": task.trace_id,
                "accepted": True,
                "deterministic": True,
                "payload_keys": sorted(task.payload.keys()),
            }}
        '''


def services() -> None:
    for service_name, meta in SERVICES.items():
        base = f"services/{service_name}"
        write(f"{base}/app/__init__.py", "")
        write(
            f"{base}/app/config.py",
            f'''
            from __future__ import annotations

            from pydantic_settings import BaseSettings, SettingsConfigDict


            class Settings(BaseSettings):
                service_name: str = "{service_name}"
                log_level: str = "INFO"
                redis_url: str = ""
                neo4j_uri: str = ""
                postgres_url: str = ""
                otel_exporter_otlp_endpoint: str = ""

                model_config = SettingsConfigDict(env_file=".env", extra="ignore")


            settings = Settings()
            ''',
        )
        write(
            f"{base}/app/telemetry.py",
            """
            from __future__ import annotations

            import logging
            from time import perf_counter
            from typing import Callable

            from fastapi import Request, Response


            def configure_logger(name: str, level: str = "INFO") -> logging.Logger:
                logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))
                return logging.getLogger(name)


            async def trace_middleware(request: Request, call_next: Callable):
                start = perf_counter()
                response: Response = await call_next(request)
                elapsed_ms = (perf_counter() - start) * 1000
                response.headers["x-jimsai-trace-ms"] = f"{elapsed_ms:.3f}"
                response.headers["x-jimsai-deterministic"] = "true"
                return response
            """,
        )
        write(f"{base}/app/routes.py", service_route_code(service_name, meta))
        write(
            f"{base}/app/main.py",
            f'''
            from __future__ import annotations

            from fastapi import FastAPI
            from fastapi.middleware.cors import CORSMiddleware
            from fastapi.responses import PlainTextResponse

            from .config import settings
            from .routes import router
            from .telemetry import configure_logger, trace_middleware

            logger = configure_logger(settings.service_name, settings.log_level)
            app = FastAPI(title="JIMS-AI {service_name}", version="0.1.0")
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["http://127.0.0.1:3001", "http://localhost:3001", "http://127.0.0.1:3000", "http://localhost:3000"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            app.middleware("http")(trace_middleware)
            app.include_router(router)


            @app.get("/health")
            async def health() -> dict[str, str | bool]:
                return {{
                    "status": "ok",
                    "service": settings.service_name,
                    "deterministic": True,
                    "layer": "{meta["layer"]}",
                }}


            @app.get("/metrics", response_class=PlainTextResponse)
            async def metrics() -> str:
                return "jimsai_service_up{{service='" + settings.service_name + "'}} 1\\n"


            @app.get("/trace")
            async def trace() -> dict[str, str]:
                return {{"service": settings.service_name, "trace_policy": "all requests emit deterministic trace headers"}}
            ''',
        )
        write(
            f"{base}/README.md",
            f"""
            # {service_name}

            ## Architecture Mapping

            - Layer: {meta["layer"]}
            - Purpose: {meta["purpose"]}
            - PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

            ## Local Setup

            ```bash
            cd services/{service_name}
            python -m pip install -r requirements.txt
            uvicorn app.main:app --reload --port 8000
            ```

            ## Docker

            ```bash
            docker build -f services/{service_name}/Dockerfile -t jimsai/{service_name}:local .
            ```

            ## API

            - `GET /health`
            - `GET /metrics`
            - `GET /trace`
            - Service endpoints: {", ".join(meta["endpoints"])}

            ## Tests

            ```bash
            pytest services/{service_name}/tests
            ```
            """,
        )
        write(
            f"{base}/Dockerfile",
            f"""
            FROM python:3.12-slim

            ENV PYTHONDONTWRITEBYTECODE=1
            ENV PYTHONUNBUFFERED=1
            ENV PYTHONPATH=/app

            WORKDIR /app
            COPY pyproject.toml README.md /app/
            COPY prototype /app/prototype
            COPY services/{service_name} /app/services/{service_name}

            RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings python-multipart prometheus-client httpx

            WORKDIR /app/services/{service_name}
            EXPOSE 8000
            CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
            """,
        )
        write(
            f"{base}/requirements.txt",
            """
            fastapi>=0.111
            uvicorn>=0.30
            pydantic>=2.7
            pydantic-settings>=2.3
            prometheus-client>=0.20
            httpx>=0.27
            """,
        )
        write(
            f"{base}/config.example.env",
            f"""
            SERVICE_NAME={service_name}
            LOG_LEVEL=INFO
            REDIS_URL=rediss://default:password@host:port/0
            NEO4J_URI=neo4j+s://instance.databases.neo4j.io
            SUPABASE_URL=https://project-ref.supabase.co
            OTEL_EXPORTER_OTLP_ENDPOINT=https://otel.example.com
            """,
        )
        write(
            f"{base}/api.yaml",
            f"""
            openapi: 3.1.0
            info:
              title: JIMS-AI {service_name}
              version: 0.1.0
            paths:
              /health:
                get:
                  summary: Service health
                  responses:
                    "200":
                      description: OK
              /metrics:
                get:
                  summary: Prometheus metrics
                  responses:
                    "200":
                      description: OK
              /trace:
                get:
                  summary: Trace policy
                  responses:
                    "200":
                      description: OK
            """,
        )
        write(
            f"{base}/tests/test_health.py",
            """
            from fastapi.testclient import TestClient

            from app.main import app


            def test_health():
                client = TestClient(app)
                response = client.get("/health")
                assert response.status_code == 200
                assert response.json()["deterministic"] is True
            """,
        )


def frontend() -> None:
    write(
        "frontend/package.json",
        """
        {
          "name": "jims-ai-frontend",
          "version": "0.1.0",
          "private": true,
            "scripts": {
              "dev": "next dev",
              "build": "next build",
              "start": "next start",
              "test:e2e": "playwright test",
              "lint": "next lint"
            },
          "dependencies": {
            "next": "15.5.18",
            "react": "19.0.0",
            "react-dom": "19.0.0",
            "lucide-react": "^1.16.0",
            "zustand": "^5.0.0"
          },
          "devDependencies": {
            "@playwright/test": "^1.60.0",
            "@types/node": "^22.0.0",
            "@types/react": "^19.0.0",
            "@types/react-dom": "^19.0.0",
            "typescript": "^5.6.0",
            "eslint": "^9.0.0",
            "eslint-config-next": "15.5.18"
          },
          "overrides": {
            "postcss": "^8.5.10"
          }
        }
        """,
    )
    write(
        "frontend/next.config.ts",
        """
        import type { NextConfig } from "next";

        const nextConfig: NextConfig = {
          typedRoutes: true
        };

        export default nextConfig;
        """,
    )
    write(
        "frontend/playwright.config.ts",
        """
        import { defineConfig, devices } from "@playwright/test";

        export default defineConfig({
          testDir: "./tests",
          timeout: 30_000,
          use: {
            baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3001",
            trace: "on-first-retry"
          },
          projects: [
            {
              name: "msedge",
              use: { ...devices["Desktop Edge"], channel: "msedge" }
            }
          ]
        });
        """,
    )
    write(
        "frontend/tsconfig.json",
        """
        {
          "compilerOptions": {
            "target": "ES2020",
            "lib": ["dom", "dom.iterable", "esnext"],
            "allowJs": false,
            "skipLibCheck": true,
            "strict": true,
            "noEmit": true,
            "esModuleInterop": true,
            "module": "esnext",
            "moduleResolution": "bundler",
            "resolveJsonModule": true,
            "isolatedModules": true,
            "jsx": "preserve",
            "incremental": true,
            "plugins": [{ "name": "next" }]
          },
          "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
          "exclude": ["node_modules"]
        }
        """,
    )
    write("frontend/next-env.d.ts", "/// <reference types=\"next\" />\n/// <reference types=\"next/image-types/global\" />\n")
    write(
        "frontend/Dockerfile",
        """
        FROM node:22-alpine AS deps
        WORKDIR /app
        COPY frontend/package.json ./
        RUN npm install

        FROM node:22-alpine AS runner
        WORKDIR /app
        COPY --from=deps /app/node_modules ./node_modules
        COPY frontend ./
        EXPOSE 3000
        CMD ["npm", "run", "dev"]
        """,
    )
    write(
        "frontend/app/layout.tsx",
        """
        import "./globals.css";
        import type { Metadata } from "next";

        export const metadata: Metadata = {
          title: "JIMS-AI",
          description: "Deterministic semantic execution runtime",
          icons: {
            icon: "/icon.svg"
          }
        };

        export default function RootLayout({ children }: { children: React.ReactNode }) {
          return (
            <html lang="en">
              <body>{children}</body>
            </html>
          );
        }
        """,
    )
    write(
        "frontend/public/icon.svg",
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
          <rect width="64" height="64" rx="8" fill="#0f766e"/>
          <path d="M14 18h36v6H21v8h22v6H21v8h29v6H14z" fill="#ffffff"/>
        </svg>
        """,
    )
    write(
        "frontend/app/globals.css",
        """
        :root {
          --bg: #f7f7f4;
          --panel: #ffffff;
          --ink: #1d1f22;
          --muted: #60656c;
          --line: #d9ddd7;
          --accent: #0f766e;
          --accent-2: #7c2d12;
          --warn: #b45309;
        }

        * { box-sizing: border-box; }
        body {
          margin: 0;
          background: var(--bg);
          color: var(--ink);
          font-family: Arial, Helvetica, sans-serif;
        }
        button, input, textarea { font: inherit; }
        .shell {
          min-height: 100vh;
          display: grid;
          grid-template-columns: minmax(0, 1fr) 360px;
        }
        .main {
          display: grid;
          grid-template-rows: auto 1fr auto;
          min-height: 100vh;
          border-right: 1px solid var(--line);
        }
        .topbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          padding: 14px 20px;
          border-bottom: 1px solid var(--line);
          background: #fbfbf8;
        }
        .brand { font-weight: 700; letter-spacing: 0; }
        .status { color: var(--muted); font-size: 13px; }
        .messages {
          padding: 20px;
          overflow: auto;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .message {
          max-width: 920px;
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 12px 14px;
          background: var(--panel);
          white-space: pre-wrap;
          line-height: 1.45;
        }
        .message.user {
          align-self: flex-end;
          border-color: #a7c9c4;
          background: #eef8f6;
        }
        .composer {
          display: grid;
          grid-template-columns: auto 1fr auto auto;
          gap: 10px;
          padding: 14px 20px;
          border-top: 1px solid var(--line);
          background: #fbfbf8;
        }
        textarea {
          resize: none;
          min-height: 48px;
          max-height: 140px;
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 10px;
          background: #fff;
          color: var(--ink);
        }
        .iconButton, .sendButton {
          border: 1px solid var(--line);
          border-radius: 8px;
          background: var(--panel);
          color: var(--ink);
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-width: 44px;
          height: 44px;
          cursor: pointer;
        }
        .sendButton {
          background: var(--accent);
          color: white;
          border-color: var(--accent);
          padding: 0 14px;
          gap: 8px;
        }
        .sidebar {
          min-height: 100vh;
          padding: 18px;
          background: #ffffff;
          overflow: auto;
        }
        .section {
          border-bottom: 1px solid var(--line);
          padding: 14px 0;
        }
        .section h2 {
          font-size: 14px;
          margin: 0 0 10px;
        }
        .toggle {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          font-size: 13px;
          color: var(--muted);
          margin: 8px 0;
        }
        .pill {
          display: inline-flex;
          align-items: center;
          border: 1px solid var(--line);
          border-radius: 999px;
          padding: 4px 8px;
          font-size: 12px;
          margin: 3px 4px 3px 0;
          color: var(--muted);
        }
        .traceList {
          display: grid;
          gap: 8px;
          font-size: 12px;
        }
        .traceItem {
          border-left: 3px solid var(--accent);
          padding-left: 8px;
          color: var(--muted);
        }
        @media (max-width: 900px) {
          .shell { grid-template-columns: 1fr; }
          .sidebar { min-height: auto; border-top: 1px solid var(--line); }
          .composer { grid-template-columns: auto 1fr auto; }
          .sendButton span { display: none; }
        }
        """,
    )
    write(
        "frontend/app/page.tsx",
        """
        "use client";

        import { ChangeEvent, FormEvent, useMemo, useRef, useState } from "react";
        import { FileUp, GitBranch, ListTree, Send, ShieldCheck } from "lucide-react";

        type TraceEvent = { stage: string; message: string; data: Record<string, unknown> };
        type ApiResponse = {
          response: string;
          confidence: number;
          gaps: string[];
          sources: string[];
          simulation_results: Array<{ scenario: string; passed: boolean; confidence: number; outcomes: string[] }>;
          trace: TraceEvent[];
        };
        type IngestResponse = {
          signature: { id: string };
          world_model_candidates: Array<{ rule: string; confidence: number; review_required: boolean }>;
          sppe_training_pair: { accepted: boolean; confidence: number };
          memory_stats: Record<string, number>;
        };
        type Message = { role: "user" | "assistant"; content: string };

        export default function Home() {
          const [messages, setMessages] = useState<Message[]>([
            { role: "assistant", content: "JIMS-AI Phase 1 runtime ready. Ask a workspace, graph, or dependency question." }
          ]);
          const [input, setInput] = useState("What services are affected if UserModel.id changes?");
          const [memoryTrace, setMemoryTrace] = useState(true);
          const [reasoningTrace, setReasoningTrace] = useState(true);
          const [last, setLast] = useState<ApiResponse | null>(null);
          const [loading, setLoading] = useState(false);
          const [ingestText, setIngestText] = useState("InventoryService depends on StockLedger. StockLedger.update causes InventoryService.recount.");
          const [ingestStatus, setIngestStatus] = useState<string>("No training batch ingested.");
          const fileInputRef = useRef<HTMLInputElement | null>(null);

          const apiBase = useMemo(() => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000", []);

          async function ingestContent(content: string) {
            if (!content.trim()) return;
            setLoading(true);
            try {
              const response = await fetch(`${apiBase}/v1/training/ingest`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  user_id: "frontend-local",
                  content,
                  modality: "text",
                  source_trust: 0.92,
                  domain_hint: "workspace_training"
                })
              });
              const data = (await response.json()) as IngestResponse;
              setIngestStatus(`signature ${data.signature.id} - world models ${data.world_model_candidates.length} - SPPE ${data.sppe_training_pair.accepted ? "accepted" : "queued"}`);
            } catch {
              setIngestStatus("ingestion failed");
            } finally {
              setLoading(false);
            }
          }

          async function handleFileSelected(event: ChangeEvent<HTMLInputElement>) {
            const file = event.target.files?.[0];
            if (!file) return;
            const text = await file.text();
            setIngestText(text);
            await ingestContent(text);
            event.target.value = "";
          }

          async function submit(event: FormEvent) {
            event.preventDefault();
            if (!input.trim() || loading) return;
            const query = input.trim();
            setMessages((current) => [...current, { role: "user", content: query }]);
            setInput("");
            setLoading(true);
            try {
              const response = await fetch(`${apiBase}/v1/query`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ user_id: "frontend-local", query, return_trace: true })
              });
              const data = (await response.json()) as ApiResponse;
              setLast(data);
              setMessages((current) => [...current, { role: "assistant", content: data.response }]);
            } catch {
              setMessages((current) => [...current, { role: "assistant", content: "API request failed. Start the prototype or API Gateway on port 8000." }]);
            } finally {
              setLoading(false);
            }
          }

          return (
            <main className="shell">
              <section className="main">
                <header className="topbar">
                  <div>
                    <div className="brand">JIMS-AI</div>
                    <div className="status">Deterministic semantic execution - local Phase 1</div>
                  </div>
                  <div className="status">confidence {last ? last.confidence.toFixed(2) : "n/a"}</div>
                </header>

                <div className="messages">
                  {messages.map((message, index) => (
                    <article className={`message ${message.role === "user" ? "user" : ""}`} key={`${message.role}-${index}`}>
                      {message.content}
                    </article>
                  ))}
                </div>

                <form className="composer" onSubmit={submit}>
                  <input ref={fileInputRef} type="file" hidden onChange={handleFileSelected} />
                  <button className="iconButton" type="button" title="Attach files" onClick={() => fileInputRef.current?.click()}>
                    <FileUp size={18} />
                  </button>
                  <textarea value={input} onChange={(event) => setInput(event.target.value)} />
                  <button className="iconButton" type="button" title="Run canvas">
                    <GitBranch size={18} />
                  </button>
                  <button className="sendButton" type="submit" disabled={loading}>
                    <Send size={18} /><span>{loading ? "Running" : "Send"}</span>
                  </button>
                </form>
              </section>

              <aside className="sidebar">
                <section className="section">
                  <h2>Transparency</h2>
                  <label className="toggle">Memory trace <input type="checkbox" checked={memoryTrace} onChange={(event) => setMemoryTrace(event.target.checked)} /></label>
                  <label className="toggle">Reasoning trace <input type="checkbox" checked={reasoningTrace} onChange={(event) => setReasoningTrace(event.target.checked)} /></label>
                </section>

                <section className="section">
                  <h2>Training Ingestion</h2>
                  <textarea value={ingestText} onChange={(event) => setIngestText(event.target.value)} />
                  <button className="sendButton" type="button" disabled={loading} onClick={() => ingestContent(ingestText)}>
                    <GitBranch size={18} /><span>Ingest</span>
                  </button>
                  <div className="status">{ingestStatus}</div>
                </section>

                <section className="section">
                  <h2><ShieldCheck size={14} /> Sources</h2>
                  {last?.sources.length ? last.sources.map((source) => <span className="pill" key={source}>{source}</span>) : <div className="status">No response sources yet.</div>}
                </section>

                <section className="section">
                  <h2>Gaps</h2>
                  {last?.gaps.length ? last.gaps.map((gap) => <div className="traceItem" key={gap}>{gap}</div>) : <div className="status">No explicit gaps reported.</div>}
                </section>

                <section className="section">
                  <h2><ListTree size={14} /> Simulation</h2>
                  <div className="traceList">
                    {last?.simulation_results.map((sim) => (
                      <div className="traceItem" key={sim.scenario}>
                        {sim.scenario}: {sim.passed ? "passed" : "failed"} - {sim.confidence.toFixed(2)}
                      </div>
                    ))}
                  </div>
                </section>

                <section className="section">
                  <h2>Execution Trace</h2>
                  <div className="traceList">
                    {reasoningTrace && last?.trace.map((event, index) => (
                      <div className="traceItem" key={`${event.stage}-${index}`}>
                        <strong>{event.stage}</strong><br />{event.message}
                      </div>
                    ))}
                  </div>
                </section>
              </aside>
            </main>
          );
        }
        """,
    )
    write(
        "frontend/tests/ui-smoke.spec.ts",
        """
        import { expect, test } from "@playwright/test";

        test("loads the JIMS-AI runtime UI without browser runtime errors", async ({ page }) => {
          const browserErrors: string[] = [];

          page.on("pageerror", (error) => {
            browserErrors.push(error.message);
          });
          page.on("console", (message) => {
            if (message.type() === "error") {
              browserErrors.push(message.text());
            }
          });

          await page.goto("/", { waitUntil: "networkidle" });
          await expect(page.locator(".brand")).toHaveText("JIMS-AI");
          await expect(page.getByText("Deterministic semantic execution - local Phase 1")).toBeVisible();

          await page.getByRole("button", { name: "Ingest" }).click();
          await expect(page.getByText(/signature sig_/)).toBeVisible();

          await page.locator("form textarea").fill("What happens if StockLedger.update changes?");
          await page.getByRole("button", { name: "Send" }).click();
          await expect(page.getByText("Source signatures:")).toBeVisible();

          expect(browserErrors).toEqual([]);
        });
        """,
    )


def infra() -> None:
    for folder in [
        "mvp", "production", "infrastructure/docker", "infrastructure/kubernetes", "infrastructure/terraform",
        "infrastructure/monitoring", "infrastructure/redis", "infrastructure/neo4j", "infrastructure/postgres",
        "infrastructure/vector-cache", "infrastructure/deployment", "sdk", "cli", "tests", "benchmarks",
        "datasets", "prompts", "configs",
    ]:
        (ROOT / folder).mkdir(parents=True, exist_ok=True)

    write("mvp/README.md", "# MVP\n\nPhase 2 service integrations, Redis/Neo4j/PostgreSQL adapters, Canvas MVP, review queues, SDK, and UIs land here.\n")
    write("production/README.md", "# Production\n\nPhase 3 distributed graph runtime, graph decay, HA orchestration, enterprise deployment, and scaling work land here.\n")
    write("datasets/README.md", "# Datasets\n\nLocal benchmark and ingestion datasets. Do not commit private user memory or raw customer files.\n")
    write("prompts/README.md", "# Prompts\n\nDesign-time prompts only. Runtime deterministic execution must not depend on prompt templates for correctness.\n")
    write(
        "configs/default.yaml",
        """
        runtime:
          namespace: TECHNICAL
          deterministic_core: true
          simulation_time_budget_ms: 200
        compiler:
          confidence_threshold: 0.18
          hot_cache_ttl_seconds: 86400
        memory:
          auto_accept_threshold: 0.90
          soft_accept_threshold: 0.75
        """,
    )
    write(
        "infrastructure/postgres/init.sql",
        """
        CREATE TABLE IF NOT EXISTS signatures (
          id TEXT PRIMARY KEY,
          provenance TEXT NOT NULL,
          confidence DOUBLE PRECISION NOT NULL,
          modality TEXT NOT NULL,
          payload JSONB NOT NULL,
          created_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS execution_traces (
          id BIGSERIAL PRIMARY KEY,
          trace_id TEXT NOT NULL,
          service TEXT NOT NULL,
          stage TEXT NOT NULL,
          payload JSONB NOT NULL,
          created_at TIMESTAMPTZ DEFAULT now()
        );
        """,
    )
    write(
        "infrastructure/monitoring/prometheus.yml",
        """
        global:
          scrape_interval: 15s
        scrape_configs:
          - job_name: jims-ai
            static_configs:
              - targets: ["api-gateway:8000", "semantic-compiler:8000", "graph-runtime:8000"]
        """,
    )
    write(
        "infrastructure/monitoring/grafana-dashboard.json",
        """
        {
          "title": "JIMS-AI Deterministic Runtime",
          "panels": [
            { "type": "timeseries", "title": "Service Up", "targets": [{ "expr": "jimsai_service_up" }] },
            { "type": "timeseries", "title": "Memory Signatures", "targets": [{ "expr": "jimsai_memory_semantic" }] }
          ]
        }
        """,
    )
    write(
        "infrastructure/kubernetes/api-gateway.yaml",
        """
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: api-gateway
        spec:
          replicas: 2
          selector:
            matchLabels:
              app: api-gateway
          template:
            metadata:
              labels:
                app: api-gateway
            spec:
              containers:
                - name: api-gateway
                  image: jimsai/api-gateway:local
                  ports:
                    - containerPort: 8000
                  envFrom:
                    - secretRef:
                        name: jimsai-env
        """,
    )
    write(
        "infrastructure/terraform/main.tf",
        """
        terraform {
          required_version = ">= 1.6.0"
        }

        variable "project_name" {
          type    = string
          default = "jims-ai"
        }

        output "next_steps" {
          value = "Wire managed Redis, Neo4j Aura, Supabase, Cloudflare R2, and Vectorize providers for the target cloud account."
        }
        """,
    )
    for name, title in [
        ("cloudflare_r2.md", "Cloudflare R2"),
        ("cloudflare_vectorize.md", "Cloudflare Vectorize"),
        ("supabase.md", "Supabase"),
        ("neo4j_aura.md", "Neo4j AuraDB"),
        ("vast_ai.md", "Vast.ai GPU Jobs"),
        ("local_dev.md", "Local Dev with Ollama and LanceDB"),
    ]:
        write(
            f"infrastructure/deployment/{name}",
            f"""
            # {title} Setup Guide

            This guide is a Phase 2 integration note. Phase 1 runs locally without this provider.

            ## Role in JIMS-AI

            The provider is used only for the architecture function assigned in the PDF. It must not become a hidden
            reasoning engine or unbounded generation path.

            ## Configuration

            Add the matching placeholders in `.env.example`, provision the provider resource, then map credentials
            into Docker, Kubernetes, or the deployment platform secret manager.

            ## Verification

            - Health check passes.
            - Deterministic test still passes without provider-specific behavior drift.
            - Traces include provider operation names and resource identifiers.
            """,
        )
    write("infrastructure/redis/README.md", "# Redis\n\nSession state, IR hot cache, graph shortcut cache, and ontology staging.\n")
    write("infrastructure/neo4j/README.md", "# Neo4j\n\nCausal graph, concept lattice, entity relationships, dependency graph, temporal links.\n")
    write("infrastructure/vector-cache/README.md", "# Vector Cache\n\nVectorize-compatible embedding lookup layer. Phase 1 uses deterministic local hash vectors.\n")


def sdk_cli_bench_tests() -> None:
    write(
        "sdk/README.md",
        """
        # SDK

        Python SDK skeleton for agentic access to the API Gateway.
        """,
    )
    write(
        "sdk/jimsai_client.py",
        """
        from __future__ import annotations

        import httpx


        class JimsAIClient:
            def __init__(self, base_url: str = "http://localhost:8000", user_id: str = "sdk-user") -> None:
                self.base_url = base_url.rstrip("/")
                self.user_id = user_id

            async def query(self, query: str, return_trace: bool = True) -> dict:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        f"{self.base_url}/v1/query",
                        json={"user_id": self.user_id, "query": query, "return_trace": return_trace},
                    )
                    response.raise_for_status()
                    return response.json()
        """,
    )
    write(
        "cli/jimsai.py",
        """
        from __future__ import annotations

        import argparse
        import asyncio

        from prototype.jimsai.encoder import DualRepresentationEncoder
        from prototype.jimsai.graph import CausalGraphEngine
        from prototype.jimsai.models import PipelineRequest, TrainingIngestRequest
        from prototype.jimsai.pipeline import JimsAIPipeline


        async def main() -> None:
            parser = argparse.ArgumentParser(description="Run the local JIMS-AI deterministic prototype")
            parser.add_argument("query")
            args = parser.parse_args()
            pipeline = JimsAIPipeline()
            result = await pipeline.run(PipelineRequest(user_id="cli", query=args.query))
            print(result.response)


        if __name__ == "__main__":
            asyncio.run(main())
        """,
    )
    write(
        "benchmarks/determinism_benchmark.py",
        """
        from __future__ import annotations

        import asyncio
        import time

        from prototype.jimsai.models import PipelineRequest
        from prototype.jimsai.pipeline import JimsAIPipeline


        async def main() -> None:
            pipeline = JimsAIPipeline()
            query = "What services are affected if UserModel.id changes?"
            start = time.perf_counter()
            first = await pipeline.run(PipelineRequest(user_id="bench", query=query))
            second = await pipeline.run(PipelineRequest(user_id="bench", query=query))
            elapsed_ms = (time.perf_counter() - start) * 1000
            print({
                "deterministic_response": first.response == second.response,
                "deterministic_ir": first.ir.target_ir == second.ir.target_ir,
                "latency_ms_total_two_runs": round(elapsed_ms, 3),
                "sources": first.sources,
                "gaps": first.gaps,
            })


        if __name__ == "__main__":
            asyncio.run(main())
        """,
    )
    write(
        "benchmarks/hallucination_barrier.py",
        """
        from __future__ import annotations

        import asyncio

        from prototype.jimsai.models import PipelineRequest
        from prototype.jimsai.pipeline import JimsAIPipeline


        async def main() -> None:
            pipeline = JimsAIPipeline()
            result = await pipeline.run(PipelineRequest(user_id="bench", query="Tell me about UnknownServiceZeta impacts"))
            unsupported_claims = [step for step in result.reasoning_chain if not step.sources and step.relation != "HEDGE"]
            print({
                "unsupported_claim_count": len(unsupported_claims),
                "explicit_gaps": result.gaps,
                "response": result.response,
            })


        if __name__ == "__main__":
            asyncio.run(main())
        """,
    )
    write(
        "tests/test_phase1_pipeline.py",
        """
        import pytest

        from prototype.jimsai.models import PipelineRequest
        from prototype.jimsai.pipeline import JimsAIPipeline


        @pytest.mark.asyncio
        async def test_pipeline_returns_grounded_response():
            pipeline = JimsAIPipeline()
            result = await pipeline.run(PipelineRequest(user_id="test", query="What services are affected if UserModel.id changes?"))
            assert result.ir.target_ir in {"WORKSPACE_QUERY", "GENERAL_FACT"}
            assert result.sources
            assert "Source signatures" in result.response
            assert result.trace


        @pytest.mark.asyncio
        async def test_pipeline_is_deterministic_for_same_memory_state():
            query = "Explain the Semantic Compiler deterministic execution"
            pipeline_a = JimsAIPipeline()
            pipeline_b = JimsAIPipeline()
            first = await pipeline_a.run(PipelineRequest(user_id="test", query=query))
            second = await pipeline_b.run(PipelineRequest(user_id="test", query=query))
            assert first.ir.target_ir == second.ir.target_ir
            assert first.response == second.response


        @pytest.mark.asyncio
        async def test_unknown_query_flags_gap_or_sandbox():
            pipeline = JimsAIPipeline()
            result = await pipeline.run(PipelineRequest(user_id="test", query="zzzz qqqq novalue unrouteable"))
            assert result.ir.target_ir == "OP_ESCAPE_TO_SANDBOX" or result.gaps


        def test_encoder_extracts_clean_relations():
            signature = DualRepresentationEncoder().encode_text(
                "AuthService depends on UserModel. UserModel.id_change causes AuthService.token_invalidation."
            )
            relations = {(relation.subject, relation.predicate, relation.object) for relation in signature.structured.relations}
            assert ("AuthService", "depends_on", "UserModel") in relations
            assert ("UserModel.id_change", "causes", "AuthService.token_invalidation") in relations


        def test_graph_deduplicates_relation_and_causal_edges():
            signature = DualRepresentationEncoder().encode_text(
                "UserModel.id_change causes AuthService.token_invalidation."
            )
            graph = CausalGraphEngine()
            graph.add_signature(signature)
            paths = graph.traverse("UserModel.id_change")
            edges = paths["usermodel.id_change"]
            assert len(edges) == 1


        @pytest.mark.asyncio
        async def test_training_ingest_then_query_uses_new_memory():
            pipeline = JimsAIPipeline()
            ingest = await pipeline.ingest_training(
                TrainingIngestRequest(
                    user_id="test",
                    content="InventoryService depends on StockLedger. StockLedger.update causes InventoryService.recount.",
                    source_trust=0.92,
                    domain_hint="workspace_training",
                )
            )
            assert ingest.signature.id
            assert ingest.world_model_candidates
            assert ingest.sppe_training_pair.accepted

            result = await pipeline.run(
                PipelineRequest(user_id="test", query="What happens if StockLedger.update changes?")
            )
            assert ingest.signature.id in result.sources
        """,
    )
    write(
        "tests/test_semantic_compiler.py",
        """
        from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime, sanitize


        def test_sanitize_is_stable():
            assert sanitize("Yo, send over that layout please!") == ["send", "layout"]


        def test_compiler_routes_canvas():
            compiler = SemanticCompilerRuntime()
            ir = compiler.compile("Run deep analysis on the full codebase")
            assert ir.target_ir == "RUN_CANVAS"
            assert ir.execution_mode == "DETERMINISTIC_CORE"


        def test_compiler_uses_sandbox_for_unmatched_input():
            compiler = SemanticCompilerRuntime()
            ir = compiler.compile("zzzz qqqq")
            assert ir.target_ir == "OP_ESCAPE_TO_SANDBOX"


        def test_compiler_extracts_causal_entity_scope():
            compiler = SemanticCompilerRuntime()
            ir = compiler.compile("What services are affected if UserModel.id changes?")
            assert "What" not in ir.scope_constraints["entities"]
            assert "UserModel.id" in ir.scope_constraints["entities"]
            assert "UserModel.id_change" in ir.scope_constraints["entities"]
        """,
    )


def main() -> None:
    copy_pdf()
    root_files()
    docs()
    prototype_files()
    services()
    frontend()
    infra()
    sdk_cli_bench_tests()
    print("JIMS-AI scaffold generated.")


if __name__ == "__main__":
    main()

