# Requirements Document

## Introduction

This document specifies the formal requirements for fixing four architectural gaps in the JIMS-AI system. The gaps span the Autonomous Training Agent (stub metrics and data connectors), the Re-Embedding Pipeline (no background worker to close the fallback loop), the `JimsAIPipeline.run()` method (monolithic and untestable), and the `SPPEBatchStore` (isolated raw-SQL store disconnected from `ProductionRuntime` and the eventing module).

All four gaps share common infrastructure: `ProductionRuntime` (Supabase + Cloudflare Vectorize), `AuditEventStore` (SQLite CQRS log), `FourLayerMemoryStore` (in-memory), and the external HuggingFace embedding service. Requirements are derived directly from the approved design document and are intended to be minimally invasive — wiring up existing, correct infrastructure rather than introducing new persistence layers.

---

## Glossary

- **AutonomousTrainingAgent**: The system component responsible for autonomously ingesting training data and evaluating the system state to drive continuous learning.
- **MetricsCollector**: A component that derives real `SystemState` values from live telemetry in `AuditEventStore`, `FourLayerMemoryStore`, and `ProductionRuntime`.
- **WikipediaConnector**: A component that fetches and normalizes Wikipedia articles via the MediaWiki REST API.
- **OpenSubtitlesConnector**: A component that fetches subtitle dialogue lines from the OpenSubtitles REST API.
- **SyntheticDataGenerator**: A component that generates templated Q&A pairs targeting identified training gaps without calling external LLMs.
- **RawDocument**: A data transfer object representing a single normalized source document with fields: `source`, `lang`, `title`, `content`, and `metadata`.
- **SystemState**: A dataclass holding float metric scores (all in `[0.0, 1.0]`) used by the agent to decide training actions.
- **IdentifiedGap**: A record describing a coverage gap in the system's knowledge (capability, language, or domain).
- **ReEmbeddingWorker**: A background asyncio task that scans `MemorySignature` objects flagged with `reembedding_required=True` and upgrades their embeddings using the HF embedding service.
- **ReEmbeddingResult**: A dataclass summarizing one scan-and-reembed cycle with fields: `scanned`, `upgraded`, `deferred`, `failed`, `elapsed_ms`.
- **MemorySignature**: A persisted representation of an encoded document, including `latent_embedding`, `metadata`, and `id`.
- **FourLayerMemoryStore**: The in-memory store organized into sensory, working, semantic, and episodic layers.
- **ProductionRuntime**: The cloud persistence layer wrapping Supabase Postgres, Cloudflare Vectorize, and Cloudflare R2.
- **AuditEventStore**: The local SQLite CQRS log that records all pipeline and agent audit events.
- **JimsAIPipeline**: The central pipeline class whose `run()` method orchestrates all inference and learning steps.
- **PipelineRequest**: The input value object for a single pipeline invocation, containing `user_id`, `workspace_id`, `thread_id`, `query`, `modality`, `canvas_hint`, and `invention_hint`.
- **PipelineResponse**: The output value object from `run()`, containing `response` text, `confidence`, `layer_results`, and `trace_id`.
- **SPPEBatchStore**: The persistence component for Soft Positive Pair Extraction (SPPE) training pairs.
- **SPPEPair**: A training pair record with fields `pair_id`, `semantic_ir_hash`, `output_hash`, `quality_score`, `signal_efficiency`, and `provenance`.
- **SPPEPairGenerated**: A domain event emitted by `SPPEBatchStore` when a pair is successfully persisted, consumed by `SPPEPairProjection`.
- **EventStore**: The SQLAlchemy-backed eventing store in `prototype/jimsai/eventing/event_store.py`.
- **SupabasePostgresStore**: The concrete Postgres adapter inside `ProductionRuntime` that owns all parameterized SQL operations.
- **HF Embedding Service**: The external HuggingFace-hosted embedding endpoint at `POST /v1/embed`.
- **eventing_session**: An optional SQLAlchemy `AsyncSession` passed to `SPPEBatchStore` to enable domain event emission.
- **NFKC normalization**: Unicode Normalization Form KC, applied to all fetched document content via `unicodedata.normalize("NFKC", ...)`.

---

## Requirements

### Requirement 1: Real Metrics Collection

**User Story:** As a system operator, I want the Autonomous Training Agent to evaluate real system health metrics, so that training decisions are based on actual pipeline performance rather than hardcoded placeholder values.

#### Acceptance Criteria

1. THE `MetricsCollector` SHALL derive `intent_stability_score` from the fraction of `query_completed` events in `AuditEventStore` where `confidence >= 0.72`, computed over the most recent 5000 events.
2. THE `MetricsCollector` SHALL derive `provider_dependency_rate` as the ratio of `query_completed` events where `used_groq=True` to total `query_completed` events in the rolling window.
3. THE `MetricsCollector` SHALL derive `retrieval_accuracy` as the ratio of `query_completed` events where `len(sources) >= 1 AND confidence >= 0.80` to total `query_completed` events.
4. THE `MetricsCollector` SHALL derive `world_model_confidence_avg` as the average `confidence.score` across all semantic-layer signatures in `FourLayerMemoryStore`.
5. WHEN `AuditEventStore` contains zero events, THE `MetricsCollector` SHALL return a `SystemState` with all float fields set to `0.0`.
6. FOR ALL `SystemState` objects returned by `MetricsCollector.collect()`, every ratio field SHALL satisfy `0.0 <= value <= 1.0`.
7. THE `MetricsCollector` SHALL accept `FourLayerMemoryStore`, `AuditEventStore`, and `ProductionRuntime` as constructor dependencies, with no hardcoded values in its implementation.

---

### Requirement 2: Wikipedia Data Connector

**User Story:** As a system operator, I want the agent to fetch real Wikipedia articles for training, so that the system ingests factual, naturally-occurring language data.

#### Acceptance Criteria

1. WHEN `WikipediaConnector.fetch_batch()` is called with a language code and optional topic filter, THE `WikipediaConnector` SHALL query the MediaWiki API at `{lang}.wikipedia.org/w/api.php` using `action=query&list=random&prop=extracts&exintro=true` and return up to `limit` `RawDocument` objects.
2. THE `WikipediaConnector` SHALL normalize all fetched article content using NFKC Unicode normalization before storing it in `RawDocument.content`.
3. THE `WikipediaConnector` SHALL truncate article content to a maximum of 2000 characters per article.
4. IF an `httpx.HTTPError` or `httpx.TimeoutException` occurs during a Wikipedia API call, THEN THE `WikipediaConnector` SHALL log a warning and return an empty list without raising an exception.
5. THE `WikipediaConnector` SHALL use a request timeout of 10 seconds and retry failed requests with exponential backoff up to a maximum of 3 attempts before returning an empty list.
6. FOR ALL `RawDocument` objects returned by `WikipediaConnector`, `RawDocument.source` SHALL equal `"wikipedia"` and `RawDocument.lang` SHALL equal the requested language code.

---

### Requirement 3: OpenSubtitles Data Connector

**User Story:** As a system operator, I want the agent to fetch real subtitle dialogue for training, so that the system ingests natural conversational language patterns.

#### Acceptance Criteria

1. WHEN `OPENSUBTITLES_API_KEY` environment variable is set, THE `OpenSubtitlesConnector` SHALL query the OpenSubtitles REST API at `https://api.opensubtitles.com/api/v1` and return up to `limit` `RawDocument` objects containing cleaned dialogue lines.
2. WHEN `OPENSUBTITLES_API_KEY` environment variable is absent or empty, THE `OpenSubtitlesConnector` SHALL log an `INFO`-level warning and return an empty list without raising an exception.
3. THE `OpenSubtitlesConnector` SHALL strip SRT sequence numbers, timestamps matching the pattern `\d+:\d+:\d+,\d+`, and HTML formatting tags (e.g., `<i>`, `{...}`) from subtitle content.
4. THE `OpenSubtitlesConnector` SHALL limit each subtitle file to a maximum of 20 cleaned dialogue lines joined with newlines.
5. IF a malformed SRT file is encountered, THEN THE `OpenSubtitlesConnector` SHALL skip that file and continue processing remaining files without raising an exception.
6. FOR ALL `RawDocument` objects returned by `OpenSubtitlesConnector`, `RawDocument.source` SHALL equal `"opensubtitles"` and `RawDocument.lang` SHALL equal the requested language code.

---

### Requirement 4: Synthetic Data Generator

**User Story:** As a system operator, I want the agent to generate synthetic training pairs targeting identified gaps, so that the system can self-improve in domains where real data is sparse.

#### Acceptance Criteria

1. WHEN `SyntheticDataGenerator.generate_batch()` is called with a list of `IdentifiedGap` objects, THE `SyntheticDataGenerator` SHALL return a list of `RawDocument` objects using template-based generation with no external LLM calls.
2. THE `SyntheticDataGenerator` SHALL use the `gap_type` field of each `IdentifiedGap` to select the appropriate template family: capability gaps use query-response templates, language gaps use factual statement templates in the target language, and domain gaps use Wikipedia-style factoid sentence templates.
3. FOR ALL `RawDocument` objects returned by `SyntheticDataGenerator`, `RawDocument.source` SHALL equal `"synthetic"`.
4. IF a template error occurs for a specific gap, THEN THE `SyntheticDataGenerator` SHALL skip that gap and continue processing remaining gaps without raising an exception.

---

### Requirement 5: Real Ingestion Pipeline

**User Story:** As a system operator, I want the agent's `_ingest_source()` method to process real documents, so that training batches reflect actual data rather than simulated counts.

#### Acceptance Criteria

1. WHEN `_ingest_source()` is called with `source["source"] == "wikipedia"`, THE `AutonomousTrainingAgent` SHALL instantiate `WikipediaConnector`, fetch documents, encode each via `DualRepresentationEncoder`, insert into `FourLayerMemoryStore`, and persist via `ProductionRuntime.save_training_ingest()`.
2. WHEN `_ingest_source()` is called with `source["source"] == "opensubtitles"`, THE `AutonomousTrainingAgent` SHALL instantiate `OpenSubtitlesConnector` and follow the same encode-insert-persist flow.
3. WHEN `_ingest_source()` is called with `source["source"] == "synthetic_generation"`, THE `AutonomousTrainingAgent` SHALL instantiate `SyntheticDataGenerator` and follow the same encode-insert-persist flow.
4. THE `AutonomousTrainingAgent` SHALL apply NFKC normalization to each document's `content` field before encoding.
5. IF encoding or persistence fails for an individual document, THEN THE `AutonomousTrainingAgent` SHALL log the error, increment the failed count, and continue processing remaining documents in the batch without aborting.
6. IF any data connector raises an exception, THEN THE `_ingest_source()` method SHALL return a result dict with `documents_processed == 0` without propagating the exception to the caller.
7. THE `_ingest_source()` method SHALL return a result dict containing real counts derived from actual processing, not simulated arithmetic.
8. FOR ALL valid documents in a batch, THE `AutonomousTrainingAgent` SHALL attempt SPPE pair generation from each `(content, signature)` pair after encoding.

---

### Requirement 6: RawDocument Data Model

**User Story:** As a developer, I want a well-defined `RawDocument` type, so that all data connectors share a consistent interface and validation rules.

#### Acceptance Criteria

1. THE `RawDocument` dataclass SHALL contain fields: `source` (str), `lang` (str), `title` (str), `content` (str), and `metadata` (dict).
2. FOR ALL `RawDocument` objects produced by any connector, `content` SHALL be non-empty and SHALL NOT exceed 4000 characters.
3. FOR ALL `RawDocument` objects produced by any connector, `lang` SHALL be a valid two-letter ISO 639-1 language code.
4. FOR ALL `RawDocument` objects produced by any connector, `source` SHALL be one of: `"wikipedia"`, `"opensubtitles"`, or `"synthetic"`.

---

### Requirement 7: Re-Embedding Background Worker

**User Story:** As a system operator, I want a background worker to automatically upgrade hash-fallback embeddings, so that signatures receive real semantic embeddings once the HF embedding service becomes available.

#### Acceptance Criteria

1. THE `ReEmbeddingWorker` SHALL run as a continuous background asyncio task, started via `start()` and stopped via `stop()`.
2. WHEN `ReEmbeddingWorker.run_once()` is called, THE `ReEmbeddingWorker` SHALL scan `FourLayerMemoryStore` sensory and working layers for signatures where `metadata["reembedding_required"] is True`.
3. WHILE `ProductionRuntime.cloud_authoritative` is `True`, THE `ReEmbeddingWorker` SHALL also query `ProductionRuntime.load_recent_signatures()` and include signatures with `reembedding_required=True` from that source, deduplicating by `signature.id`.
4. THE `ReEmbeddingWorker` SHALL process at most `batch_size` candidate signatures per `run_once()` invocation, prioritized by most recent `created_at` first.
5. WHEN the HF embedding service returns a real (non-fallback) vector for a flagged signature, THE `ReEmbeddingWorker` SHALL update the signature with `metadata["reembedding_required"] = False`, `metadata["latent_embedding_source"] = "external_service_recovered"`, and the new `latent_embedding` vector.
6. WHEN a signature is successfully re-embedded, THE `ReEmbeddingWorker` SHALL update the signature in `FourLayerMemoryStore` and, when `cloud_authoritative` is `True`, persist it to `ProductionRuntime` and Vectorize.
7. WHEN a signature is successfully re-embedded, THE `ReEmbeddingWorker` SHALL append a `"reembedding_completed"` event to `AuditEventStore`.
8. IF the HF embedding service returns `fallback=True` or raises a connection error, THEN THE `ReEmbeddingWorker` SHALL increment the retry count for that signature, append a `"reembedding_deferred"` event, and skip the signature until the next cycle.
9. IF a signature's retry count reaches `max_retries_per_signature`, THEN THE `ReEmbeddingWorker` SHALL set `metadata["reembedding_required"] = False`, set `metadata["reembedding_permanent_fallback"] = True`, update the signature in memory, and append a `"reembedding_exhausted"` event.
10. THE `ReEmbeddingWorker` SHALL NOT include signatures with `reembedding_required=False` in scan candidates.
11. IF an uncaught exception occurs in the worker loop, THEN THE `ReEmbeddingWorker` SHALL log the error, sleep for 60 seconds, and continue the next poll cycle without terminating.
12. THE `ReEmbeddingWorker` SHALL be registered as `self.reembedding_worker` on `JimsAIPipeline` and accept `poll_interval_seconds` from the `JIMS_REEMBED_POLL_INTERVAL` environment variable (default `120`) and `batch_size` from `JIMS_REEMBED_BATCH_SIZE` (default `20`).

---

### Requirement 8: ReEmbeddingResult Invariants

**User Story:** As a developer, I want `ReEmbeddingResult` to accurately summarize each worker cycle, so that monitoring and testing can verify worker correctness.

#### Acceptance Criteria

1. THE `ReEmbeddingResult` dataclass SHALL contain fields: `scanned` (int), `upgraded` (int), `deferred` (int), `failed` (int), and `elapsed_ms` (float), all non-negative.
2. FOR ALL `ReEmbeddingResult` objects returned by `ReEmbeddingWorker.run_once()`, `upgraded + deferred + failed` SHALL equal `scanned`.
3. FOR ALL `ReEmbeddingResult` objects, `0 <= upgraded <= scanned`, `0 <= deferred <= scanned`, and `0 <= failed <= scanned`.

---

### Requirement 9: Pipeline `run()` Decomposition

**User Story:** As a developer, I want `JimsAIPipeline.run()` decomposed into named sub-methods, so that each step is independently testable without changing any observable pipeline behavior.

#### Acceptance Criteria

1. THE `JimsAIPipeline` SHALL implement the following private sub-methods: `_resolve_cache()`, `_resolve_session()`, `_detect_context_drift()`, `_encode_and_learn()`, `_hydrate_context()`, `_route_capabilities()`, `_build_cognitive_object()`, `_render_response()`, and `_persist_and_audit()`.
2. THE `JimsAIPipeline.run()` method SHALL delegate to these sub-methods in the order specified by the design without performing any inline logic that belongs to a sub-method.
3. FOR ALL `PipelineRequest` inputs, THE `JimsAIPipeline.run()` SHALL produce `PipelineResponse` outputs with the same `response`, `confidence`, and `trace_id` fields as the original monolithic implementation.
4. WHEN `_resolve_cache()` returns a non-None `cached_response`, THE `JimsAIPipeline.run()` SHALL return that cached response immediately without calling any other sub-method.
5. THE `_resolve_cache()` method SHALL return a deterministic cache key computed as a SHA-256 hash over `(user_id, workspace_id, thread_id, query, modality, canvas_hint, invention_hint)`.
6. WHEN two `PipelineRequest` objects have identical `(user_id, workspace_id, thread_id, query, modality, canvas_hint, invention_hint)` fields, THE `_resolve_cache()` method SHALL return the same cache key for both.
7. THE `_resolve_session()` method SHALL load an existing session from `ProductionRuntime` when `cloud_authoritative` is `True`, and from `self.sessions` in-memory dict otherwise; it SHALL create a new session dict if none exists for the given `user_id`.
8. WHEN `_detect_context_drift()` detects that `session["last_activity"]` is older than 15 minutes, THE `JimsAIPipeline` SHALL remove `ACTIVE_OBJECT` and `ACTIVE_INTENT` from the session and set `session["_prevent_active_object"] = True`.
9. WHEN `_detect_context_drift()` detects that the cosine similarity between `hash_embedding(request.query)` and `hash_embedding(session["ACTIVE_OBJECT"])` is below `0.35`, THE `JimsAIPipeline` SHALL remove `ACTIVE_OBJECT` and `ACTIVE_INTENT` from the session and set `session["_prevent_active_object"] = True`.
10. THE `_detect_context_drift()` method SHALL update `session["last_activity"]` to the current UTC time on every invocation.
11. THE `_encode_and_learn()` method SHALL run intent inference before encoding, save the session immediately after setting `ACTIVE_INTENT` and `ACTIVE_OBJECT`, and trigger learning and user-fact promotion after encoding.
12. THE `_hydrate_context()` method SHALL be called after `_encode_and_learn()` and SHALL return the count of newly hydrated signatures.
13. THE `_persist_and_audit()` method SHALL store the result in `result_cache` under `cache_key`, save the chat exchange to `ProductionRuntime`, and append a `"query_completed"` event to `AuditEventStore`.
14. FOR ALL non-cached `PipelineRequest` invocations, THE `JimsAIPipeline` SHALL append exactly one `"query_completed"` event to `AuditEventStore` per `run()` call.
15. THE `obj.layer_results` list SHALL contain all layer results including `"output"` and `"feedback"` entries before `PipelineResponse` is constructed.

---

### Requirement 10: Pipeline Cache Idempotency

**User Story:** As a system operator, I want repeated identical queries to return cached responses, so that pipeline throughput is preserved and the audit log is not polluted with duplicate events.

#### Acceptance Criteria

1. WHEN `JimsAIPipeline.run()` is called twice with the same `PipelineRequest`, THE `JimsAIPipeline` SHALL return responses with equal `response` and `confidence` fields on both calls.
2. WHEN the second call to `run()` returns a cached response, THE `JimsAIPipeline` SHALL NOT append a new `"query_received"` event to `AuditEventStore`.
3. WHEN `_resolve_cache()` returns a cache hit, THE `JimsAIPipeline` SHALL append a `"query_cache_hit"` event to `AuditEventStore`.

---

### Requirement 11: SPPE Batch Store Wiring

**User Story:** As a system operator, I want the SPPE training pair store to persist data through `ProductionRuntime`, so that generated training pairs are stored reliably using the same infrastructure as the rest of the pipeline.

#### Acceptance Criteria

1. THE redesigned `SPPEBatchStore` SHALL accept `ProductionRuntime`, `AuditEventStore`, and an optional `eventing_session` as constructor dependencies, replacing the raw `db_session` parameter.
2. WHEN `SPPEBatchStore.add_pair()` is called, THE `SPPEBatchStore` SHALL persist the pair via `ProductionRuntime.save_sppe_pair()` and append an `"sppe_pair_stored"` event to `AuditEventStore`.
3. WHEN `SPPEBatchStore.add_pair()` is called, THE `SPPEBatchStore` SHALL get or create an open batch for the workspace via `ProductionRuntime.get_or_create_sppe_batch()` and return the `batch_id`.
4. WHEN `SPPEBatchStore.add_pair()` is called with the same `pair_id` more than once, THE `SPPEBatchStore` SHALL return the same `batch_id` on all calls and persist exactly one row in `sppe_pairs` (via `ON CONFLICT (pair_id) DO NOTHING`).
5. IF `Postgres` is unavailable, THEN THE `SPPEBatchStore` SHALL fall back to storing pairs in the in-memory `self._pairs` list, log a warning, and continue without raising an exception.
6. THE `SPPEBatchStore.get_batch()` method SHALL delegate to `ProductionRuntime.get_sppe_batch_stats()` when Postgres is available, and fall back to aggregating `self._pairs` otherwise.
7. THE `SPPEBatchStore.get_batches_for_workspace()` method SHALL delegate to `ProductionRuntime.list_sppe_batches()` with the provided workspace and status filter.

---

### Requirement 12: SPPE Domain Event Emission

**User Story:** As a system operator, I want `SPPEPairGenerated` events emitted to the eventing store when pairs are persisted, so that downstream projections receive real training data.

#### Acceptance Criteria

1. WHEN `SPPEBatchStore.add_pair()` is called and `eventing_session` is not `None`, THE `SPPEBatchStore` SHALL emit exactly one `SPPEPairGenerated` event to `EventStore` with `aggregate_id == str(pair.pair_id)`.
2. THE `SPPEPairGenerated` event SHALL contain `pair_id`, `workspace_id`, `semantic_ir_hash`, `output_hash`, `quality_score`, `signal_efficiency`, `provenance`, and `batch_id` fields matching the corresponding fields of the persisted `SPPEPair`.
3. IF `eventing_session` is `None`, THEN THE `SPPEBatchStore` SHALL skip domain event emission entirely without raising an exception.
4. IF `EventStore.append()` raises an exception, THEN THE `SPPEBatchStore` SHALL log the error and continue without propagating the exception to the caller.

---

### Requirement 13: SPPE SQL Schema

**User Story:** As a system operator, I want the SPPE Postgres schema created automatically, so that the tables are available without manual migration steps.

#### Acceptance Criteria

1. WHEN `SupabasePostgresStore.ensure_schema()` is called, THE `SupabasePostgresStore` SHALL create the `sppe_pairs` table with columns: `pair_id` (TEXT PRIMARY KEY), `batch_id` (TEXT NOT NULL), `workspace_id` (TEXT NOT NULL), `semantic_ir_hash` (TEXT NOT NULL), `output_hash` (TEXT NOT NULL), `quality_score` (DOUBLE PRECISION NOT NULL), `signal_efficiency` (DOUBLE PRECISION NOT NULL), `provenance` (JSONB NOT NULL DEFAULT `'{}'::jsonb`), and `created_at` (TIMESTAMPTZ DEFAULT now()).
2. WHEN `SupabasePostgresStore.ensure_schema()` is called, THE `SupabasePostgresStore` SHALL create the `sppe_batches` table with columns: `batch_id` (TEXT PRIMARY KEY), `workspace_id` (TEXT NOT NULL), `status` (TEXT NOT NULL DEFAULT `'open'`), `created_at` (TIMESTAMPTZ DEFAULT now()), and `updated_at` (TIMESTAMPTZ DEFAULT now()).
3. WHEN `SupabasePostgresStore.ensure_schema()` is called, THE `SupabasePostgresStore` SHALL create indexes: `sppe_pairs_batch_idx` on `(batch_id, created_at DESC)`, `sppe_pairs_workspace_idx` on `(workspace_id, created_at DESC)`, and `sppe_batches_workspace_status_idx` on `(workspace_id, status, created_at DESC)`.
4. THE `ensure_schema()` method SHALL use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` so that repeated calls are idempotent.

---

### Requirement 14: SPPE Production Runtime Methods

**User Story:** As a developer, I want `ProductionRuntime` to expose the SPPE persistence methods, so that `SPPEBatchStore` can use the shared infrastructure instead of raw SQL.

#### Acceptance Criteria

1. THE `SupabasePostgresStore` SHALL implement `save_sppe_pair(pair: SPPEPair, workspace_id: str, batch_id: str) -> None` using a parameterized `INSERT INTO sppe_pairs` query with `ON CONFLICT (pair_id) DO NOTHING`.
2. THE `SupabasePostgresStore` SHALL implement `get_or_create_sppe_batch(workspace_id: str) -> str` that selects an open batch or inserts a new one within a single transaction, returning the `batch_id`.
3. THE `SupabasePostgresStore` SHALL implement `get_sppe_batch_stats(batch_id: str) -> dict[str, Any] | None` that returns aggregate statistics matching the shape of the original `SPPEBatchStore.get_batch()` return value.
4. THE `SupabasePostgresStore` SHALL implement `list_sppe_batches(workspace_id: str, status: str = "open") -> list[dict[str, Any]]` that returns batches filtered by workspace and status.
5. FOR ALL SQL operations in the new SPPE methods, THE `SupabasePostgresStore` SHALL use parameterized queries with no user-supplied strings interpolated directly into SQL.

---

### Requirement 15: Backward Compatibility and No Regression

**User Story:** As a developer, I want all four gap fixes to be backward-compatible with the existing system, so that no currently-working behavior is broken by the changes.

#### Acceptance Criteria

1. THE refactored `JimsAIPipeline.run()` SHALL produce identical `PipelineResponse.response`, `PipelineResponse.confidence`, and `PipelineResponse.layer_results` for any given `PipelineRequest` compared to the pre-refactoring monolithic implementation.
2. THE redesigned `SPPEBatchStore` interface (`add_pair`, `get_batch`, `get_batches_for_workspace`) SHALL maintain the same method signatures and return types as the original implementation.
3. WHEN `OPENSUBTITLES_API_KEY` is absent, THE `AutonomousTrainingAgent` SHALL skip the OpenSubtitles source and continue with remaining sources without requiring operator intervention.
4. WHEN `eventing_session` is `None`, THE `SPPEBatchStore` SHALL operate in a degraded mode using only `ProductionRuntime` and `AuditEventStore`, without requiring changes to callers that do not pass an eventing session.
5. THE `ReEmbeddingWorker` SHALL be an opt-in background component — the application host is responsible for calling `asyncio.create_task(pipeline.reembedding_worker.start())`, and omitting this call SHALL NOT affect pipeline correctness.
