# Requirements Document

## Introduction

The World Model Rule Promotion feature closes the loop between causal pattern observation and durable, human-reviewed causal knowledge in the JimsAI pipeline. The existing `LatentWorldModelLayer` already produces `WorldModelActivation` objects on every query, and `review_action` already handles the review lifecycle — but nothing populates `world_model_candidates`. This feature introduces a frequency-based `WorldModelPromotionEngine` to accumulate observations and promote repeated causal patterns for human review, a `WorldModelFastPath` lookup table for serving accepted rules deterministically, and the pipeline wiring to connect both into the existing query and review flows.

## Glossary

- **Promotion_Engine**: The `WorldModelPromotionEngine` class in `world_model_promotion.py`. Counts causal rule observations across queries and promotes rules that exceed configured thresholds.
- **Fast_Path**: The `WorldModelFastPath` class in `world_model_promotion.py`. An in-memory lookup table of accepted causal rules, used to answer matching queries without model inference.
- **Pipeline**: The `JimsAIPipeline` class in `pipeline.py`. The main query processing orchestrator.
- **World_Model_Activation**: A `WorldModelActivation` object produced by `LatentWorldModelLayer.activate()`, with fields `rule` (e.g. `"A causes B"`), `confidence`, and `source` (signature ID).
- **World_Model_Candidate**: A `WorldModelCandidate` object (models.py) with fields `rule`, `confidence`, `provenance`, and `review_required`.
- **Review_Action**: The `review_action()` method on the Pipeline. Handles `accept`, `promote`, `correct`, `reject`, and `rollback` mutations on `world_model_candidates`.
- **Causal_Query**: A query whose `SemanticIR.scope_constraints["question_intent"]["relation"]` equals `"causes"`.
- **Normalized_Rule**: A rule string processed through case-folding and whitespace collapsing, used as the stable dedup key inside the Promotion_Engine.

---

## Requirements

### Requirement 1: WorldModelPromotionEngine Module

**User Story:** As a JimsAI developer, I want a standalone promotion engine module so that causal rule accumulation logic is isolated, testable, and does not require changes to existing pipeline internals beyond wiring.

#### Acceptance Criteria

1. THE Promotion_Engine SHALL be implemented in a new file `prototype/jimsai/world_model_promotion.py`.
2. THE Promotion_Engine SHALL expose an `observe(activations: list[WorldModelActivation]) -> list[WorldModelCandidate]` method that accepts the output of `LatentWorldModelLayer.activate()`.
3. THE Promotion_Engine SHALL expose a `stats() -> dict[str, int | float]` method that returns `{"observed_rules": int, "promoted_rules": int, "avg_confidence": float}`.
4. THE Promotion_Engine SHALL never invoke T1, T2, or any external model or API — it is stateless with respect to model inference.

### Requirement 2: Causal Rule Observation Accumulation

**User Story:** As a JimsAI developer, I want the Promotion_Engine to accumulate observations of causal rules across queries so that frequency and confidence can be measured over time.

#### Acceptance Criteria

1. WHEN `observe()` is called with a list of World_Model_Activations, THE Promotion_Engine SHALL record each activation whose `rule` contains the substring `" causes "`.
2. WHEN the same Normalized_Rule is observed across multiple `observe()` calls, THE Promotion_Engine SHALL increment its observation count and accumulate its confidence sum.
3. WHEN `observe()` is called with an activation whose `rule` does not contain `" causes "`, THE Promotion_Engine SHALL skip that activation and not record it.
4. THE Promotion_Engine SHALL use case-insensitive, whitespace-collapsed normalization when computing Normalized_Rule dedup keys.

### Requirement 3: Threshold-Based Promotion to WorldModelCandidate

**User Story:** As a JimsAI developer, I want rules to be promoted to `WorldModelCandidate` only when they have been observed enough times with sufficient confidence so that the human review queue contains only well-supported rules.

#### Acceptance Criteria

1. WHEN a rule's observation count reaches or exceeds `JIMS_WM_PROMOTION_MIN_COUNT` (env var, default 3) AND its average confidence reaches or exceeds `JIMS_WM_PROMOTION_MIN_CONF` (env var, default 0.6), THE Promotion_Engine SHALL return a `WorldModelCandidate` for that rule in the `observe()` return value.
2. IF a rule's observation count is below `JIMS_WM_PROMOTION_MIN_COUNT`, THEN THE Promotion_Engine SHALL NOT promote it regardless of confidence.
3. IF a rule's average confidence is below `JIMS_WM_PROMOTION_MIN_CONF`, THEN THE Promotion_Engine SHALL NOT promote it regardless of observation count.
4. WHEN a rule is promoted, THE Promotion_Engine SHALL set `review_required=True` on the returned `WorldModelCandidate`.
5. WHEN a rule has already been promoted, THE Promotion_Engine SHALL NOT include it in the return value of any subsequent `observe()` call for the same rule — each rule is promoted at most once.
6. WHEN a rule is promoted, THE Promotion_Engine SHALL set the `provenance` field to the comma-joined sorted set of `source` values seen across all observations of that rule.

### Requirement 4: WorldModelFastPath Lookup Table

**User Story:** As a JimsAI developer, I want a fast lookup table of accepted causal rules so that matching causal queries can be answered deterministically without model inference.

#### Acceptance Criteria

1. THE Fast_Path SHALL be implemented as a class in `world_model_promotion.py` with `rebuild()`, `lookup()`, `lookup_effects_of()`, and `lookup_causes_of()` methods.
2. WHEN `rebuild(candidates)` is called, THE Fast_Path SHALL index only World_Model_Candidates where `review_required=False` AND whose `rule` matches the pattern `"<cause> causes <effect>"`.
3. WHEN `rebuild(candidates)` is called, THE Fast_Path SHALL clear all previously indexed rules before re-indexing, so the table always reflects the current candidate list exactly.
4. WHEN `lookup(cause, effect)` is called, THE Fast_Path SHALL return the matching World_Model_Candidate if an accepted rule exists for that exact (cause, effect) pair after normalization, or `None` if no match exists.
5. WHEN `lookup_effects_of(cause)` is called, THE Fast_Path SHALL return all accepted World_Model_Candidates whose cause matches the given string after normalization.
6. WHEN `lookup_causes_of(effect)` is called, THE Fast_Path SHALL return all accepted World_Model_Candidates whose effect matches the given string after normalization.
7. IF `rebuild()` has not yet been called or the candidate list is empty, THEN THE Fast_Path SHALL return empty results for all lookup methods without raising exceptions.

### Requirement 5: Pipeline Initialization Wiring

**User Story:** As a JimsAI developer, I want the Promotion_Engine and Fast_Path to be instantiated as pipeline attributes so that all query and review flows can access them through the standard pipeline interface.

#### Acceptance Criteria

1. WHEN `JimsAIPipeline.__init__()` runs, THE Pipeline SHALL instantiate `self.world_model_promotion = WorldModelPromotionEngine()`.
2. WHEN `JimsAIPipeline.__init__()` runs, THE Pipeline SHALL instantiate `self.world_model_fast_path = WorldModelFastPath()`.
3. THE Pipeline SHALL import `WorldModelPromotionEngine` and `WorldModelFastPath` from `world_model_promotion`.

### Requirement 6: Per-Query Promotion Accumulation in pipeline.run()

**User Story:** As a JimsAI developer, I want every query's world model activations to be fed to the Promotion_Engine so that causal rules accumulate automatically without requiring explicit ingestion steps.

#### Acceptance Criteria

1. WHEN `LatentWorldModelLayer.activate()` produces `world_model_activations` inside `pipeline.run()`, THE Pipeline SHALL call `self.world_model_promotion.observe(world_model_activations)` immediately after.
2. WHEN `observe()` returns one or more newly promoted candidates, THE Pipeline SHALL extend `self.world_model_candidates` with those candidates, deduplicating by `rule` string (exact match, not normalized).
3. WHEN `world_model_candidates` is extended with new candidates, THE Pipeline SHALL call `self.world_model_fast_path.rebuild(self.world_model_candidates)`.
4. WHEN `observe()` returns an empty list, THE Pipeline SHALL NOT call `rebuild()` on that query.

### Requirement 7: Fast-Path Sync After Review Actions

**User Story:** As a human reviewer, I want the fast-path lookup table to reflect my accept/correct/reject/rollback decisions immediately so that approved rules are served instantly on the next matching query.

#### Acceptance Criteria

1. WHEN `review_action()` executes any mutating action (`accept`, `promote`, `correct`, `reject`, or `rollback`) on an in-memory World_Model_Candidate, THE Pipeline SHALL call `self.world_model_fast_path.rebuild(self.world_model_candidates)` before returning the response.
2. WHEN `review_action()` takes the persistent fallback path (candidate not found in `world_model_candidates`), THE Pipeline SHALL still call `self.world_model_fast_path.rebuild(self.world_model_candidates)` to ensure consistency.

### Requirement 8: Deterministic Fast-Path Answer for Causal Queries

**User Story:** As a JimsAI user, I want repeated, human-approved causal queries to be answered instantly and deterministically so that the system's best-verified knowledge is served without incurring model inference cost.

#### Acceptance Criteria

1. WHEN a `PipelineRequest` produces a `SemanticIR` with `question_intent.relation == "causes"` AND `scope_constraints["entities"]` is non-empty AND `world_model_fast_path._accepted` is non-empty, THE Pipeline SHALL attempt a fast-path lookup before executing the full retrieval and reasoning pipeline.
2. WHEN the fast-path lookup returns one or more matching World_Model_Candidates, THE Pipeline SHALL construct and return a `PipelineResponse` from those candidates without invoking `retrieval_layer`, `reasoning_bridge_layer`, `render_layer`, or any model inference.
3. WHEN the fast-path lookup returns no matches, THE Pipeline SHALL fall through to the full pipeline and behave identically to pre-feature behavior.
4. WHEN a fast-path answer is returned, THE Pipeline SHALL set `used_groq=False` in the `PipelineResponse`.
5. WHEN a fast-path answer is returned, THE Pipeline SHALL include the matched rule strings and their confidence values in the response data.
6. WHEN `question_intent.relation` is not `"causes"`, THE Pipeline SHALL NOT enter the fast-path block.

### Requirement 9: AutonomousTrainingAgent — Real Confidence Average

**User Story:** As a JimsAI developer, I want `world_model_confidence_avg` in `SystemState` to reflect the actual average confidence of promoted rules so that training gap analysis is based on real measurements rather than a hardcoded placeholder.

#### Acceptance Criteria

1. WHEN `AutonomousTrainingAgent._evaluate_system_state()` computes `world_model_confidence_avg`, THE Agent SHALL use `self.pipeline.world_model_promotion.stats()["avg_confidence"]` instead of the hardcoded value `0.73`.
2. IF the agent has no valid `pipeline` reference, THEN THE Agent SHALL use `0.0` as the default for `world_model_confidence_avg`.
3. THE Agent SHALL NOT use any hardcoded numeric constant for `world_model_confidence_avg`.

### Requirement 10: No Auto-Acceptance and No Fuzzy Matching

**User Story:** As a JimsAI operator, I want all promoted rules to require explicit human review before becoming active in the fast-path so that the system never autonomously promote unverified causal claims into the deterministic answer path.

#### Acceptance Criteria

1. THE Promotion_Engine SHALL set `review_required=True` on every promoted `WorldModelCandidate` — no code path SHALL set `review_required=False` on a newly promoted candidate.
2. THE Fast_Path SHALL use exact normalized-string matching only — no embedding similarity, fuzzy matching, or approximate string comparison SHALL be used in any lookup method.
3. THE Promotion_Engine SHALL only process rule strings containing the substring `" causes "` — no other rule shapes SHALL be introduced in this iteration.
