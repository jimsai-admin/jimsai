# Requirements Document

## Introduction

The `jimsai-embedding-service` HuggingFace Space is the centralized inference backend for the JIMS-AI pipeline. It exposes four model layers — semantic/code/technical embedding, zero-shot capability routing, T1 intent encoding (Qwen3-1.7B GGUF), and T2 render generation (Qwen3-4B GGUF) — as a single FastAPI service running in Docker on port 7860.

This requirements document captures what the service must do to be correctly configured and operational. The implementation targets three infrastructure files: `requirements.txt` (dependency correctness), `README.md` (operational documentation completeness), `Dockerfile` (preserved as-is), and `app.py` (preserved as-is).

---

## Glossary

- **Service**: The `jimsai-embedding-service` FastAPI application running in the HuggingFace Space Docker container.
- **Embedding_Layer**: The set of three embedding models (`multilingual-e5-small`, `codebert-base`, `jina-embeddings-v3`) served via `/v1/embed`.
- **T1_Encoder**: The Qwen3-1.7B GGUF model serving intent inference via `/v1/chat/completions`.
- **T2_Render**: The Qwen3-4B GGUF model serving canvas/render generation via `/v1/chat/render`.
- **Capability_Router**: The `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` zero-shot classification model serving `/v1/classify/capability`.
- **Requirements_File**: The `requirements.txt` file in `infrastructure/huggingface-space/jimsai-embedding-service/`.
- **Dockerfile**: The `Dockerfile` in `infrastructure/huggingface-space/jimsai-embedding-service/`.
- **README**: The `README.md` in `infrastructure/huggingface-space/jimsai-embedding-service/`.
- **Hash_Fallback**: The deterministic `hash_embed()` function that produces embedding vectors when the embedding model is unavailable.
- **Bearer_Token**: The value of `JIMS_RENDER_AGENT_TOKEN` or `JIMS_EMBEDDING_SERVICE_TOKEN` used to authenticate protected endpoints.
- **GGUF_Model**: A quantized large language model in the GGUF format, loaded via `llama-cpp-python`.
- **HF_Space**: The HuggingFace Spaces runtime environment hosting the Docker container.
- **TARGET_DIMENSIONS**: The configured embedding output dimension (default 768, set via `JIMS_EMBEDDING_DIMENSIONS`).
- **models_cache**: The in-process dictionary that caches loaded embedding model instances.

---

## Requirements

### Requirement 1: Embedding Layer Model Accessibility

**User Story:** As a pipeline operator, I want all three embedding models to be accessible via `/v1/embed`, so that the AdaptiveHybridEncoder can select the right embedding model for each query type.

#### Acceptance Criteria

1. WHEN a `/v1/embed` request is received with `model` set to `intfloat/multilingual-e5-small`, THE Embedding_Layer SHALL return an embedding vector of length TARGET_DIMENSIONS (default 768) with L2 norm within 0.001 of 1.0.
2. WHEN a `/v1/embed` request is received with `model` set to `microsoft/codebert-base`, THE Embedding_Layer SHALL return an embedding vector of length TARGET_DIMENSIONS with L2 norm within 0.001 of 1.0.
3. WHEN a `/v1/embed` request is received with `model` set to `jinaai/jina-embeddings-v3`, THE Embedding_Layer SHALL return an embedding vector of length TARGET_DIMENSIONS with L2 norm within 0.001 of 1.0.
4. WHEN a `/v1/embed` request is received with no `model` parameter, THE Embedding_Layer SHALL use `intfloat/multilingual-e5-small` as the default model and return the same response format as criterion 1.
5. THE Embedding_Layer SHALL return every embedding vector with length exactly equal to TARGET_DIMENSIONS, regardless of the native output dimension of the selected model, truncating if longer and zero-padding if shorter before normalization.
6. WHEN a `/v1/embed` request is received with an unrecognized `model` value, THE Service SHALL attempt to load the model as a generic `SentenceTransformer` and, if that fails, return the hash fallback response (if enabled) or HTTP 503.

---

### Requirement 2: Embedding Hash Fallback

**User Story:** As a pipeline operator, I want the service to return deterministic fallback embeddings when a model is unavailable, so that downstream requests do not fail hard during model load failures.

#### Acceptance Criteria

1. IF an embedding model fails to load AND WHEN `JIMS_EMBEDDING_HASH_FALLBACK_ENABLED` is `true`, THE Service SHALL return HTTP 200 with `fallback: true`, `model: "hash_fallback"`, and a fixed-length float vector of length TARGET_DIMENSIONS.
2. WHILE hash fallback is active, THE Service SHALL include the exception message in the `error` field of the response.
3. IF an embedding model fails to load AND WHEN `JIMS_EMBEDDING_HASH_FALLBACK_ENABLED` is `false`, THE Service SHALL return HTTP 503 with the message `"embedding model unavailable: <exc>"`.
4. FOR ALL input texts, `hash_embed(text)` SHALL return the identical vector on every invocation within the same process instance AND across service restarts, given the same `JIMS_EMBEDDING_DIMENSIONS` value.
5. IF hash fallback is NOT used, THEN THE Service SHALL return `fallback: false` and `model` set to the actual model ID used.

---

### Requirement 3: T1 Encoder Accessibility

**User Story:** As a pipeline operator, I want the Qwen3-1.7B GGUF model to serve intent inference via `/v1/chat/completions`, so that the JIMS-AI pipeline can perform T1-level reasoning tasks.

#### Acceptance Criteria

1. WHEN a `/v1/chat/completions` request is received with a non-empty `messages` array and the T1_Encoder is loaded, THE T1_Encoder SHALL return a response containing `id`, `object`, `choices` (with at least one entry having `message.role` and `message.content`), and `usage` fields.
2. WHEN `response_format` is `{"type": "json_object"}`, THE T1_Encoder SHALL strip all `<think>...</think>` blocks (including malformed or unclosed ones) from the response content before returning, such that no `<think>` tag remains in the returned `message.content`.
3. WHEN the T1_Encoder is not loaded and a `/v1/chat/completions` request is received, THE Service SHALL return HTTP 503 with the message `"qwen model unavailable: <error>"`.
4. WHEN an unhandled exception is raised during T1 inference, THE Service SHALL reset the `qwen_model` reference to `None`, return HTTP 500, and on subsequent `/v1/chat/completions` requests return HTTP 503 until the model is reloaded.
5. WHEN a `/v1/chat/completions` request is received with a missing `messages` field or an empty `messages` array, THE Service SHALL return HTTP 422 or HTTP 400.

---

### Requirement 4: T2 Render Accessibility

**User Story:** As a pipeline operator, I want the Qwen3-4B GGUF model to serve canvas/render generation via `/v1/chat/render`, so that the JIMS-AI pipeline can perform T2-level render and synthesis tasks.

#### Acceptance Criteria

1. WHILE the T2_Render is loaded AND WHEN a `/v1/chat/render` request is received with a non-empty `messages` array, THE T2_Render SHALL return a response containing `id`, `object`, `choices` (with at least one entry having `message.role` and `message.content`), and `usage` fields.
2. WHEN `response_format` is `{"type": "json_object"}`, THE T2_Render SHALL strip all `<think>...</think>` blocks (including unclosed tags) from response content using the regex `<think>.*?</think>` (DOTALL, IGNORECASE), such that no `<think>` tag remains in the returned `message.content`.
3. WHEN the T2_Render is not loaded and a `/v1/chat/render` request is received, THE Service SHALL return HTTP 503 with the message `"render model unavailable: <error>"`.
4. WHEN an unhandled exception is raised during T2 inference, THE Service SHALL reset the `render_model` reference to `None`, return HTTP 500, and on subsequent `/v1/chat/render` requests return HTTP 503 until the model is reloaded.
5. WHEN a `/v1/chat/render` request is received with a missing `messages` field or an empty `messages` array, THE Service SHALL return HTTP 422 or HTTP 400.

---

### Requirement 5: Capability Router Accessibility

**User Story:** As a pipeline operator, I want the mDeBERTa-v3 model to classify query capabilities via `/v1/classify/capability`, so that the pipeline can route requests to the correct model layer.

#### Acceptance Criteria

1. WHEN a valid `/v1/classify/capability` request is received with a non-empty `text` field and the Capability_Router is loaded, THE Capability_Router SHALL return a response with `primary_kind` (string), `confidence` (float in [0.0, 1.0]), `secondary_kinds` (array of 0–3 strings with score ≥ 0.35), and `scores` (array of objects each containing `kind` and `score` float in [0.0, 1.0]) fields.
2. WHERE the Service starts up, THE Capability_Router SHALL be loaded before the HTTP listener accepts any request.
3. IF the Capability_Router fails to load during startup, THEN THE Service SHALL log the error, set `router_error` to the exception string, and return HTTP 503 with the message `"router model unavailable: <router_error>"` for all subsequent `/v1/classify/capability` requests.
4. THE `primary_kind` field in every `/v1/classify/capability` response SHALL be exactly one of: `memory_chat`, `world_knowledge`, `coding`, `math_science`, `creative_text`, `image_generation`, `audio_generation`, `video_generation`, `agentic_task`.
5. WHEN a `/v1/classify/capability` request is received with a missing or empty `text` field, THE Service SHALL return HTTP 422 or HTTP 400.

---

### Requirement 6: Dependencies in requirements.txt

**User Story:** As a deployment engineer, I want `requirements.txt` to list exactly the packages the application needs (excluding those installed separately in the Dockerfile), so that the container builds correctly without pulling incorrect package variants.

#### Acceptance Criteria

1. THE Requirements_File SHALL contain `httpx` as an uncommented entry with a version specifier (e.g., `httpx>=0.24`).
2. THE Requirements_File SHALL contain `accelerate` as an uncommented entry with a version specifier (e.g., `accelerate>=0.20`).
3. THE Requirements_File SHALL contain `einops` as an uncommented entry with a version specifier (e.g., `einops>=0.6`).
4. THE Requirements_File SHALL NOT contain any uncommented entry whose package name matches `torch` exactly.
5. THE Requirements_File SHALL NOT contain any uncommented entry whose package name matches `llama-cpp-python` exactly.
6. THE Requirements_File SHALL contain uncommented entries for all of: `fastapi`, `uvicorn[standard]`, `sentence-transformers`, `transformers`, `numpy`, `pydantic`, `python-dotenv`, `huggingface-hub`, each with a version specifier.

---

### Requirement 7: Dockerfile Preservation

**User Story:** As a deployment engineer, I want the Dockerfile to remain unchanged, so that the correct Docker layer caching and CPU-specific wheel installation order is preserved.

#### Acceptance Criteria

1. THE Dockerfile SHALL contain a `RUN pip install ... torch --index-url https://download.pytorch.org/whl/cpu` instruction that appears before any `RUN pip install -r requirements.txt` instruction.
2. THE Dockerfile SHALL contain a `RUN pip install ... llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu` instruction that appears before any `RUN pip install -r requirements.txt` instruction.
3. THE Dockerfile SHALL contain a `RUN apt-get install` instruction that includes `libgomp1` and that appears before all `RUN pip install` instructions.
4. THE Dockerfile SHALL run the Service as a non-root user with uid 1000 (e.g., `USER user` after `RUN useradd -m -u 1000 user`).
5. THE Dockerfile SHALL set the `HF_HOME` environment variable to `/home/user/.cache/huggingface`.
6. THE Requirements_File referenced by the Dockerfile SHALL NOT contain `torch` or `llama-cpp-python` as uncommented entries, so that the Dockerfile's CPU wheels are not overridden during the requirements install step.

---

### Requirement 8: Bearer Token Authentication

**User Story:** As a security engineer, I want all model-serving endpoints to require a valid Bearer token, so that the service does not serve inference to unauthorized callers.

#### Acceptance Criteria

1. WHEN a protected endpoint receives a request with a valid Bearer token, THE Service SHALL process the request normally and return the expected model output.
2. WHEN a protected endpoint receives a request with an absent `Authorization` header, a non-Bearer scheme, or a token string that does not match the configured token, THE Service SHALL return HTTP 401 with `"invalid token"`.
3. WHEN neither `JIMS_RENDER_AGENT_TOKEN` nor `JIMS_EMBEDDING_SERVICE_TOKEN` is set to a non-empty value, THE Service SHALL return HTTP 503 with `"agent token not configured"` on all protected endpoints.
4. WHEN an unprotected endpoint receives a request without an `Authorization` header, THE Service SHALL process the request normally without requiring authentication.
5. THE Service SHALL allow `GET /`, `GET /health`, `GET /ready`, and `GET /v1/artifact/current` without authentication.
6. THE Service SHALL require authentication for all `POST` endpoints and for `GET /v1/warm`.
7. THE Service SHALL validate a token as valid if it exactly matches `JIMS_RENDER_AGENT_TOKEN` OR `JIMS_EMBEDDING_SERVICE_TOKEN` (checked in that order), using constant-time comparison to prevent timing attacks.

---

### Requirement 9: Service Startup and Warm-Up Sequence

**User Story:** As a pipeline operator, I want the service to automatically load the embedding and router models on startup, and to support explicit pre-loading of GGUF models, so that the service is ready to serve requests predictably.

#### Acceptance Criteria

1. WHEN the Service starts AND the embedding model (`intfloat/multilingual-e5-small`) fails to load, THE Service SHALL exit with a non-zero process exit code and SHALL NOT open an HTTP listener on port 7860.
2. WHEN the Service starts, THE Service SHALL call `load_router()` during the startup event handler before the HTTP listener accepts any request.
3. WHEN `GET /ready` is called after startup completes with both models loaded, THE Service SHALL return `{"ready": true}` (with `model` and `router_model` being non-None).
4. WHEN `GET /ready` is called before startup completes or when either model failed to load, THE Service SHALL return `{"ready": false}`.
5. WHEN a `POST /v1/warm` request is received with `load_qwen: true` and the T1_Encoder loads successfully, THE Service SHALL return HTTP 200 with `{"qwen_loaded": true}` in the response.
6. WHEN a `POST /v1/warm` request is received with `load_qwen: true` and the T1_Encoder fails to load, THE Service SHALL return HTTP 200 with `{"qwen_loaded": false, "qwen_error": "<exception message>"}`.
7. WHEN a `POST /v1/warm` request is received with `load_render: true` and the T2_Render loads successfully, THE Service SHALL return HTTP 200 with `{"render_loaded": true}` in the response.
8. WHEN a `POST /v1/warm` request is received with `load_render: true` and the T2_Render fails to load, THE Service SHALL return HTTP 200 with `{"render_loaded": false, "render_error": "<exception message>"}`.
9. WHILE a GGUF model is already loaded (module-level reference is non-None), THE Service SHALL return HTTP 200 with `{"loaded": false, "reason": "already_loaded"}` or equivalent idempotent success without re-downloading or re-initializing the model.

---

### Requirement 10: Concurrent Request Safety

**User Story:** As a pipeline operator, I want GGUF inference requests to be serialized per model, so that concurrent requests do not corrupt the llama-cpp model state.

#### Acceptance Criteria

1. WHILE a `/v1/chat/completions` request is being processed by the T1_Encoder lock, THE Service SHALL return HTTP 503 with a response body indicating the model is busy and the caller should retry, for any other `/v1/chat/completions` request that cannot acquire the lock immediately.
2. WHILE a `/v1/chat/render` request is being processed by the T2_Render lock, THE Service SHALL return HTTP 503 with a response body indicating the render model is busy, for any other `/v1/chat/render` request that cannot acquire the lock immediately.
3. WHILE a `/v1/embed` or `/v1/encode` request holds the `models_lock` to load a new embedding model into `models_cache`, THE Service SHALL return HTTP 503 with a response body indicating a model load is in progress, for any concurrent `/v1/embed` or `/v1/encode` request that cannot acquire the lock immediately.

---

### Requirement 11: README Documentation Completeness

**User Story:** As a pipeline operator, I want the README to document all model layers, hardware requirements, environment variables, startup sequence, endpoints, client configuration, and known limitations, so that I can configure and operate the service without consulting source code.

#### Acceptance Criteria

1. THE README SHALL contain a model cards section with a table or structured list documenting exactly these six model entries: `intfloat/multilingual-e5-small` (~120 MB, eager, semantic embeddings), `microsoft/codebert-base` (~500 MB, lazy, code embeddings), `jinaai/jina-embeddings-v3` (~570 MB, lazy, technical embeddings), `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` (~560 MB, eager, capability routing), `ggml-org/Qwen3-1.7B-GGUF / Qwen3-1.7B-Q4_K_M.gguf` (~1.1 GB, lazy, T1 intent encoder), and `Qwen/Qwen3-4B-GGUF / Qwen3-4B-Q4_K_M.gguf` (~2.5 GB, lazy, T2 render engine); each entry must include model name/ID, role, approximate download size in MB or GB, and loading strategy (eager or lazy).
2. THE README SHALL contain a hardware requirements section specifying: minimum 16 GB RAM, recommended 32 GB RAM, CPU-only operation (no GPU required), and minimum 6 GB free disk for `HF_HOME` model cache.
3. THE README SHALL contain an environment variables table with columns Variable, Default, Required, and Description covering all of: `JIMS_RENDER_AGENT_TOKEN`, `JIMS_EMBEDDING_SERVICE_TOKEN`, `JIMS_EMBEDDING_MODEL`, `JIMS_EMBEDDING_DIMENSIONS`, `JIMS_EMBEDDING_HASH_FALLBACK_ENABLED`, `JIMS_ACTIVE_ARTIFACT_ID`, `JIMS_QWEN_ENABLED`, `JIMS_QWEN_MODEL_REPO`, `JIMS_QWEN_MODEL_FILE`, `JIMS_QWEN_MODEL`, `JIMS_QWEN_CONTEXT`, `JIMS_QWEN_MAX_TOKENS`, `JIMS_QWEN_THREADS`, `JIMS_QWEN_BATCH`, `JIMS_QWEN_CHAT_FORMAT`, `JIMS_RENDER_MODEL_REPO`, `JIMS_RENDER_MODEL_FILE`, `JIMS_RENDER_MODEL_NAME`, `JIMS_RENDER_CONTEXT`, `JIMS_RENDER_MAX_TOKENS`, `JIMS_RENDER_THREADS`, `JIMS_RENDER_BATCH`, `JIMS_ROUTER_MODEL`, and `HF_TOKEN`.
4. THE README SHALL contain a startup and warm-up section documenting Phase 1 (automatic on container start: `intfloat/multilingual-e5-small` and `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` loaded via startup event; verify via `GET /ready`) and Phase 2 (manual: `POST /v1/warm` with `load_qwen: true` and/or `load_render: true` to preload GGUF models before production traffic).
5. THE README SHALL contain a complete endpoint reference table with columns Method, Path, Auth Required, and Description, documenting exactly these endpoints: `GET /`, `GET /health`, `GET /ready`, `GET /v1/warm`, `POST /v1/warm`, `POST /v1/embed`, `POST /v1/embed-batch`, `POST /v1/encode`, `POST /v1/chat/completions`, `POST /v1/chat/render`, `POST /v1/classify/capability`, `GET /v1/artifact/current`, `POST /v1/reload-artifact`.
6. THE README SHALL contain a client configuration section with a code block listing these environment variables that the Lambda/pipeline side must set: `JIMS_LLM_PROVIDER`, `JIMS_ENABLE_LOCAL_QWEN`, `JIMS_LOCAL_INFERENCE_URL`, `JIMS_LOCAL_INFERENCE_API_KEY`, `JIMS_LOCAL_INFERENCE_MODEL`, `JIMS_LOCAL_INFERENCE_CHAT_PATH`, `JIMS_LOCAL_RENDER_MODEL`, `JIMS_LOCAL_RENDER_CHAT_PATH`, `JIMS_EMBEDDING_SERVICE_URL`, and `JIMS_EMBEDDING_SERVICE_TOKEN`.
7. THE README SHALL contain a known limitations section covering all of: CPU-only inference latency, serialized GGUF requests via asyncio locks, cold start delay and HF Space idle spin-down, `jinaai/jina-embeddings-v3` requiring `trust_remote_code=True`, `JIMS_QWEN_ENABLED=false` disabling both T1 and T2 models, and hash fallback vectors being non-semantic.
8. THE README SHALL preserve the existing HF Space YAML front matter block exactly as: `title: jimsai-embedding-service`, `emoji: 🤖`, `colorFrom: blue`, `colorTo: green`, `sdk: docker`, `app_port: 7860`.
