# JIMS-AI v9: Memory-Centric General Capability Architecture

Status: implementation target layered on top of `JimsAI_Complete_Specification_v8.pdf`.

## Goal

JIMS-AI v9 keeps the v8 memory-centric brain and adds a general capability layer for public-facing AI use:
text chat, coding, world knowledge, math/science, creative writing, media generation, and approved agentic
task execution.

The goal is not to become one giant standalone transformer. The goal is to become a structured intelligence
system that uses transformers and generators as bounded interfaces/tools while JIMS-AI owns memory, routing,
source grounding, retrieval, causal reasoning, verification, human review, and continuous improvement.

## Non-Negotiable Principles

1. Transformers are interfaces, not the brain.
2. Generators are adapters, not trusted reasoning engines.
3. Persistent memory is the primary context system.
4. Every capability route must produce typed plans, traces, confidence, and gaps.
5. All external outputs must pass verification before becoming memory or final user claims.
6. Human approval is required for risky tool execution, video generation, irreversible changes, or low-confidence world-model updates.
7. Training is unified: ingestion produces signatures, SPPE pairs, world-model candidates, review items, retrieval signals, and future fine-tuning batches.

## v9 Layer Addition

v9 adds two runtime layers around the v8 chain:

- `V9_persistent_retrieval_hydration`: hydrates local runtime memory from Vectorize and Supabase before L6 retrieval.
- `V9_capability_router`: selects a typed public-facing task capability after L4 sparse activation.

`V9_capability_router` selects one of:

- `memory_chat`
- `world_knowledge`
- `coding`
- `math_science`
- `creative_text`
- `image_generation`
- `audio_generation`
- `video_generation`
- `agentic_task`

The router does not answer, browse, generate, or execute. It only returns a typed `CapabilityPlan`.

## Runtime Flow

1. User prompt enters protected API with Supabase identity and workspace scope.
2. T1 converts messy human language into bounded Semantic IR, but adaptive thinning skips T1 when deterministic intent confidence is high.
3. L1 creates dual representation: structured signature plus latent vector when available.
4. L2 performs real-time learning, conflict checks, and multi-index insertion.
5. `V9_persistent_retrieval_hydration` pulls relevant persisted signatures from Vectorize/Supabase into the local runtime graph.
6. L3 Active Canvas may synthesize large-context patterns when explicitly routed.
7. L4 sparse activation selects retrieval/canvas/invention/sandbox.
8. V9 capability router selects the task capability.
9. V9 capability adapters report configured providers or block unavailable/risky execution.
10. L5-L9 perform invention, retrieval, abstraction, world-model activation, simulation, and reasoning bridge.
11. CSSE renders only verified cognitive objects.
12. T2 may improve fluency, but adaptive thinning skips T2 when CSSE already has a high-confidence sourced answer.
13. Feedback and human review update memory, training signals, and future Kaggle batches.

## Codebase Implementation Overview

The current implementation is intentionally incremental and mapped to v8/v9 layers:

| Area | File(s) | Role |
| --- | --- | --- |
| Runtime orchestration | `prototype/jimsai/pipeline.py` | Strict layer chain, persistent hydration, capability routing, training dashboard, Kaggle run scheduling. |
| L1 encoder | `prototype/jimsai/encoder.py` | Dual structured/latent signature creation, entity/relation/causal extraction, modality routing. |
| L2 memory | `prototype/jimsai/memory.py` | Four-layer memory, entity/temporal/causal indexes, workspace/user visibility. |
| Retrieval | `prototype/jimsai/retrieval.py` | Multi-index local retrieval over structured, causal, semantic, and importance signals. |
| Cloud persistence | `prototype/jimsai/provider_adapters.py` | R2 artifacts, Supabase signatures/panels, Vectorize query/insert, Neo4j graph, Redis/Celery. |
| T1/T2 interfaces | `prototype/jimsai/model_bridge.py`, `prototype/jimsai/runtime_layers.py` | Bounded Groq calls with adaptive skip reasons in trace output. |
| v9 capabilities | `prototype/jimsai/capability_router.py` | Deterministic capability classification and provider gate reporting. |
| Auto training detection | `prototype/jimsai/training_policy.py` | Threshold-based Kaggle training readiness decisions with human approval preserved. |
| Kaggle training | `prototype/jimsai/kaggle_orchestrator.py` | KaggleHub dataset upload package, notebook template, output sync and hot-swap staging. |
| API | `prototype/app.py` | Protected chat, training, feedback, panel pagination, Kaggle endpoints. |
| User UI | `frontend/app/user/page.tsx`, `frontend/app/globals.css` | Enterprise chat layout with Supabase auth, sources, gaps, layer traces, capability display. |
| Training UI | `frontend/app/training/TrainingPanelClient.tsx` | Separate panel pages, infinite pagination, ingestion, canvas/invention scheduling, Kaggle run trigger, auto-training status. |

## Persistent Retrieval Strategy

JIMS-AI must not depend on whatever happens to be in process memory.

Current target behavior:

- Training ingestion stores raw content in R2.
- Extracted `MemorySignature` payloads are stored in Supabase.
- Signature vectors are inserted into Cloudflare Vectorize.
- Structured relationships are upserted to Neo4j Aura.
- Runtime startup hydrates recent signatures from Supabase.
- Each user prompt performs Vectorize nearest-neighbor lookup and loads matching signatures from Supabase before L6 retrieval.
- Workspace/user scope is enforced before signatures are visible to the runtime.

This makes retrieval better as the system grows because evidence is first persisted, then pulled into the deterministic chain with source IDs and confidence.

## Encoder Training And Auto-Improvement

Every ingest automatically produces:

- a structured memory signature;
- a latent vector when an encoder/provider is available;
- SPPE training pair;
- world-model candidate set;
- ambiguity/review cases;
- persisted panel records;
- an `AutoTrainingDecision` with counters and threshold reason.

Kaggle training does not run after every single ingest. It becomes eligible when:

- enough new SPPE pairs accumulate;
- enough media signatures are queued for multimodal encoder work;
- retrieval misses cross a reranker threshold;
- enough accepted human-reviewed pairs exist;
- a scheduled training window begins.

New weights are activated only after validation and human approval. This keeps the system progressive without allowing unreviewed model drift.

## Reducing External T1/T2 Usage

v9 adds adaptive transformer thinning:

- T1 is skipped when deterministic intent confidence is already high and the route is not a risky/ambiguous route.
- T2 is skipped when CSSE can render a high-confidence sourced answer with no gaps.
- Trace output records `groq_skip_reason` so operators can see when the system is relying on deterministic infrastructure.

The long-term target is to reduce T1/T2 calls as the encoder, compiler, retrieval, and CSSE improve, while still allowing bounded external interfaces for messy input and fluent output when useful.

## Lower Energy Usage

v9 does not claim zero energy or universally lower energy. It targets lower repeated inference cost through:

- memory-first routing for known/workspace questions;
- structured retrieval instead of stuffing every past document into a prompt;
- sparse activation so expensive tools run only when needed;
- batch encoder training on Kaggle instead of always-on local GPU inference;
- small T1/T2 boundary models instead of a giant model call for every step;
- adaptive T1/T2 thinning when deterministic confidence is high;
- persistent indexes in Supabase, Neo4j, Vectorize, and R2.

High-energy routes still exist: image/video/audio generation, large code runs, and model training.

## Infinite Context Definition

JIMS-AI v9 does not have a literal infinite transformer context window. It has persistent memory beyond a prompt
window:

- raw artifacts in R2;
- signatures in Supabase;
- entity/causal graph in Neo4j;
- latent vectors in Vectorize;
- workspace/user scoped retrieval;
- Active Canvas for large data passes;
- human-reviewed abstractions and world models.

The practical bottleneck is retrieval quality. v9 therefore treats "infinite context" as persistent memory with
retrieval, not as unlimited tokens.

## Low Hallucination Strategy

v9 reduces hallucination through:

- source signatures for factual claims;
- explicit gaps when no source supports a claim;
- confidence scoring;
- conflict checks during learning;
- causal graph validation;
- simulation before causal/impact answers;
- constrained rendering that cannot add new claims;
- provider result provenance;
- human correction and review loops.

It can still fail when extraction is wrong, training data is false, retrieval misses the right evidence, or a
provider returns bad output. v9 must expose those risks, not hide them.

## Capability Provider Matrix

| Capability | Primary route | Required provider type | Verification |
| --- | --- | --- | --- |
| Text chat | memory first | Groq T1/T2 optional | source/gap/confidence |
| World knowledge | web augmented retrieval | search/fetch API | freshness and citations |
| Coding | docs + sandbox | docs search, package metadata, test runner | tests/static checks |
| Math/science | solver verified | calculator, symbolic solver, paper retrieval | calculation trace |
| Creative text | CSSE style memory | T2 renderer optional | style constraints |
| Image generation | provider adapter | image model API | prompt safety, asset provenance |
| Audio generation | provider adapter | TTS/audio model API | voice rights, asset provenance |
| Video generation | provider adapter | video model API | human approval, provenance |
| Agentic tasks | approved tool execution | browser/API/job tools | permissions, dry run, rollback |

## UI Requirements

The user and training UI must show why JIMS-AI is different:

- clean enterprise chat surface with strong spacing, stable composer, and theme-aware colors;
- collapsible side panels so users can create more working space;
- sources, gaps, confidence, capability route, and trace visible without overwhelming the answer;
- training pages separated by concern: ingestion, review, ambiguity, memory, world model, pipeline, sessions, feedback;
- infinite pagination over stored provider-backed panel data;
- visible auto-training decision and Kaggle run state;
- no hidden local-only fallback as the production default.

The default UI must stay operational rather than decorative. Remove controls that do not commit a real action,
collapse deep traces by default, and reserve the main screen for the user answer, source count, gap count,
confidence, capability route, and the action that changes the system: Learn This.

Admin-facing workspaces must expose a System Health Score from 0 to 100. The score is a composite of retrieval
precision, average signature/world-model confidence, T1 bypass readiness, SPPE quality, and human-review backlog.
It must also name the current limiting factor and the next action required to improve the score.

## Scale Feasibility For Math And Code

Math solving and code testing are feasible between prompt and response, but only if execution is treated as a
cached, verified capability route rather than an always-fresh model generation step.

Launch target:

- basic Docker sandbox for code execution;
- SymPy-style symbolic solving with a 500 ms timeout;
- one Celery worker;
- expected code-execution response overhead around 1.5-2 seconds.

Hundreds of users:

- pre-warmed sandbox/container pool to remove cold-start latency;
- Redis-backed result cache keyed by canonical code, dependency lock, runtime image, and test command;
- expected execution overhead under one second for common cases.

Thousands of users:

- Kubernetes autoscaling for sandbox workers;
- tiered symbolic solver handling with timeouts and fallback;
- materialized hot-path caches for repeated expressions and repeated code/test requests;
- compute spent mainly on genuinely novel work.

The invariant from day one is result caching. Every sandbox execution and every symbolic solve must write a
verified result signature before returning. Cached entries include input hash, runtime image or solver version,
stdout/stderr summary, pass/fail status, timeout flag, and provenance. Retrieval can then turn common math/code
queries into memory lookups instead of repeat compute.

## Battle-Tested Patterns To Adopt

- Event Sourcing plus CQRS: memory writes, feedback, review decisions, model activations, and sandbox executions
  are append-only events. Read models are derived from the stream, which makes rollback, audit, and replay natural.
- Materialized Views: Redis/Supabase views hold the importance index, hot-path retrieval cache, common math/code
  results, and workspace health metrics so query-time work stays bounded.
- Saga Pattern: Canvas, Invention Engine, training, and sandbox flows are long-running processes with explicit
  compensation steps for partial signatures, queued jobs, and failed provider calls.
- MCTS in the Invention Engine: keep the Recursive Planner interface, but use Monte Carlo Tree Search as the
  search strategy for large theorem, design, and architecture-invention spaces.
- SAT/SMT verification: use Z3 for formal constraints such as ownership rules, concurrency invariants,
  permission invariants, and logical consistency. Heuristic world-model checks remain useful, but formal
  constraints should be solver-backed when possible.
- Self-consistency voting: for high-stakes or borderline-confidence outputs, generate multiple reasoning paths
  through the reasoning bridge and use agreement as the confidence input on the Verified Cognitive Object.
- Active learning plus synthetic bootstrap: generate an initial synthetic set of query, expected signature, and
  expected output triples for encoder/SPPE evaluation, then progressively replace synthetic data with real
  reviewed workspace data.

## Grounding And Fluency Boundary

The Verified Cognitive Object remains the boundary between grounded output and fluent rendering:

- FACT mode: every factual claim needs source signatures, confidence, and explicit gaps.
- CREATIVE mode: style and analogy are allowed more freedom, but false factual premises are still blocked.
- HYBRID mode: separates sourced claims from creative framing so users can see what is verified.

This boundary must be visible in trace output and review UI. It cannot depend only on prompt wording.

## Current Implementation Slice

Implemented now:

- v9 capability models;
- deterministic capability router;
- structured adapter availability registry;
- runtime trace layers `V9_persistent_retrieval_hydration`, `V9_capability_router`, and `V9_capability_adapters`;
- provider-gated gaps for unavailable capabilities;
- Vectorize query plus Supabase signature hydration before retrieval;
- auto-training threshold detection with human approval retained;
- adaptive T1/T2 thinning with traceable skip reasons;
- production readiness entries for v9 adapter groups;
- training UI surfacing auto-training decisions;
- compact chat evidence panel with confidence, sources, gaps, capability route, Learn This, and collapsed traces;
- admin System Health Score surfaced through the pipeline monitor;
- dedicated sign-in/create-account gate before protected chat loads;
- durable SQLite audit events for query lifecycle, memory writes, feedback, and cache invalidation;
- CQRS-style read-model projections for memory signatures, feedback events, query results, cache hits, and invalidations;
- scoped persistent verified result cache for repeated identical workspace queries;
- Saga events and verified result signatures for Canvas, Invention, training, review actions, sandbox runs, and math solver outputs;
- protected API routes for review actions, deterministic sandbox runs, and SymPy-backed math solving.

## Next Implementation Targets

1. Build the web/world-knowledge adapter with citation ingestion, freshness checks, and source signature persistence.
2. Build the coding adapter with package docs retrieval, sandbox execution, static checks, and test-result memory.
3. Add validated Kaggle artifact activation: compare new encoder/reranker/world-model artifacts against held-out memory tests before hot-swap.
4. Add retrieval quality evaluation: track misses, false positives, source precision, and review outcomes per workspace.
5. Add image generation adapter with asset provenance, prompt safety, and R2 asset storage.
6. Add audio generation adapter with voice-right checks and generated artifact provenance.
7. Add video generation adapter with mandatory human approval before execution.
8. Add agentic task executor with approval queue, dry-run plan, permissions, and rollback metadata.
9. Add richer training UI for review decisions: accept, correct, reject, and promote artifacts.
10. Add workspace-level governance: training budgets, provider quotas, audit logs, and model activation policy.
11. Add Event Sourcing/CQRS for memory, feedback, execution, and review state.
12. Add Saga orchestration for Canvas, Invention, training, and sandbox workflows.
13. Replace naive recursive search inside the Invention Engine with MCTS.
14. Add Z3-backed constraint verification where constraints can be formalized.
15. Add result caching for sandbox executions and symbolic solver outputs.
