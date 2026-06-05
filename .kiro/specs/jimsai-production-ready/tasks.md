# Implementation Plan: JimsAI Production-Ready

## Overview

20 tasks across 7 phases that take JimsAI from its current state (internal labels in responses, Lambda cold start delays, no embedding retry, training loop stub, missing loggers, duplicate model class, debug print statements) to a fully production-ready system deployed on both HuggingFace Space and AWS Lambda.

**Production gaps being fixed:**
1. CSSE response reads like internal system output — users see `[Gap • Unresolved]` labels
2. Lambda cold start (60–150s) — first query feels broken
3. Real embeddings not flowing — no retry on HF Space timeout, hash fallback silently used
4. T2 render (Qwen3-4B) frequently skipped — raw CSSE output shown
5. Fallback responses have no helpful context — "I don't know" with no guidance
6. KaggleTrainingOrchestrator.upload_batch() is a stub — training loop non-functional
7. Jina embeddings-v3 linked on HF Space but never called
8. `logger` missing in `provider_adapters.py` and `encoder/dual_encoder.py` — `logger.warning()` calls crash at runtime
9. Duplicate `Modality` class in `models.py` — Python silently uses the second definition, dropping `IMAGE/AUDIO/VIDEO/DATA` variants
10. `print()` debug statements in `pipeline.py` — leak session internals to Lambda logs
11. `AdaptiveHybridEncoder._fetch_remote_vector()` hardcodes 5s timeout — times out on cold HF Space start

---

## Tasks

### Phase 1 — User-Facing Response Quality

- [x] 1. Rewrite CSSE to produce natural, warm responses
  - **File:** `prototype/jimsai/csse.py`
  - Remove all provenance label prefixes (`[Verified • Symbolic Solver]`, `[Gap • Unresolved]`, `[High Confidence • Approved Memory]` etc.) from the `response` field — move them to a separate `internal_label` field only
  - Replace "I do not have enough verified memory to answer that confidently yet." with genuinely helpful fallback text based on what IS known
  - Replace "Here's what I can verify from memory:" with direct natural phrasing
  - For tier 3 (learned pattern): remove "Based on workspace patterns, it is likely that..." — just say it naturally
  - For tier 4 (unverified): remove `⚠️ [Unverified Memory] [Fix/Edit](...)` inline links — those belong in the training panel, not chat
  - For verified math: format result as `**answer**` with a clean step breakdown
  - Always end with something useful — if there's a gap, suggest the next action
  - _Requirements: No `[Tier labels]` visible in user-facing responses_

- [x] 2. Make fallback responses genuinely helpful
  - **File:** `prototype/jimsai/csse.py`
  - Detect query type from `obj.intent` and `obj.style_signature` when no source signatures matched
  - GENERAL_FACT with no memory: `"I haven't learned about [topic] yet — you can teach me by sharing a document or telling me directly."`
  - WORKSPACE_QUERY / profile with no memory: `"I don't know your name yet. You can tell me by saying 'My name is [name]' and I'll remember it."`
  - CODE query with no memory: `"Share your codebase or a specific file and I can help with [topic]."`
  - Math parse failure: `"I can solve arithmetic like 2+9 or equations like 2x+5=11."`
  - EMOTIONAL_CATCH: always respond warmly, never with a gap message
  - Never return blank or empty `response`
  - _Requirements: Every query type returns something useful even with zero memory_

- [x] 3. Improve Qwen3-4B T2 render trigger conditions
  - **File:** `prototype/jimsai/model_bridge.py`
  - Remove the `generation_mode != "FACT"` skip condition — T2 should run for all modes when `qwen_enabled`
  - Lower `t2_skip_confidence` threshold default from 0.82 to 0.95 (only skip T2 for near-perfect symbolic solver results)
  - Never skip T2 when `obj.knowledge_gaps` is non-empty — gaps need natural language explanation
  - Verify the casual/conversational path already skips T2 correctly
  - `JIMS_T2_SKIP_CONFIDENCE=0.95` will be set in Task 11 deploy script update
  - _Requirements: T2 render runs on responses that need natural language polish_

---

### Phase 2 — Performance: Fix Lambda Cold Start

- [x] 4. Lazy provider initialization in ProductionRuntime
  - **File:** `prototype/jimsai/provider_adapters.py`
  - Verify `_initialized: bool = False` flag is present (already added per earlier work)
  - Verify `_ensure_initialized()` method exists and calls `_initialize()` once on first use
  - Audit every method that uses a provider (`save_training_ingest`, `retrieve_similar`, `load_recent_signatures`, etc.) — confirm each calls `_ensure_initialized()` at the top
  - Remove any remaining direct `self._initialize()` call from `__init__()` if still present
  - Keep `check_health()` as explicit method for `/health` and `/providers/readiness` endpoints
  - _Requirements: Lambda cold start drops from 60–150s to under 10s_

- [x] 5. Lazy pipeline component initialization
  - **File:** `prototype/jimsai/pipeline.py`
  - Move `SemanticCompilerRuntime()` to a lazy `@property` — only instantiate when `self.compiler` is first accessed
  - Move `KaggleGPUOrchestrator()` to lazy init — only needed for training runs
  - Keep `QwenBridge()`, `FourLayerMemoryStore()`, `CausalGraphEngine()` eager (zero-cost constructors)
  - Keep `ProductionRuntime()` eager but without network calls (after Task 4)
  - Protect `_hydrate_memory()` in `__init__`: if `cloud_authoritative` and Supabase not yet initialized, defer hydration
  - _Requirements: Combined with Task 4, cold start drops to <5s_

---

### Phase 3 — Real Embeddings (Semantic Retrieval)

- [x] 6. Add retry logic to ExternalMultimodalEncoderAdapter.encode()
  - **File:** `prototype/jimsai/provider_adapters.py`
  - Wrap the single `httpx.post` call in a `for attempt in range(2):` loop
  - First attempt uses `target_timeout` (from `JIMS_MULTIMODAL_ENCODER_TIMEOUT`, default 30s)
  - Second attempt uses 45s timeout
  - On final failure: `logger.warning("Embedding service unavailable after retry, using hash fallback")` then `return []`
  - In `DualRepresentationEncoder._external_embedding()`: log when falling back to hash: `logger.warning("Embedding service unavailable, using hash fallback")`
  - _Requirements: Real embeddings flow on warm Lambda; degrades gracefully with visibility on cold start_

- [x] 7. Verify and complete MultimodalEncoderAdapter model selection and embed_batch
  - **File:** `prototype/jimsai/provider_adapters.py`
  - Verify `Modality.CODE` → `microsoft/codebert-base` (768-dim)
  - Verify all other modalities → `intfloat/multilingual-e5-small` (768-dim)
  - Verify `_extract_vector()` handles all payload shapes and returns normalized list
  - Verify `latent_embedding_source = "external_service"` is set in signature metadata when encoder returns a real vector
  - Add `embed_batch(texts: list[str], purpose: str, model_id: str) -> list[list[float]]` method for bulk ingest — loop over texts using the retry logic from Task 6
  - _Requirements: Batch ingest uses real embeddings; modality routing confirmed correct_

- [x] 8. Verify retrieval embedding weight and add retrieval_stats
  - **File:** `prototype/jimsai/retrieval.py`
  - Verify 35% weight applied for `latent_embedding_source == "external_service"` hits vs 8% tiebreaker for `hash_projection`
  - Add `retrieval_stats: dict` to the return value (or to `RetrievalResult`) showing count of semantic vs lexical hits
  - Example: `{"semantic_hits": 3, "lexical_hits": 2, "total": 5}`
  - _Requirements: Retrieval scoring confirmed; observability added for debugging_

---

### Phase 4 — Response Always Has Something Useful

- [x] 9. Add graceful degradation for every query type
  - **Files:** `prototype/jimsai/csse.py`, `prototype/jimsai/pipeline.py`
  - Math queries: if solver succeeded → show answer prominently with steps; if failed → explain supported formats, never show "sympy unavailable" raw
  - Code queries: if memory hit → show with context; if no memory → `"Share your code or describe the function"`
  - General fact queries: if no memory → `"I don't have information about [topic] in my memory yet. You can teach me by sharing documents or facts about it."`
  - Profile queries: if known → answer directly; if unknown → prompt to share
  - Emotional queries: always respond warmly, never with a gap message
  - _Requirements: Every query type returns a genuinely useful response_

- [x] 10. Add suggestions field to pipeline response
  - **Files:** `prototype/jimsai/models.py`, `prototype/jimsai/csse.py`, `prototype/jimsai/pipeline.py`
  - Add `suggestions: list[str] = []` optional field to `PipelineResponse`
  - Populate when: confidence < 0.60 → suggest follow-up questions or ways to improve memory
  - Math failed → suggest correct expression format
  - Profile unknown → `"Tell me your name to help me remember you"`
  - Code query with no codebase → `"Share a file or describe what you're building"`
  - _Requirements: Frontend has actionable suggestions to show below every low-confidence response_

---

### Phase 5 — Training Loop & New Modality

- [x] 11. Implement KaggleTrainingOrchestrator.upload_batch()
  - **File:** `prototype/jimsai/training_loop.py`
  - Replace stub with real implementation:
  - Check `kagglehub` is importable; if not → `raise RuntimeError("kagglehub not installed")`
  - Check `KAGGLE_API_TOKEN` and `KAGGLE_DATASET_OWNER` env vars; if missing → `raise RuntimeError` with clear message
  - Serialize `batch` to a temp JSON file under a timestamped local dir (`/tmp/jims_training_{batch_id}/batch.json`)
  - Use `kagglehub.dataset_upload()` to push to `{kaggle_dataset_owner}/jims-training-{batch_id}` as private dataset
  - If `KAGGLE_KERNEL_SLUG` env var is set: trigger training notebook via `kaggle.api.kernels_push()`; if not set → log warning, don't fail
  - Return `{"batch_id": batch_id, "status": "uploaded", "kaggle_dataset": ..., "uploaded_at": ..., "notebook_triggered": bool}`
  - Add `test_upload_batch_missing_credentials_raises` test in `tests/test_training_loop.py`
  - _Requirements: Training batches actually upload to Kaggle; missing credentials raise clear errors_

- [x] 12. Add Jina embeddings-v3 as gated third modality branch
  - **File:** `prototype/jimsai/provider_adapters.py`
  - Add `JIMS_JINA_EMBEDDINGS_ENABLED` env var check (default `false`) to gate this path — do not activate unless Space confirms support
  - When enabled: if `modality == Modality.DATA` → use `jinaai/jina-embeddings-v3`
  - Keep `Modality.CODE` → `microsoft/codebert-base`
  - Keep all other modalities → `intfloat/multilingual-e5-small`
  - Document which modality triggers Jina in a docstring comment on `encode()`
  - _Requirements: Jina path exists but is off by default; togglable via env var_

---

### Phase 5 — Code Quality & Correctness Fixes

- [ ] 16. Add missing logger to provider_adapters.py and encoder/dual_encoder.py
  - **Files:** `prototype/jimsai/provider_adapters.py`, `prototype/jimsai/encoder/dual_encoder.py`
  - `provider_adapters.py`: add `import logging` and `logger = logging.getLogger(__name__)` near the top (after existing imports) — `logger.warning()` is already called on lines ~1361 and ~1415 but `logger` is never defined, causing `NameError` at runtime
  - `encoder/dual_encoder.py`: add `import logging` and `logger = logging.getLogger(__name__)` — needed for the `logger.warning("Embedding service unavailable, using hash fallback")` call added in Task 6
  - Verify with `python -c "from prototype.jimsai.provider_adapters import ExternalMultimodalEncoderAdapter"` — must import without error
  - _Requirements: No NameError on logger calls during embedding operations_

- [ ] 17. Remove duplicate Modality class in models.py
  - **File:** `prototype/jimsai/models.py`
  - Lines 22–25 define `class Modality` with only `TEXT` and `CODE`
  - Lines 27–33 define `class Modality` again with `TEXT`, `CODE`, `IMAGE`, `AUDIO`, `VIDEO`, `DATA`
  - Remove the first (incomplete) definition — keep only the second full definition with all 6 variants
  - Run `python -c "from prototype.jimsai.models import Modality; assert hasattr(Modality, 'DATA')"` to confirm
  - _Requirements: `Modality.DATA`, `Modality.IMAGE`, `Modality.AUDIO`, `Modality.VIDEO` all accessible_

- [ ] 18. Replace print() debug statements in pipeline.py with logger.debug()
  - **File:** `prototype/jimsai/pipeline.py`
  - Find and replace all `print(f"DEBUG ...")` calls with `logger.debug(...)` — there are 2 on lines ~320 and ~338:
    - `print(f"DEBUG LOADED SESSION: ...")` → `logger.debug("Loaded session: keys=%s", list(session.keys()))`
    - `print(f"DEBUG DECOUPLING: ...")` → `logger.debug("Context decoupling check: active_obj=%s query=%s", active_obj, request.query)`
  - Confirm `logger = logging.getLogger(__name__)` exists in pipeline.py (add if missing)
  - Run `grep -n "print(" prototype/jimsai/pipeline.py` to confirm no print statements remain in production code paths
  - _Requirements: No debug output to Lambda CloudWatch in production; structured log entries instead_

- [ ] 19. Fix AdaptiveHybridEncoder._fetch_remote_vector() timeout
  - **File:** `prototype/jimsai/encoder/adaptive_hybrid_encoder.py`
  - In `_fetch_remote_vector()`, the `httpx.post()` call uses `timeout=5.0` hardcoded
  - Replace with env-var-controlled timeout:
    ```python
    timeout = float(os.environ.get("JIMS_MULTIMODAL_ENCODER_TIMEOUT", "30"))
    response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    ```
  - Note: `AdaptiveHybridEncoder` is the HF Space's internal encoder (runs inside the Space, not on Lambda) — this fix ensures it respects the same timeout env var used by the HTTP client on Lambda, keeping behaviour consistent across both environments
  - Also fix the response parsing: current code does `data.get("data", [[]])[0].get("embedding", [])` which assumes the `/v1/embed` response shape `{"data": [{"embedding": [...]}]}` — the HF Space actually returns `{"data": [...], "embeddings": [...], "vectors": [...]}`. Update to try multiple keys: check `data.get("embeddings")` first, then `data.get("data", [[]])[0].get("embedding", [])` as fallback
  - _Requirements: Timeout respects JIMS_MULTIMODAL_ENCODER_TIMEOUT; response parsing handles actual HF Space shape_

---

### Phase 6 — Code Quality & Correctness Fixes

- [ ] 16. Add missing logger to provider_adapters.py and encoder/dual_encoder.py
  - **Files:** `prototype/jimsai/provider_adapters.py`, `prototype/jimsai/encoder/dual_encoder.py`
  - `provider_adapters.py`: add `import logging` and `logger = logging.getLogger(__name__)` after the existing imports — `logger.warning()` is already called in `encode()` and `embed_batch()` but `logger` is never defined, causing `NameError` at runtime
  - `encoder/dual_encoder.py`: add `import logging` and `logger = logging.getLogger(__name__)` — needed for the `logger.warning("Embedding service unavailable, using hash fallback")` call in `_external_embedding()`
  - Verify: `python -c "from prototype.jimsai.provider_adapters import ExternalMultimodalEncoderAdapter"` must import cleanly
  - _Requirements: No NameError on logger calls during embedding operations_

- [ ] 17. Remove duplicate Modality class in models.py
  - **File:** `prototype/jimsai/models.py`
  - Lines 22–25 define `class Modality` with only `TEXT` and `CODE`
  - Lines 27–33 define `class Modality` again with the full set: `TEXT`, `CODE`, `IMAGE`, `AUDIO`, `VIDEO`, `DATA`
  - Remove the first incomplete definition — keep only the full second definition
  - Verify: `python -c "from prototype.jimsai.models import Modality; assert hasattr(Modality, 'DATA') and hasattr(Modality, 'IMAGE')"`
  - _Requirements: All 6 Modality variants accessible; no silent class shadowing_

- [ ] 18. Replace print() debug statements in pipeline.py with logger.debug()
  - **File:** `prototype/jimsai/pipeline.py`
  - Replace `print(f"DEBUG LOADED SESSION: keys={list(session.keys())} content={session}")` with `logger.debug("Loaded session: keys=%s", list(session.keys()))`
  - Replace `print(f"DEBUG DECOUPLING: active_obj={active_obj} query={request.query}")` with `logger.debug("Context decoupling check: active_obj=%s query=%r", active_obj, request.query)`
  - Confirm `logger = logging.getLogger(__name__)` exists in pipeline.py (it should — add if missing)
  - _Requirements: No debug output in Lambda CloudWatch logs in production; session content never logged at INFO level_

- [ ] 19. Fix AdaptiveHybridEncoder._fetch_remote_vector() timeout and response parsing
  - **File:** `prototype/jimsai/encoder/adaptive_hybrid_encoder.py`
  - In `_fetch_remote_vector()`, replace hardcoded `timeout=5.0` with:
    ```python
    timeout = float(os.environ.get("JIMS_MULTIMODAL_ENCODER_TIMEOUT", "30"))
    response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    ```
  - Fix response parsing: current code `data.get("data", [[]])[0].get("embedding", [])` only handles one shape. Update to try multiple keys matching the actual HF Space response:
    ```python
    data = response.json()
    # Try each known response shape in order
    vec = (
        data.get("embedding")
        or (data.get("embeddings") or [[]])[0] if isinstance(data.get("embeddings"), list) else None
        or (data.get("data") or [[]])[0].get("embedding", []) if isinstance(data.get("data"), list) else None
        or data.get("vectors", [[]])[0] if isinstance(data.get("vectors"), list) else None
        or []
    )
    return vec if isinstance(vec, list) else []
    ```
  - Note: `AdaptiveHybridEncoder` runs inside the HF Space (not Lambda) — this fix prevents it from timing out when calling other models within the same Space, and ensures consistent timeout behaviour with `JIMS_MULTIMODAL_ENCODER_TIMEOUT`
  - _Requirements: Timeout env-var controlled; response handles all HF Space payload shapes_

---

### Phase 7 — Deploy & Verify

- [x] 13. Update deploy script with production-ready settings
  - **File:** `infrastructure/aws-lambda/deploy-lambda-zip.ps1`
  - Set `JIMS_T2_SKIP_CONFIDENCE=0.95` (from 0.82)
  - Set `JIMS_T1_SKIP_CONFIDENCE=0.60` (from 0.68)
  - Set `JIMS_MULTIMODAL_ENCODER_TIMEOUT=45`
  - Set `JIMS_RESOLUTION_LEARNING_MIN_CONFIDENCE=0.90`
  - Set `JIMS_ENABLE_RESOLUTION_LEARNING=true`
  - Set `JIMS_ADAPTIVE_TRANSFORMER_THINNING=true`
  - Update Lambda memory to 1536 MB (from 1024 MB)
  - _Requirements: All production env vars correct before deploy_

- [ ] 14. Deploy HuggingFace Space (embedding service)
  - **File:** `infrastructure/huggingface-space/jimsai-embedding-service/app.py`
  - Push the updated Space files to the HF Space repo (the `adaptive_hybrid_encoder.py` fix from Task 19 lives inside the Space, not Lambda)
  - After push, poll `GET /health` on the Space URL until `model_loaded=true` (Space cold start is 2–3 min)
  - Verify `GET /ready` returns `{"ready": true}`
  - Verify `POST /v1/embed` with `{"input": "hello", "model": "intfloat/multilingual-e5-small"}` returns a 768-dim vector with `"fallback": false`
  - _Requirements: HF Space serving real embeddings before Lambda deploy_

- [ ] 15. Deploy to Lambda
  - Run `.\infrastructure\aws-lambda\deploy-lambda-zip.ps1`
  - Verify exit code 0 and Lambda function URL printed
  - Verify `GET /health` returns `{"status": "ok"}`
  - _Requirements: All code quality fixes (Tasks 16–19) and production settings deployed_

- [ ] 20. Live end-to-end response quality test
  - Test `"What is 2+9?"` → returns `**11**` naturally, confidence ≥ 0.95
  - Test `"What is my name?"` (after ingesting profile) → returns name naturally, no tier labels
  - Test `"Write a Python function to find the maximum in a list"` → CODE_GENERATE, Qwen3-4B render
  - Test `"What causes slow response times?"` (after causal ingest) → causal retrieval, natural phrasing
  - Test `"What is machine learning?"` (no memory) → helpful gap response, not `[Gap • Unresolved]`
  - Test `"I'm feeling overwhelmed with work"` → EMOTIONAL_CATCH, warm empathetic response
  - Test `"3x - 7 = 14, solve for x"` → symbolic solver, answer is **7**, clean presentation
  - Test `"What is the meaning of life?"` → graceful general response
  - Verify at least one response shows `latent_embedding_source = "external_service"` in audit log (real embedding, not hash)
  - Verify no `[Tier labels]` visible, all responses readable, warm Lambda < 30s
  - _Requirements: All major query types return natural, helpful responses in production_

---

## Task Dependency Graph

```
1 (CSSE natural responses)
2 (helpful fallbacks) → depends on 1
3 (T2 trigger fix) → independent
4 (lazy ProductionRuntime) → independent
5 (lazy pipeline init) → depends on 4
6 (encode retry) → independent
7 (embed_batch + model selection) → depends on 6
8 (retrieval stats) → depends on 7
9 (graceful degradation) → depends on 1, 2
10 (suggestions field) → depends on 9
11 (KaggleTrainingOrchestrator) → independent
12 (Jina embeddings) → depends on 6
16 (add logger) → independent
17 (remove duplicate Modality) → independent
18 (replace print with logger) → depends on 16
19 (fix AdaptiveHybridEncoder timeout) → independent
13 (deploy script) → depends on 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 16, 17, 18
14 (deploy HF Space) → depends on 19
15 (deploy Lambda) → depends on 13, 14
20 (live tests) → depends on 14, 15
```

**Execution order:** Tasks 1, 3, 4, 6, 11, 16, 17, 19 can run in parallel (no dependencies). Tasks 2, 5, 7, 12, 18 follow their parents. Then 9, 10, 8. Then 13 → 14 → 15 → 20.
