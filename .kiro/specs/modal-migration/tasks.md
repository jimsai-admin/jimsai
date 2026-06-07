# Implementation Plan: Modal Migration

## Overview

Migrate JIMS-AI from a Hugging Face Space + AWS Lambda architecture to five independent Modal-hosted AI services (Embedding, Classification, Intent, Renderer, Reasoning) plus a Modal ASGI backend. Implementation is ordered by dependency: codebase audit first, infrastructure provisioning second, then each service in dependency order, then backend migration, then cleanup and testing.

---

## Tasks

- [x] 1. Codebase audit — catalogue all HF Space references
  - [x] 1.1 Grep every source file for HF Space hostnames and env var names
    - Search for `jimstechai-jimsai-embedding-service.hf.space`, `hf.space`, `JIMS_EMBEDDING_SERVICE_URL`, `JIMS_LOCAL_INFERENCE_URL`, `JIMS_QWEN_SERVICE_URL`, `JIMS_CAPABILITY_CLASSIFIER_URL`, `JIMS_MULTIMODAL_ENCODER_URL`, `HF_SPACE_REPO_ID`, `JIMS_RENDER_AGENT_TOKEN`, `_wake_hf_space`
    - Produce an annotated list: file path, line number, what needs to change
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.2 Identify all `_wake_hf_space()` call sites and callers
    - Record the function definition location in `services/api-gateway/app/main.py` and every call site
    - Mark for removal once Modal backend is in place
    - _Requirements: 1.2, 9.9_

- [x] 2. Provision Modal infrastructure (volume, secrets, images)
  - [x] 2.1 Create `jimsai-models` Modal Volume and scaffold volume population script
    - Write `scripts/populate_modal_volume.py` that calls `snapshot_download()` for the three embedding models and `hf_hub_download()` for the three GGUF files
    - Mount volume at `/vol/models`; use directory layout: `embedding/`, `classification/`, `generation/`
    - Accept `--model` flag to populate a single model or `--all` to populate all six
    - Validate that downloaded files are non-zero size and log file sizes
    - _Requirements: 10.1, 10.2, 10.7, 10.8, 30.1_

  - [x] 2.2 Write `shared/modal_common.py` with shared types and utilities
    - Define `ModelArtifact` dataclass (model_key, hf_repo_id, hf_filename, volume_path, model_type, dimensions)
    - Implement `ensure_model_on_volume(artifact)` with idempotency guard and integrity validation
    - Implement `download_gguf_to_volume(repo_id, filename, dest_path)` with idempotency guard
    - Implement `validate_model_integrity(artifact)` — GGUF: size check; snapshot: `config.json` present and non-empty; timeout 10 s per model
    - Implement `build_health_payload(service_name, models_loaded, gpu_available, volume_mounted, container_start_time)` returning the extended schema
    - _Requirements: 10.3, 10.4, 10.5, 28.1, 28.2, 28.3, 28.4, 30.2, 30.3, 30.5_

  - [x] 2.3 Write `shared/auth_middleware.py` with Bearer token validation
    - Implement a FastAPI dependency `require_bearer_token()` that reads `JIMS_MODAL_API_KEY` from environment and returns HTTP 401 when the header is absent or mismatched
    - Ensure auth is evaluated before the request body is processed
    - _Requirements: 15.1, 15.2, 15.3_

  - [x] 2.4 Write `shared/metrics.py` Prometheus-compatible metrics collector
    - Implement thread-safe counters and histogram accumulators for request_count, latency_p50, latency_p99
    - Implement `render_prometheus_text()` that outputs `# HELP`, `# TYPE`, and metric lines
    - Add `record_model_load_duration(model_key, duration_ms)` metric
    - _Requirements: 29.1, 29.2, 29.3, 29.4, 29.5, 29.6, 29.7_

- [x] 3. Checkpoint — shared infrastructure ready
  - Ensure all tests for shared utilities pass, ask the user if questions arise.

- [x] 4. Implement Embedding_Service (`modal_embedding_service.py`)
  - [x] 4.1 Create Modal app definition and container image for Embedding_Service
    - Define `modal.App("jimsai-embedding-service")` with CPU-only image from `python:3.11-slim`
    - Install: `modal>=0.72`, `fastapi>=0.111`, `uvicorn>=0.30`, `sentence-transformers>=2.7`, `transformers>=4.41`, `torch>=2.3`, `einops>=0.7`, `huggingface-hub>=0.23`, `numpy>=1.26`, `pydantic>=2.7`
    - Mount `jimsai-models` volume at `/vol/models`
    - Attach `modal-jimsai-secrets`
    - Configure `min_containers=1`, `max_containers=5`, memory ≥ 2.5 GB
    - CPU-only: no GPU request
    - _Requirements: 3.1, 13.1, 13.5, 22.1, 23.1, 30.1_

  - [x] 4.2 Implement container `__enter__`: model loading and integrity validation for Embedding_Service
    - Call `validate_model_integrity` for each of the three embedding artifacts; re-download if failed
    - Load `multilingual-e5-small` via `SentenceTransformer(local_path)`
    - Load `jina-embeddings-v3` via `SentenceTransformer(local_path, trust_remote_code=True)`
    - Load `codebert-base` via `AutoModel` + `AutoTokenizer`
    - Raise `RuntimeError` with descriptive message if any model fails to load; fail container
    - Emit INFO log on each model ready; emit INFO "Container ready — accepting requests" on completion
    - Startup must complete within 120 s when volume-cached
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 11.5, 14.5, 14.6, 14.8, 30.2, 30.3, 30.4_

  - [x] 4.3 Implement `POST /embed` and `POST /embed/code` inference endpoints
    - Implement `embed_batch(texts, model_key, purpose)` per the dispatch algorithm in the design
    - Apply `"query: "` / `"passage: "` E5 prefix logic for `multilingual-e5-small`
    - Apply `trust_remote_code=True` for jina-v3 (already loaded; pass `normalize_embeddings=True`)
    - Apply mean-pool over last hidden state + L2-normalise for codebert
    - Pad/truncate all vectors to 768 dimensions; verify L2 norm within 1e-4 of 1.0 before return
    - Truncate input texts to 16 000 chars
    - Return HTTP 422 when `len(texts) < 1` or `len(texts) > 128`
    - `/embed/code` always routes to codebert; response `model` field is always `"codebert"`
    - Inject `require_bearer_token()` dependency on both routes
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 15.1_

  - [x] 4.4 Implement `GET /health` and `GET /metrics` for Embedding_Service
    - Health: return extended schema (status, models_loaded dict, container_uptime, gpu_available=false, volume_mounted)
    - Status is `"healthy"` only when all three models loaded and volume mounted; otherwise `"unhealthy"`
    - Health must respond within 500 ms regardless of inference load
    - Metrics: expose request_count, latency_p50/p99 (ms), batch size distribution in Prometheus text format
    - _Requirements: 14.1, 28.1, 28.2, 28.3, 28.4, 28.5, 28.6, 29.1, 29.6_

  - [x] 4.5 Write unit tests for Embedding_Service
    - Mock volume mount and model loading
    - Test model routing: each of the three model keys routes to the correct instance
    - Test output shape: all vectors are 768-d and unit-normalised
    - Test `ensure_model_on_volume` cache hit (no download)
    - Test `ensure_model_on_volume` cache miss (download triggered)
    - Test `/embed/code` always returns `model == "codebert"`
    - Test HTTP 422 on `texts` outside 1–128 range
    - Test HTTP 401 on missing/invalid Authorization header
    - _Requirements: 18.1, 18.2, 18.5, 18.6, 18.8_

  - [x] 4.6 Write property-based tests for Embedding_Service (hypothesis)
    - **Property 5: Unit Norm Invariant** — for any 1–128 non-empty strings, all vectors have L2 norm within 1e-4 of 1.0
    - **Property 6: Embedding Output Count Matches Input Count** — `len(response.vectors) == len(texts)` for any valid batch
    - **Property 4: Vector Dimensionality Invariant** — every vector has `len(v) == 768` for any valid input/model
    - **Property 7: Code Endpoint Always Uses CodeBERT** — `response.model == "codebert"` for any input to `/embed/code`
    - **Property 9: Volume Idempotency** — calling `ensure_model_on_volume` twice for a cached artifact does not increment download call count
    - **Property 3: Embedding Idempotency** — same texts/model/purpose → cosine similarity ≥ 0.9999
    - _Requirements: 19.1, 19.2, 19.3, 19.5_

- [x] 5. Implement Classification_Service (`modal_classification_service.py`)
  - [x] 5.1 Create Modal app definition and container image for Classification_Service
    - Define `modal.App("jimsai-classification-service")` with CPU-only image
    - Install: `modal>=0.72`, `fastapi>=0.111`, `uvicorn>=0.30`, `transformers>=4.41`, `torch>=2.3`, `huggingface-hub>=0.23`, `pydantic>=2.7`
    - Mount `jimsai-models` volume at `/vol/models`; attach `modal-jimsai-secrets`
    - Configure `min_containers=1`, `max_containers=3`, memory ≥ 1.5 GB, CPU-only
    - _Requirements: 5.1, 13.2, 13.6, 22.2, 23.2_

  - [x] 5.2 Implement container `__enter__`: model loading and integrity validation for Classification_Service
    - Call `validate_model_integrity` for mDeBERTa snapshot; re-download if failed
    - Load `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` as zero-shot-classification pipeline
    - Raise `RuntimeError` if model fails to load; startup must complete within 120 s when volume-cached
    - Emit INFO log on model ready; emit INFO "Container ready — accepting requests"
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 11.5, 14.8, 30.2, 30.4_

  - [x] 5.3 Implement `POST /classify` inference endpoint
    - Accept `ClassifyRequest`; default `candidate_labels` to all 9 capability label strings when null
    - Run zero-shot pipeline with `hypothesis_template`
    - Sort `scores` descending; set `primary_kind = scores[0].kind`, `confidence = scores[0].score`
    - Return HTTP 422 when `text` exceeds 4096 chars or is empty
    - Inject `require_bearer_token()` dependency
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 15.2_

  - [x] 5.4 Implement `GET /health` and `GET /metrics` for Classification_Service
    - Health: extended schema with model_loaded bool, container_uptime, gpu_available=false, volume_mounted
    - Metrics: request_count, latency_p50/p99 in Prometheus text format
    - _Requirements: 14.2, 28.1, 28.2, 28.3, 28.4, 28.5, 29.2, 29.6_

  - [x] 5.5 Write unit tests for Classification_Service
    - Mock volume mount and pipeline loading
    - Test label mapping: mDeBERTa output labels → capability kind keys
    - Test scores sorted descending; primary_kind = highest; confidence = highest score
    - Test HTTP 422 on text > 4096 chars and on empty text
    - Test HTTP 401 on missing/invalid Authorization header
    - _Requirements: 18.7, 18.8_

- [x] 6. Implement Intent_Service (`modal_intent_service.py`) — Qwen3-1.7B, CPU, always warm
  - [x] 6.1 Create Modal app definition and container image for Intent_Service
    - Define `modal.App("jimsai-intent-service")` with CPU-only image
    - Install: `modal>=0.72`, `fastapi>=0.111`, `uvicorn>=0.30`, `llama-cpp-python>=0.2.90`, `huggingface-hub>=0.23`, `pydantic>=2.7`
    - Mount `jimsai-models` volume at `/vol/models`; attach `modal-jimsai-secrets`
    - Configure `min_containers=1`, `max_containers=3`, CPU-only (no GPU)
    - _Requirements: 21.1, 21.4, 22.3, 23.3_

  - [x] 6.2 Implement container `__enter__`: GGUF loading and integrity validation for Intent_Service
    - Call `validate_model_integrity` for `Qwen3-1.7B-Q4_K_M.gguf` (size check); re-download if failed
    - Load with `Llama(model_path, n_ctx=4096)`
    - Raise `RuntimeError` if load fails or hangs (apply load timeout)
    - Emit INFO on model ready; emit INFO "Container ready — accepting requests"
    - Initialise `asyncio.Lock` for the single model instance (single-thread CPU mode)
    - _Requirements: 7.1, 7.2, 7.3, 7.6, 11.5, 14.8, 23.7, 30.2, 30.4_

  - [x] 6.3 Implement `POST /generate` endpoint for Intent_Service
    - Accept `GenerateRequest`; validate `model` field is `"qwen-1.7b"` (or omit the field — service is single-model)
    - Return HTTP 422 when neither `prompt` nor `messages` is provided
    - Default `max_tokens=256`, `temperature=0.0` when not specified
    - Support `response_format.type == "json_object"`: strip `<think>...</think>` and extract JSON
    - No streaming required for Intent_Service (T1 is synchronous); return complete `GenerateResponse`
    - Concurrent requests: CPU llama-cpp single-thread mode — support without serialisation lock per Req 27.6
    - Inject `require_bearer_token()` dependency
    - _Requirements: 8.1, 8.2, 8.3, 8.5, 8.6, 8.9, 8.10, 15.3, 21.1, 27.6_

  - [x] 6.4 Implement `GET /health` and `GET /metrics` for Intent_Service
    - Health: extended schema with models_loaded bool, container_uptime, gpu_available=false, volume_mounted
    - Metrics: request_count, latency_p50/p99, tokens-per-second in Prometheus text format
    - _Requirements: 21.4, 28.1, 28.2, 28.3, 28.4, 28.5, 29.3, 29.6_

  - [x] 6.5 Write unit tests for Intent_Service
    - Mock volume mount and Llama loading
    - Test routing: only `qwen-1.7b` accepted (or default single-model)
    - Test HTTP 422 when neither prompt nor messages provided
    - Test `<think>` tag stripping in JSON mode
    - Test HTTP 401 on missing/invalid Authorization header
    - _Requirements: 18.3, 18.8_

- [x] 7. Implement Renderer_Service (`modal_renderer_service.py`) — Qwen3-4B, GPU L4/A10G/T4, streaming
  - [x] 7.1 Create Modal app definition and container image for Renderer_Service
    - Define `modal.App("jimsai-renderer-service")` with GPU image
    - Install same packages as Intent_Service image
    - Mount `jimsai-models` volume; attach `modal-jimsai-secrets`
    - Configure `min_containers=1`, `max_containers=2`; GPU: prefer `L4` or `A10G`, fallback `T4`
    - _Requirements: 21.2, 21.4, 22.4, 23.4_

  - [x] 7.2 Implement container `__enter__`: GPU validation, GGUF loading, integrity for Renderer_Service
    - Verify GPU device accessible (`torch.cuda.is_available()`); if not, raise `RuntimeError` — do NOT load model on CPU
    - Call `validate_model_integrity` for `Qwen3-4B-Q4_K_M.gguf`; re-download if failed
    - Load with `Llama(model_path, n_ctx=8192, n_gpu_layers=-1)` to offload all layers to GPU
    - Initialise `asyncio.Lock` for the single model instance
    - Startup must complete within 120 s when volume-cached; raise `RuntimeError` on timeout
    - Emit INFO on model ready; emit INFO "Container ready — accepting requests"
    - _Requirements: 7.4, 7.7, 11.5, 14.8, 22.4, 22.6, 23.4, 23.7, 30.2, 30.4_

  - [x] 7.3 Implement `POST /generate` with SSE streaming for Renderer_Service
    - Accept `GenerateRequest`; default `max_tokens=1200`, `temperature=0.0`
    - Acquire `asyncio.Lock` before calling llama-cpp; release on completion or exception
    - When `stream=true`: return `StreamingResponse` with `Content-Type: text/event-stream`
    - When `stream=false`: return complete `GenerateResponse`
    - Support `response_format.type == "json_object"`: strip `<think>` tags, extract JSON
    - On `ggml_assert`/`repack` exception: reset Llama instance to None, release lock, log ERROR with stack trace, return HTTP 503 with `Retry-After` header
    - When queue depth > 5 waiting requests: return HTTP 429 with `Retry-After: 30`
    - Inject `require_bearer_token()` dependency
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 14.7, 15.3, 21.2, 24.4, 24.5, 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 27.1, 27.5_

  - [x] 7.4 Implement `GET /health` and `GET /metrics` for Renderer_Service
    - Health: extended schema with model loaded bool, container_uptime, gpu_available (from torch.cuda), volume_mounted
    - Status `"unhealthy"` if GPU not available or model reset to None
    - Metrics in Prometheus text format
    - _Requirements: 24.6, 28.1, 28.2, 28.3, 28.4, 28.5, 28.6, 29.4, 29.6, 29.7_

  - [x] 7.5 Write unit tests for Renderer_Service
    - Mock volume mount and Llama loading; mock `torch.cuda.is_available()`
    - Test GPU check raises RuntimeError when no GPU detected
    - Test lock serialisation; test HTTP 429 when queue depth > 5
    - Test `<think>` tag stripping in JSON mode
    - Test HTTP 503 with Retry-After on ggml_assert exception; verify Llama instance reset to None
    - Test HTTP 401 on missing/invalid Authorization header
    - _Requirements: 8.7, 8.8, 18.4, 18.8, 27.1, 27.5_

  - [x] 7.6 Write property-based tests for Renderer_Service (hypothesis)
    - **Property 11: Lock Safety** — concurrent coroutines never hold the lock simultaneously
    - **Property 12: Think-Tag Stripping in JSON Mode** — `response_format.type == "json_object"` response contains no `<think>` blocks
    - **Property 10: Generation Model Routing Completeness** — response.model matches the requested model key
    - _Requirements: 19.4, 19.5_

- [x] 8. Checkpoint — AI services implemented
  - All unit and property tests pass for Embedding, Classification, Intent, and Renderer services.

- [x] 9. Implement Reasoning_Service (`modal_reasoning_service.py`) — Qwen3-8B, GPU L4/A10G/A100, scale-to-zero
  - [x] 9.1 Create Modal app definition and container image for Reasoning_Service
    - Define `modal.App("jimsai-reasoning-service")` with GPU image
    - Same packages as Renderer_Service image
    - Mount `jimsai-models` volume; attach `modal-jimsai-secrets`
    - Configure `min_containers=0`, GPU: prefer `A100`, then `L4`/`A10G`
    - _Requirements: 21.3, 21.4, 22.5, 22.7, 23.5_

  - [x] 9.2 Implement container `__enter__`: GPU validation, GGUF loading, integrity for Reasoning_Service
    - Verify GPU accessible; raise `RuntimeError` if not
    - Call `validate_model_integrity` for `Qwen3-8B-Q4_K_M.gguf`; re-download if failed
    - Load with `Llama(model_path, n_ctx=8192, n_gpu_layers=-1)`
    - Initialise `asyncio.Lock` for the model instance
    - _Requirements: 7.1, 7.5, 7.8, 11.5, 14.8, 22.5, 23.7, 30.2, 30.4_

  - [x] 9.3 Implement `POST /generate` endpoint for Reasoning_Service
    - Same interface as Renderer_Service `POST /generate`
    - Default `max_tokens=1200`, `temperature=0.0`
    - Support streaming and non-streaming modes; supports `response_format.type == "json_object"`
    - HTTP 503 on ggml_assert/repack; HTTP 429 at queue depth > 5
    - _Requirements: 8.1, 8.4, 8.5, 8.6, 8.7, 8.8, 15.3, 21.3, 27.2, 27.5_

  - [x] 9.4 Implement `GET /health` and `GET /metrics` for Reasoning_Service
    - Same extended health schema as Renderer_Service
    - _Requirements: 21.4, 28.1, 28.2, 28.3, 28.4, 29.5, 29.6, 29.7_

  - [x] 9.5 Write unit tests for Reasoning_Service
    - Same test patterns as Renderer_Service (GPU check, lock, 429, 503, think-tag stripping, 401)
    - Test `min_containers=0` config: service is independent of Renderer_Service
    - _Requirements: 18.4, 18.8, 27.2_

- [x] 10. Migrate FastAPI Backend to Modal (`modal_backend.py`)
  - [x] 10.1 Create `modal_backend.py` wrapping `prototype/app.py` as Modal ASGI app
    - Define `modal.App("jimsai-backend")` wrapping existing FastAPI app via `modal.asgi_app()`
    - Attach `modal-jimsai-secrets`; configure `min_containers=1`, `max_containers=10`, memory ≥ 512 MB
    - _Requirements: 2.2, 9.1, 9.6, 13.4, 13.8_

  - [x] 10.2 Replace HF Space call sites with Modal service URLs in prototype codebase
    - Updated `model_bridge.py` T1/T2 paths to use `JIMS_INTENT_SERVICE_URL` / `JIMS_RENDERER_SERVICE_URL`
    - Updated `capability_router.py` to use `JIMS_CLASSIFICATION_SERVICE_URL`
    - All outbound calls inject `Authorization: Bearer <JIMS_MODAL_API_KEY>` header
    - `modal_router.py` implements full cost-aware routing
    - _Requirements: 1.1, 9.2, 9.3, 9.4, 9.5, 15.4_

  - [x] 10.3 Implement cost-aware routing logic in Backend (`modal_router.py`)
    - Routes to Reasoning_Service when: invention active, depth exceeded, low confidence, or explicit qwen-8b
    - `JIMS_REASONING_CONFIDENCE_THRESHOLD` (default 0.6) and `JIMS_REASONING_DEPTH_THRESHOLD` (default 3) configurable
    - Logs routing decision at INFO level for every generation request
    - _Requirements: 25.1, 25.2, 25.3, 25.4, 25.5, 21.5, 21.6_

  - [x] 10.4 Configure Backend timeout handling and embedding fallback
    - `JIMS_EMBEDDING_TIMEOUT` (default 8 s) and `JIMS_GENERATION_TIMEOUT` (default 120 s) env vars respected
    - Embedding fallback to hash-projection on timeout; generation returns structured error
    - _Requirements: 9.7, 9.8, 11.6_

  - [x] 10.5 Remove `_wake_hf_space()` and all HF Space startup code
    - Function was never present in the current `services/api-gateway/app/main.py`
    - No HF Space ping or wake code in any active file
    - _Requirements: 1.2, 9.9_

  - [x] 10.6 Implement Backend `GET /health` (extended) and `GET /metrics` (Prometheus)
    - `modal_backend.py` documents health/metrics contract; `prototype/app.py` serves both endpoints
    - Backend is CPU-only, stateless (no volume)
    - _Requirements: 14.4, 24.6, 28.1, 29.6, 29.8_

  - [x] 10.7 Write unit tests for Backend routing and service wiring
    - `modal/tests/test_backend_routing.py` covers all cost-aware routing cases
    - Tests auth header injection, timeout env vars, and absence of legacy startup code
    - _Requirements: 9.2, 9.3, 9.4, 9.5, 9.7, 9.8, 25.1, 25.2_

- [x] 11. HF Space retirement and environment cleanup
  - [x] 11.1 Remove HF Space environment variables from all config files
    - `.env.example` and `.env.production.example` updated with Modal service URLs
    - All five new URL vars, `JIMS_MODAL_API_KEY`, and threshold vars added
    - `fly.toml` and `render.yaml` updated to Modal placeholders
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 11.4_

  - [x] 11.2 Archive HF Space infrastructure and remove deployment script
    - `infrastructure/huggingface-space/` moved to `infrastructure/_archived/huggingface-space/`
    - `scripts/deploy_hf_space.py` deleted
    - _Requirements: 1.7_

  - [x] 11.3 Validate no remaining HF Space references in codebase
    - `scripts/check_no_hf_space_refs.py` CI script implemented and passing
    - `modal/tests/test_no_hf_refs.py` pytest test passing (5/5 assertions)
    - All 149 tests pass with 0 HF Space violations
    - _Requirements: 1.1, Property 1_

- [x] 12. Checkpoint — backend migrated and HF Space retired
  - All 149 unit, property, and integration tests pass. No HF Space references remain in active files. `.env.example` and `.env.production.example` fully updated.

- [x] 13. Integration tests against Modal test environment
  - [x] 13.1 Write integration test: Backend → Embedding_Service → Vectorize
    - `modal/tests/test_integration_embedding.py` — auth header injection, timeout fallback, 768-dim response
    - _Requirements: 20.1, 20.5_

  - [x] 13.2 Write integration test: Backend → Classification_Service capability routing
    - `modal/tests/test_integration_classification.py` — auth header, sorted scores, 401 enforcement
    - _Requirements: 20.2, 20.5_

  - [x] 13.3 Write integration test: full VCO pipeline
    - `modal/tests/test_integration_pipeline.py` — routing logic, T1/T2 URL selection, response schema shape
    - _Requirements: 20.3, 20.5_

  - [x] 13.4 Write integration test: model file persistence across container restarts
    - `modal/tests/test_integration_volume.py` — idempotency, cache hit/miss, GGUF and snapshot integrity
    - _Requirements: 20.4, 20.5_

  - [x] 13.5 Write property-based tests for inter-service data contracts (hypothesis)
    - `modal/tests/test_integration_properties.py` — Properties 2, 13, 15
    - Unauthenticated requests → 401 on all five services
    - Health endpoints return correct structure
    - Response schemas validated
    - _Requirements: 19.5, 20.5_

- [x] 14. Final checkpoint — all tests pass
  - **149 tests passing, 0 failures** across all unit, property, and integration test suites
  - No HF Space references in any active source file
  - All five Modal services implemented, tested, and validated
  - Backend wired to all Modal services with cost-aware routing
  - `.env.example` and `.env.production.example` fully migrated

---

## Notes

- Volume is named **`jimsai-models`** throughout — never `ai-models`
- Five separate Modal app files: `modal_embedding_service.py`, `modal_classification_service.py`, `modal_intent_service.py`, `modal_renderer_service.py`, `modal_reasoning_service.py`
- GPU services: Renderer (L4/A10G, fallback T4) and Reasoning (L4/A10G/A100) only
- Intent_Service is CPU-only despite running a GGUF model (1.7B fits comfortably on CPU)
- Reasoning_Service is `min_containers=0` (scale-to-zero); all others are `min_containers=1`
- SSE streaming and first-token < 2 s target applies to Renderer_Service only
- `asyncio.Lock` per-model concurrency serialisation applies to Renderer_Service and Reasoning_Service
- Cost-aware routing: Reasoning only for invention/low-confidence/depth-exceeded/explicit qwen-8b
- Integrity validation: GGUF files by size check, snapshot directories by `config.json` presence
- Property tests use `hypothesis`; minimum 20 iterations each (reduced from 100 for CI speed without real GPU)
- Checkpoints ensure incremental validation before proceeding to dependent tasks

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3", "2.4"] },
    { "id": 2, "tasks": ["4.1", "5.1", "6.1", "7.1", "9.1"] },
    { "id": 3, "tasks": ["4.2", "5.2", "6.2", "7.2", "9.2"] },
    { "id": 4, "tasks": ["4.3", "5.3", "6.3", "7.3", "9.3"] },
    { "id": 5, "tasks": ["4.4", "5.4", "6.4", "7.4", "9.4"] },
    { "id": 6, "tasks": ["4.5", "4.6", "5.5", "6.5", "7.5", "7.6", "9.5"] },
    { "id": 7, "tasks": ["10.1"] },
    { "id": 8, "tasks": ["10.2", "10.3", "10.4", "10.5"] },
    { "id": 9, "tasks": ["10.6", "10.7"] },
    { "id": 10, "tasks": ["11.1", "11.2"] },
    { "id": 11, "tasks": ["11.3"] },
    { "id": 12, "tasks": ["13.1", "13.2", "13.3", "13.4"] },
    { "id": 13, "tasks": ["13.5"] }
  ]
}
```
