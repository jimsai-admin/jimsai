# Implementation Plan: HuggingFace Space Model Setup

## Overview

This plan targets three infrastructure files in
`infrastructure/huggingface-space/jimsai-embedding-service/`:

1. **`requirements.txt`** — add missing deps with version specifiers; enforce no `torch`/`llama-cpp-python`.
2. **`README.md`** — full rewrite with all required sections (model cards, hardware, env vars, startup, endpoints, client config, limitations).
3. **`Dockerfile`** / **`app.py`** — verified unchanged.
4. **Tests** — property-based and unit tests for the five pure utility functions in `app.py`.

All code tasks use Python. Tests use `hypothesis` (already imported in the test file) and `pytest`.

---

## Tasks

- [x] 1. Update `requirements.txt` with correct dependencies
  - Open `infrastructure/huggingface-space/jimsai-embedding-service/requirements.txt`
  - Add version specifiers to every existing entry: `fastapi>=0.100`, `uvicorn[standard]>=0.23`, `sentence-transformers>=2.2`, `transformers>=4.35`, `numpy>=1.24`, `pydantic>=2.0`, `python-dotenv>=1.0`, `huggingface-hub>=0.19`
  - Append the three new entries: `httpx>=0.24`, `accelerate>=0.20`, `einops>=0.6`
  - Ensure `torch` and `llama-cpp-python` are absent (they are installed separately in Dockerfile layers 2 & 3)
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 2. Verify `Dockerfile` and `app.py` are unchanged
  - [x] 2.1 Confirm Dockerfile still contains `libgomp1` apt install before all pip layers, `torch` CPU-wheel install before `requirements.txt`, `llama-cpp-python` CPU-wheel install before `requirements.txt`, non-root user uid 1000, and `HF_HOME` env var
    - Read `infrastructure/huggingface-space/jimsai-embedding-service/Dockerfile` and assert each required instruction is present in the correct order
    - No edits to the Dockerfile; raise an error/comment if anything is missing
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - [x] 2.2 Confirm `app.py` is unchanged
    - Read `infrastructure/huggingface-space/jimsai-embedding-service/app.py` and verify its SHA-256 or byte-for-byte content matches the last committed version
    - No edits to `app.py`
    - _Requirements: (preservation requirement — no-change contract)_

- [x] 3. Rewrite `README.md` with all required sections
  - [x] 3.1 Preserve YAML front matter exactly and add service title
    - Keep the existing front matter block (`title`, `emoji`, `colorFrom`, `colorTo`, `sdk: docker`, `app_port: 7860`) at the top of the file, unmodified
    - Add an `# JIMS-AI Embedding Service` heading immediately after the front matter
    - _Requirements: 11.8_
  - [x] 3.2 Add model cards section
    - Write a `## Models` section containing a Markdown table with columns: `#`, `Model`, `Role`, `Size`, `Load Strategy`
    - Include all six entries: `intfloat/multilingual-e5-small` (~120 MB, eager), `microsoft/codebert-base` (~500 MB, lazy), `jinaai/jina-embeddings-v3` (~570 MB, lazy), `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` (~560 MB, eager), `ggml-org/Qwen3-1.7B-GGUF / Qwen3-1.7B-Q4_K_M.gguf` (~1.1 GB, lazy), `Qwen/Qwen3-4B-GGUF / Qwen3-4B-Q4_K_M.gguf` (~2.5 GB, lazy)
    - _Requirements: 11.1_
  - [x] 3.3 Add hardware requirements section
    - Write a `## Hardware Requirements` section specifying: minimum 16 GB RAM, recommended 32 GB RAM, CPU-only (no GPU required, `n_gpu_layers=0` / `device=-1`), minimum 6 GB free disk for `HF_HOME`
    - Include cold-start timing notes: ~2–3 min (eager only), ~8–12 min (full warm with both GGUFs)
    - _Requirements: 11.2_
  - [x] 3.4 Add environment variables table
    - Write a `## Environment Variables` section with a Markdown table: columns `Variable`, `Default`, `Required`, `Description`
    - Include all 24 variables: `JIMS_RENDER_AGENT_TOKEN`, `JIMS_EMBEDDING_SERVICE_TOKEN`, `JIMS_EMBEDDING_MODEL`, `JIMS_EMBEDDING_DIMENSIONS`, `JIMS_EMBEDDING_HASH_FALLBACK_ENABLED`, `JIMS_ACTIVE_ARTIFACT_ID`, `JIMS_QWEN_ENABLED`, `JIMS_QWEN_MODEL_REPO`, `JIMS_QWEN_MODEL_FILE`, `JIMS_QWEN_MODEL`, `JIMS_QWEN_CONTEXT`, `JIMS_QWEN_MAX_TOKENS`, `JIMS_QWEN_THREADS`, `JIMS_QWEN_BATCH`, `JIMS_QWEN_CHAT_FORMAT`, `JIMS_RENDER_MODEL_REPO`, `JIMS_RENDER_MODEL_FILE`, `JIMS_RENDER_MODEL_NAME`, `JIMS_RENDER_CONTEXT`, `JIMS_RENDER_MAX_TOKENS`, `JIMS_RENDER_THREADS`, `JIMS_RENDER_BATCH`, `JIMS_ROUTER_MODEL`, `HF_TOKEN`
    - Note that if neither auth token is set, all protected endpoints return HTTP 503 (not 401)
    - _Requirements: 11.3_
  - [x] 3.5 Add startup and warm-up section
    - Write a `## Startup & Warm-Up` section describing Phase 1 (automatic: e5-small + mDeBERTa loaded on startup; verify via `GET /ready`) and Phase 2 (manual: `POST /v1/warm` with `load_qwen: true` and/or `load_render: true`)
    - Include the exact `POST /v1/warm` JSON body and the equivalent `GET /v1/warm` query-param form
    - Explain that warm-up is optional but strongly recommended before production GGUF traffic
    - _Requirements: 11.4_
  - [x] 3.6 Add endpoint reference table
    - Write a `## Endpoints` section with a Markdown table: columns `Method`, `Path`, `Auth`, `Description`
    - Include all 13 endpoints: `GET /`, `GET /health`, `GET /ready`, `GET /v1/warm`, `POST /v1/warm`, `POST /v1/embed`, `POST /v1/embed-batch`, `POST /v1/encode`, `POST /v1/chat/completions`, `POST /v1/chat/render`, `POST /v1/classify/capability`, `GET /v1/artifact/current`, `POST /v1/reload-artifact`
    - Document the `/v1/embed` `model` body parameter with three example values
    - _Requirements: 11.5_
  - [x] 3.7 Add client configuration section
    - Write a `## Client Configuration (Lambda / Pipeline)` section with a fenced code block containing all 10 Lambda-side env vars: `JIMS_LLM_PROVIDER`, `JIMS_ENABLE_LOCAL_QWEN`, `JIMS_LOCAL_INFERENCE_URL`, `JIMS_LOCAL_INFERENCE_API_KEY`, `JIMS_LOCAL_INFERENCE_MODEL`, `JIMS_LOCAL_INFERENCE_CHAT_PATH`, `JIMS_LOCAL_RENDER_MODEL`, `JIMS_LOCAL_RENDER_CHAT_PATH`, `JIMS_EMBEDDING_SERVICE_URL`, `JIMS_EMBEDDING_SERVICE_TOKEN`
    - _Requirements: 11.6_
  - [x] 3.8 Add known limitations section
    - Write a `## Known Limitations` section listing all 6 limitations: CPU-only inference latency (15–45 s/response for T2), serialized GGUF requests via `qwen_lock` / `render_lock`, cold start delay and HF Space idle spin-down, `jinaai/jina-embeddings-v3` requiring `trust_remote_code=True`, `JIMS_QWEN_ENABLED=false` disabling both T1 and T2, hash fallback vectors being non-semantic
    - _Requirements: 11.7_

- [x] 4. Checkpoint — verify `requirements.txt` and `README.md` are correct
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Write property-based and unit tests for `app.py` utility functions
  - Create `infrastructure/huggingface-space/jimsai-embedding-service/tests/test_app_utils.py`
  - Set up a `conftest.py` (or inline fixture) that patches `TARGET_DIMENSIONS` to a fixed value (e.g., 16) for fast iteration
  - Import `hash_embed`, `fit_dimensions`, `normalize`, `strip_thinking_for_json`, and `verify_token` from `app`
  - [x] 5.1 Write property test for `hash_embed` determinism and dimension correctness
    - **Property 3: Hash fallback determinism** — for any non-empty string `s`, `hash_embed(s) == hash_embed(s)` (same call twice) and `len(hash_embed(s)) == TARGET_DIMENSIONS`
    - Use `hypothesis.strategies.text(min_size=1)` as the input strategy
    - **Validates: Requirements 2.4**
  - [x]* 5.2 Write property test for `fit_dimensions` dimension invariant
    - **Property 2: Dimension-fitting correctness** — for any list of floats `v` of any length, `len(fit_dimensions(v)) == TARGET_DIMENSIONS`
    - Use `hypothesis.strategies.lists(floats(allow_nan=False, allow_infinity=False))` as input
    - **Validates: Requirements 1.5**
  - [x]* 5.3 Write property test for `normalize` L2 norm invariant
    - For any non-zero list of floats `v`, `abs(sum(x**2 for x in normalize(v))**0.5 - 1.0) < 1e-5`
    - Use `hypothesis.strategies.lists(floats(...), min_size=1)` filtered to exclude all-zero lists
    - **Validates: Requirements 1.1, 1.2, 1.3**
  - [x]* 5.4 Write property test for `strip_thinking_for_json` think-block removal
    - **Property 6: Think-block stripping** — for any JSON-serialisable dict `d` and any string `thinking`, `strip_thinking_for_json(f"<think>{thinking}</think>{json.dumps(d)}")` returns a string equal to `json.dumps(d)` (modulo whitespace) and contains no `<think>` tag
    - Use `hypothesis.strategies.text()` for `thinking` and `hypothesis.strategies.dictionaries(...)` for `d`
    - **Validates: Requirements 3.2, 4.2**
  - [x]* 5.5 Write property test for `verify_token` auth correctness
    - **Property 5: Token authentication correctness** — with `AGENT_TOKEN` patched to a non-empty value `t`, calling `verify_token` with `credentials.credentials == t` succeeds; with any other non-empty string it raises `HTTPException(status_code=401)`
    - Use `hypothesis.strategies.text(min_size=1)` for token values
    - **Validates: Requirements 8.1, 8.2**
  - [x] 5.6 Write unit tests for `verify_token` with unconfigured token
    - Patch `AGENT_TOKEN` to `""` and assert `verify_token` raises `HTTPException(status_code=503, detail="agent token not configured")`
    - _Requirements: 8.3_
  - [x] 5.7 Write unit tests for `hash_embed` with known inputs
    - Call `hash_embed("hello")` twice and assert identical results (regression anchor)
    - Call `hash_embed("")` and assert result has length TARGET_DIMENSIONS (empty string edge case)
    - _Requirements: 2.4_

- [x] 6. Final checkpoint — ensure all tests pass
  - Run `pytest infrastructure/huggingface-space/jimsai-embedding-service/tests/ -v`
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP pass.
- `app.py` and `Dockerfile` must not be modified — tasks 2.1 and 2.2 are read-only verification steps.
- Property tests in tasks 5.1–5.5 use `hypothesis`; install with `pip install hypothesis pytest` in the dev environment.
- `TARGET_DIMENSIONS` must be monkeypatched in the test module (e.g., `import app; app.TARGET_DIMENSIONS = 16`) so tests run without loading real model weights.
- Each property test must use `@given(...)` from `hypothesis` and pass `@settings(max_examples=200)` for adequate coverage.
- The `verify_token` tests (5.5, 5.6) require patching both `app.AGENT_TOKEN` and constructing a mock `HTTPAuthorizationCredentials` object.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "2.2"] },
    { "id": 1, "tasks": ["1"] },
    { "id": 2, "tasks": ["3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4"] },
    { "id": 4, "tasks": ["3.5", "3.6", "3.7", "3.8"] },
    { "id": 5, "tasks": ["5.1", "5.6", "5.7"] },
    { "id": 6, "tasks": ["5.2", "5.3", "5.4", "5.5"] }
  ]
}
```
