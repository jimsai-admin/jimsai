# Implementation Plan: JimsAI Production-Ready

## Overview

36 tasks across 9 phases — backend API quality, cold start performance, real embeddings, full math/science reasoning, live web search, code quality fixes, future-proof model-swap, prompt robustness, and a complete frontend chat UI redesign.

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
12. Math solver returns a single result string — no step-by-step, no physics/calculus/chemistry support
13. Web search (`WebAugmentedRetrieval`) exists but is completely disconnected from the main pipeline
14. Dead code in `semantic_compiler.py`: unused `STOP_WORDS`, `_semantic_vocabulary()`, `template_vectors`, `score_intents()` — marked "no longer used" but still present
15. T1/T2 model identity not swappable without code changes — needs clean env-var model-config API
16. Chaotic/typo-heavy prompts may sandbox instead of route correctly; multi-intent prompts drop second intent; context-less follow-ups break; causal depth hardcoded
17. Frontend is a single 1000-line `page.tsx` — no component structure, no GFM markdown, no per-message insights, outdated layout

---

## Tasks

### Phase 1 — User-Facing Response Quality

- [x] 1. Rewrite CSSE to produce natural, warm responses
  - **File:** `prototype/jimsai/csse.py`
  - Remove all provenance label prefixes (`[Verified • Symbolic Solver]`, `[Gap • Unresolved]`, `[High Confidence • Approved Memory]` etc.) from the `response` field
  - Replace robotic phrases with genuinely helpful fallback text driven by `obj.intent` + `obj.knowledge_gaps`
  - Format verified math results as `**answer**` with a clean step breakdown
  - Always end with something useful — if there's a gap, suggest the next action
  - _Requirements: No `[Tier labels]` visible in user-facing responses_

- [x] 2. Make fallback responses genuinely helpful
  - **File:** `prototype/jimsai/csse.py`
  - Detect query type from `obj.intent` and `obj.style_signature` when no source signatures matched
  - GENERAL_FACT with no memory → warm offer to learn; CODE with no memory → prompt to share; EMOTIONAL → always warm; math failure → explain supported format
  - Never return blank or empty `response`
  - _Requirements: Every query type returns something useful even with zero memory_

- [x] 3. Improve Qwen3-4B T2 render trigger conditions
  - **File:** `prototype/jimsai/model_bridge.py`
  - Lower `t2_skip_confidence` default to 0.95; never skip when knowledge gaps present; never skip for non-English or conversational prompts
  - _Requirements: T2 render runs on responses that need natural language polish_

---

### Phase 2 — Performance: Fix Lambda Cold Start

- [x] 4. Lazy provider initialization in ProductionRuntime
  - **File:** `prototype/jimsai/provider_adapters.py`
  - `_initialized = False` flag; `_ensure_initialized()` called on first use of any provider method
  - _Requirements: Lambda cold start drops from 60–150s to under 10s_

- [x] 5. Lazy pipeline component initialization
  - **File:** `prototype/jimsai/pipeline.py`
  - `SemanticCompilerRuntime` and `KaggleGPUOrchestrator` as lazy `@property` — zero-cost at startup
  - Defer `_hydrate_memory()` when `cloud_authoritative` and providers not yet initialized
  - _Requirements: Combined with Task 4, cold start drops to <5s_

---

### Phase 3 — Real Embeddings (Semantic Retrieval)

- [x] 6. Add retry logic to ExternalMultimodalEncoderAdapter.encode()
  - **File:** `prototype/jimsai/provider_adapters.py`
  - 2-attempt retry loop; attempt 0 uses `JIMS_MULTIMODAL_ENCODER_TIMEOUT`, attempt 1 uses 45s
  - On final failure: `logger.warning(...)` then `return []`
  - In `DualRepresentationEncoder._external_embedding()`: log when falling back to hash
  - _Requirements: Real embeddings flow on warm Lambda; degrades gracefully with visibility_

- [x] 7. Verify and complete MultimodalEncoderAdapter model selection and embed_batch
  - **File:** `prototype/jimsai/provider_adapters.py`
  - `Modality.CODE` → `microsoft/codebert-base`; others → `intfloat/multilingual-e5-small`; `Modality.DATA` + Jina flag → `jinaai/jina-embeddings-v3`
  - `embed_batch(texts, purpose, model_id)` method using same retry logic
  - `latent_embedding_source = "external_service"` set when real vector returned
  - _Requirements: Batch ingest uses real embeddings; modality routing correct_

- [x] 8. Verify retrieval embedding weight and add retrieval_stats
  - **File:** `prototype/jimsai/retrieval.py`
  - 35% weight for `external_service` hits; 8% tiebreaker for `hash_projection`
  - `get_last_retrieval_stats()` → `{"semantic_hits": N, "lexical_hits": N, "total": N}`
  - _Requirements: Retrieval scoring confirmed; semantic vs lexical counts observable_

---

### Phase 4 — Response Always Has Something Useful

- [x] 9. Add graceful degradation for every query type
  - **Files:** `prototype/jimsai/csse.py`, `prototype/jimsai/pipeline.py`
  - Math: solver succeeded → answer with steps; failed → explain supported format; never show "sympy unavailable"
  - Code: memory hit → show with context; no memory → prompt to share
  - General fact: no memory → warm offer to learn
  - Profile: known → answer directly; unknown → prompt to share
  - Emotional: always warm, never gap message
  - _Requirements: Every query type returns a genuinely useful response_

- [x] 10. Add suggestions field to pipeline response
  - **Files:** `prototype/jimsai/models.py`, `prototype/jimsai/csse.py`, `prototype/jimsai/pipeline.py`
  - `suggestions: list[str] = []` on `PipelineResponse`
  - Populate: confidence < 0.60 → improve-memory suggestion; math failed → format hint; profile unknown → name prompt; code no codebase → share-file prompt
  - _Requirements: Frontend has actionable suggestions below low-confidence responses_

---

### Phase 5 — Training Loop & New Modality

- [x] 11. Implement KaggleTrainingOrchestrator.upload_batch()
  - **File:** `prototype/jimsai/training_loop.py`
  - Validate `KAGGLE_API_TOKEN` and `KAGGLE_DATASET_OWNER`; serialize batch to temp JSON; use `kagglehub.dataset_upload()`; optionally trigger `KAGGLE_KERNEL_SLUG` notebook
  - Tests: `test_upload_batch_missing_credentials_raises` in `tests/test_training_loop.py`
  - _Requirements: Training batches actually upload to Kaggle; missing credentials raise clear errors_

- [x] 12. Add Jina embeddings-v3 as gated third modality branch
  - **File:** `prototype/jimsai/provider_adapters.py`
  - `JIMS_JINA_EMBEDDINGS_ENABLED=false` default; when enabled: `Modality.DATA` → `jinaai/jina-embeddings-v3`
  - Docstring documents which modality triggers which model
  - _Requirements: Jina path exists, off by default, togglable via env var_

---

### Phase 6 — Code Quality & Correctness Fixes

- [ ] 16. Add missing logger to provider_adapters.py and encoder/dual_encoder.py
  - **Files:** `prototype/jimsai/provider_adapters.py`, `prototype/jimsai/encoder/dual_encoder.py`
  - Add `import logging` and `logger = logging.getLogger(__name__)` after imports in both files
  - `logger.warning()` calls already exist in both but `logger` is undefined — causes `NameError` at runtime on any embedding failure
  - Verify: `python -c "from prototype.jimsai.provider_adapters import ExternalMultimodalEncoderAdapter"` imports cleanly
  - _Requirements: No NameError on logger calls during embedding operations_

- [ ] 17. Remove duplicate Modality class in models.py
  - **File:** `prototype/jimsai/models.py`
  - Lines 22–25: first `class Modality` with only `TEXT`/`CODE` — remove this stub
  - Lines 27–33: second `class Modality` with all 6 variants (`TEXT`, `CODE`, `IMAGE`, `AUDIO`, `VIDEO`, `DATA`) — keep this
  - Verify: `python -c "from prototype.jimsai.models import Modality; assert hasattr(Modality, 'DATA') and hasattr(Modality, 'IMAGE')"`
  - _Requirements: All 6 Modality variants accessible; no silent class shadowing_

- [ ] 18. Replace print() debug statements in pipeline.py with logger.debug()
  - **File:** `prototype/jimsai/pipeline.py`
  - `print(f"DEBUG LOADED SESSION: ...")` → `logger.debug("Loaded session: keys=%s", list(session.keys()))`
  - `print(f"DEBUG DECOUPLING: ...")` → `logger.debug("Context decoupling check: active_obj=%s query=%r", active_obj, request.query)`
  - Confirm `logger = logging.getLogger(__name__)` exists in pipeline.py (add if missing)
  - _Requirements: No debug output in Lambda CloudWatch logs in production_

- [ ] 19. Fix AdaptiveHybridEncoder._fetch_remote_vector() timeout and response parsing
  - **File:** `prototype/jimsai/encoder/adaptive_hybrid_encoder.py`
  - Replace hardcoded `timeout=5.0` with `float(os.environ.get("JIMS_MULTIMODAL_ENCODER_TIMEOUT", "30"))`
  - Fix response parsing — try all HF Space shapes in order: `data.get("embedding")`, then `data.get("embeddings")[0]`, then `data.get("data")[0]["embedding"]`, then `data.get("vectors")[0]`, fallback to `[]`
  - `AdaptiveHybridEncoder` runs inside the HF Space (not on Lambda) — this makes timeout consistent with the Lambda-side client
  - _Requirements: Timeout env-var controlled; response handles all HF Space payload shapes_

- [ ] 21. Remove dead code from semantic_compiler.py
  - **File:** `prototype/jimsai/semantic_compiler.py`
  - Remove `STOP_WORDS` set — replace `keep_stop or token not in STOP_WORDS` filter in `canonical_terms()` with `keep_stop or True` (i.e. always pass when `keep_stop=False`), or inline the logic
  - Remove `_semantic_vocabulary()` — returns empty set, never produces output
  - Remove `self.template_vectors` dict from `SemanticCompilerRuntime.__init__()`
  - Remove `score_intents()` method — marked "kept for backward compatibility" with no external callers
  - Remove `hypotheses = self.resolve_hypotheses(self.score_intents(tokens))` call in `compile()` — replace with `hypotheses = []`
  - Keep `GENERATION_ACTION_TOKENS`, `CODE_CAPABILITY_TOKENS`, `IMAGE_CAPABILITY_TOKENS`, `AUDIO_CAPABILITY_TOKENS`, `VIDEO_CAPABILITY_TOKENS`, `CREATIVE_CAPABILITY_TOKENS`, `AGENTIC_CAPABILITY_TOKENS`, `ARCHITECTURE_TOKENS`, `PUBLIC_MEMORY_QUERY_TOKENS` — all actively used in `_v9_capability_override()`
  - Run `python -m pytest tests/ -x -q -k "semantic or compiler or intent"` to confirm no regressions
  - _Requirements: No dead module-level code or methods; `compile()` still returns valid `SemanticIR`_

---

### Phase 7 — Full Capability Unlocks

- [ ] 22. Upgrade SymbolicMathSolver with step-by-step output and extended domain support
  - **File:** `prototype/jimsai/execution_runtime.py`
  - **Problem:** `SymbolicMathSolver.solve()` returns only `{"status", "result", "method"}` — no step breakdown. Physics, calculus, chemistry fall back to "failed".

  - **Add `steps: list[str]` to all return dicts.** Examples:
    - `"3x - 7 = 14"` → steps: `["Original: 3x - 7 = 14", "Add 7: 3x = 21", "Divide by 3: x = 7"]`
    - `"diff(x**2 + 3*x, x)"` → steps: `["Expression: x² + 3x", "d/dx(x²) = 2x", "d/dx(3x) = 3", "Result: 2x + 3"]`

  - **Extend dispatch in `solve()` to detect query type before sympy**:
    - Calculus keywords (`"derivative"`, `"differentiate"`, `"d/dx"`, `"∂"`, `"integrate"`, `"∫"`, `"integral"`) → route to `_solve_calculus(text, solve_for)` using `sympy.diff()` / `sympy.integrate()`
    - Multi-equation systems (`","` or `"\n"` between two `=` expressions) → `_solve_system(exprs, vars)` using `sympy.solve([eq1, eq2], [x, y])`
    - Physics constants in expression (`"g"`, `"c"`, `"h"`, `"k_B"`, `"R"`, `"N_A"`) → inject into sympy namespace: `{"g": 9.81, "c": 3e8, "h": 6.626e-34, "k_B": 1.38e-23, "R": 8.314, "N_A": 6.022e23}`
    - `"molar mass of [formula]"` pattern → `_compute_molar_mass(formula)` using a small built-in element-weight dict (H=1.008, C=12.011, O=15.999, N=14.007, Na=22.990, Cl=35.45, Fe=55.845, Ca=40.078, etc.) — no external deps
    - Quadratic/polynomial → factor first (`sympy.factor(expr)`) then solve, include factor in steps

  - **Add `show_steps` parameter** (bool, default `True` when query contains `"show"`, `"step"`, `"how"`, `"why"`, `"explain"`, `"working"`, `"derivation"`)

  - **Update `_apply_capability_gates()` in `pipeline.py`**: pass each step as a `ReasoningStep` with `relation="CALCULATION_TRACE"` when `len(steps) > 1`

  - **Update `CSSE._render_math()`**: when result has multiple steps, render as a numbered list instead of a single bold line

  - Run `python -m pytest tests/ -x -q -k "math or solver"` to confirm no regressions
  - _Requirements: Step-by-step shown for all solvable expressions; calculus/physics/chemistry dispatch correct; no regression on existing arithmetic tests_

- [ ] 23. Wire web search (DuckDuckGo) into the main pipeline for WORLD_KNOWLEDGE queries
  - **Files:** `prototype/jimsai/pipeline.py`, `prototype/jimsai/capability_router.py`, `services/world-knowledge/web_retrieval.py`
  - **Problem:** `WebAugmentedRetrieval` exists but is disconnected. `WORLD_KNOWLEDGE` always shows `"unavailable"` because `CapabilityAdapterRegistry.readiness()` only checks `BRAVE_SEARCH_API_KEY` — DuckDuckGo needs no key.

  - **Step 1 — Fix `readiness()` in `capability_router.py`**:
    ```python
    "web_search_available": True,  # DuckDuckGo is always available — no key required
    "web_search_provider": "brave" if os.getenv("BRAVE_SEARCH_API_KEY") else "duckduckgo",
    ```

  - **Step 2 — Copy `WebAugmentedRetrieval` into `prototype/jimsai/web_search.py`** (same Lambda package boundary):
    - Class stays the same; just relocate so `pipeline.py` can import it without a cross-package boundary
    - Keep `services/world-knowledge/web_retrieval.py` as the canonical source — `web_search.py` is a thin re-export

  - **Step 3 — Upgrade `_perform_search()` in `web_retrieval.py`** to try `duckduckgo_search` package first:
    ```python
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=self.max_results))
        return [WebSource(url=r["href"], title=r["title"], snippet=r["body"], fetched_at=fetched_at) for r in results]
    except ImportError:
        pass  # fall through to urllib instant-answer path
    ```
    Add `duckduckgo-search==6.*` to `services/api-gateway/requirements.lambda.txt`

  - **Step 4 — Wire into `pipeline._execute_capability_adapters()`**:
    ```python
    if result.kind == CapabilityKind.WORLD_KNOWLEDGE:
        return await self._execute_web_search(request, result)
    ```
    Implement `_execute_web_search()`: search, ingest top 3 snippets as `MemorySignature` objects (with `metadata["is_live_web"] = True`, `metadata["web_source_url"]`), return updated `CapabilityExecutionResult` with `web_sources` in `data`

  - **Step 5 — Add citation rendering in `CSSE._render_claims()`**: when `obj.capability_results` has a `WORLD_KNOWLEDGE` entry with `web_sources`, append:
    ```
    **Sources:**
    - [Title](url)
    ```

  - Mock `DDGS` in tests to avoid real HTTP: `python -m pytest tests/ -x -q -k "world_knowledge or web"`
  - _Requirements: `"What is the latest on X?"` routes to DuckDuckGo; top 3 results ingested as memory signatures; response cites sources; no API key needed; graceful fallback if search fails_

- [ ] 24. Make T1/T2 model identity fully swappable via env vars
  - **Files:** `prototype/jimsai/model_bridge.py`, `infrastructure/huggingface-space/jimsai-embedding-service/app.py`

  - **Step 1 — Add `/v1/model/config` endpoint to HF Space `app.py`** (no auth — public metadata):
    ```python
    @app.get("/v1/model/config")
    def model_config() -> dict[str, Any]:
        return {
            "t1_model": {"repo": QWEN_REPO_ID, "file": QWEN_FILENAME, "name": QWEN_MODEL_NAME, "loaded": qwen_model is not None},
            "t2_model": {"repo": RENDER_MODEL_REPO, "file": RENDER_MODEL_FILE, "name": RENDER_MODEL_NAME, "loaded": render_model is not None},
            "embedding_model": MODEL_NAME,
            "router_model": ROUTER_MODEL_NAME,
            "context": {"t1_ctx": QWEN_CONTEXT, "t2_ctx": RENDER_CONTEXT},
        }
    ```

  - **Step 2 — Add `JIMS_QWEN_GPU_LAYERS` / `JIMS_RENDER_GPU_LAYERS` to HF Space `app.py`**:
    ```python
    QWEN_GPU_LAYERS = int(os.environ.get("JIMS_QWEN_GPU_LAYERS", "0") or "0")
    RENDER_GPU_LAYERS = int(os.environ.get("JIMS_RENDER_GPU_LAYERS", "0") or "0")
    # Pass as n_gpu_layers= in Llama() constructors
    ```
    GPU Space upgrade = set env var only, no code change.

  - **Step 3 — Add `QwenBridge.describe()` method**:
    ```python
    def describe(self) -> dict[str, str]:
        return {
            "t1_model": self.local_model,
            "t2_model": self.local_render_model,
            "t1_endpoint": f"{self.local_url}{self.local_chat_path}",
            "t2_endpoint": f"{self.local_url}{self.local_render_path}",
            "qwen_enabled": str(self.qwen_enabled),
        }
    ```
    Surface in training dashboard `production_readiness` dict.

  - **Step 4 — Document full model-swap env var matrix in `QwenBridge` docstring**:
    ```
    T1 (intent/routing, smaller/faster):    JIMS_QWEN_MODEL_REPO, JIMS_QWEN_MODEL_FILE, JIMS_QWEN_MODEL, JIMS_QWEN_CONTEXT
    T2 (render/canvas/invention, larger):   JIMS_RENDER_MODEL_REPO, JIMS_RENDER_MODEL_FILE, JIMS_RENDER_MODEL_NAME, JIMS_RENDER_CONTEXT
    Any OpenAI-compatible endpoint:         JIMS_LOCAL_INFERENCE_URL, JIMS_LOCAL_INFERENCE_API_KEY
    Custom chat paths:                       JIMS_LOCAL_INFERENCE_CHAT_PATH, JIMS_LOCAL_RENDER_CHAT_PATH
    GPU layers (HF Space):                   JIMS_QWEN_GPU_LAYERS, JIMS_RENDER_GPU_LAYERS
    ```
  - _Requirements: Any GGUF model swappable via env vars only; GPU offloading via single env var; `/v1/model/config` returns current state; `QwenBridge.describe()` surfaces model identity in dashboard_

- [ ] 25. Strengthen prompt robustness — chaotic input, multi-intent, and context-less queries
  - **Files:** `prototype/jimsai/semantic_compiler.py`, `prototype/jimsai/model_bridge.py`, `prototype/jimsai/capability_router.py`, `prototype/jimsai/runtime_layers.py`

  - **Problem 1 — Extreme typos fall through to sandbox**: `normalize_language()` handles OCR confusables and known slang, but arbitrary misspellings (`"wha iz kinnetic enrgy formla"`) may fall below the confidence threshold and get sandboxed even though the intent is recognisable.
  - **Fix — T1 rewrite-for-clarity pass**: In `compile()`, when `confidence < local_threshold` AND query is ASCII-only (not a low-resource language) AND `JIMS_TYPO_CORRECTION_ENABLED=true` (default), call a new `QwenBridge.rewrite_for_clarity()` method and re-classify:
    ```python
    if typo_correction_enabled and qwen_enabled and 0.20 <= confidence < local_threshold:
        clean = await bridge.rewrite_for_clarity(raw_input)
        if clean and clean.strip() != raw_input.strip():
            ir2, conf2 = self.classifier.classify_intent(clean)
            if conf2 > confidence:
                target_ir, confidence = ir2, conf2
                scope["typo_corrected_query"] = clean
    ```
    Add to `QwenBridge`:
    ```python
    async def rewrite_for_clarity(self, raw_input: str) -> str | None:
        """Normalise chaotic/typo-heavy input without changing meaning."""
        if not self.qwen_enabled:
            return None
        system = 'Fix spelling and typos only. Do not rephrase or change meaning. Return JSON {"clean": "corrected text"} only.'
        data = await self._chat_json(self.local_model, system, raw_input[:512], max_tokens=120)
        return str(data.get("clean") or "").strip() or None if data else None
    ```
    Note: `compile()` is synchronous — call this via `asyncio.get_event_loop().run_until_complete()` when a loop exists, or skip if no loop is running (Lambda async context handles this naturally).

  - **Problem 2 — Multi-intent prompts pick only one capability**: `"solve 3x-7=14 and explain what causes high blood pressure"` → system picks MATH, drops the medical question entirely.
  - **Fix — Dual-intent execution**: In `CapabilityRouter.route()`, after scoring, if the top-2 scores are both ≥ 0.52 and the query contains a conjunction keyword (`" and also"`, `" and then"`, `" also "`, `"; "`) and the two top capabilities are different kinds, add the second to `secondary_intents`. In `pipeline._execute_capability_adapters()`, execute secondary intents that have a registered adapter (math solver, web search). In `CSSE._render_claims()`, when `obj.capability_results` has 2+ executed results, section the response with a brief header per section.

  - **Problem 3 — Context-less follow-ups sandbox**: `"what about the error?"` with no prior entity scores low confidence and routes to sandbox. The session already stores `ACTIVE_INTENT` and `ACTIVE_OBJECT` — but a vague first message leaves nothing to inherit.
  - **Fix — Session intent carry-forward**: In `compile()`, after all classification, when `confidence < 0.50` and `session.get("ACTIVE_INTENT")` is set, boost confidence to `max(confidence, 0.35)` and set `target_ir = session["ACTIVE_INTENT"]` unless current `target_ir` is already something specific (not `OP_ESCAPE_TO_SANDBOX`). This prevents vague follow-ups from sandboxing when a clear conversational context exists.

  - **Problem 4 — Causal reasoning depth hardcoded at 4 hops**: Deep engineering/medical causal chains truncate at 4.
  - **Fix — Configurable causal depth**: Add `JIMS_CAUSAL_TRAVERSAL_DEPTH` env var (default `4`, max `8`). Pass from `LatentWorldModelLayer.activate()` to `graph.incoming_edges()` / `graph.outgoing_edges()` / `_add_causal_path_steps()`. Only use depth > 4 when the query explicitly requests a complete chain (`"trace all"`, `"full chain"`, `"complete path"`, `"all causes"`, `"all effects"`).

  - Run `python -m pytest tests/ -x -q --ignore=tests/test_training_loop.py` to confirm no regressions
  - _Requirements: Extreme typos route correctly after T1 rewrite; multi-intent queries produce sectioned responses; context-less follow-ups inherit session intent; deep causal chains configurable_

---

### Phase 8 — Deploy & Verify

- [x] 13. Update deploy script with production-ready settings
  - **File:** `infrastructure/aws-lambda/deploy-lambda-zip.ps1`
  - `JIMS_T2_SKIP_CONFIDENCE=0.95`, `JIMS_T1_SKIP_CONFIDENCE=0.60`, `JIMS_MULTIMODAL_ENCODER_TIMEOUT=45`
  - `JIMS_RESOLUTION_LEARNING_MIN_CONFIDENCE=0.90`, `JIMS_ENABLE_RESOLUTION_LEARNING=true`
  - `JIMS_ADAPTIVE_TRANSFORMER_THINNING=true`, Lambda memory 1536 MB
  - Add new env vars: `JIMS_TYPO_CORRECTION_ENABLED=true`, `JIMS_CAUSAL_TRAVERSAL_DEPTH=4`
  - _Requirements: All production env vars correct before deploy_

- [ ] 14. Deploy HuggingFace Space (embedding service)
  - **File:** `infrastructure/huggingface-space/jimsai-embedding-service/app.py`
  - Push updated Space files (Tasks 19, 24 changes)
  - Poll `GET /health` until `model_loaded=true`; verify `GET /ready` returns `{"ready": true}`
  - Verify `GET /v1/model/config` returns T1/T2 model info
  - Verify `POST /v1/embed` with `{"input": "hello"}` returns 768-dim vector with `"fallback": false`
  - _Requirements: HF Space serving real embeddings and exposing model config before Lambda deploy_

- [ ] 15. Deploy to Lambda
  - Run `.\infrastructure\aws-lambda\deploy-lambda-zip.ps1`
  - Verify exit code 0, Lambda URL printed, `GET /health` → `{"status": "ok"}`
  - _Requirements: All fixes (Tasks 16–19, 21–25) and new capabilities deployed_

- [ ] 20. Live end-to-end response quality test
  - **Core**: `"What is 2+9?"` → `**11**`, confidence ≥ 0.95; `"3x - 7 = 14, solve for x"` → x=7, clean
  - **Steps**: `"Solve 3x - 7 = 14, show steps"` → numbered step breakdown
  - **Calculus**: `"What is the derivative of x² + 3x?"` → `2x + 3` with working
  - **Physics**: `"Kinetic energy, mass=2kg, velocity=3m/s"` → `KE = ½mv² = 9 J`
  - **Chemistry**: `"Molar mass of H2O"` → `18.015 g/mol`
  - **Web**: `"What is the latest AI news today?"` → response with cited DuckDuckGo sources
  - **Web**: `"Who is the current president of France?"` → live answer with source URL
  - **Typo**: `"wht iz kinnetic enrgy"` → correctly routed to physics/science, not sandbox
  - **Multi-intent**: `"solve 2+2 and what is photosynthesis"` → both answered in sections
  - **Profile**: `"What is my name?"` (after ingesting) → name returned naturally, no tier labels
  - **Code**: `"Write a Python function for max in a list"` → Qwen3-4B render
  - **Emotional**: `"I'm feeling overwhelmed"` → warm response, no gap label
  - **Verify**: `latent_embedding_source = "external_service"` in at least one audit log entry
  - **Verify**: no `[Tier labels]` visible; warm Lambda < 30s
  - _Requirements: Full-capability end-to-end verification across all enhanced domains_

---

### Phase 9 — Frontend Chat UI Redesign

The existing `frontend/app/user/page.tsx` is a single 1000-line monolithic file with an outdated layout, no proper markdown rendering, and all insights locked in a side rail. The redesign breaks it into small focused components, adds a Claude-style icon sidebar, per-message insights bottom drawer, full GFM markdown, and mobile-first responsive design.

**Dependencies to add first:** `react-markdown` + `remark-gfm` to `frontend/package.json`.

- [ ] 26. Create shared types and Zustand store
  - **Files:** `frontend/app/user/types.ts`, `frontend/app/user/store.ts`

  - **`types.ts`** — all shared types:
    ```typescript
    export type ApiResponse = { response: string; confidence: number; gaps: string[]; sources: string[]; ir: { trace_id: string; target_ir: string; confidence: number }; capability_plan?: CapabilityPlan; capability_results?: CapabilityResult[]; layer_results: LayerResult[]; simulation_results: SimulationResult[]; trace: TraceEvent[]; /* ... full type */ };
    export type Message = { role: "user" | "assistant"; content: string; apiResponse?: ApiResponse; };
    export type Thread = { id: string; title: string; updated_at: string; created_at?: string; };
    ```

  - **`store.ts`** — Zustand store, **online-first, no localStorage for threads/messages**:
    ```typescript
    interface ChatStore {
      // Thread / message state — loaded from backend
      activeThreadId: string;
      threads: Thread[];
      messages: Record<string, Message[]>;
      threadsLoaded: boolean;
      messagesLoaded: Record<string, boolean>;
      // Drawer
      drawerOpen: boolean;
      drawerMessageIndex: number | null;
      drawerTab: string;
      // Navigation
      sidebarPanel: "threads" | "learn" | null;
      mobileNavOpen: boolean;
      // Query
      loading: boolean;
      feedbackStatus: string;
      learnedSignatureIds: Record<string, string>; // keyed by trace_id
      canvasHint: boolean;
      inventionHint: boolean;
    }
    ```

  - **Online-first thread storage**:
    - `loadThreads(apiBase, headers)` → `GET /v1/chat/threads?user_id=...&workspace_id=...&limit=50` → populate `threads`
    - `loadMessages(threadId, apiBase, headers)` → `GET /v1/chat/threads/{threadId}/messages?user_id=...&limit=200` → populate `messages[threadId]`
    - `sendQuery(input, apiBase, headers)` → POST `/v1/query`, append both user + assistant messages to store; if thread title is still "New chat", set title to first 48 chars of query
    - **No localStorage for threads or messages** — only `activeThreadId` persists in localStorage
    - On store init: restore `activeThreadId` from localStorage; threads loaded by `loadThreads` on mount

  - **Correct feedback action**:
    ```typescript
    submitFeedback(rating, message, apiBase, headers) {
      POST /v1/feedback {
        user_id, trace_id: message.apiResponse.ir.trace_id,
        rating,           // "positive" | "negative" | "correction"
        notes: "",
        workspace_id,
        thread_id: activeThreadId,
        source_signature_ids: message.apiResponse.sources  // ← key: pass actual sources
      }
    }
    ```

  - **Correct learn/unlearn actions**:
    ```typescript
    learnResponse(message, apiBase, headers) {
      // 1. Ingest the response text
      POST /v1/training/ingest {
        user_id, workspace_id, content: message.content, modality: "text",
        source_trust: Math.min(0.98, Math.max(0.5, message.apiResponse.confidence)),
        domain_hint: "learn_this_user_confirmed"
      }
      // 2. Record positive feedback
      POST /v1/feedback {
        user_id, trace_id: message.apiResponse.ir.trace_id,
        rating: "positive", notes: "learn_this",
        workspace_id, thread_id: activeThreadId,
        source_signature_ids: message.apiResponse.sources
      }
      // 3. Store returned signature.id in learnedSignatureIds[trace_id]
    }

    unlearnResponse(traceId, apiBase, headers) {
      POST /v1/memory/delete {
        user_id, workspace_id,
        signature_id: learnedSignatureIds[traceId],
        reason: "user_unlearn_response"
      }
      // Remove from learnedSignatureIds
    }
    ```

  - _Requirements: Online-first threads/messages; no localStorage for chat data; correct FeedbackRequest with source_signature_ids; correct TrainingIngestRequest fields; correct MemoryDeleteRequest_

- [ ] 27. Create MarkdownRenderer component
  - **File:** `frontend/app/user/MarkdownRenderer.tsx`
  - Install `react-markdown` and `remark-gfm`: add to `package.json` dependencies
  - Use `ReactMarkdown` with `remarkPlugins={[remarkGfm]}`
  - Custom renderers:
    - `code`: if `inline` → `<code className="inlineCode">`, else → `<CodeBlock language={lang} code={children} />`
    - `table` → wrapped in `<div className="tableWrapper">` for horizontal scroll
    - `img` → `<img className="markdownImage" loading="lazy" ... />`
    - `a` → `target="_blank" rel="noopener noreferrer"`
    - `blockquote` → `<blockquote className="markdownQuote">`
  - `CodeBlock` sub-component:
    - Header: language label on left, copy button on right
    - On copy click: write code to clipboard, swap button icon to `Check` for 1400ms, then restore
    - Uses existing `.codeBlock`, `.codeBlockHeader`, `.codeCopyButton` CSS classes
  - Add new CSS to `globals.css`:
    ```css
    .inlineCode { border: 1px solid var(--line); border-radius: 4px; padding: 1px 5px; background: var(--surface-soft); font-family: monospace; font-size: 0.91em; }
    .tableWrapper { overflow-x: auto; }
    .tableWrapper table { border-collapse: collapse; width: 100%; }
    .tableWrapper th, .tableWrapper td { border: 1px solid var(--line); padding: 7px 11px; text-align: left; font-size: 13px; }
    .tableWrapper tr:nth-child(even) { background: var(--surface-soft); }
    .markdownImage { max-width: 100%; border-radius: var(--radius); border: 1px solid var(--line); }
    .markdownQuote { border-left: 3px solid var(--accent); padding: 4px 0 4px 12px; color: var(--muted); margin: 0; }
    ```
  - _Requirements: All GFM elements render correctly; code copy works; tables scroll on mobile; images render_

- [ ] 28. Create MessageBubble component
  - **File:** `frontend/app/user/MessageBubble.tsx`
  - Props: `message: Message`, `messageIndex: number`, `apiBase: string`, `authHeaders: () => Record<string, string>`
  - **User bubble**: right-aligned, `className="message user"`, renders `<MarkdownRenderer content={message.content} />`
  - **Assistant bubble**: left-aligned, `className="message assistant"`, renders `<MarkdownRenderer content={message.content} />`
  - **Action row** (below assistant bubble only), `className="messageActions"`:
    ```tsx
    <div className="messageActions">
      <button title="Copy response" onClick={copyResponse}><Copy size={14} /></button>
      <button title="Good response" onClick={() => submitFeedback("positive")}><ThumbsUp size={14} /></button>
      <button title="Bad response" onClick={() => submitFeedback("negative")}><ThumbsDown size={14} /></button>
      <button title="View insights" className="insightsButton" onClick={() => store.openDrawer(messageIndex, "answer")}>
        <Layers3 size={14} />
      </button>
      <button title="Regenerate" onClick={onRegenerate}><RotateCcw size={14} /></button>
    </div>
    ```
  - Add CSS:
    ```css
    .messageActions { display: flex; align-items: center; gap: 4px; margin-top: 4px; padding: 0 2px; }
    .messageActions button { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 1px solid transparent; border-radius: 6px; color: var(--muted); background: transparent; cursor: pointer; }
    .messageActions button:hover { border-color: var(--line); background: var(--surface-soft); color: var(--ink); }
    .insightsButton { background: var(--accent-soft) !important; border-color: color-mix(in srgb, var(--accent) 40%, var(--line)) !important; color: var(--accent) !important; }
    ```
  - _Requirements: User/assistant styling correct; action row only on assistant; all 5 actions functional_

- [ ] 29. Create InsightsDrawer component
  - **File:** `frontend/app/user/InsightsDrawer.tsx`
  - Uses `store.drawerOpen`, `store.drawerMessageIndex`, `store.drawerTab`, `store.messages[activeThreadId]`
  - Renders as `position: fixed; bottom: 0; left: 0; right: 0` with `height: 50vh` (desktop) / `75vh` (mobile)
  - Drag handle at top center, close button at top right
  - Backdrop: `position: fixed; inset: 0; z-index: 39; background: rgba(0,0,0,0.38)` — click to close
  - Horizontal scrollable tabs: `Answer State | Sources | Reasoning | Simulation | Capability | Gaps | Memory Controls`
  - **Answer State tab**: confidence (large font), sources count, gaps count, capability kind — using `.metric` grid
  - **Sources tab**: each source ID as `.pill` with "Learn" and "Unlearn" buttons — POST to `/v1/training/ingest` and `/v1/memory/delete` respectively
  - **Reasoning tab**: layer chain using `.layerRow` — activated dot + name + deterministic label + summary
  - **Simulation tab**: each simulation with scenario name + pass (✓) / fail (✗) badge + confidence
  - **Capability tab**: plan fields in `.traceItem` rows + capability results list
  - **Gaps tab**: each gap in `.gapPanel` styled `div` with warning colors
  - **Memory Controls tab**: "Learn this response" button → POST response text to `/v1/training/ingest`; after success show "Unlearn" button; show `trace_id` as reference
  - Add CSS:
    ```css
    .insightsDrawer { position: fixed; bottom: 0; left: 0; right: 0; z-index: 40; height: 50vh; background: var(--surface); border-top: 1px solid var(--line); border-radius: 14px 14px 0 0; box-shadow: 0 -8px 32px rgba(0,0,0,0.18); display: flex; flex-direction: column; }
    .drawerHandle { width: 40px; height: 4px; border-radius: 2px; background: var(--line-strong); margin: 10px auto 0; flex: 0 0 auto; }
    .drawerHeader { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px 0; flex: 0 0 auto; }
    .drawerTabs { display: flex; gap: 4px; overflow-x: auto; padding: 10px 16px; border-bottom: 1px solid var(--line); flex: 0 0 auto; scrollbar-width: none; }
    .drawerTabs::-webkit-scrollbar { display: none; }
    .drawerTab { white-space: nowrap; border: 1px solid var(--line); border-radius: var(--radius); padding: 5px 10px; font-size: 12px; font-weight: 650; color: var(--muted); background: var(--surface-soft); cursor: pointer; }
    .drawerTab.active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
    .drawerBody { flex: 1 1 auto; overflow-y: auto; padding: 14px 16px 24px; }
    .drawerBackdrop { position: fixed; inset: 0; z-index: 39; background: rgba(0,0,0,0.38); }
    @media (max-width: 767px) { .insightsDrawer { height: 80vh; } }
    ```
  - _Requirements: All 7 tabs functional; learn/unlearn work; backdrop closes drawer; correct heights per breakpoint_

- [ ] 30. Create Sidebar component
  - **File:** `frontend/app/user/Sidebar.tsx`
  - Narrow `52px` wide sidebar, `position: sticky; top: 0; height: 100dvh; flex-shrink: 0`
  - Top section (vertically stacked with `gap: 8px`):
    - JimsAI logo mark `J` (reuse existing `.brandMark` styles)
    - `+` new thread button — calls `store.addThread()` + sets active thread
    - Chat history button (`MessageSquare` icon) — toggles `sidebarPanel: "threads"`
    - Learn button (`BookOpen` icon) — toggles `sidebarPanel: "learn"`
  - Bottom section: user avatar circle with initials — click to sign out
  - All buttons: `title` tooltip, `className="iconButton compact"`, no text labels
  - **ThreadsPanel** (slides in to the right of sidebar as `position: absolute; left: 52px; top: 0; width: 280px; height: 100dvh` panel):
    - Header: "Chats" title + "New chat" button
    - Search input (filters threads by title)
    - Scrollable thread list: each item shows `thread.title` + relative timestamp (`X days ago`, `May 24`, etc.)
    - Click thread → `store.setActiveThread(id)` + close panel
    - On mobile (`< 768px`): renders as full-screen overlay (`position: fixed; inset: 0; z-index: 50`)
  - **LearnPanel** (same positioning as ThreadsPanel):
    - Title "Teach workspace"
    - Textarea for pasting content
    - "Teach" submit button → POST to `/v1/training/ingest`, show status
  - Add CSS:
    ```css
    .sidebar { width: 52px; flex-shrink: 0; height: 100dvh; position: sticky; top: 0; display: flex; flex-direction: column; align-items: center; padding: 12px 0; gap: 8px; border-right: 1px solid var(--line); background: var(--surface); z-index: 20; }
    .sidebarBottom { margin-top: auto; }
    .avatarCircle { width: 32px; height: 32px; border-radius: 50%; background: linear-gradient(135deg, #13233a, #243b63); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 800; cursor: pointer; border: none; }
    .sidePanel { position: absolute; left: 52px; top: 0; width: 280px; height: 100dvh; background: var(--surface); border-right: 1px solid var(--line); box-shadow: var(--shadow); z-index: 19; display: flex; flex-direction: column; overflow: hidden; }
    .sidePanelHeader { display: flex; align-items: center; justify-content: space-between; padding: 14px 14px 10px; border-bottom: 1px solid var(--line); }
    .sidePanelHeader h2 { margin: 0; font-size: 15px; }
    .sidePanelSearch { margin: 10px 10px 4px; }
    .sidePanelSearch input { width: 100%; height: 36px; padding: 0 10px; border-radius: var(--radius); }
    .threadItem { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 14px; border-bottom: 1px solid var(--line); cursor: pointer; font-size: 13px; }
    .threadItem:hover { background: var(--surface-soft); }
    .threadItem.active { background: var(--accent-soft); color: var(--accent); }
    .threadTimestamp { color: var(--muted); font-size: 11px; white-space: nowrap; }
    @media (max-width: 767px) { .sidebar { display: none; } .sidePanel { position: fixed; inset: 0; width: 100vw; left: 0; z-index: 50; } }
    ```
  - _Requirements: Icon-only sidebar; ThreadsPanel with search and relative timestamps; LearnPanel posts to API; mobile full-screen overlay_

- [ ] 31. Create Composer component
  - **File:** `frontend/app/user/Composer.tsx`
  - Floating box centered, `max-width: 760px`, `width: calc(100% - 32px)`, elevated shadow
  - Grid: `[attach-btn] [textarea] [actions]` on a single row, actions below on small screens
  - Left: `<Paperclip>` button → triggers hidden `<input type="file">` → reads file as text, appends to textarea
  - Center: auto-resize `<textarea>` — grows up to 220px
    - `onKeyDown`: if `Enter` without `Shift` → submit; if `Shift+Enter` → let browser insert newline (do NOT call `preventDefault`)
    - Placeholder: `"Ask JimsAI anything..."`
  - Bottom-right row inside composer: canvas hint toggle + invention hint toggle + model label `"Qwen3"` + send button
  - Send button: disabled when `store.loading`
  - On submit: `store.setLoading(true)`, `store.appendMessage(threadId, {role:"user", content: query})`, POST to `/v1/query`, on response `store.appendMessage(threadId, {role:"assistant", content: data.response, apiResponse: data})`, `store.setLoading(false)`
  - On mobile (`< 768px`): `position: sticky; bottom: 0` above the bottom tab bar, full width
  - Reuse and extend existing `.composer`, `.composerActions`, `.sendButton` CSS classes — add:
    ```css
    .composerModelLabel { color: var(--muted); font-size: 12px; font-weight: 650; padding: 0 4px; }
    .hintToggle { min-width: 32px; height: 32px; border-radius: 6px; border: 1px solid var(--line); background: transparent; color: var(--muted); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
    .hintToggle.active { background: var(--accent-soft); border-color: color-mix(in srgb, var(--accent) 50%, var(--line)); color: var(--accent); }
    ```
  - _Requirements: Enter/Shift+Enter correct; file attach works; canvas/invention toggles; send dispatches to store; mobile sticky_

- [ ] 32. Create MessageList component
  - **File:** `frontend/app/user/MessageList.tsx`
  - Renders `store.messages[activeThreadId]` mapped to `<MessageBubble>` components
  - Auto-scrolls to bottom on new message — `useEffect` on messages length, `scrollIntoView` on a sentinel `div`
  - Shows a loading indicator (spinning `Loader2` icon) when `store.loading` is true, appended after last message
  - Empty state: centered "Start a conversation" text when messages list has only the initial assistant message
  - Reuse `.messages`, `.message`, `.markdownMessage` CSS classes
  - Add: `@media (max-width: 767px) { .message { max-width: 100%; width: auto; } }`
  - _Requirements: Auto-scroll works; loading state shown; all messages rendered; mobile full-width_

- [ ] 33. Create ChatLayout and wire everything
  - **File:** `frontend/app/user/ChatLayout.tsx`
  - Root element: `<div className="chatRoot">` — `display: flex; flex-direction: row; height: 100dvh; overflow: hidden`
  - Children: `<Sidebar />` + `<div className="chatMain">` containing `<MessageList />` and `<Composer />`
  - Add CSS:
    ```css
    .chatRoot { display: flex; flex-direction: row; height: 100dvh; overflow: hidden; background: var(--canvas); }
    .chatMain { flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }
    .mobileTabBar { display: none; }
    @media (max-width: 767px) {
      .chatRoot { flex-direction: column; }
      .chatMain { padding-bottom: 56px; } /* space for tab bar */
      .mobileTabBar { display: flex; position: fixed; bottom: 0; left: 0; right: 0; height: 56px; background: var(--surface); border-top: 1px solid var(--line); z-index: 30; justify-content: space-around; align-items: center; padding: 0 16px; }
      .mobileTabBar button { display: flex; flex-direction: column; align-items: center; gap: 3px; font-size: 10px; color: var(--muted); background: none; border: none; cursor: pointer; padding: 4px 8px; }
      .mobileTabBar button.active { color: var(--accent); }
    }
    ```
  - Mobile tab bar (visible only `< 768px`): 4 icon+label buttons — New Chat (`+`), History (`MessageSquare`), Learn (`BookOpen`), Profile (avatar)
  - Remove the old `appHeader` from `layout.tsx` for the chat route — the new sidebar replaces it on chat pages, or keep it but hide on chat route
  - Render `<InsightsDrawer />` at root level so it overlays everything
  - **Update `frontend/app/user/page.tsx`**: replace the entire content with:
    ```tsx
    "use client";
    import ChatLayout from "./ChatLayout";
    export default function UserPage() { return <ChatLayout />; }
    ```
  - Preserve all existing API call logic (`/v1/query`, `/v1/feedback`, `/v1/training/ingest`, `/v1/memory/delete`, `/v1/chat/threads`, `/v1/auth/*`) — move it into the store actions and component-level `useCallback` hooks
  - _Requirements: Full layout assembled; mobile tab bar works; InsightsDrawer overlays; page.tsx is thin shell_

- [ ] 34. E2E smoke tests for the new chat UI
  - **File:** `frontend/tests/chat-ui.spec.ts` (Playwright)
  - Test: sign-in flow renders auth form → submit → chat layout appears
  - Test: type message → press Enter → user bubble appears → loading indicator shows → assistant bubble appears
  - Test: click Insights button on assistant bubble → InsightsDrawer opens → shows "Answer State" tab
  - Test: click backdrop → InsightsDrawer closes
  - Test: click `+` button in sidebar → new thread created → empty chat state
  - Test: resize viewport to 375px → mobile tab bar visible, sidebar hidden
  - Mock `/v1/query` response in tests to avoid real API dependency
  - _Requirements: Core user flows covered; mobile viewport tested; drawer open/close tested_

---

## Notes

- Tasks 1–12 are complete (marked `[x]`). Implementation work starts at Task 16.
- Tasks 16–19, 21 (code quality) are fast — each is a targeted fix. Do these first.
- Tasks 22–25 (full capability unlocks) are the substantial backend engineering.
- Tasks 26–34 (frontend redesign) are independent of backend tasks — can run in parallel.
- Task 26 (store + types) must be done before Tasks 27–33 (components depend on it).
- Task 33 (ChatLayout wire-up) must be last among frontend tasks — it assembles everything.
- Task 34 (E2E tests) runs after Task 33.
- Deploy sequence remains: HF Space (14) → Lambda (15) → live tests (20).

---

## Task Dependency Graph

```
1–12 ✓ (complete)
16 (add logger) → independent
17 (remove duplicate Modality) → independent
18 (replace print with logger) → 16
19 (fix AdaptiveHybridEncoder timeout) → independent
21 (remove dead code) → independent
22 (math step-by-step + extended domains) → independent
23 (wire web search) → independent
24 (T1/T2 model swap) → 19
25 (prompt robustness) → 24
26 (store + types) → independent (frontend)
27 (MarkdownRenderer) → 26
28 (MessageBubble) → 27
29 (InsightsDrawer) → 26
30 (Sidebar) → 26
31 (Composer) → 26
32 (MessageList) → 28
33 (ChatLayout wire-up) → 27, 28, 29, 30, 31, 32
34 (E2E tests) → 33
13 (deploy script) → 16, 17, 18, 19, 21, 22, 23, 24, 25
14 (deploy HF Space) → 19, 24
15 (deploy Lambda) → 13, 14
20 (live tests) → 14, 15
```

**Execution waves:**
- **Wave A (parallel):** 16, 17, 19, 21, 22, 23, 26
- **Wave B (after Wave A):** 18 (after 16), 24 (after 19), 27/29/30/31 (after 26)
- **Wave C (after Wave B):** 25 (after 24), 28 (after 27), 32 (after 28)
- **Wave D (after Wave C):** 33 (after 27–32), 13 (deploy script after backend work)
- **Wave E:** 34 (after 33), 14 (HF Space deploy after backend)
- **Wave F:** 15 (Lambda) → 20 (live tests)

