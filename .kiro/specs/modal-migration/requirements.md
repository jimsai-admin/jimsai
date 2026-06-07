# Requirements Document

## Introduction

This document specifies the requirements for the Modal Migration feature. JIMS-AI currently relies on a single Hugging Face Space (`jimstechai-jimsai-embedding-service.hf.space`) that hosts all AI model inference (embeddings, zero-shot classification, and GGUF generation), while the main FastAPI pipeline runs on AWS Lambda. The migration moves every AI model and the FastAPI backend to [Modal](https://modal.com), replacing the HF Space with five independent Modal-hosted AI services and migrating the Lambda-hosted FastAPI backend to a Modal ASGI app, all behind the same stable API surface the frontend already targets.

JIMS-AI is a memory-centric cognitive runtime whose primary goal is low-latency VCO generation, deterministic retrieval, persistent memory, and bounded language rendering. The Modal deployment must function as a permanent cognitive runtime — not a collection of serverless inference endpoints — optimised for fast first-token latency, low cold-start frequency, predictable performance, efficient GPU usage, cost-aware scaling, and production reliability.

---

## Glossary

- **Embedding_Service**: The Modal-hosted FastAPI application (`modal_embedding_service.py`) that serves all three embedding models on CPU.
- **Classification_Service**: The Modal-hosted FastAPI application (`modal_classification_service.py`) that serves the mDeBERTa zero-shot classifier on CPU.
- **Intent_Service**: The Modal-hosted FastAPI application (`modal_intent_service.py`) that serves Qwen3-1.7B (T1) on CPU, kept permanently warm.
- **Renderer_Service**: The Modal-hosted FastAPI application (`modal_renderer_service.py`) that serves Qwen3-4B (T2) on GPU, kept permanently warm.
- **Reasoning_Service**: The Modal-hosted FastAPI application (`modal_reasoning_service.py`) that serves Qwen3-8B on GPU, scaled to zero when idle.
- **Backend**: The Modal-hosted FastAPI ASGI application (`modal_backend.py`) that wraps the existing `prototype/app.py` and exposes the public `/v1/...` API surface.
- **Volume**: The Modal persistent network-attached storage volume named `jimsai-models`, mounted at `/vol/models` inside every AI service container.
- **Modal_Secrets**: The Modal Secrets object (`modal-jimsai-secrets`) that stores all sensitive configuration values.
- **HF_Space**: The retired Hugging Face Space (`jimstechai/jimsai-embedding-service`) that the migration replaces.
- **ModelArtifact**: A descriptor that identifies a model by its HuggingFace repo ID, volume path, and model type.
- **GGUF**: A binary model file format used by llama-cpp-python for quantised language model inference.
- **SentenceTransformer**: A Python class from the `sentence-transformers` library used to load and run the E5 and Jina embedding models.
- **Llama_Instance**: An in-memory `llama_cpp.Llama` object loaded from a GGUF file.
- **Bearer_Token**: The `JIMS_MODAL_API_KEY` value sent as an HTTP `Authorization: Bearer <token>` header on all inter-service requests.
- **Cold_Start**: The period from when Modal spawns a new container to when it has loaded all models and is ready to serve requests.
- **HF_Hub**: The HuggingFace model Hub (`huggingface.co`) used as the remote source for all model files.
- **VCO**: Verbalised Cognitive Output — the bounded language response produced by the T2 rendering path.
- **T1**: The intent/understanding tier, served by Qwen3-1.7B in the Intent_Service.
- **T2**: The rendering/generation tier, served by Qwen3-4B in the Renderer_Service.
- **First_Token_Latency**: The elapsed time from request receipt to emission of the first output token in a streaming response.

---

## Requirements

### Requirement 1: HF Space Retirement and URL Migration

**User Story:** As a system operator, I want all HF Space URLs and related environment variables removed from the codebase, so that the system no longer depends on the retired Hugging Face Space.

#### Acceptance Criteria

1. THE Backend SHALL replace every reference to `jimstechai-jimsai-embedding-service.hf.space` with the corresponding Modal service URL before the migration is considered complete.
2. THE Backend SHALL remove the `_wake_hf_space()` startup function from `services/api-gateway/app/main.py` and replace it with a Modal-compatible health probe.
3. THE Backend SHALL remove the environment variables `JIMS_EMBEDDING_SERVICE_URL` (HF value), `JIMS_LOCAL_INFERENCE_URL`, `JIMS_QWEN_SERVICE_URL`, `JIMS_CAPABILITY_CLASSIFIER_URL`, `JIMS_MULTIMODAL_ENCODER_URL`, `HF_SPACE_REPO_ID`, and the HF-specific `JIMS_RENDER_AGENT_TOKEN` from all configuration files.
4. THE Backend SHALL replace `JIMS_LOCAL_INFERENCE_URL` with `JIMS_GENERATION_SERVICE_URL` pointing to the Modal Generation Service URL.
5. THE Backend SHALL replace `JIMS_CAPABILITY_CLASSIFIER_URL` with `JIMS_CLASSIFICATION_SERVICE_URL` pointing to the Modal Classification Service URL.
6. THE Backend SHALL replace the HF-specific `JIMS_RENDER_AGENT_TOKEN` with `JIMS_MODAL_API_KEY` stored in Modal Secrets.
7. WHEN the migration is complete, THE Backend SHALL archive the `infrastructure/huggingface-space/jimsai-embedding-service/` directory and remove the `scripts/deploy_hf_space.py` deployment script.

---

### Requirement 2: Public API Surface Preservation

**User Story:** As a frontend developer, I want all existing `/v1/...` API routes to remain unchanged after the migration, so that no frontend code changes are required.

#### Acceptance Criteria

1. THE Backend SHALL expose every route listed in the design's interface section (`GET /health`, `GET /metrics`, `POST /v1/auth/signin`, `POST /v1/auth/signup`, `POST /v1/auth/refresh`, `POST /v1/query`, `POST /v1/training/ingest`, `POST /v1/feedback`, `POST /v1/review/action`, `POST /v1/sandbox/run`, `POST /v1/math/solve`, `GET /v1/training/dashboard`, `GET /v1/training/panels/{panel}/items`, `POST /v1/canvas/run`, `GET /v1/canvas/status/{session_id}`, `POST /v1/invention/run`, `GET /v1/invention/status/{session_id}`, `POST /v1/memory/insert`, `POST /v1/memory/update`, `POST /v1/memory/delete`, `POST /v1/memory/rollback`, `GET /v1/memory/stats`, `GET /v1/audit/events`, `GET /v1/chat/threads`, `GET /v1/chat/threads/{thread_id}/messages`, `DELETE /v1/chat/threads/{thread_id}`) with identical request and response schemas as before the migration.
2. THE Backend SHALL be reachable at a stable public HTTPS URL of the form `https://<org>--jimsai-backend.modal.run`.
3. WHEN a caller sends a valid request to any existing route, THE Backend SHALL route the request to the same handler logic that existed before the migration.

---

### Requirement 3: Embedding Service — Model Loading

**User Story:** As a system operator, I want all embedding models to load from the Modal Volume at container startup, so that no model re-downloads occur on warm starts.

#### Acceptance Criteria

1. WHEN the Embedding_Service container starts, THE Embedding_Service SHALL check for the presence of `multilingual-e5-small`, `jina-embeddings-v3`, and `codebert-base` model files under `/vol/models/embedding/` on the Volume.
2. IF a model directory is absent from the Volume, THEN THE Embedding_Service SHALL download the model from HF_Hub using `snapshot_download()` into the corresponding Volume path before accepting requests.
3. IF a model directory is already present on the Volume, THEN THE Embedding_Service SHALL load the model from the Volume path without any network I/O to HF_Hub.
4. WHEN all three embedding models are loaded into memory, THE Embedding_Service SHALL respond to `GET /health` with `{"status": "ok", "models_loaded": {...}}` within 120 seconds of container spawn (when models are volume-cached); IF model loading from the Volume exceeds 120 seconds, THEN THE Embedding_Service SHALL raise a `RuntimeError` and allow Modal to mark the container as failed.
5. IF any model fails to load during container startup, THEN THE Embedding_Service SHALL raise a `RuntimeError` with a descriptive message and allow Modal to mark the container as failed.
6. THE Embedding_Service SHALL use `trust_remote_code=True` when loading `jina-embeddings-v3`.
7. THE Embedding_Service SHALL require `HF_TOKEN` from Modal_Secrets when downloading models from HF_Hub.

---

### Requirement 4: Embedding Service — Inference

**User Story:** As a backend developer, I want the Embedding Service to produce normalised 768-dimensional vectors for any combination of model and input texts, so that the vector store receives consistent embeddings regardless of which model was used.

#### Acceptance Criteria

1. WHEN the Embedding_Service receives `POST /embed` with `texts` (1–128 strings) and a valid `model` value (`"multilingual-e5-small"`, `"jina-v3"`, or `"codebert"`), THE Embedding_Service SHALL return an `EmbedResponse` containing one vector per input text.
2. THE Embedding_Service SHALL return vectors of exactly 768 dimensions for all three embedding models.
3. THE Embedding_Service SHALL return vectors with L2 norm within `1e-4` of `1.0` (unit-normalised) for all three embedding models.
4. WHEN `model` is `"multilingual-e5-small"` and `purpose` is `"query"`, THE Embedding_Service SHALL prepend `"query: "` to each input text before encoding.
5. WHEN `model` is `"multilingual-e5-small"` and `purpose` is `"passage"` or `"document"`, THE Embedding_Service SHALL prepend `"passage: "` to each input text before encoding.
6. WHEN the Embedding_Service receives `POST /embed/code`, THE Embedding_Service SHALL use the `codebert-base` model regardless of any `model` field in the request.
7. THE Embedding_Service SHALL apply mean-pooling over the last hidden state and L2-normalise the result when encoding with `codebert-base`.
8. IF the request contains fewer than 1 or more than 128 texts, THEN THE Embedding_Service SHALL return HTTP 422 with a validation error.
9. WHEN called with the same input texts, model, and purpose, THE Embedding_Service SHALL return vectors with pairwise cosine similarity ≥ 0.9999 (deterministic within floating-point tolerance).
10. THE Embedding_Service SHALL truncate each input text to 16 000 characters before encoding when the input exceeds that length.

---

### Requirement 5: Classification Service — Model Loading

**User Story:** As a system operator, I want the mDeBERTa classifier to load from the Modal Volume at container startup, so that classification requests are served without cold-start model downloads.

#### Acceptance Criteria

1. WHEN the Classification_Service container starts, THE Classification_Service SHALL check for `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` model files under `/vol/models/classification/` on the Volume.
2. IF the model directory is absent from the Volume, THEN THE Classification_Service SHALL download it from HF_Hub using `snapshot_download()` before accepting requests.
3. IF the model directory is already present on the Volume, THEN THE Classification_Service SHALL load the model without network I/O.
4. WHEN the model is loaded, THE Classification_Service SHALL respond to `GET /health` with `{"status": "ok", "model_loaded": true}` within 120 seconds of container spawn (when volume-cached); IF model loading from the Volume exceeds 120 seconds, THEN THE Classification_Service SHALL raise a `RuntimeError` and allow Modal to mark the container as failed.
5. IF the model fails to load, THEN THE Classification_Service SHALL raise a `RuntimeError` and allow Modal to mark the container as failed.

---

### Requirement 6: Classification Service — Inference

**User Story:** As a capability router, I want the Classification Service to rank capability labels for any query text, so that the backend can route requests to the right pipeline.

#### Acceptance Criteria

1. WHEN the Classification_Service receives `POST /classify` with a non-empty `text` field, THE Classification_Service SHALL run zero-shot classification using the `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` model and return a `ClassifyResponse`.
2. THE Classification_Service SHALL default to classifying against all 9 capability label strings when `candidate_labels` is `null`.
3. THE Classification_Service SHALL return a `scores` list sorted in descending order by score.
4. THE Classification_Service SHALL populate `primary_kind` with the label that has the highest score.
5. THE Classification_Service SHALL populate `confidence` with the score of `primary_kind`, which SHALL always equal the highest score in the `scores` list.
6. IF `text` exceeds 4096 characters, THEN THE Classification_Service SHALL return HTTP 422 with a validation error.
7. THE Classification_Service SHALL use `hypothesis_template` from the request when provided, and default to `"This request is about {}."` otherwise.

---

### Requirement 7: Generation Service — Model Loading

**User Story:** As a system operator, I want all three Qwen3 GGUF files to load from the Modal Volume at container startup, so that generation requests can be served without downloading large model files on every start.

#### Acceptance Criteria

1. WHEN the Generation_Service container starts, THE Generation_Service SHALL check for `Qwen3-1.7B-Q4_K_M.gguf`, `Qwen3-4B-Q4_K_M.gguf`, and `Qwen3-8B-Q4_K_M.gguf` under `/vol/models/generation/` on the Volume.
2. IF a GGUF file is absent from the Volume, THEN THE Generation_Service SHALL download it from HF_Hub using `hf_hub_download()` to the Volume path before accepting requests.
3. IF a GGUF file is already present on the Volume, THEN THE Generation_Service SHALL load it without any network I/O.
4. WHEN all three GGUF models are loaded, THE Generation_Service SHALL respond to `GET /health` with `{"status": "ok", "models": {"qwen-1.7b": true, "qwen-4b": true, "qwen-8b": true}}` within 120 seconds of container spawn (when volume-cached); IF model loading from the Volume exceeds 120 seconds, THEN THE Generation_Service SHALL raise a `RuntimeError` and allow Modal to mark the container as failed.
5. IF any GGUF file fails to load or if a load operation hangs without completing, THEN THE Generation_Service SHALL raise a `RuntimeError` (treating hangs as failures via a load timeout) and allow Modal to mark the container as failed; a partial success where some models loaded SHALL NOT prevent container failure.
6. THE Generation_Service SHALL load `Qwen3-1.7B-Q4_K_M.gguf` with `n_ctx=4096`.
7. THE Generation_Service SHALL load `Qwen3-4B-Q4_K_M.gguf` with `n_ctx=8192`.
8. THE Generation_Service SHALL load `Qwen3-8B-Q4_K_M.gguf` with `n_ctx=8192`.

---

### Requirement 8: Generation Service — Inference

**User Story:** As a backend developer, I want the Generation Service to route generation requests to the correct Qwen3 model and return structured responses, so that each pipeline tier gets the right capability/cost trade-off.

#### Acceptance Criteria

1. WHEN the Generation_Service receives `POST /generate` with `model` set to `"qwen-1.7b"`, `"qwen-4b"`, or `"qwen-8b"`, THE Generation_Service SHALL route the request to the corresponding Llama_Instance and return a `GenerateResponse`.
2. THE Generation_Service SHALL accept either `prompt` (single-turn) or `messages` (chat-style) as the input; at least one MUST be non-null.
3. IF neither `prompt` nor `messages` is provided, THEN THE Generation_Service SHALL return HTTP 422 with a validation error.
4. WHEN `stream` is `true`, THE Generation_Service SHALL return a `StreamingResponse` yielding SSE lines containing incremental content.
5. WHEN `stream` is `false`, THE Generation_Service SHALL return a complete `GenerateResponse` with `response`, `model`, `usage`, and `finish_reason` fields.
6. WHEN `response_format.type` is `"json_object"`, THE Generation_Service SHALL strip all `<think>...</think>` blocks from the raw model output and extract the outer JSON object before returning.
7. THE Generation_Service SHALL serialise concurrent requests to the same Llama_Instance using a per-model `asyncio.Lock`, so that no two coroutines hold the same model's lock simultaneously.
8. IF llama-cpp raises a `ggml_assert` or `repack` exception during inference, THEN THE Generation_Service SHALL reset the affected Llama_Instance to `None`, release the lock, log the exception at ERROR level with the full stack trace, and return HTTP 503 with a `Retry-After` header.
9. THE Generation_Service SHALL use `temperature=0.0` as the default when `temperature` is not specified in the request.
10. THE Generation_Service SHALL use `max_tokens=256` as the default for `"qwen-1.7b"` and `max_tokens=1200` as the default for `"qwen-4b"` and `"qwen-8b"` when `max_tokens` is not specified.

---

### Requirement 9: FastAPI Backend — Modal Hosting

**User Story:** As a system operator, I want the FastAPI backend to run as a Modal ASGI app, so that it benefits from Modal's scaling, warm containers, and integrated secrets management without requiring AWS Lambda.

#### Acceptance Criteria

1. THE Backend SHALL be deployed using `modal.asgi_app()` wrapping the existing `prototype/app.py` FastAPI application; deployment SHALL be blocked until all container configuration requirements (including `min_containers`, `max_containers`, memory allocation, and secrets attachment) are validated.
2. THE Backend SHALL replace calls to `JIMS_EMBEDDING_SERVICE_URL` with HTTP calls to the Modal Embedding Service URL (`https://<org>--jimsai-embedding-service.modal.run`).
3. THE Backend SHALL replace calls to the HF-space-based generation URL with HTTP calls to the Modal Generation Service URL (`https://<org>--jimsai-generation-service.modal.run`).
4. THE Backend SHALL replace calls to the HF-space-based classification URL with HTTP calls to the Modal Classification Service URL (`https://<org>--jimsai-classification-service.modal.run`).
5. THE Backend SHALL inject the `Authorization: Bearer <JIMS_MODAL_API_KEY>` header on all outbound HTTP calls to the three Modal AI services.
6. THE Backend SHALL configure `min_containers=1` and `max_containers=10` for the Backend container to enable stateless ASGI scaling.
7. IF an HTTP call to the Embedding_Service exceeds 8 seconds, THEN THE Backend SHALL fall back to hash-projection embeddings and continue serving the original request.
8. IF an HTTP call to the Generation_Service exceeds 120 seconds, THEN THE Backend SHALL return a structured error response to the caller.
9. THE Backend SHALL remove all code that calls `_wake_hf_space()` or otherwise pings the HF Space at startup.

---

### Requirement 10: Modal Volume — Model Storage

**User Story:** As a system operator, I want all model files to be stored on a persistent Modal Volume, so that container restarts and scale-out events do not re-download model files from HuggingFace Hub.

#### Acceptance Criteria

1. THE Volume SHALL be named `ai-models` and mounted at `/vol/models` inside every AI service container.
2. THE Volume SHALL store embedding models under `/vol/models/embedding/`, the classification model under `/vol/models/classification/`, and GGUF files under `/vol/models/generation/`.
3. WHEN a model file is successfully downloaded to the Volume, THE Volume SHALL make that file available to all subsequent containers without re-downloading.
4. THE Embedding_Service SHALL call `ensure_model_on_volume` for each ModelArtifact before loading, ensuring volume writes are idempotent — calling the function twice for a cached artifact SHALL trigger no additional network I/O.
5. THE Generation_Service SHALL call `download_gguf_to_volume` idempotently — if the GGUF file already exists at `dest_path`, the function SHALL return the existing path without downloading.
6. IF the Volume cannot be mounted at container startup, THEN THE affected service SHALL fail its health check immediately — before container startup completes — and allow Modal to retry container spawn.
7. THE Embedding_Service SHALL use `snapshot_download()` (full model directory) for all three embedding models.
8. THE Generation_Service SHALL use `hf_hub_download()` (single-file download) for each GGUF file.

---

### Requirement 11: Environment Variables and Secrets Management

**User Story:** As a security engineer, I want all sensitive configuration to be stored exclusively in Modal Secrets, so that credentials are never present in source code, environment files committed to version control, or container environment variables.

#### Acceptance Criteria

1. THE Modal_Secrets object SHALL store `JIMS_MODAL_API_KEY`, `HF_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`, `NEO4J_URI`, `NEO4J_PASSWORD`, `CF_VECTORIZE_API_TOKEN`, `CF_R2_ACCESS_KEY`, `CF_R2_SECRET_KEY`, and `GROQ_API_KEY`.
2. THE Backend SHALL reference all secrets exclusively via the Modal Secrets injection mechanism, not via hardcoded values in source files.
3. WHEN any of the three AI services needs `HF_TOKEN`, THE service SHALL obtain it from Modal_Secrets at container startup.
4. THE Backend SHALL update `.env.example` and `.env.production.example` to replace the seven retired HF Space environment variables with the three new Modal service URL variables (`JIMS_EMBEDDING_SERVICE_URL`, `JIMS_GENERATION_SERVICE_URL`, `JIMS_CLASSIFICATION_SERVICE_URL`).
5. IF a required secret is absent from Modal_Secrets at container startup, THEN THE affected service SHALL fail with a descriptive `RuntimeError` before accepting requests, regardless of which specific secrets the service uses.
6. THE Backend SHALL configure `JIMS_EMBEDDING_TIMEOUT` and `JIMS_GENERATION_TIMEOUT` as configurable environment values (not hardcoded), defaulting to 8 seconds and 120 seconds respectively.
7. WHEN all required secrets are validated successfully at container startup, THE affected service SHALL emit a structured log entry at INFO level confirming that secrets validation passed.

---

### Requirement 12: Performance — Latency Targets

**User Story:** As a product owner, I want all AI service calls to meet defined latency targets on warm containers, so that the user experience is not degraded relative to the previous architecture.

#### Acceptance Criteria

1. WHILE the Embedding_Service container is warm, THE Embedding_Service SHALL return a single-text embedding using `multilingual-e5-small` with P50 latency below 50 ms.
2. WHILE the Embedding_Service container is warm, THE Embedding_Service SHALL return a 128-text batch embedding with P50 latency below 500 ms and P99 latency below 2 seconds.
3. WHILE the Classification_Service container is warm, THE Classification_Service SHALL return a classification result with P50 latency below 800 ms and P99 latency below 3 seconds.
4. WHILE the Generation_Service container is warm, THE Generation_Service SHALL return a `qwen-1.7b` completion (256 tokens) with P50 latency below 5 seconds and P99 latency below 15 seconds.
5. WHILE the Generation_Service container is warm, THE Generation_Service SHALL return a `qwen-4b` completion (1200 tokens) with P50 latency below 20 seconds and P99 latency below 45 seconds.
6. WHILE the Generation_Service container is warm, THE Generation_Service SHALL return a `qwen-8b` completion (1200 tokens) with P50 latency below 30 seconds and P99 latency below 60 seconds.

---

### Requirement 13: Performance — Scaling Configuration

**User Story:** As a system operator, I want each Modal service to scale independently with sensible minimum and maximum container counts, so that resources are allocated proportionally to each service's load profile.

#### Acceptance Criteria

1. THE Embedding_Service SHALL be configured with `min_containers=1` and `max_containers=5`.
2. THE Classification_Service SHALL be configured with `min_containers=1` and `max_containers=3`.
3. THE Generation_Service SHALL be configured with `min_containers=1` and `max_containers=2`.
4. THE Backend SHALL be configured with `min_containers=1` and `max_containers=10`.
5. THE Embedding_Service container SHALL be provisioned with at least 2.5 GB of memory.
6. THE Classification_Service container SHALL be provisioned with at least 1.5 GB of memory.
7. THE Generation_Service container SHALL be provisioned with at least 8 GB of memory.
8. THE Backend container SHALL be provisioned with at least 512 MB of memory.

---

### Requirement 14: Observability and Health Endpoints

**User Story:** As a system operator, I want all four Modal services to expose health endpoints and structured logs, so that I can monitor service readiness and diagnose failures without access to container internals.

#### Acceptance Criteria

1. THE Embedding_Service SHALL expose `GET /health` returning `{"status": "ok", "models_loaded": {"multilingual-e5-small": bool, "jina-v3": bool, "codebert": bool}}`.
2. THE Classification_Service SHALL expose `GET /health` returning `{"status": "ok", "model_loaded": bool}`.
3. THE Generation_Service SHALL expose `GET /health` returning `{"status": "ok", "models": {"qwen-1.7b": bool, "qwen-4b": bool, "qwen-8b": bool}}`.
4. THE Backend SHALL expose `GET /health` and `GET /metrics` as before the migration.
5. WHEN a model is downloaded to the Volume, THE affected service SHALL emit a structured log entry at INFO level with the model key and volume path; IF the logging system fails, THE model download operation SHALL still complete successfully.
6. WHEN a model is loaded from the Volume into memory, THE affected service SHALL emit a structured log entry at INFO level confirming the model is ready; IF the logging system fails, THE model load operation SHALL still complete successfully.
7. WHEN an error occurs during model loading or inference, THE affected service SHALL emit a structured log entry at ERROR level with the exception message and stack trace.
8. WHEN a container startup completes successfully with all models ready, THE affected service SHALL emit a structured log entry at INFO level indicating "Container ready — accepting requests".

---

### Requirement 15: Inter-Service Security

**User Story:** As a security engineer, I want all inter-service communication to require a shared Bearer token, so that unauthenticated callers cannot reach the AI model endpoints.

#### Acceptance Criteria

1. THE Embedding_Service SHALL reject requests that do not include a valid `Authorization: Bearer <JIMS_MODAL_API_KEY>` header with HTTP 401; THE Embedding_Service SHALL always validate the Authorization header before processing the request body, so that even requests that would otherwise result in a service error (HTTP 500) are first checked for valid authentication.
2. THE Classification_Service SHALL reject requests that do not include a valid `Authorization: Bearer <JIMS_MODAL_API_KEY>` header with HTTP 401; THE Classification_Service SHALL always validate the Authorization header before processing the request body.
3. THE Generation_Service SHALL reject requests that do not include a valid `Authorization: Bearer <JIMS_MODAL_API_KEY>` header with HTTP 401; THE Generation_Service SHALL always validate the Authorization header before processing the request body.
4. THE Backend SHALL inject the `Authorization: Bearer <JIMS_MODAL_API_KEY>` header on every outbound HTTP call to the Embedding_Service, Classification_Service, and Generation_Service.
5. THE Embedding_Service, Classification_Service, and Generation_Service SHALL NOT be directly reachable from the public-facing frontend; only the Backend SHALL call them.

---

### Requirement 16: Error Handling — Hub Unreachable

**User Story:** As a system operator, I want clear failure behaviour when HuggingFace Hub is unreachable during model download, so that the system fails fast with a diagnostic message rather than hanging indefinitely.

#### Acceptance Criteria

1. IF the Volume is missing a model file AND HF_Hub is unreachable during container startup, THEN THE affected service SHALL raise `RuntimeError("Cannot load model <key>: volume miss + hub unreachable")` within the container startup timeout.
2. WHEN the affected service fails startup, THE Modal platform SHALL retry container spawn up to 3 times with exponential backoff.
3. WHEN all retry attempts are exhausted, THE Modal platform SHALL return HTTP 503 to callers of the affected service endpoint.
4. WHEN HF_Hub becomes reachable again, THE affected service SHALL download the missing model on the next container spawn without operator intervention.
5. THE availability of other Modal services SHALL NOT be affected when a single service fails to start due to a Hub connectivity issue.

---

### Requirement 17: Error Handling — GGUF Inference Failure

**User Story:** As a backend developer, I want generation inference failures to be handled gracefully, so that a corrupt model state does not permanently block the service.

#### Acceptance Criteria

1. IF llama-cpp-python raises an exception containing `ggml_assert` or `repack` during inference, THEN THE Generation_Service SHALL catch the exception, reset the affected Llama_Instance to `None`, and release the per-model lock.
2. WHEN an inference failure occurs, THE Generation_Service SHALL return HTTP 503 to the caller for that specific request, including an error detail body describing whether the failure is likely temporary (reloadable model corruption) and a `Retry-After` header indicating when the client may retry.
3. WHEN the next request arrives for the same model key after a reset, THE Generation_Service SHALL reload the Llama_Instance from the Volume path without re-downloading from HF_Hub.
4. THE reset and reload of one model instance SHALL NOT affect the availability of the other two model instances.

---

### Requirement 18: Unit Testing

**User Story:** As a developer, I want each Modal service to have an isolated unit test suite, so that routing logic, encoding correctness, and volume interactions can be verified without spinning up Modal infrastructure.

#### Acceptance Criteria

1. THE Embedding_Service test suite SHALL include a test verifying that `"multilingual-e5-small"`, `"jina-v3"`, and `"codebert"` routes each map to the correct loaded model instance.
2. THE Embedding_Service test suite SHALL include a test verifying all output vectors are 768-dimensional and unit-normalised.
3. THE Generation_Service test suite SHALL include a test verifying that `"qwen-1.7b"`, `"qwen-4b"`, and `"qwen-8b"` route to the correct Llama_Instance.
4. THE Generation_Service test suite SHALL include a test verifying that concurrent requests to the same model are serialised (no two coroutines hold the lock simultaneously).
5. THE Embedding_Service test suite SHALL include a test verifying that `ensure_model_on_volume` does not trigger a download when the model file is already present on the Volume.
6. THE Embedding_Service test suite SHALL include a test verifying that `ensure_model_on_volume` triggers a download when the model file is absent from the Volume.
7. THE Classification_Service test suite SHALL include a test verifying that mDeBERTa output labels map correctly to capability kind keys.
8. ALL unit tests SHALL mock the Modal Volume mount and model loading so that tests run without network access or Modal infrastructure.

---

### Requirement 19: Property-Based Testing

**User Story:** As a developer, I want property-based tests to verify universal correctness properties across a wide range of inputs, so that edge cases in embedding, generation, and volume idempotency logic are caught automatically.

#### Acceptance Criteria

1. THE Embedding_Service property tests SHALL use `hypothesis` and SHALL verify that for any list of 1–128 non-empty strings, all output vectors from `embed_batch` are unit-normalised with L2 norm within `1e-4` of `1.0`.
2. THE Embedding_Service property tests SHALL verify that for any list of 1–128 non-empty strings, `len(response.vectors) == len(input_texts)`.
3. THE Embedding_Service property tests SHALL verify that calling `ensure_model_on_volume` twice for a model key that is already cached on the Volume does not increment the download call count.
4. THE Generation_Service property tests SHALL verify that for any valid model key and non-empty prompt string, `route_and_generate` returns a `GenerateResponse` where `response.model` matches the requested model key.
5. ALL property tests SHALL run a minimum of 100 iterations per property.

---

### Requirement 20: Integration Testing

**User Story:** As a QA engineer, I want end-to-end integration tests that exercise the full call chain from the Backend through each AI service, so that service wiring and data contracts are validated against real Modal infrastructure.

#### Acceptance Criteria

1. THE integration test suite SHALL include a test that sends a POST request to `Backend /v1/query` and verifies that the Backend calls the Embedding_Service, receives vectors, and stores them in Cloudflare Vectorize.
2. THE integration test suite SHALL include a test that calls the Classification_Service via the Backend and verifies a valid `ClassifyResponse` is returned.
3. THE integration test suite SHALL include a test that exercises the full query pipeline: `POST /v1/query` → Backend → Embedding → Classification → Generation → response.
4. THE integration test suite SHALL include a test that verifies model file persistence: after a first cold-start, the Volume contains the downloaded model files and a second container startup skips all downloads.
5. ALL integration tests SHALL run against a dedicated Modal test environment, not the production deployment.


---

### Requirement 21: Service Decomposition — Five Specialised Services

**User Story:** As a system architect, I want the three Qwen models split into three dedicated single-model services (Intent, Renderer, Reasoning), so that each service can be independently scaled, GPU-allocated, and warm-managed to match its role in the VCO pipeline.

#### Acceptance Criteria

1. THE Intent_Service SHALL host exclusively Qwen3-1.7B (T1) and SHALL NOT load Qwen3-4B or Qwen3-8B.
2. THE Renderer_Service SHALL host exclusively Qwen3-4B (T2) and SHALL NOT load Qwen3-1.7B or Qwen3-8B.
3. THE Reasoning_Service SHALL host exclusively Qwen3-8B and SHALL NOT load Qwen3-1.7B or Qwen3-4B.
4. THE Embedding_Service, Classification_Service, Intent_Service, Renderer_Service, and Reasoning_Service SHALL each expose their own `GET /health` endpoint and SHALL be independently deployable via `modal deploy`.
5. THE Backend SHALL route generation requests to the correct service based on the `model` field: `"qwen-1.7b"` → Intent_Service, `"qwen-4b"` → Renderer_Service, `"qwen-8b"` → Reasoning_Service.
6. THE Renderer_Service path SHALL NOT block on or wait for the Reasoning_Service; if the Reasoning_Service is cold or unavailable, the Backend SHALL return HTTP 503 for that specific request without delaying Renderer_Service responses.

---

### Requirement 22: GPU Allocation Strategy

**User Story:** As a system operator, I want each service allocated to the correct compute type (CPU or GPU) based on its inference workload, so that GPU costs are incurred only where they meaningfully reduce latency.

#### Acceptance Criteria

1. THE Embedding_Service SHALL run on CPU-only containers; no GPU SHALL be requested or allocated.
2. THE Classification_Service SHALL run on CPU-only containers; no GPU SHALL be requested or allocated.
3. THE Intent_Service SHALL run on CPU-only containers by default; no GPU SHALL be requested unless latency benchmarking justifies it.
4. THE Renderer_Service SHALL request a GPU for every container; the preferred GPU type is L4 or A10G, with T4 as the fallback if neither is available.
5. THE Reasoning_Service SHALL request a dedicated GPU for every container; the preferred GPU type is L4 or A10G, with A100 when available.
6. WHEN the Renderer_Service container starts, THE Renderer_Service SHALL verify that a GPU device is accessible before loading the model; IF no GPU is detected, THEN THE Renderer_Service SHALL raise a `RuntimeError` and allow Modal to retry on a GPU-equipped host.
7. THE Reasoning_Service SHALL be configured independently of the Renderer_Service so that Reasoning_Service GPU allocation never competes with or delays Renderer_Service GPU allocation.

---

### Requirement 23: Container Warming Strategy

**User Story:** As a runtime operator, I want the frequently-used services to maintain at least one warm container at all times, so that cold-start latency never appears on the critical VCO generation path.

#### Acceptance Criteria

1. THE Embedding_Service SHALL be configured with `min_containers=1` so that at least one container with all three embedding models preloaded is always available.
2. THE Classification_Service SHALL be configured with `min_containers=1` so that at least one container with mDeBERTa preloaded is always available.
3. THE Intent_Service SHALL be configured with `min_containers=1` so that Qwen3-1.7B is always loaded and immediately available for T1 semantic compilation.
4. THE Renderer_Service SHALL be configured with `min_containers=1` so that Qwen3-4B on GPU is always loaded and immediately available for T2 rendering; THE Renderer_Service SHALL never be subject to scale-to-zero.
5. THE Reasoning_Service SHALL be configured with `min_containers=0` to allow scale-to-zero when idle; Modal SHALL spin up a Reasoning_Service container only when a request explicitly routes to `"qwen-8b"`.
6. WHEN any service with `min_containers=1` has its warm container replaced (e.g., after a crash), THE replacement container SHALL complete model loading and pass its `/health` check before the previous container is considered retired.
7. Models SHALL be loaded during container `__enter__` (startup), not during request handling; no request SHALL trigger model loading as a side effect.

---

### Requirement 24: Production Latency Targets (Cognitive Runtime)

**User Story:** As a product owner, I want the Modal deployment to meet strict end-to-end latency targets that reflect JIMS-AI's cognitive runtime goals, so that the VCO pipeline delivers a responsive user experience.

#### Acceptance Criteria

1. WHILE the Embedding_Service container is warm, THE Embedding_Service SHALL return embedding vectors with P50 latency below 200 ms for a single-text request.
2. WHILE the Classification_Service container is warm, THE Classification_Service SHALL return a classification result with P50 latency below 300 ms.
3. WHILE the Backend container is warm, THE Backend SHALL complete retrieval from Cloudflare Vectorize (including embedding) with P50 latency below 150 ms.
4. WHILE the Renderer_Service container is warm, THE Renderer_Service SHALL emit the first output token of a streaming response within 2 seconds of receiving the request (first-token latency P50 < 2 s).
5. WHILE the Renderer_Service container is warm, THE Renderer_Service SHALL complete a typical VCO response (≤ 1200 tokens) within 5 seconds end-to-end (P50 < 5 s).
6. THE Backend SHALL expose a `first_token_ms` field in its metrics endpoint tracking the P50 and P99 first-token latency of Renderer_Service calls.

---

### Requirement 25: Cost-Aware Routing — Reasoning Service Activation

**User Story:** As a system architect, I want the Reasoning_Service (Qwen3-8B) invoked only under specific high-complexity conditions, so that GPU costs for the 8B model are incurred only when the task genuinely requires it.

#### Acceptance Criteria

1. THE Backend SHALL route generation requests to the Reasoning_Service ONLY when at least one of the following conditions is met: (a) the invention engine is active for the current session, (b) planning depth threshold is exceeded (configurable, default: depth > 3), (c) capability confidence score falls below threshold (configurable, default: < 0.6), or (d) the request explicitly sets `model: "qwen-8b"`.
2. THE Backend SHALL route all other generation requests to the Renderer_Service (`"qwen-4b"`); THE Reasoning_Service SHALL NOT handle ordinary conversational responses.
3. THE Backend SHALL expose `JIMS_REASONING_CONFIDENCE_THRESHOLD` and `JIMS_REASONING_DEPTH_THRESHOLD` as configurable environment values with defaults of `0.6` and `3` respectively.
4. WHEN a request is routed to the Reasoning_Service and the Reasoning_Service container is cold (scale-to-zero), THE Backend SHALL wait up to 120 seconds for the Reasoning_Service to become available before returning HTTP 503.
5. THE Backend SHALL log the routing decision (which service was selected and which condition triggered it) at INFO level for every generation request.

---

### Requirement 26: Streaming — Renderer Service

**User Story:** As a frontend developer, I want the Renderer_Service to support token-level streaming over SSE, so that the frontend can begin displaying output before generation completes.

#### Acceptance Criteria

1. WHEN the Renderer_Service receives `POST /generate` with `stream: true`, THE Renderer_Service SHALL return a `StreamingResponse` with `Content-Type: text/event-stream`.
2. THE streaming response SHALL emit individual SSE lines in the format `data: {"token": "<text>", "finish_reason": null}\n\n` for each generated token.
3. THE streaming response SHALL emit a final SSE line `data: {"token": "", "finish_reason": "stop"}\n\n` followed by `data: [DONE]\n\n` when generation is complete.
4. THE Renderer_Service SHALL emit the first SSE token within 2 seconds of receiving the request on a warm container (First_Token_Latency P50 < 2 s).
5. THE Renderer_Service SHALL NOT buffer the entire generation before beginning to stream; each token SHALL be forwarded to the client as soon as it is produced by the model.
6. IF the client disconnects mid-stream, THE Renderer_Service SHALL detect the disconnection and abort inference to release the GPU lock.

---

### Requirement 27: Concurrency and GPU Safety

**User Story:** As a system operator, I want concurrent inference requests handled safely without GPU memory errors or deadlocks, so that the Renderer_Service and Reasoning_Service remain stable under load.

#### Acceptance Criteria

1. THE Renderer_Service SHALL enforce a per-container concurrency limit of 1 simultaneous inference request using an `asyncio.Lock` or equivalent; additional requests SHALL queue and wait, not be rejected.
2. THE Reasoning_Service SHALL enforce a per-container concurrency limit of 1 simultaneous inference request using an `asyncio.Lock` or equivalent.
3. THE Embedding_Service SHALL support concurrent requests without serialisation; the underlying `SentenceTransformer.encode()` calls are thread-safe on CPU.
4. THE Classification_Service SHALL support concurrent requests; the `transformers` zero-shot pipeline on CPU is stateless and thread-safe.
5. IF the Renderer_Service queue depth exceeds 5 waiting requests, THEN THE Renderer_Service SHALL return HTTP 429 (Too Many Requests) with a `Retry-After: 30` header to new incoming requests.
6. THE Intent_Service SHALL support concurrent requests without serialisation when running on CPU with llama-cpp-python in single-thread mode.

---

### Requirement 28: Extended Health Endpoint Schema

**User Story:** As a system operator, I want each service's health endpoint to return a rich status payload including GPU availability and volume mount state, so that I can diagnose service readiness without access to container logs.

#### Acceptance Criteria

1. EVERY service (Embedding, Classification, Intent, Renderer, Reasoning, Backend) SHALL expose `GET /health` returning a JSON object containing at minimum: `"status"` (`"healthy"` or `"unhealthy"`), `"models_loaded"` (bool or dict), `"container_uptime"` (seconds as integer), `"gpu_available"` (bool), and `"volume_mounted"` (bool).
2. WHEN all models are loaded and the volume is mounted, `"status"` SHALL be `"healthy"`; in any other state it SHALL be `"unhealthy"`.
3. THE `"gpu_available"` field SHALL be `true` only when a CUDA device is accessible; for CPU-only services (Embedding, Classification, Intent) it SHALL always be `false`.
4. THE `"volume_mounted"` field SHALL be `true` when `/vol/models` is accessible and non-empty; it SHALL be `false` if the volume mount failed or the directory is empty.
5. THE health endpoint SHALL respond within 500 ms regardless of current inference load; it SHALL NOT block on any in-flight model inference.
6. IF any model is in a failed or reset state, `"models_loaded"` SHALL reflect that model as `false` and `"status"` SHALL be `"unhealthy"`.

---

### Requirement 29: Inference Observability Metrics

**User Story:** As a system operator, I want per-request inference metrics collected and accessible, so that I can track latency, throughput, and GPU utilisation across the cognitive runtime.

#### Acceptance Criteria

1. THE Embedding_Service SHALL record and expose: request count, P50 and P99 embedding latency (ms), and batch size distribution.
2. THE Classification_Service SHALL record and expose: request count and P50 and P99 classification latency (ms).
3. THE Intent_Service SHALL record and expose: request count, P50 and P99 inference latency (ms), and tokens-per-second.
4. THE Renderer_Service SHALL record and expose: request count, P50 and P99 first-token latency (ms), P50 and P99 total generation latency (ms), tokens-per-second, GPU memory used (MB), and GPU utilisation (%).
5. THE Reasoning_Service SHALL record and expose the same metrics as the Renderer_Service.
6. ALL metrics SHALL be accessible via the service's `GET /metrics` endpoint in a format compatible with Prometheus scraping (text/plain, `# HELP` and `# TYPE` headers included).
7. WHEN a model load event occurs (download or volume load), THE service SHALL record model load duration (ms) in its metrics.
8. THE Backend SHALL aggregate and re-expose the `first_token_ms` P50 and P99 from the Renderer_Service in its own `GET /metrics` endpoint.

---

### Requirement 30: Volume Renamed and Model Integrity Validation

**User Story:** As a system operator, I want the Modal Volume named `jimsai-models` and model integrity validated on every container startup, so that corrupted or partial model files are detected before serving requests.

#### Acceptance Criteria

1. THE Volume SHALL be named `jimsai-models` (not `ai-models`) and mounted at `/vol/models` inside every AI service container.
2. WHEN a container starts and a model directory or GGUF file is present on the Volume, THE service SHALL validate model integrity before loading: for GGUF files, validate that file size matches the expected size recorded at download time; for snapshot directories, validate that `config.json` is present and non-empty.
3. IF integrity validation fails for any model, THEN THE service SHALL delete the corrupt file or directory, re-download from HF_Hub, and re-validate before accepting requests.
4. THE service SHALL record the outcome of integrity validation (pass/fail per model) in its startup log at INFO level.
5. Model integrity validation SHALL complete within 10 seconds per model; IF validation exceeds this threshold, THE service SHALL treat it as a failure and trigger re-download.
6. THE service SHALL never serve requests using a model that has not passed integrity validation.
