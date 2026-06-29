# Raw Intelligence Missing Plan

This file tracks the six remaining pipeline gaps that matter most for making JimsAI behave like a genuine AI system instead of a thin model wrapper.

Core rule: fixes must be architectural and general. No prompt-specific patches, no hardcoded answers, and no changes whose only purpose is to pass one test.

## Progress

1. Adaptive planning and task decomposition
   - Status: first pass complete
   - Goal: turn the symbolic planner into a dependency-aware execution planner that reacts to complexity, uncertainty, scope, and task type.
   - Correctness test: plan invariants, ordering, sandbox behavior, code/invention behavior, and pipeline integration.

2. Retrieval depth and reranking
   - Status: first pass complete
   - Goal: move from mostly hot-cache lexical/structured retrieval plus Vectorize hydration to multi-hop retrieval, query decomposition, learned reranking, and contradiction-aware retrieval.
   - Correctness test: retrieval precision, miss recovery, workspace isolation, multi-hop causal recall, and no prior-prompt contamination.

3. World-model breadth and promotion
   - Status: first pass complete
   - Goal: expand beyond exact repeated causal rules into evidence-backed typed relations, temporal rules, dependency rules, and contradiction-aware promotion.
   - Correctness test: no automatic truth promotion, review gates remain intact, accepted rules become fast-path candidates, conflicting rules stay quarantined.

4. Verification and critic layer
   - Status: first pass complete
   - Goal: upgrade checks from confidence/source/simulation basics into claim-level validation, tool-output validation, contradiction checks, and failure-aware answer blocking.
   - Correctness test: unsupported claims are blocked, failed tool results do not render as answers, source gaps remain visible, code/math are actually verified.

5. Learned capability routing policy
   - Status: first pass complete
   - Goal: make routing improve from outcomes, feedback, latency, cost, and task success, while keeping critical services fail-closed.
   - Correctness test: ambiguous multi-intent prompts preserve secondary routes, unavailable tool routes report unavailability, routing improves from accepted feedback without keyword hacks.

6. Memory consolidation and safe real-time learning
   - Status: first pass complete
   - Goal: separate transient prompt memory, episodic memory, semantic workspace facts, user preferences, contradictions, and training candidates.
   - Correctness test: user/workspace isolation, rollback, confidence decay, contradiction handling, source trust, and no pollution from hallucinated outputs.

## Progressive Test Strategy

Each gap should be tested one at a time before moving to the next:

1. Unit tests for the changed layer.
2. Integration test through `JimsAIPipeline` when the layer is part of query execution.
3. Regression tests proving no prompt-specific or stale fallback behavior was added.
4. Latency check when the change is on the user query path.
5. Failure-mode check: required AI services fail closed; optional tools report unavailable.

## Current Work Item

Gap 1 is first because planning is upstream of retrieval, world-model activation, verification, and rendering. A stronger planner gives later layers a better contract without pretending T1 or T2 alone provides raw intelligence.
