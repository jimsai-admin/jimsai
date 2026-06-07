---
title: jimsai-embedding-service
emoji: 🤖
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
---

# JIMS-AI Embedding Service

Centralized inference backend for the JIMS-AI pipeline. Hosts four model layers — semantic/code/technical embedding, zero-shot capability routing, T1 intent encoding (Qwen3-1.7B GGUF), and T2 render generation (Qwen3-4B GGUF) — as a single FastAPI service running in Docker on port 7860.

All protected endpoints require:

```text
Authorization: Bearer <JIMS_RENDER_AGENT_TOKEN>
```

---

## Models

| # | Model | Role | Size | Load Strategy |
|---|-------|------|------|---------------|
| 1 | `intfloat/multilingual-e5-small` | Primary semantic embeddings for memory retrieval | ~120 MB | **Eager** (startup) |
| 2 | `microsoft/codebert-base` | Code-aware embeddings via mean-pool CLS | ~500 MB | Lazy (first `/v1/embed` request) |
| 3 | `jinaai/jina-embeddings-v3` | Technical / multilingual embeddings (`trust_remote_code=True`) | ~570 MB | Lazy (first `/v1/embed` request) |
| 4 | `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` | Zero-shot capability classification (9 kinds) | ~560 MB | **Eager** (startup) |
| 5 | `ggml-org/Qwen3-1.7B-GGUF` / `Qwen3-1.7B-Q4_K_M.gguf` | T1 intent encoder — intent inference, math extraction, capability classification | ~1.1 GB | Lazy (warm endpoint or first `/v1/chat/completions`) |
| 6 | `Qwen/Qwen3-4B-GGUF` / `Qwen3-4B-Q4_K_M.gguf` | T2 render engine — canvas synthesis, invention candidates, NL rendering | ~2.5 GB | Lazy (warm endpoint or first `/v1/chat/render`) |

Select the embedding model per request by passing `model` in the `/v1/embed` request body:
- `{"input": "...", "model": "intfloat/multilingual-e5-small"}` — default
- `{"input": "...", "model": "microsoft/codebert-base"}` — code queries
- `{"input": "...", "model": "jinaai/jina-embeddings-v3"}` — technical/multilingual queries

---

## Hardware Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| RAM | 16 GB | 32 GB |
| CPU | Any x86-64 | 4+ cores |
| GPU | Not required (`n_gpu_layers=0`, `device=-1`) | — |
| Free disk (HF_HOME cache) | 6 GB | 10 GB |

**Cold-start timing:**
- Startup with eager models only (e5-small + mDeBERTa): ~2–3 min
- Full warm with both GGUF models downloaded: ~8–12 min (first load) / ~3–5 min (from cache)

---

## Environment Variables

### Authentication

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `JIMS_RENDER_AGENT_TOKEN` | — | **Yes** (one of two) | Bearer token for all protected endpoints. Takes precedence over `JIMS_EMBEDDING_SERVICE_TOKEN`. If neither is set, all protected endpoints return HTTP 503 (not 401). |
| `JIMS_EMBEDDING_SERVICE_TOKEN` | `""` | Yes (one of two) | Fallback token variable. Either this or `JIMS_RENDER_AGENT_TOKEN` must be non-empty. |

### Embedding Layer

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `JIMS_EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | No | Primary model loaded on startup. Default for `/v1/embed` when no `model` param is passed. |
| `JIMS_EMBEDDING_DIMENSIONS` | `768` | No | Target output dimension. Vectors are truncated or zero-padded to match. Must be ≥ 1. |
| `JIMS_EMBEDDING_HASH_FALLBACK_ENABLED` | `true` | No | When `true`, failed embeddings return deterministic hash vectors instead of HTTP 503. |
| `JIMS_ACTIVE_ARTIFACT_ID` | `hf_space_encoder` | No | Identifier echoed in embedding responses for tracing. |

### T1 Encoder (Qwen3-1.7B)

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `JIMS_QWEN_ENABLED` | `true` | No | Set to `false` to disable both T1 and T2 GGUF loading (reduces memory usage). |
| `JIMS_QWEN_MODEL_REPO` | `ggml-org/Qwen3-1.7B-GGUF` | No | HuggingFace repo ID for the T1 GGUF file. |
| `JIMS_QWEN_MODEL_FILE` | `Qwen3-1.7B-Q4_K_M.gguf` | No | Filename within the repo. ~1.1 GB download. |
| `JIMS_QWEN_MODEL` | `qwen3-1.7b-instruct` | No | Model name echoed in chat completion responses. |
| `JIMS_QWEN_CONTEXT` | `4096` | No | Context window in tokens. Minimum 512. |
| `JIMS_QWEN_MAX_TOKENS` | `256` | No | Maximum output tokens for intent/classification tasks. |
| `JIMS_QWEN_THREADS` | `2` | No | CPU threads for llama-cpp inference. |
| `JIMS_QWEN_BATCH` | `64` | No | Batch size for prompt processing. |
| `JIMS_QWEN_CHAT_FORMAT` | `chatml` | No | llama-cpp chat format template. |

### T2 Render (Qwen3-4B)

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `JIMS_RENDER_MODEL_REPO` | `Qwen/Qwen3-4B-GGUF` | No | HuggingFace repo ID for the T2 render GGUF. |
| `JIMS_RENDER_MODEL_FILE` | `Qwen3-4B-Q4_K_M.gguf` | No | Filename within the repo. ~2.5 GB download. |
| `JIMS_RENDER_MODEL_NAME` | `qwen3-4b-instruct` | No | Model name echoed in render responses. |
| `JIMS_RENDER_CONTEXT` | `8192` | No | Context window for render tasks (larger for canvas/ingestion). |
| `JIMS_RENDER_MAX_TOKENS` | `1200` | No | Maximum output tokens for render/canvas/ingestion tasks. |
| `JIMS_RENDER_THREADS` | `2` | No | CPU threads for render inference. |
| `JIMS_RENDER_BATCH` | `128` | No | Batch size for render prompt processing. |

### Capability Router

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `JIMS_ROUTER_MODEL` | `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` | No | Zero-shot classification model. Loaded eagerly on startup alongside the embedding model. |

### HuggingFace Access

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `HF_TOKEN` | — | Conditional | HuggingFace access token. Required if the GGUF repos are gated. Also checked as `HUGGINGFACE_HUB_TOKEN`, `HUGGING_ACCESS_TOKEN`, `HUGGING_ACESS_TOKEN`. |

---

## Startup & Warm-Up

### Phase 1 — Automatic on container start (no action needed)

When the container starts, `startup_warm_embedding()` runs automatically and loads:
- `intfloat/multilingual-e5-small` — primary semantic embedding model
- `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` — capability router

Verify startup completion:

```bash
curl https://<your-space>.hf.space/ready
# Returns: {"ready": true, ...} when both models are loaded
```

**Phase 1 is complete when `/ready` returns `{"ready": true}`.**

### Phase 2 — Manual warm-up (recommended before production traffic)

Pre-load the Qwen3 GGUF models before serving requests. This prevents the first `/v1/chat/completions` or `/v1/chat/render` request from blocking for 60–120 seconds while the model downloads and initialises.

**POST form:**

```bash
curl -X POST https://<your-space>.hf.space/v1/warm \
  -H "Authorization: Bearer <JIMS_RENDER_AGENT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"load_qwen": true, "load_render": true}'
```

**GET form:**

```bash
curl "https://<your-space>.hf.space/v1/warm?load_qwen_model=true&load_render_model=true" \
  -H "Authorization: Bearer <JIMS_RENDER_AGENT_TOKEN>"
```

The response includes `qwen_loaded`, `render_loaded`, and any error strings. Warm-up is optional but strongly recommended for production workloads.

---

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | No | Service identity check |
| GET | `/health` | No | Full model status — loaded state, error strings, context sizes |
| GET | `/ready` | No | Returns `{"ready": true}` when embedding + capability router are loaded |
| GET | `/v1/warm` | **Yes** | Trigger model pre-loading via query params (`load_qwen_model`, `load_render_model`, `load_router_model`) |
| POST | `/v1/warm` | **Yes** | Trigger model pre-loading via JSON body (`load_qwen`, `load_render`, `load_router`, `load_embedding`) |
| POST | `/v1/embed` | **Yes** | Embed texts; pass `model` in body to select embedding model |
| POST | `/v1/embed-batch` | **Yes** | Alias for `/v1/embed` |
| POST | `/v1/encode` | **Yes** | Single-text encode (legacy interface) |
| POST | `/v1/chat/completions` | **Yes** | T1 intent inference via Qwen3-1.7B GGUF |
| POST | `/v1/chat/render` | **Yes** | T2 render / canvas synthesis via Qwen3-4B GGUF |
| POST | `/v1/classify/capability` | **Yes** | Zero-shot capability routing (9 kinds) |
| GET | `/v1/artifact/current` | No | Current artifact and model configuration |
| POST | `/v1/reload-artifact` | **Yes** | Reload the primary embedding model |

### `/v1/embed` model selection

```json
// Default — multilingual semantic
{"input": "what is machine learning?"}

// Code-aware
{"input": "def train_model(X, y): ...", "model": "microsoft/codebert-base"}

// Technical / multilingual
{"input": "Comment fonctionne le réseau de neurones?", "model": "jinaai/jina-embeddings-v3"}
```

---

## Client Configuration (Lambda / Pipeline)

Set these environment variables on the Lambda function or local pipeline to connect to this service:

```bash
JIMS_LLM_PROVIDER=local
JIMS_ENABLE_LOCAL_QWEN=true
JIMS_LOCAL_INFERENCE_URL=https://jimstechai-jimsai-embedding-service.hf.space
JIMS_LOCAL_INFERENCE_API_KEY=<same value as JIMS_RENDER_AGENT_TOKEN>
JIMS_LOCAL_INFERENCE_MODEL=qwen3-1.7b-instruct
JIMS_LOCAL_INFERENCE_CHAT_PATH=/v1/chat/completions
JIMS_LOCAL_RENDER_MODEL=qwen3-4b-instruct
JIMS_LOCAL_RENDER_CHAT_PATH=/v1/chat/render
JIMS_EMBEDDING_SERVICE_URL=https://jimstechai-jimsai-embedding-service.hf.space
JIMS_EMBEDDING_SERVICE_TOKEN=<same value as JIMS_RENDER_AGENT_TOKEN>
```

> If `JIMS_LOCAL_INFERENCE_URL` is not set, `GroqBridge` falls back to `JIMS_EMBEDDING_SERVICE_URL` for Qwen when `JIMS_ENABLE_LOCAL_QWEN=true`.

---

## Known Limitations

- **CPU-only inference**: All models run on CPU (`n_gpu_layers=0`, `device=-1`). Qwen3-4B render tasks take 15–45 seconds per response depending on output length and HF Space CPU allocation. Qwen3-1.7B intent tasks take 5–15 seconds.

- **Serialized GGUF requests**: `qwen_lock` and `render_lock` are `asyncio.Lock` instances that serialize all calls to the respective Qwen models. llama-cpp-python is not thread-safe. High request rates will queue at the lock boundary.

- **Cold start delay and idle spin-down**: HF Spaces may idle and spin down the container. The first request after idle triggers a full cold start. If `HF_HOME` cache is persisted, GGUF models reload from disk (~30–60 s). If not cached, models re-download from HuggingFace Hub (~5–10 min for both GGUFs).

- **`jinaai/jina-embeddings-v3` requires `trust_remote_code=True`**: Loading this model executes code from the model repository. This is required for the model to function correctly and has been reviewed as safe, but it means the model's custom code runs inside the container.

- **`JIMS_QWEN_ENABLED=false` disables both T1 and T2**: Setting this flag disables all GGUF loading. Both `/v1/chat/completions` and `/v1/chat/render` will return HTTP 503. There is no way to disable only one of the two GGUF models via environment variable — if you need only T1, simply do not warm T2.

- **Hash fallback vectors are non-semantic**: When embedding models fail to load and `JIMS_EMBEDDING_HASH_FALLBACK_ENABLED=true`, the service returns deterministic hash vectors. These vectors are positionally consistent across calls but carry no semantic meaning. Memory retrieval quality degrades significantly. Monitor `"fallback": true` in embedding responses.
