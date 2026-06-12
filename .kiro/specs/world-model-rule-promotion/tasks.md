# Implementation Plan: World Model Rule Promotion

## Overview

Implement the `WorldModelPromotionEngine` and `WorldModelFastPath` classes in a new `world_model_promotion.py` module, then wire them into the pipeline with four targeted edits. Finally, replace the hardcoded `world_model_confidence_avg` constant in the autonomous training agent with a live computation. The implementation is Python throughout, using only the standard library.

## Tasks

- [x] 1. Create `world_model_promotion.py` with `WorldModelPromotionEngine` and `WorldModelFastPath`
  - Create `prototype/jimsai/world_model_promotion.py`
  - Implement `_normalize_rule(rule: str) -> str` using `re.sub(r"\s+", " ", rule.strip().lower())`
  - Implement `_RuleObservation` dataclass with `rule`, `count`, `confidence_sum`, `provenances: set[str]`, and `avg_confidence` property
  - Implement `WorldModelPromotionEngine.__init__` with `_observations: dict[str, _RuleObservation]` and `_promoted_keys: set[str]`
  - Implement `WorldModelPromotionEngine._min_count()` and `_min_confidence()` reading from env vars `JIMS_WM_PROMOTION_MIN_COUNT` (default 3) and `JIMS_WM_PROMOTION_MIN_CONF` (default 0.6)
  - Implement `WorldModelPromotionEngine.observe(activations)`: skip activations without `" causes "`, accumulate counts/confidence/provenances, promote when threshold crossed (exactly once per rule), always set `review_required=True`
  - Implement `WorldModelPromotionEngine.stats()` returning `{"observed_rules": int, "promoted_rules": int, "avg_confidence": float}`
  - Implement `WorldModelFastPath.__init__` with `_accepted: dict[tuple[str, str], WorldModelCandidate]`
  - Implement `WorldModelFastPath.rebuild(candidates)`: clear `_accepted`, parse `"X causes Y"` via `re.compile(r"^(.+?)\s+causes\s+(.+)$", re.IGNORECASE)`, index only `review_required=False` candidates
  - Implement `WorldModelFastPath.lookup(cause, effect)`, `lookup_effects_of(cause)`, `lookup_causes_of(effect)` using normalized keys
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 10.1, 10.2, 10.3_

  - [x] 1.1 Write property test: promotion threshold gate
    - **Property 1: Promotion threshold gate**
    - Generate arbitrary `(count, avg_confidence)` pairs; when either is below threshold, assert `observe()` never returns a candidate for that rule
    - **Validates: Requirements 3.1, 3.2, 3.3**

  - [x] 1.2 Write property test: promotion exactly-once and review_required invariant
    - **Property 2: Promotion happens exactly once per rule, always with review_required=True**
    - Generate arbitrary sequences of activations for the same rule crossing the threshold; assert the rule appears in combined observe() results exactly once and always with `review_required=True`
    - **Validates: Requirements 3.4, 3.5**

  - [x] 1.3 Write property test: causal-rule filter
    - **Property 3: Causal-rule filter — only " causes " activations are processed**
    - Generate lists mixing activations with and without `" causes "`; assert non-causal activations leave internal state unchanged
    - **Validates: Requirements 2.1, 2.3**

  - [x] 1.4 Write property test: normalization dedup
    - **Property 4: Normalization dedup — case and whitespace variants are the same rule**
    - Generate rule strings that differ only in casing or whitespace; assert they combine into a single observation counter and at most one promotion
    - **Validates: Requirements 2.4**

  - [x] 1.5 Write property test: fast-path accepted-only invariant
    - **Property 5: Fast-path contains only accepted rules after rebuild**
    - Generate lists of WorldModelCandidates with mixed `review_required` values; call `rebuild()`; assert every result from all three lookup methods has `review_required=False`
    - **Validates: Requirements 4.2, 4.3, 10.1**

  - [x] 1.6 Write property test: fast-path lookup completeness
    - **Property 6: Fast-path lookup completeness and correctness**
    - Generate a list of accepted candidates; call `rebuild()`; assert `lookup_effects_of` and `lookup_causes_of` return exactly the expected subsets — no omissions, no spurious inclusions
    - **Validates: Requirements 4.4, 4.5, 4.6**

  - [x] 1.7 Write property test: stats() reflects actual state
    - **Property 10: world_model_confidence_avg reflects actual state, not a constant**
    - Generate two sequences of observations producing different rule sets; assert `stats()["avg_confidence"]` differs between the two states
    - **Validates: Requirements 9.1, 9.3**

- [x] 2. Checkpoint — unit tests pass
  - Run `pytest prototype/tests/test_world_model_promotion.py` (or equivalent) and ensure all property tests pass. Ask the user if questions arise.

- [x] 3. Wire `WorldModelPromotionEngine` and `WorldModelFastPath` into `pipeline.py` — Edit 1: `__init__`
  - Add import in `pipeline.py`: `from .world_model_promotion import WorldModelPromotionEngine, WorldModelFastPath`
  - In `JimsAIPipeline.__init__()`, after `self.world_model_layer = LatentWorldModelLayer(self.graph)`, add:
    ```python
    self.world_model_promotion = WorldModelPromotionEngine()
    self.world_model_fast_path = WorldModelFastPath()
    ```
  - `self.world_model_candidates: list[WorldModelCandidate] = []` already exists — no change needed
  - _Requirements: 5.1, 5.2, 5.3_

  - [x] 3.1 Write example test: pipeline attributes exist after init
    - Construct a `JimsAIPipeline()` and assert `isinstance(pipeline.world_model_promotion, WorldModelPromotionEngine)` and `isinstance(pipeline.world_model_fast_path, WorldModelFastPath)`
    - _Requirements: 5.1, 5.2_

- [x] 4. Wire promotion accumulation — Edit 2: after `world_model_layer.activate()` in `pipeline.run()`
  - Locate the line `world_model_activations, graph_view, world_model_layer_result = self.world_model_layer.activate(ir, retrieved, activation)` in `pipeline.run()`
  - Immediately after `record(world_model_layer_result)`, add:
    ```python
    newly_promoted = self.world_model_promotion.observe(world_model_activations)
    if newly_promoted:
        existing_rules = {c.rule for c in self.world_model_candidates}
        self.world_model_candidates.extend(
            c for c in newly_promoted if c.rule not in existing_rules
        )
        self.world_model_fast_path.rebuild(self.world_model_candidates)
    ```
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 4.1 Write property test: deduplication in pipeline.world_model_candidates
    - **Property 9: world_model_candidates deduplication**
    - Drive `observe()` with the same rule across multiple calls simulating multiple queries; assert the rule appears in `world_model_candidates` exactly once
    - **Validates: Requirements 6.2**

- [x] 5. Wire fast-path sync — Edit 3: call `rebuild()` after `review_action()` mutations
  - In `pipeline.review_action()`, locate the block that handles `accept`/`promote`/`correct`/`reject`/`rollback` mutations on `world_model_candidates` (lines ~1400-1425)
  - After all mutation branches converge and before the `event_payload` dict is constructed, add:
    ```python
    self.world_model_fast_path.rebuild(self.world_model_candidates)
    ```
  - Also add the same `rebuild()` call in the persistent fallback path (the `if updated_panel_items:` branch at the top of `review_action()`) so both paths stay in sync
  - _Requirements: 7.1, 7.2_

  - [x] 5.1 Write example test: review lifecycle — accept makes rule available in fast-path
    - Manually add a `WorldModelCandidate(rule="TestA causes TestB", review_required=True, ...)` to `pipeline.world_model_candidates`; call `review_action(action="accept", ...)`; assert `pipeline.world_model_fast_path.lookup("TestA", "TestB")` returns the candidate
    - _Requirements: 7.1_

- [x] 6. Implement fast-path lookup — Edit 4: early-return in `pipeline.run()` after `ir` is available
  - Locate the point in `pipeline.run()` where `ir` is first available (after `ir, intent_layer_result = await self.intent_layer.infer(request, session)`)
  - Add the fast-path check block after `ir` is computed but before retrieval/L8 runs:
    ```python
    question_intent = ir.scope_constraints.get("question_intent", {})
    entities = [str(e) for e in ir.scope_constraints.get("entities", [])]
    if (
        isinstance(question_intent, dict)
        and question_intent.get("relation") == "causes"
        and len(entities) >= 1
        and self.world_model_fast_path._accepted
    ):
        direction = str(question_intent.get("direction") or "outgoing")
        fast_matches: list[WorldModelCandidate] = []
        for entity in entities[:3]:
            if direction == "incoming":
                fast_matches.extend(self.world_model_fast_path.lookup_causes_of(entity))
            else:
                fast_matches.extend(self.world_model_fast_path.lookup_effects_of(entity))
        if fast_matches:
            summary_lines = [
                f"{c.rule} (confidence {c.confidence:.2f}, verified rule)"
                for c in fast_matches[:5]
            ]
            fast_sig = self._write_result_signature(
                "world_model_fast_path",
                "solved",
                "Answered from a human-approved world model rule (deterministic, no model inference).",
                user_id=request.user_id,
                confidence=min(c.confidence for c in fast_matches),
                provenance=[p for c in fast_matches for p in c.provenance.split(",") if p],
                data={
                    "matched_rules": [c.model_dump(mode="json") for c in fast_matches],
                    "summary_lines": summary_lines,
                },
            )
            # Build a minimal deterministic PipelineResponse from the fast-path result
            from .models import SemanticIR  # already imported
            fast_response = PipelineResponse(
                response="\n".join(summary_lines),
                ir=ir,
                reasoning_chain=[],
                confidence=fast_sig.confidence,
                gaps=[],
                sources=fast_sig.provenance,
                simulation_results=[],
                trace=[],
                used_groq=False,
            )
            self.event_store.append(
                "world_model_fast_path_hit",
                ir.trace_id,
                {"entities": entities, "matched_rules": len(fast_matches)},
                user_id=request.user_id,
            )
            return fast_response
    ```
  - Note: If the render layer needs to be involved for richer formatting, thread `fast_matches` through the VCO builder instead of building the response inline — see design doc section on the fast-path answer flow.
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 6.1 Write property test: fast-path bypasses model inference
    - **Property 8: Fast-path hits produce deterministic, model-free responses**
    - Seed the fast-path with accepted candidates, send a matching causal query, assert `PipelineResponse.used_groq=False` and response contains the rule data
    - **Validates: Requirements 8.1, 8.2, 8.4, 8.5**

  - [x] 6.2 Write property test: non-causal queries bypass fast-path
    - **Property 7: Non-causal queries bypass the fast-path**
    - Generate queries where `question_intent.relation != "causes"`; assert the fast-path block is not entered (pipeline runs fully, `world_model_fast_path` lookup methods are not called)
    - **Validates: Requirements 8.6**

- [x] 7. Checkpoint — integration tests pass
  - Write and run an integration test that:
    1. Sends 3 queries that each generate a `"TestService causes TestEffect"` world model activation (use the ingestion path or directly call `pipeline.world_model_promotion.observe()` with mock activations)
    2. Asserts `len(pipeline.world_model_candidates) == 1` and `pipeline.world_model_candidates[0].review_required is True`
    3. Calls `review_action(action="accept", ...)` and asserts `review_required=False` and fast-path lookup returns the candidate
    4. Sends a matching causal query and asserts `PipelineResponse.used_groq=False`
    5. Sends a non-matching causal query and asserts the full pipeline ran
  - Ensure all tests pass. Ask the user if questions arise.

- [x] 8. Edit `autonomous_training_agent.py` — replace hardcoded `world_model_confidence_avg`
  - In `AutonomousTrainingAgent._evaluate_system_state()`, find the line `world_model_confidence_avg=0.73`
  - Replace with:
    ```python
    world_model_confidence_avg=(
        self.pipeline.world_model_promotion.stats()["avg_confidence"]
        if getattr(self, "pipeline", None) is not None
        else 0.0
    ),
    ```
  - Verify that `AutonomousTrainingAgent.__init__` already stores `self.pipeline = pipeline` (confirmed in the existing code — the constructor takes `pipeline: JimsAIPipeline` and assigns it)
  - _Requirements: 9.1, 9.2, 9.3_

  - [x] 8.1 Write example test: world_model_confidence_avg uses live value
    - Create a `JimsAIPipeline()`, inject a few promoted rules via `world_model_promotion.observe()`, create an `AutonomousTrainingAgent(pipeline=pipeline)`, call `_evaluate_system_state()`, and assert `state.world_model_confidence_avg != 0.73` and equals `pipeline.world_model_promotion.stats()["avg_confidence"]`
    - Also assert that with a fresh pipeline (no promoted rules), the value is `0.0` not `0.73`
    - _Requirements: 9.1, 9.2, 9.3_

- [x] 9. Final checkpoint — full test suite
  - Run the full test suite and ensure no regressions. Verify:
    - All unit and property tests for `world_model_promotion.py` pass
    - All pipeline integration tests pass
    - The autonomous training agent test passes
    - No existing tests are broken by the four pipeline edits
  - Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The fast-path (Edit 4 / Task 6) is the most integration-sensitive change — test it first with a simple inline response before attempting to thread through the full render layer
- The `review_action` persistent fallback path (Task 5, second `rebuild()` call) is a defensive addition; the main path is the in-memory mutation branch
- All new code is Python 3.11+, standard library only (os, re, collections, dataclasses)
- Property tests should use `hypothesis` (already present in the repo per `.hypothesis/` directory)

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 1, "tasks": ["1"]},
    {"wave": 2, "tasks": ["2"]},
    {"wave": 3, "tasks": ["3"]},
    {"wave": 4, "tasks": ["4", "5"]},
    {"wave": 5, "tasks": ["6"]},
    {"wave": 6, "tasks": ["7"]},
    {"wave": 7, "tasks": ["8"]},
    {"wave": 8, "tasks": ["9"]}
  ]
}
```
