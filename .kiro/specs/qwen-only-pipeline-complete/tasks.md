# Implementation Plan: Qwen-Only Pipeline — Complete Fix & Deploy

## Overview

Six phases that take JIMS-AI from its current broken state (hash-only embeddings, Groq refs, disconnected feedback loop, stubbed training) to a fully working, deployed, live-tested system using Qwen3-4B as the sole LLM backend.

**Target stack after this work:**
- AWS Lambda → JIMS-AI pipeline → HF Space (Qwen3-4B render + Qwen3-1.7B intent + multilingual-e5 embeddings)
- Real 768-dim embeddings → semantic retrieval working (35% weight)
- Feedback loop closed → graph reinforcement on accept, confidence decay on reject
- Resolution learning threshold raised → no more noisy write-back
- Deploy script clean (no Groq vars)
- Live end-to-end tested with real training data and real prompts

---

## Phase 1 — Groq → Qwen Cleanup

- [x] 1. Rename `GroqBridge` → `QwenBridge` in `prototype/jimsai/model_bridge.py`
  - Rename class, update all internal references and docstrings
  - Remove dead `allow_external_groq`, `intent_model`, `render_model`, `canvas_model`, `invention_model`, `ingest_model` attributes that referenced Groq model names
  - Keep `local_first`, `local_url`, `local_api_key`, `local_model`, `local_render_model`, `local_chat_path`, `local_render_path` — these are the Qwen routing vars
  - Remove `enabled_t1`, `enabled_t2`, `enabled_canvas`, `enabled_invention`, `enabled_ingest` boolean flags (Groq-era toggles) — replace with single `qwen_enabled = bool(local_first and local_url)`
  - Simplify `_should_skip_t1` / `_should_skip_t2` to use only `adaptive_thinning` + confidence thresholds (no Groq-specific logic)
  - All methods (`infer_intent`, `classify_capability`, `render`, `canvas_synthesis`, `invention_candidates`, `extract_ingestion_memory`, `extract_math_expression`) already route to Qwen via `_chat_json` / `_render_chat_json` — just remove the early-return `if not self.enabled_*` guards and use `if not self.qwen_enabled` uniformly
  - _Requirements: Groq removed, Qwen3-4B is sole LLM backend_

- [x] 2. Update all imports and usages of `GroqBridge` → `QwenBridge`
  - `prototype/jimsai/runtime_layers.py` — 8 references (`TransformerIntentInterface`, `ActiveCanvasLayer`, `InventionEngineLayer`, `TransformerRenderInterface`)
  - `prototype/jimsai/pipeline.py` — `self.bridge = QwenBridge()`
  - Any other files importing `GroqBridge`
  - _Requirements: No broken imports after rename_

- [x] 3. Remove Groq env vars from deploy script and deployment guide
  - `infrastructure/aws-lambda/deploy-lambda-zip.ps1`: remove `GROQ_API_KEY`, `GROQ_GENERATOR_MODEL`, `GROQ_REASONING_MODEL`, `GROQ_INTENT_MODEL`, `GROQ_RENDER_MODEL`, `GROQ_CANVAS_MODEL`, `GROQ_INVENTION_MODEL` from `$allowedKeys`
  - Set `JIMS_ENABLE_GROQ_T1=false`, `JIMS_ENABLE_GROQ_T2=false`, `JIMS_ENABLE_GROQ_CANVAS=false`, `JIMS_ENABLE_GROQ_INVENTION=false` as hardcoded values in the script
  - Add `JIMS_LLM_PROVIDER=local` and `JIMS_ENABLE_LOCAL_QWEN=true` as hardcoded values
  - _Requirements: No Groq API key in Lambda env_

---

## Phase 2 — Wire the Real Encoder

- [x] 4. Implement `MultimodalEncoderAdapter` in `prototype/jimsai/provider_adapters.py`
  - New class `MultimodalEncoderAdapter` with `encode(content: str, modality: Modality) -> list[float]`
  - Reads `JIMS_EMBEDDING_SERVICE_URL` and `JIMS_EMBEDDING_SERVICE_TOKEN` (or `JIMS_MULTIMODAL_ENCODER_URL` / `JIMS_MULTIMODAL_ENCODER_API_KEY`)
  - Model selection per modality: `CODE` → `microsoft/codebert-base`, all text modalities → `intfloat/multilingual-e5-small`
  - Makes synchronous `httpx.post` to `/v1/embed` with `{"input": content, "model": model_id}`
  - Returns `data[0]["embedding"]` from response, or `[]` on any error (allows hash fallback to kick in)
  - 5-second timeout, no retries (fast-fail to hash)
  - `configured` property: returns `True` if URL is non-empty
  - _Requirements: Real 768-dim embeddings flow through DualRepresentationEncoder_

- [x] 5. Wire `MultimodalEncoderAdapter` into `ProductionRuntime`
  - In `ProductionRuntime.__init__()`, initialize `self.multimodal = MultimodalEncoderAdapter()` when `settings.enable_multimodal_encoders` is True
  - Ensure `DualRepresentationEncoder` receives `multimodal_adapter=self.production.multimodal` in `pipeline.py` (it already does — just confirm the adapter is actually instantiated)
  - Add `multimodal_configured` to `ProductionRuntime.readiness()` output
  - _Requirements: `latent_embedding_source = "external_service"` in signature metadata when HF Space is live_

---

## Phase 3 — Close the Feedback Loop

- [x] 6. Wire `graph.reinforce()` and confidence decay in `pipeline.record_feedback()`
  - On `request.rating in {"accept", "thumbs_up", "learn_this", "positive"}`:
    - For each `source` signature ID in the cited signatures (look up from memory), iterate its causal chain and call `self.graph.reinforce(link.cause, link.effect, delta=0.05)`
    - Call `self.graph.reinforce(source_sig_id, "verified", delta=0.03)` as a generic boost marker
  - On `request.rating in {"reject", "thumbs_down", "negative"}`:
    - For each cited signature, lower `confidence.score` by 0.10 (floor 0.1) and call `self.memory.update(sig)`
    - Call `self.graph.decay()` on the signature's outgoing edges
  - _Requirements: User feedback actually updates the graph and memory confidence_

- [x] 7. Fix `_learn_from_resolved_prompt()` threshold
  - Remove `transformer_assisted = response.used_groq and ...` check entirely
  - New condition: `response.confidence >= 0.90 AND not response.gaps AND executed_results`
  - Add env var gate: `JIMS_RESOLUTION_LEARNING_MIN_CONFIDENCE` (default `"0.90"`)
  - _Requirements: Only high-quality, verified, gap-free results write back to memory_

---

## Phase 4 — Tests

- [x] 8. Write `prototype/jimsai/tests/test_qwen_bridge.py`
  - Test `QwenBridge.available` returns True when `local_first=True` and `local_url` set
  - Test `QwenBridge.available` returns False when `local_url` empty
  - Test `infer_intent` returns None when `qwen_enabled=False`
  - Test `_should_skip_t1` respects confidence threshold (0.68 default)
  - Mock `_local_chat_json` to return valid JSON and verify `infer_intent` passes it through
  - _Validates: Phase 1 changes_

- [x] 9. Write `prototype/jimsai/tests/test_multimodal_encoder.py`
  - Mock `httpx.post` to return a valid 768-dim embedding
  - Verify `MultimodalEncoderAdapter.encode("hello", Modality.TEXT)` returns 768-element list
  - Verify `MultimodalEncoderAdapter.encode("def foo():", Modality.CODE)` uses `microsoft/codebert-base`
  - Verify fallback to `[]` when httpx raises
  - Verify `DualRepresentationEncoder` sets `latent_embedding_source = "external_service"` when adapter returns a vector
  - _Validates: Phase 2 changes_

- [x] 10. Write `prototype/jimsai/tests/test_feedback_loop.py`
  - Build a minimal memory + graph with one signature containing a causal link
  - Call `pipeline.record_feedback()` with positive rating → assert `graph.reinforce` was called
  - Call with negative rating → assert signature confidence decreased
  - Verify `_learn_from_resolved_prompt` does NOT write at confidence 0.85 (below new 0.90 threshold)
  - Verify it DOES write at confidence 0.91 with no gaps and executed results
  - _Validates: Phase 3 changes_

- [x] 11. Write `services/api-gateway/tests/test_pipeline_smoke.py`
  - Mock `QwenBridge._local_chat_json` and `MultimodalEncoderAdapter.encode`
  - POST to `/v1/query` with a simple math question — verify HTTP 200, response non-empty
  - POST to `/v1/query` with a profile question — verify routing to WORKSPACE_QUERY
  - POST to `/v1/training/ingest` with a sample document — verify signature is created
  - POST to `/v1/feedback` with positive rating — verify accepted=True
  - _Validates: End-to-end API layer_

---

## Phase 5 — Deploy to AWS Lambda

- [x] 12. Run deploy script and verify Lambda function update
  - Execute `.\infrastructure\aws-lambda\deploy-lambda-zip.ps1` from `C:\Users\ajibe\Jims-AI`
  - Verify exit code 0 and Lambda function URL is printed
  - Run direct Lambda health test via `aws lambda invoke`
  - Verify `/health` returns `{"status": "ok"}`
  - _Requirements: Lambda running updated code with no Groq vars_

- [x] 13. Verify Lambda environment variables are correct post-deploy
  - Confirm `GROQ_API_KEY` is NOT in Lambda env
  - Confirm `JIMS_LLM_PROVIDER=local` is set
  - Confirm `JIMS_ENABLE_LOCAL_QWEN=true` is set
  - Confirm `JIMS_EMBEDDING_SERVICE_URL` points to HF Space
  - Confirm `JIMS_ENABLE_GROQ_T1=false`, `JIMS_ENABLE_GROQ_T2=false`
  - _Requirements: Clean env, no Groq_

---

## Phase 6 — Live End-to-End Tests

- [x] 14. Warm the HF Space before live tests
  - POST `{"load_qwen": true, "load_render": true}` to `/v1/warm` on HF Space
  - Poll `/ready` until `qwen_loaded=true` and `render_loaded=true`
  - _Requirements: Qwen3-4B available for render tasks_

- [x] 15. Live training data ingest test
  - Ingest 3 documents through Lambda `/v1/training/ingest`:
    1. Technical doc: `"The JimsAI pipeline uses DualRepresentationEncoder. The encoder depends on MultimodalEncoderAdapter. High CPU usage causes slow response times."` (tests causal graph + relation extraction)
    2. Profile fact: `"My name is Jim. I am building JimsAI, an AI memory system."` (tests profile memory)
    3. Code snippet: Python function (tests CODE modality + codebert embedding)
  - Verify `/v1/memory/stats` shows 3+ new signatures
  - Verify at least one signature has `latent_embedding_source = "external_service"` (confirms encoder wired)
  - _Requirements: Real data flows through the full pipeline_

- [x] 16. Live prompt response tests
  - Test 1: `"What is my name?"` → should return profile memory, mention "Jim"
  - Test 2: `"What causes slow response times?"` → should return causal hit from ingest
  - Test 3: `"Write a Python function to reverse a string"` → CODE_GENERATE route, Qwen3-4B render
  - Test 4: `"3x - 7 = 14, solve for x"` → math_science route, symbolic solver returns x=7
  - Test 5: `"What is quantum entanglement?"` → GENERAL_FACT, no memory hit expected, graceful gap response
  - Verify all 5 return HTTP 200 with non-empty `response` field
  - Verify confidence > 0.60 on tests 1, 2, 4 (memory/solver backed)
  - _Requirements: Live system handles all major query types correctly_

- [x] 17. Live feedback loop test
  - Submit positive feedback on test 1 or 2 response → verify `graph.reinforce` path executed (check audit events)
  - Submit negative feedback → verify source signature confidence decreased
  - Re-run the same query → verify response confidence shifted
  - _Requirements: Closed feedback loop working in production_

---

## Notes

- Phases execute sequentially. Each phase's tests must pass before moving to next.
- `app.py` on HF Space is unchanged — already correctly routes to Qwen3-4B.
- `semantic_compiler.py` and `intent_classifier.py` are unchanged — already multilingual.
- HF Space warm-up before Phase 6 is mandatory — cold Qwen3-4B load takes 2–3 min.
- Lambda timeout is 120s — sufficient for Qwen3-4B render (45–90s worst case).
- The `GROQ_*` env var names in the deploy script are being removed, not repurposed.
