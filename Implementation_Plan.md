# Implementation Plan: Tiered Confidence Framework, Reactive Traceback, & Adaptive Multilingual Alignment (With L5 MCTS & Rollback Upgrades)

This implementation plan outlines the engineering transition of JIMS-AI to a highly responsive, self-correcting **Closed-Loop Neuro-Symbolic Operating System**. 

By separating the core computational workloads, JIMS-AI uses small models ($1.7\text{B} - 4\text{B}$ parameters) loaded on CPUs or light GPUs for real-time task boundary translation, while offloading logic, memory, and validation to relational, vector, and graph databases. Heavy learning is handled asynchronously via offline GPU batch training, keeping inference overhead and costs extremely low.

Additionally, this plan integrates **Tier Thresholds**, **Provenance Output Labels**, a **24-Hour Rollback window**, and upgrades the **L5 Invention Engine** to run a **Monte Carlo Tree Search (MCTS) and Sandbox Self-Correction Loop**.

---

## Architectural Pillars

### 1. Tiered Confidence Framework & Provenance Labels
Instead of using flat confidence values or binary logic gates, JIMS-AI ranks queries and claims using a dynamic **5-Tier Confidence Model** bound to specific provenance classes. 

The final rendered response must always include the corresponding **Provenance Label** tag:

| Tier | Confidence Range | Provenance Class & Verification Method | Rendered Provenance Label |
| :--- | :--- | :--- | :--- |
| **Tier 1** | **99% – 100%** | Symbolic solver execution, arithmetic validation, sandbox unit test passes. | `[Verified • Symbolic Solver]` |
| **Tier 2** | **90% – 98%** | Exact relational database matches, human-approved memories. | `[High Confidence • Approved Memory]` |
| **Tier 3** | **70% – 89%** | Fine-tuned semantic weights matching, concept lattice analogies. | `[Plausible • Learned Pattern]` |
| **Tier 4** | **40% – 69%** | Low-similarity vector hits, stale timestamps. (Triggers warning block). | `[Unverified • Needs Review]` |
| **Tier 5** | **< 40%** | Unresolved capability execution, failed sandboxes, or missing sources. | `[Gap • Unresolved]` |

### 2. Reactive Traceback (Post-Ingest Audit) & Rollback Safety
We are replacing the blocking **Pre-Ingest Gate** with a Git-like **Post-Ingest Audit** flow:
- **Instant Commit:** Ingestion and resolution memory logs immediately insert facts into active memory stores (Postgres, Vectorize, Neo4j).
- **Reasoning Citations:** Response claims outputted by JIMS-AI are tagged with the exact database IDs (`source_signature_ids`) from which they were retrieved.
- **Auditing & Corrections:** Humans review chat responses in production. If a claim is wrong, the operator clicks its citation to trace it back, perform a reactive edit/deletion on that specific signature, and propagate updates instantly.
- **Rollback Safety (24h Undo Window):** To protect the database from corrupt or low-quality bulk uploads, JIMS-AI implements a transaction rollback endpoint. This allows an operator or script to undo all memory signatures committed within a sliding **24-hour window** based on `created_at` timestamps.

### 3. Adaptive Multilingual Intent Routing
To fix the production serverless bottleneck where AWS Lambda falls back to a rigid, English-only `_FallbackClassifier` (returning flat `GENERAL_FACT` with $0.5$ confidence):
- **Remote Semantic Intent Classifier:** If local `sentence-transformers` is unavailable, JIMS-AI queries the Hugging Face Space endpoint `/v1/embed` over HTTP to obtain query embeddings, and performs cosine similarity calculations locally against cached prototype vectors.
- **Error-Tolerant Multilingual Prototypes:** Prototype descriptor texts are expanded to cover multilingual command terms (e.g. Yoruba, Igbo, Hausa) and typo-ridden variations.

### 4. Bounded T2 Rendering & Dual Fine-Tuning
- **Conversational Rendering:** The $T_2$ render skip condition is optimized to ensure conversational, multi-language, or style-specific inputs are never bypassed, instructing Qwen to match user tone/language while keeping retrieved facts invariant.
- **Asynchronous Batch GPU Training:** Relational, vector, and graph databases ingest and delete signatures in real-time. Asynchronously, the training pipeline compiles these audited records and runs offline fine-tuning scripts on GPU compute nodes (using Kaggle or another GPU executor) across three specific tasks:
  * `encoder_finetune`: Fine-tuning the multilingual E5 encoder to improve retrieval precision.
  * `sppe_renderer_finetune`: Fine-tuning the Qwen3-4B model on SPPE pairs to align rendering fluency.
  * `sppe_refiner`: Fine-tuning the Qwen3-1.7B model to improve $T_1$ intent compilation.

### 5. L5 Invention Engine MCTS & Self-Correction Upgrade
To allow a 4B parameter model to solve highly complex multi-step coding logic and out-of-domain concepts, we upgrade the Invention Engine to run search-based reasoning (test-time compute) at inference:
- **Dynamic Task Decomposition:** Break down coding or concept synthesis into tree-structured micro-steps instead of a static linear plan.
- **MCTS Node Search:** Build an active search tree where nodes represent candidate code blocks, reasoning claims, or functions. The engine runs Selection, Expansion, Simulation, and Backpropagation iterations.
- **Interactive Sandbox & Causal Simulation:** For each generated child node, the engine executes it inside the local air-gapped Python sandbox (for code compilation/testing) or queries Neo4j (for concept causal dependency validity).
- **Simulated Reflection:** If a candidate node fails verification, JIMS-AI extracts the fail/compilation log, prunes the branch, and prompts the Qwen model to generate corrected alternative child nodes.
- **Rollout Selection:** Selects the path with the highest verified backpropagated confidence, delivering a verified solution to the T2 renderer.

### 6. Adaptive Hybrid Ingestion Encoder (`AdaptiveHybridEncoder`)
To dramatically improve retrieval accuracy on highly technical, mathematical, and programming domains while keeping operational overhead low:
- **Weighted Embeddings Fusion:** The encoder combines semantic embeddings (`multilingual-e5-small`, 50% weight), code embeddings (`codebert-base`, 25% weight), and technical embeddings (`jina-embeddings-v3`, 25% weight) into a single representational space, projected uniformly to 768 dimensions.
- **Symbolic Processing Augmentation:** Utilizes the [SymbolicAugmenter](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/encoder/adaptive_hybrid_encoder.py) to perform math normalization (SymPy-backed standard form translation), regex-based structural code block extraction, and causal statement parsing.
- **Serverless & Local Dual Compatibility:** Runs heavy inference models locally when dependencies are available (e.g. GPU training context), but falls back automatically to HTTP remote space endpoints (`/v1/embed`) when executed inside constrained environments (like AWS Lambda) to preserve zero cold-start limits.

---

## Critical Edge Cases & Robustness Solutions

To ensure JIMS-AI remains robust under edge conditions across different domains, the following algorithmic solutions and test cases are integrated into the development roadmap:

### 1. Multi-Equation Variable Coordination (Math/Science Domain)
- **Edge Case:** Systems of simultaneous linear or non-linear equations (e.g., `2x + y = 10` and `x - y = 2`) outputted by standard LLMs are often parsed incorrectly, causing symbolic solver crashes.
- **Robustness Solution:** Update `math_solver.py` to detect comma-separated or multi-line mathematical constraints, translating them to SymPy's multi-variable equation solver. If variable mapping or resolution fails, fallback to a Tier 5 Gap payload.
- **Verification Test:** `tests/test_tiered_confidence.py` ➔ `test_simultaneous_equations_solving()`.

### 2. Sandbox Resource Exhaustion & Infinite Loops (Coding Domain)
- **Edge Case:** Generated code contains infinite loops (`while True: pass`) or deep recursion, leading to sandbox execution hangs or CPU thread locking.
- **Robustness Solution:** Ensure the sandbox runner (`pipeline.run_sandbox`) captures timeout executions and returns a distinct `TimeoutError` status payload. The MCTS loop prunes the node, sets its score to `0.0`, and uses the timeout trace to trigger self-correction reflection loops.
- **Verification Test:** `tests/test_invention_mcts.py` ➔ `test_sandbox_infinite_loop_mitigation()`.

### 3. Causal Conflict & Semantic Concept Drift (General Domain)
- **Edge Case:** A new document contradicts an existing database fact (e.g. migrating database models), causing conflicting Neo4j graph nodes and vector queries.
- **Robustness Solution:** Update the L2 Real-Time Learning Layer to perform a temporal conflict check on predicate slots (same subject/predicate, different object). If a conflict is found, the older signature is downgraded to Tier 4 (`UNVERIFIED_STALE_MEMORY`), and an alert is placed on the Human Review Queue.
- **Verification Test:** `tests/test_rollback_safety.py` ➔ `test_causal_conflict_downgrades_stale_signature()`.

### 4. Dangling Graph Edges & Vector Decoupling (Rollback Safety)
- **Edge Case:** Executing a 24-hour rollback deletes signatures from Postgres but leaves orphaned relationship edges in Neo4j and dangling vectors in Vectorize, causing database search crashes.
- **Robustness Solution:** Update the rollback engine endpoint `rollback_memory` to execute transactional cascading deletions across all three layers (metadata database, graph engine, and vector search).
- **Verification Test:** `tests/test_rollback_safety.py` ➔ `test_cascading_rollback_clears_graph_and_vectorize()`.

### 5. Stale Topic Drift & Session Context Bloat (No-Instruction / Vague Queries) (NEW)
- **Edge Case:** The user shifts topics without explicit instructions. For example, they were debugging `Node-09` (`ACTIVE_OBJECT = Node-09`), and then paste a raw SQL query related to a completely different module. The compiler inherits the stale `Node-09` context.
- **Robustness Solution:** Update `pipeline.py` context inheritance logic to check for semantic similarity (vector distance) between the new vague query and the inherited entity. If semantic similarity is low ($< 0.35$) or if the idle time between messages exceeds 15 minutes, decouple the working memory and clear the active entity context.
- **Verification Test:** `tests/test_multilingual_routing.py` ➔ `test_context_decoupling_on_topic_drift()`.

### 6. Intent Conflict on Ambient Queries (Multi-Intent Snippets) (NEW)
- **Edge Case:** The user inputs a prompt that is a Python function containing embedded math formulas (e.g., `def calc_tax(): return x * 0.15`). The compiler flags both `coding` (due to syntax) and `math_science` (due to formula operators) and crashes trying to parse Python code inside the symbolic SymPy solver.
- **Robustness Solution:** Update `capability_router.py` to route multi-intent snippets to `coding` as the primary handler. The symbolic math engine is only invoked on values explicitly extracted and isolated by Qwen during sandbox runs, rather than parsing the code raw.
- **Verification Test:** `tests/test_tiered_confidence.py` ➔ `test_ambient_math_in_code_routing()`.

---

## User Review Required

> [!IMPORTANT]
> **Active Memory Deployment:** Data committed to Postgres, Vectorize, and Neo4j goes live instantly. However, deploying **fine-tuned neural weight artifacts** generated by Kaggle still requires a verification check before hot-swapping onto production model endpoints.

> [!WARNING]
> **Production API Network Calls:** Upgrading Lambda's compiler runtime to use remote semantic embeddings means Lambda will execute HTTP requests to the Hugging Face Space. This adds a slight HTTP call overhead during the intent parsing phase but ensures accurate intent compilation under serverless constraints.

---

## Proposed Changes

### 1. Codebase Layer: Models & Core API

#### [MODIFY] [models.py](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/models.py)
- Add `ProvenanceClass` enum representing the 6 verification levels.
- Add `source_signature_ids: list[str]` and `provenance_class: ProvenanceClass` to `ReasoningStep`.
- Update `VerifiedCognitiveObject` to contain and track the computed overall confidence tier.
- Update `InventionResult` schema to carry structured MCTS traces, node scores, and simulation/reflection metrics.
- Add `MemoryRollbackRequest` and `MemoryRollbackResponse` schemas to support time-based undo requests.

---

### 2. Codebase Layer: Query & Ingestion Pipelines

#### [NEW] [adaptive_hybrid_encoder.py](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/encoder/adaptive_hybrid_encoder.py)
- Implement `SymbolicAugmenter` to extract code blocks, normalize formulas, and parse causal entities.
- Implement `AdaptiveHybridEncoder` supporting weighted stack fusion of multilingual semantic (E5), code (CodeBERT), and technical (Jina) embeddings.
- Add dynamic HTTP fallback `/v1/embed` when transformers modules are absent (production Lambda environment).

#### [NEW] [__init__.py](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/encoder/__init__.py)
- Expose `AdaptiveHybridEncoder` and `SymbolicAugmenter` imports to package boundaries.

#### [MODIFY] [encoder.py](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/encoder.py)
- Update `DualRepresentationEncoder` to import and wrap `AdaptiveHybridEncoder` internally for high-accuracy embedding fusion and structured abstraction tag generation.

#### [MODIFY] [pipeline.py](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/pipeline.py)
- **Traceback Citations:** Modify the exact, semantic, and graph retrieval pipelines to append source `MemorySignature.id` references to `ReasoningStep.source_signature_ids`.
- **Dynamic Confidence Tier:** Implement logic in the reasoning bridge layer to compute overall confidence based on the minimum confidence or weighted average of the reasoning step levels.
- **Instant Commits:** Update `_learn_from_resolved_prompt` to insert signatures into `self.memory` and `self.graph` instantly.
- **Low-Resource Language Recognition:** Enhance `_response_language_hint` to detect low-resource dialects (such as ASCII Yoruba, Igbo, and Hausa) to trigger the correct translation and render paths.
- **Rollback Engine Endpoint:** Implement `rollback_memory(self, request: MemoryRollbackRequest)` to delete all signatures committed within the defined time range (e.g. last 24h) from `self.memory`, Postgres, and Neo4j.
- **Context Decoupling:** Update the context inheritance logic to clear `ACTIVE_OBJECT` on topic drift or time gaps.

#### [MODIFY] [app.py](file:///c:/Users/ajibe/Jims-AI/prototype/app.py)
- Expose the POST endpoint `/v1/memory/rollback` to allow administrators/operators to trigger sliding-window undo actions on recently ingested data.

#### [MODIFY] [semantic_compiler.py](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/semantic_compiler.py)
- **Remote Semantic Intent Classifier:** Re-implement `_FallbackClassifier` as a HTTP-based classifier. If `sentence_transformers` is missing, it connects to `/v1/embed` using `JIMS_EMBEDDING_SERVICE_URL` and `JIMS_EMBEDDING_SERVICE_TOKEN` to retrieve 768-dimension vectors and computes cosine similarity locally.
- **Multilingual Prototypes:** Expand the template vectors and prototype texts to support common spelling errors and multilingual command keywords.

#### [MODIFY] [csse.py](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/csse.py)
- **Hedged and Tagged Output Rendering:**
  * Prepend logical hedging qualifiers (e.g. *"Based on workspace patterns, it is likely that..."*) to Tier 3 claims.
  * Append warning tags and traceback links directly to Tier 4 outputs: `⚠️ [Unverified Memory] [Fix/Edit](file:///v1/memory/edit/{id})`.
  * Prepend or append the exact calculated **Provenance Label** (e.g. `[Verified • Symbolic Solver]`) to the rendered output block.
  * Output reasoning traceback blocks containing clickable source links at the end of the text.

#### [MODIFY] [model_bridge.py](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/model_bridge.py)
- **T2 Rendering Contract:** Query rendering must go through the bounded T2 renderer; renderer unavailability is surfaced as a service error instead of using a deterministic bypass.
- **Prompt Translation & Style Match:** Update the system prompt in `render()` to instruct Qwen to translate the verified cognitive object facts to match the user query's language and style, prepending the structured Provenance Label at the top of the output.
- **Candidate Node Scoring:** Add a method `evaluate_candidate_node` to let the local model score the logical consistency of alternative branches during MCTS node expansion.

#### [MODIFY] [planner.py](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/planner.py)
- **Dynamic Program Decomposition:** Update `SymbolicPlanner` to parse complex coding and concept targets and decompose them into multi-step tree-like steps instead of a static list.

#### [MODIFY] [simulation.py](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/simulation.py)
- **Advanced Causal Simulation:** Enhance `BoundedSimulationEngine` to support node validation. Add functions to verify path connectivity, constraint checks, and check generated signature code layouts against existing AST configurations.

#### [MODIFY] [runtime_layers.py](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/runtime_layers.py)
- **Invention MCTS Search Loop:** Re-engineer `InventionEngineLayer.run` to implement the MCTS tree loop:
  * Run Selection using UCT (Upper Confidence Bound for Trees).
  * Expand nodes using the `model_bridge.invention_candidates` generator.
  * Simulate outcomes using the sandbox runner (`pipeline.run_sandbox`) and causal engine (`simulation.run`).
  * Backpropagate pass/fail scores to update node values.
  * Run reflection prompts to regenerate children of failed nodes.
  * Extract the best path and return it in the updated `InventionResult`.

---

### 3. Codebase Layer: Autonomous Loop & Training

#### [MODIFY] [autonomous_training_agent.py](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/autonomous_training_agent.py)
- **Repurpose Step 8 Gate:** Align `_await_human_approval` to gate model weights and encoder deployments, freeing the memory database from blocking pre-approvals.
- **Continuous SPPE Feedback Ingestion:** Update training payload builders to gather SPPE pairs from reactively audited memory signatures for the next training cycle.

#### [MODIFY] [kaggle_orchestrator.py](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/kaggle_orchestrator.py)
- **Dual Fine-Tuning Execution:** Ensure compilation scripts correctly handle `task_type` packaging for `encoder_finetune` (E5 embeddings), `sppe_renderer_finetune` (Qwen3-4B rendering), and `sppe_refiner` (Qwen3-1.7B intent parsing).

---

## Verification Plan

### Automated Tests
1. **Tiered Confidence Test Suite:** Create `tests/test_tiered_confidence.py` to assert correct tier calculations for solver vs. semantic retrieval results and verify output Provenance Labels. Also contains `test_simultaneous_equations_solving()` and `test_ambient_math_in_code_routing()`.
2. **Traceback Test Suite:** Create `tests/test_traceback_ingestion.py` to ingest a test signature, query the pipeline, and assert that the response's `ReasoningStep` contains the exact ingested signature ID.
3. **Rollback Safety Test Suite:** Create `tests/test_rollback_safety.py` to commit a test signature, trigger a rollback call for the last 24h, and verify that the signature is removed from memory stores. Also contains `test_cascading_rollback_clears_graph_and_vectorize()` and `test_causal_conflict_downgrades_stale_signature()`.
4. **Multilingual Routing Test Suite:** Create `tests/test_multilingual_routing.py` to test semantic compilation of Yoruba, Spanish, and grammatically incorrect inputs in serverless environments. Also contains `test_context_decoupling_on_topic_drift()`.
5. **MCTS Search Verification Suite:** Create `tests/test_invention_mcts.py` to assert that complex coding tasks trigger the sandbox compile-test loop and run self-correction cycles correctly. Also contains `test_sandbox_infinite_loop_mitigation()`.
6. **Adaptive Hybrid Encoder Verification Suite:** Create `tests/test_adaptive_hybrid_encoder.py` to assert correct fusion weights, math normalization using SymPy or regex fallbacks, code extraction, and remote API fallback.
7. **Execution Command:**
   ```powershell
   pytest tests/test_tiered_confidence.py
   pytest tests/test_traceback_ingestion.py
   pytest tests/test_rollback_safety.py
   pytest tests/test_multilingual_routing.py
   pytest tests/test_invention_mcts.py
   pytest tests/test_adaptive_hybrid_encoder.py
   ```

### Manual Verification
1. **Ingest Test Fact:** Execute an ingest call via curl:
   ```bash
   curl -X POST http://localhost:8000/v1/training/ingest `
     -H "Content-Type: application/json" `
     -d '{"user_id": "local", "content": "The database host has been migrated to DB_NODE_09.", "source_trust": 0.95}'
   ```
2. **Query Immediately in Yoruba:** Request the database host in Yoruba:
   ```bash
   curl -X POST http://localhost:8000/v1/query `
     -H "Content-Type: application/json" `
     -d '{"user_id": "local", "query": "Nibo ni data-base wa?"}'
   ```
3. **Check Response Traceback & Translation:** Verify that the response uses the local model to answer in natural Yoruba, includes the Provenance Label tag, lists the ingested signature ID as the traceback source, and maps to the correct confidence tier.
4. **Trigger Rollback:** Run rollback for the last 24 hours:
   ```bash
   curl -X POST http://localhost:8000/v1/memory/rollback `
     -H "Content-Type: application/json" `
     -d '{"user_id": "local", "time_window_hours": 24}'
   ```
5. **Recheck Query:** Run query again and verify that the fact has been reverted and the system reports a knowledge gap.
