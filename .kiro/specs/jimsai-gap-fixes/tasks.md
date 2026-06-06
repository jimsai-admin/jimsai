# Implementation Plan: JIMS-AI Architectural Gap Fixes

## Overview

This plan implements four self-contained gap fixes in the JIMS-AI prototype. Each gap maps cleanly to a set of coding tasks that wire up existing infrastructure rather than introducing new persistence layers. The implementation language is Python (matching the existing codebase).

The four gaps are:
1. **Gap 1** — `AutonomousTrainingAgent`: Replace stub metrics/ingestion with real `MetricsCollector` + `WikipediaConnector` + `OpenSubtitlesConnector` + `SyntheticDataGenerator`.
2. **Gap 2** — Re-embedding pipeline: New `ReEmbeddingWorker` background asyncio task in `encoder/reembedding_worker.py`.
3. **Gap 3** — `JimsAIPipeline.run()` decomposition: Extract 9 named private sub-methods from the monolithic `run()` body.
4. **Gap 4** — `SPPEBatchStore` wiring: Redesign `SPPEBatchStore` to use `ProductionRuntime` + eventing; add SPPE methods to `SupabasePostgresStore`.

---

## Tasks

- [ ] 1. Define shared data models for Gap 1 connectors
  - Add `RawDocument` dataclass to `autonomous_training_agent.py` with fields: `source` (str), `lang` (str), `title` (str), `content` (str), `metadata` (dict)
  - Validate that `content` is non-empty and does not exceed 4000 characters
  - Validate that `lang` is a 2-letter ISO 639-1 code and `source` is one of `"wikipedia"`, `"opensubtitles"`, or `"synthetic"`
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 1.1 Implement `RawDocument` dataclass in `autonomous_training_agent.py`
    - Write the dataclass with all five fields and optional validation helpers
    - _Requirements: 6.1_

  - [ ]* 1.2 Write unit tests for `RawDocument` field validation
    - Test that `content` exceeding 4000 chars is detected; test valid/invalid lang codes
    - _Requirements: 6.2, 6.3, 6.4_

- [ ] 2. Implement `MetricsCollector` class
  - Create `MetricsCollector` inside `autonomous_training_agent.py` with constructor accepting `FourLayerMemoryStore`, `AuditEventStore`, and `ProductionRuntime`
  - Implement `collect() -> SystemState` deriving all metric fields from live data (no hardcoded values)
    - `intent_stability_score`: fraction of last 5000 `query_completed` events with `confidence >= 0.72`
    - `provider_dependency_rate`: fraction of `query_completed` events with `used_groq=True`
    - `retrieval_accuracy`: fraction of `query_completed` events with `len(sources) >= 1 AND confidence >= 0.80`
    - `world_model_confidence_avg`: average `confidence.score` of semantic-layer signatures in `FourLayerMemoryStore`
  - Return all-zero `SystemState` when event store contains zero events
  - Ensure every ratio field is clamped to `[0.0, 1.0]`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [ ] 2.1 Implement `MetricsCollector.collect()` with event-store queries
    - Parse `AuditEventStore.tail()` events; derive `intent_stability_score`, `provider_dependency_rate`, `retrieval_accuracy`
    - Read `FourLayerMemoryStore.semantic` layer for `world_model_confidence_avg`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ] 2.2 Wire `MetricsCollector` into `AutonomousTrainingAgent._evaluate_system_state()`
    - Instantiate `MetricsCollector(self.pipeline.memory, self.event_store, self.pipeline.production)` inside the method
    - Replace the hardcoded `SystemState(...)` return with `collector.collect()`
    - _Requirements: 1.7_

  - [ ]* 2.3 Write property test for `MetricsCollector` unit-interval invariant
    - **Property 1: Metric scores are always bounded to the unit interval**
    - Generate synthetic `query_completed` events with random `confidence` and `used_groq` values
    - Assert `0.0 <= state.intent_stability_score <= 1.0`, `0.0 <= state.provider_dependency_rate <= 1.0`, `0.0 <= state.retrieval_accuracy <= 1.0`, `0.0 <= state.world_model_confidence_avg <= 1.0`
    - **Validates: Requirements 1.6**

- [ ] 3. Implement `WikipediaConnector`
  - Add `WikipediaConnector` class to `autonomous_training_agent.py`
  - Implement `fetch_batch(lang, topic_filter, limit) -> list[RawDocument]` hitting `{lang}.wikipedia.org/w/api.php` with `action=query&list=random&prop=extracts&exintro=true`
  - Apply NFKC normalization (`unicodedata.normalize("NFKC", content)`) and truncate to 2000 chars per article
  - Catch `httpx.HTTPError` and `httpx.TimeoutException`; log warning and return `[]`
  - Use `httpx` with 10-second timeout and exponential-backoff retry (max 3 attempts)
  - Set `RawDocument.source = "wikipedia"`, `RawDocument.lang = lang`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ] 3.1 Implement `WikipediaConnector.fetch_batch()` with httpx + retry logic
    - Write the MediaWiki API call, NFKC normalization, 2000-char truncation, and 3-attempt exponential backoff
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [ ]* 3.2 Write unit tests for `WikipediaConnector` graceful HTTP error fallback
    - Mock `httpx` to raise `httpx.TimeoutException`; assert `fetch_batch()` returns `[]` without raising
    - _Requirements: 2.4, 2.5_

- [ ] 4. Implement `OpenSubtitlesConnector`
  - Add `OpenSubtitlesConnector` class to `autonomous_training_agent.py`
  - Read `OPENSUBTITLES_API_KEY` from env; log `INFO` warning and return `[]` if absent
  - Implement `fetch_batch(lang, limit) -> list[RawDocument]` querying `https://api.opensubtitles.com/api/v1`
  - Strip SRT sequence numbers, timestamps (`\d+:\d+:\d+,\d+`), and HTML tags (`<i>`, `{...}`) from subtitle text
  - Limit each subtitle to 20 cleaned lines joined with `\n`
  - Skip malformed SRT files without raising; set `RawDocument.source = "opensubtitles"`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ] 4.1 Implement `OpenSubtitlesConnector.fetch_batch()` with SRT parsing and graceful key-absent fallback
    - Write the API call, SRT stripping regex, 20-line limit, per-file error handling
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 4.2 Write unit tests for `OpenSubtitlesConnector` key-absent and malformed-SRT paths
    - Test `OPENSUBTITLES_API_KEY=""` returns `[]`; feed malformed SRT and assert skip-and-continue
    - _Requirements: 3.2, 3.5_

- [ ] 5. Implement `SyntheticDataGenerator`
  - Add `SyntheticDataGenerator` class to `autonomous_training_agent.py`
  - Implement `generate_batch(gaps, limit) -> list[RawDocument]` using template-based generation (no LLM calls)
  - Select template family by `gap.gap_type`: capability → query-response templates; language → factual statements; domain → Wikipedia-style factoid sentences
  - Catch per-gap template errors; skip the gap and continue
  - Set `RawDocument.source = "synthetic"` on all output documents
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ] 5.1 Implement `SyntheticDataGenerator.generate_batch()` with three template families
    - Write capability, language, and domain template banks; select by `gap.gap_type`; error-isolate per gap
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 5.2 Write unit tests for `SyntheticDataGenerator` template dispatch and error isolation
    - Test each `gap_type`; inject a failing template and assert remaining gaps still produce output
    - _Requirements: 4.2, 4.4_

- [ ] 6. Rewrite `AutonomousTrainingAgent._ingest_source()` with real connector flow
  - Replace the placeholder arithmetic in `_ingest_source()` with real ingestion:
    1. Instantiate the correct connector based on `source["source"]`
    2. Fetch documents via `connector.fetch_batch(...)`
    3. For each document: NFKC-normalize content, encode via `self.pipeline.encoder.encode(...)`, insert into `self.pipeline.memory`, persist via `self.pipeline.production.save_training_ingest(...)`
    4. Attempt SPPE pair generation from `(content, signature)` after encoding
    5. Count and return real `documents_processed`, `signatures_created`, `sppe_pairs_generated`, `world_model_candidates`
  - Wrap per-document processing in try/except; log error and increment `failed` count; never abort the batch
  - If the connector itself raises, return `{"documents_processed": 0, ...}` without propagating
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [ ] 6.1 Replace stub `_ingest_source()` body with real encode-insert-persist loop
    - Wire `WikipediaConnector`, `OpenSubtitlesConnector`, `SyntheticDataGenerator`; add per-document error handling; return real counts
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.7_

  - [ ]* 6.2 Write property test for `_ingest_source()` exception containment
    - **Property 2: Connector failures never raise exceptions out of `_ingest_source()`**
    - Mock connector to raise `httpx.ConnectError`; assert result is a dict with `documents_processed == 0`
    - **Validates: Requirements 5.6**

- [ ] 7. Checkpoint — Gap 1 complete
  - Ensure all Gap 1 tests pass (`MetricsCollector`, `WikipediaConnector`, `OpenSubtitlesConnector`, `SyntheticDataGenerator`, `_ingest_source()`)
  - Ask the user if any questions arise before proceeding to Gap 2.

- [ ] 8. Create `encoder/reembedding_worker.py` with `ReEmbeddingResult` and `ReEmbeddingWorker`
  - Create new file `prototype/jimsai/encoder/reembedding_worker.py`
  - Define `ReEmbeddingResult` dataclass with fields: `scanned` (int), `upgraded` (int), `deferred` (int), `failed` (int), `elapsed_ms` (float) — all non-negative
  - Define `ReEmbeddingWorker` class with constructor: `memory`, `production`, `multimodal_adapter`, `event_store`, `poll_interval_seconds=120`, `batch_size=20`, `max_retries_per_signature=5`
  - Implement `start()`, `stop()`, and `run_once() -> ReEmbeddingResult`
  - _Requirements: 7.1, 8.1_

  - [ ] 8.1 Implement `ReEmbeddingResult` dataclass and `ReEmbeddingWorker` class skeleton
    - Write the dataclass and the `__init__`, `start`, `stop` stubs; confirm `asyncio.Task` lifecycle
    - _Requirements: 7.1, 8.1_

  - [ ]* 8.2 Write property test for `ReEmbeddingResult` count invariant
    - **Property 3: Re-embedding result counts always sum to scanned total**
    - Generate arbitrary `upgraded`, `deferred`, `failed` values; construct `ReEmbeddingResult(scanned=upgraded+deferred+failed, ...)` and assert `upgraded + deferred + failed == scanned`
    - **Validates: Requirements 8.2**

- [ ] 9. Implement `ReEmbeddingWorker._scan_flagged_signatures()` and `_attempt_reembedding()`
  - `_scan_flagged_signatures()`: scan `FourLayerMemoryStore.sensory` and `.working` for `metadata["reembedding_required"] is True`; also query `ProductionRuntime.load_recent_signatures()` when `cloud_authoritative`; deduplicate by `id`; filter out signatures where retry count ≥ `max_retries_per_signature`; return up to `batch_size` results sorted by most recent `created_at` first
  - `_attempt_reembedding(signature)`: call `multimodal_adapter.encode(raw_excerpt, modality)`; if real vector returned, clone signature with `reembedding_required=False`, `latent_embedding_source="external_service_recovered"`, `reembedding_completed_at=utc_now().isoformat()`, `confidence.source="dual_encoder_external_latent"`; otherwise increment retry and return `None`
  - _Requirements: 7.2, 7.3, 7.4, 7.5, 7.10_

  - [ ] 9.1 Implement `_scan_flagged_signatures()` with deduplication and retry-count filtering
    - Write sensory/working layer scan, cloud-authoritative branch, dedup, retry filter, and `batch_size` limit
    - _Requirements: 7.2, 7.3, 7.4, 7.10_

  - [ ] 9.2 Implement `_attempt_reembedding()` with clone-on-success and retry-on-failure
    - Write adapter call, vector check, signature field update on success, retry-count increment on failure
    - _Requirements: 7.5_

  - [ ]* 9.3 Write unit tests for `_attempt_reembedding()` success and fallback paths
    - Mock adapter returning real vector → assert `reembedding_required=False`; mock adapter returning `[]` → assert returns `None`
    - _Requirements: 7.5, 7.8_

- [ ] 10. Implement `ReEmbeddingWorker.run_once()` main loop
  - Implement the full scan-and-reembed cycle following the pseudocode in the design:
    - Call `_scan_flagged_signatures()`
    - For each candidate: call `_attempt_reembedding()`; on success: update memory + (cloud) production + Vectorize + audit event `"reembedding_completed"`; on failure: increment retry, check max retries (mark `reembedding_permanent_fallback=True` + audit `"reembedding_exhausted"` if exhausted, else audit `"reembedding_deferred"`)
  - Wrap outer loop body in try/except; on uncaught exception: log, sleep 60s, continue
  - Return `ReEmbeddingResult` with accurate counts and `elapsed_ms`
  - _Requirements: 7.6, 7.7, 7.8, 7.9, 7.11_

  - [ ] 10.1 Implement `run_once()` with accurate result counting and error recovery
    - Write the full loop; wire audit events; handle exhausted retry path; measure `elapsed_ms`
    - _Requirements: 7.6, 7.7, 7.8, 7.9, 7.11_

  - [ ]* 10.2 Write property test for successfully re-embedded signatures having flag cleared
    - **Property 4: Successfully re-embedded signatures have the flag cleared**
    - Inject signature with `reembedding_required=True`; run `run_once()` with mock adapter returning real vector; assert `memory.get(sig_id).metadata["reembedding_required"] is False` and `latent_embedding_source == "external_service_recovered"`
    - **Validates: Requirements 7.5, 7.6**

  - [ ]* 10.3 Write unit tests for `run_once()` exhausted-retry path
    - Force retry count to `max_retries_per_signature - 1`; run `run_once()` with failing adapter; assert `reembedding_permanent_fallback=True` and `"reembedding_exhausted"` audit event
    - _Requirements: 7.9_

- [ ] 11. Register `ReEmbeddingWorker` on `JimsAIPipeline` and update `encoder/__init__.py`
  - In `pipeline.py` `__init__`: import `ReEmbeddingWorker` from `encoder.reembedding_worker`; instantiate as `self.reembedding_worker` with `JIMS_REEMBED_POLL_INTERVAL` (default `120`) and `JIMS_REEMBED_BATCH_SIZE` (default `20`) from env vars
  - Export `ReEmbeddingWorker` and `ReEmbeddingResult` from `encoder/__init__.py` if that module has public exports
  - _Requirements: 7.12_

  - [ ] 11.1 Add `self.reembedding_worker` instantiation to `JimsAIPipeline.__init__()`
    - Read env vars for poll interval and batch size; construct worker; do NOT call `start()` — leave that to the app host
    - _Requirements: 7.12_

  - [ ]* 11.2 Write unit test confirming `ReEmbeddingWorker` is an opt-in component
    - Construct `JimsAIPipeline` without calling `reembedding_worker.start()`; run `pipeline.run(request)` and assert no errors
    - _Requirements: 15.5_

- [ ] 12. Checkpoint — Gap 2 complete
  - Ensure all Gap 2 tests pass (`ReEmbeddingWorker.run_once()`, scan, attempt, counts, opt-in registration)
  - Ask the user if any questions arise before proceeding to Gap 3.

- [ ] 13. Extract `_resolve_cache()` and `_resolve_session()` from `pipeline.run()`
  - Extract `_resolve_cache(request) -> tuple[str, PipelineResponse | None]`:
    - Move cache-key computation (`result_cache.key(...)`) and `result_cache.get()` check into this method
    - Append `"query_cache_hit"` event inside this method on a cache hit
    - Return `(cache_key, cached_response_or_None)`
  - Extract `_resolve_session(request) -> dict[str, str]`:
    - Move `_load_session(request.user_id, request.thread_id)` call and session-key logic into this method
  - Update `run()` to call both methods; preserve early-return on cache hit
  - _Requirements: 9.1, 9.2, 9.4, 9.5, 9.6, 9.7, 10.3_

  - [ ] 13.1 Extract `_resolve_cache()` private method
    - Move cache-key hash + `result_cache.get()` + cache-hit event into new method; update `run()` call site
    - _Requirements: 9.4, 9.5, 9.6_

  - [ ] 13.2 Extract `_resolve_session()` private method
    - Move `_load_session()` call into new method; return the session dict; update `run()` call site
    - _Requirements: 9.7_

  - [ ]* 13.3 Write unit tests for `_resolve_cache()` determinism and early-return
    - Call with two identical `PipelineRequest` objects; assert same cache key; assert second call hits cache and returns without calling `intent_layer.infer`
    - _Requirements: 9.5, 9.6, 9.4_

- [ ] 14. Extract `_detect_context_drift()` and `_encode_and_learn()` from `pipeline.run()`
  - Extract `_detect_context_drift(request, session) -> bool`:
    - Move the `last_activity` timeout check (15 min), `ACTIVE_OBJECT` cosine-similarity check (threshold 0.35), session mutation (`pop ACTIVE_OBJECT/ACTIVE_INTENT`, set `_prevent_active_object`), and `last_activity` update into this method
    - Return `True` if context was cleared
  - Extract `_encode_and_learn(request, session, layer_results) -> tuple[MemorySignature, SemanticIR]`:
    - Move intent inference (`intent_layer.infer`), session update (`ACTIVE_INTENT`, `ACTIVE_OBJECT`), `_save_session()`, encoding (`encoder_layer.encode`), `learning_layer.learn`, and `_promote_user_fact_memory` into this method
    - Append all layer results via the shared `record()` closure (pass as parameter or refactor to method)
  - Update `run()` call sites
  - _Requirements: 9.1, 9.8, 9.9, 9.10, 9.11_

  - [ ] 14.1 Extract `_detect_context_drift()` with full timeout and similarity logic
    - Move import of `datetime`/`timedelta`/`timezone` inside or to top of file if not already there; extract the full block; return bool
    - _Requirements: 9.8, 9.9, 9.10_

  - [ ] 14.2 Extract `_encode_and_learn()` preserving session-save ordering
    - Session must be saved inside this method immediately after `ACTIVE_INTENT` and `ACTIVE_OBJECT` are set; `layer_results` list is mutated in place
    - _Requirements: 9.11_

  - [ ]* 14.3 Write unit tests for `_detect_context_drift()` timeout and low-similarity paths
    - Set `session["last_activity"]` to 20 min ago → assert returns `True` and `ACTIVE_OBJECT` removed; set similar query → assert returns `False`
    - _Requirements: 9.8, 9.9, 9.10_

- [ ] 15. Extract `_hydrate_context()`, `_route_capabilities()`, `_build_cognitive_object()` from `pipeline.run()`
  - Extract `_hydrate_context(request, input_signature, layer_results) -> int`:
    - Move `_hydrate_persistent_retrieval(...)` call and the hydration `LayerResult` record into this method
    - Return count of newly hydrated signatures
  - Extract `_route_capabilities(request, ir, activation, layer_results) -> tuple[CapabilityPlan, list[CapabilityExecutionResult]]`:
    - Move `capability_router.route(...)`, `capability_adapters.prepare(...)`, `_execute_capability_adapters(...)`, and the capability `LayerResult` record into this method
  - Extract `_build_cognitive_object(ir, retrieved, canvas_result, activation, invention_result, abstraction_result, world_model_activations, graph_view, capability_plan, capability_results, request, prior_layers, layer_results) -> tuple[VerifiedCognitiveObject, list[SimulationResult]]`:
    - Move `reasoning_bridge_layer.build(...)`, `obj.capability_plan`, `obj.capability_results`, `obj.style_signature`, and `_apply_capability_gates(obj)` into this method
  - Update `run()` call sites
  - _Requirements: 9.1, 9.12_

  - [ ] 15.1 Extract `_hydrate_context()` and update `run()` call site
    - _Requirements: 9.12_

  - [ ] 15.2 Extract `_route_capabilities()` with all adapter wiring
    - _Requirements: 9.1_

  - [ ] 15.3 Extract `_build_cognitive_object()` preserving style-signature and gate application
    - _Requirements: 9.1_

- [ ] 16. Extract `_render_response()` and `_persist_and_audit()` from `pipeline.run()`, verify run() skeleton
  - Extract `_render_response(obj, layer_results) -> tuple[str, bool]`:
    - Move `render_layer.render(obj)` call and the "output" + "feedback" `LayerResult` records into this method
    - Set `obj.layer_results = layer_results` inside this method before returning
    - Return `(response_text, used_groq)`
  - Extract `_persist_and_audit(request, ir, pipeline_response, cache_key) -> None`:
    - Move `_learn_from_resolved_prompt(...)`, `result_cache.set(...)`, `production.save_chat_exchange(...)`, and `event_store.append("query_completed", ...)` into this method
  - Verify `run()` now matches the pseudocode skeleton from the design exactly; ensure `query_received` event is still appended in `run()` before any sub-method is called
  - _Requirements: 9.1, 9.2, 9.13, 9.14, 9.15_

  - [ ] 16.1 Extract `_render_response()` including layer_results finalization
    - Move render call and "output"/"feedback" records; set `obj.layer_results` inside method
    - _Requirements: 9.15_

  - [ ] 16.2 Extract `_persist_and_audit()` with cache + chat + audit event writes
    - Move cache set, chat exchange save, and `query_completed` event into method
    - _Requirements: 9.13, 9.14_

  - [ ] 16.3 Verify `run()` skeleton: confirm `query_received` precedes all sub-method calls; confirm single `query_completed` event per non-cached call
    - Read the refactored `run()` and trace the event sequence manually; fix any ordering issues
    - _Requirements: 9.2, 9.14_

  - [ ]* 16.4 Write property test for pipeline cache idempotency
    - **Property 6: Pipeline `run()` is cache-idempotent**
    - Call `pipeline.run(req)` twice with the same request; assert `r1.response == r2.response` and `r1.confidence == r2.confidence`; assert no new `"query_received"` event was appended on second call
    - **Validates: Requirements 10.1, 10.2**

  - [ ]* 16.5 Write property test for single `query_completed` event per non-cached run
    - **Property 7: Every non-cached `run()` produces exactly one `query_completed` event**
    - Assert `final_count >= initial_count + 2` (at least `query_received` + `query_completed`)
    - **Validates: Requirements 9.14**

- [ ] 17. Checkpoint — Gap 3 complete
  - Run `pytest` (or the equivalent test command) to confirm no regressions in pipeline behavior
  - Ensure all Gap 3 sub-method tests pass
  - Ask the user if any questions arise before proceeding to Gap 4.

- [ ] 18. Extend `SupabasePostgresStore.ensure_schema()` with SPPE tables
  - Add SQL statements to `ensure_schema()` in `provider_adapters.py`:
    - `CREATE TABLE IF NOT EXISTS sppe_pairs (pair_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, workspace_id TEXT NOT NULL, semantic_ir_hash TEXT NOT NULL, output_hash TEXT NOT NULL, quality_score DOUBLE PRECISION NOT NULL, signal_efficiency DOUBLE PRECISION NOT NULL, provenance JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ DEFAULT now())`
    - `CREATE TABLE IF NOT EXISTS sppe_batches (batch_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now())`
    - Three indexes: `sppe_pairs_batch_idx`, `sppe_pairs_workspace_idx`, `sppe_batches_workspace_status_idx`
  - Use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` throughout
  - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [ ] 18.1 Add SPPE table and index DDL to `SupabasePostgresStore.ensure_schema()`
    - Append the six DDL statements (2 tables + 3 indexes) to the existing `statements` list in `ensure_schema()`
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [ ]* 18.2 Write unit test confirming `ensure_schema()` is idempotent
    - Call `ensure_schema()` twice against a test Postgres instance (or mock); assert no error on second call
    - _Requirements: 13.4_

- [ ] 19. Add SPPE persistence methods to `SupabasePostgresStore`
  - Implement `save_sppe_pair(pair, workspace_id, batch_id) -> None` using parameterized `INSERT INTO sppe_pairs ... ON CONFLICT (pair_id) DO NOTHING`
  - Implement `get_or_create_sppe_batch(workspace_id) -> str` — SELECT open batch or INSERT new batch within a single transaction; return `batch_id`
  - Implement `get_sppe_batch_stats(batch_id) -> dict[str, Any] | None` — SELECT aggregate stats (pair_count, quality_avg, efficiency_avg, created_at, age_seconds, high_quality_count, high_quality_ratio)
  - Implement `list_sppe_batches(workspace_id, status="open") -> list[dict[str, Any]]` — SELECT batches filtered by workspace and status
  - All SQL must use parameterized queries; no string interpolation into SQL
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [ ] 19.1 Implement `save_sppe_pair()` with `ON CONFLICT DO NOTHING` idempotency
    - Write the parameterized INSERT; use `psycopg.types.json.Jsonb` for `provenance`
    - _Requirements: 14.1, 14.5_

  - [ ] 19.2 Implement `get_or_create_sppe_batch()` as a single transaction
    - SELECT open batch → if found return batch_id; else INSERT new batch and return new batch_id
    - _Requirements: 14.2_

  - [ ] 19.3 Implement `get_sppe_batch_stats()` and `list_sppe_batches()`
    - Write the aggregate SELECT and the filtered list SELECT; match the shape expected by `SPPEBatchStore.get_batch()`
    - _Requirements: 14.3, 14.4_

  - [ ]* 19.4 Write unit tests for `save_sppe_pair()` idempotency
    - Call `save_sppe_pair()` twice with the same `pair_id`; assert exactly one row in `sppe_pairs` (mock DB or real Postgres)
    - _Requirements: 11.4_

- [ ] 20. Redesign `SPPEBatchStore` to use `ProductionRuntime` + eventing
  - Replace the `__init__(self, db_session)` constructor with `__init__(self, production, event_store, eventing_session=None)`
  - Add in-memory fallbacks: `self._active_batches: dict[str, str] = {}` and `self._pairs: list[dict[str, Any]] = []`
  - Rewrite `add_pair(pair, workspace_id) -> str`:
    1. Get/create batch via `production.get_or_create_sppe_batch(workspace_id)` (or in-memory fallback)
    2. Persist via `production.save_sppe_pair(pair, workspace_id, batch_id)` (or append to `_pairs` on Postgres failure)
    3. Emit `SPPEPairGenerated` event via `EventStore(eventing_session).append(event)` when `eventing_session` is not None; catch and log exceptions from event emission
    4. Append `"sppe_pair_stored"` audit event to `event_store`
    5. Return `batch_id`
  - Rewrite `get_batch(batch_id)` to delegate to `production.get_sppe_batch_stats()` with in-memory fallback
  - Rewrite `get_batches_for_workspace(workspace_id, status)` to delegate to `production.list_sppe_batches()`
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [ ] 20.1 Rewrite `SPPEBatchStore.__init__()` with new constructor signature
    - Replace `db_session` with `production`, `event_store`, `eventing_session`; add `_active_batches` and `_pairs` fallback fields
    - _Requirements: 11.1_

  - [ ] 20.2 Rewrite `SPPEBatchStore.add_pair()` with full persistence + eventing + audit
    - Wire `get_or_create_sppe_batch` → `save_sppe_pair` → `EventStore.append(SPPEPairGenerated)` → `event_store.append("sppe_pair_stored")`; add in-memory fallback on Postgres failure
    - _Requirements: 11.2, 11.3, 11.5_

  - [ ] 20.3 Rewrite `SPPEBatchStore.get_batch()` and `get_batches_for_workspace()` delegating to `ProductionRuntime`
    - Add in-memory fallback for `get_batch()` when Postgres is unavailable
    - _Requirements: 11.6, 11.7_

  - [ ]* 20.4 Write property test for `add_pair()` idempotency
    - **Property 8: SPPE `add_pair()` is idempotent on duplicate `pair_id`**
    - Call `add_pair(pair, workspace_id)` twice; assert same `batch_id`; assert `production.save_sppe_pair` called twice but no exception raised
    - **Validates: Requirements 11.4**

- [ ] 21. Wire `SPPEPairGenerated` domain event and verify `eventing_session=None` degrades gracefully
  - Confirm the `SPPEPairGenerated` event is constructed with fields: `aggregate_id=str(pair.pair_id)`, `pair_id`, `workspace_id`, `semantic_ir_hash`, `output_hash`, `quality_score`, `signal_efficiency`, `provenance`, `batch_id`
  - Verify that when `eventing_session=None`, `add_pair()` completes without calling `EventStore.append()` and without error
  - Verify that when `EventStore.append()` raises, `add_pair()` logs the error and returns `batch_id` normally
  - _Requirements: 12.1, 12.2, 12.3, 12.4_

  - [ ] 21.1 Verify `SPPEPairGenerated` event field mapping in `add_pair()`
    - Inspect the `SPPEPairGenerated` dataclass from `eventing/events.py`; confirm all required fields are populated; fix any missing mappings
    - _Requirements: 12.1, 12.2_

  - [ ]* 21.2 Write property test for SPPE event emission parity
    - **Property 9: SPPE event emission parity**
    - Call `add_pair(pair, workspace_id)` with a mock `eventing_session`; assert exactly one `SPPEPairGenerated` event appended with `aggregate_id == str(pair.pair_id)` and `quality_score == pair.quality_score`
    - **Validates: Requirements 12.1, 12.2**

  - [ ]* 21.3 Write unit test for `eventing_session=None` and `EventStore.append()` exception paths
    - Test `eventing_session=None` → no call to `EventStore`; test `EventStore.append()` raises → `batch_id` still returned normally
    - _Requirements: 12.3, 12.4_

- [ ] 22. Final checkpoint — all four gaps complete
  - Run all tests across Gap 1–4
  - Confirm `JimsAIPipeline.run()` produces `PipelineResponse.response`, `confidence`, and `layer_results` identical to pre-refactoring behavior
  - Confirm `SPPEBatchStore` method signatures and return types match the original implementation
  - Confirm `OPENSUBTITLES_API_KEY` absent does not break agent startup
  - Ask the user if any final questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery
- Each task references specific requirements for traceability
- Property tests use `hypothesis` (already a dev dependency per the design)
- Checkpoints at tasks 7, 12, 17, and 22 ensure incremental validation between gaps
- The `ReEmbeddingWorker` is registered on `JimsAIPipeline` but NOT started — the app host is responsible for calling `asyncio.create_task(pipeline.reembedding_worker.start())`
- All SQL in new `SupabasePostgresStore` methods must use parameterized queries — no user-supplied strings interpolated directly
- Gap 3 is purely structural refactoring: no observable behavior should change

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "8.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "8.2", "13.1", "13.2", "18.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.1", "4.1", "5.1", "9.1", "9.2", "13.3", "14.1", "14.2", "18.2", "19.1", "19.2"] },
    { "id": 3, "tasks": ["3.2", "4.2", "5.2", "6.1", "9.3", "10.1", "14.3", "15.1", "15.2", "15.3", "19.3", "19.4", "20.1"] },
    { "id": 4, "tasks": ["6.2", "10.2", "10.3", "11.1", "16.1", "16.2", "20.2", "20.3"] },
    { "id": 5, "tasks": ["11.2", "16.3", "16.4", "16.5", "20.4", "21.1"] },
    { "id": 6, "tasks": ["21.2", "21.3"] }
  ]
}
```
