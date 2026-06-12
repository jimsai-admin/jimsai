# JimsAI Roadmap: World Model Rule Promotion (Doc 12 — Buildable Version)

## Status of this document

This is a **scoped, buildable roadmap** for the one piece of "Doc 12"
(the speculative two-layer/fine-tuning vision) that is actually close,
actually fits the existing codebase, and does **not** require:

- a fine-tuning pipeline
- a Kaggle training loop
- frontier API access (Tier 3)
- Wikipedia/Stack Overflow/arXiv ingestion at scale
- any new research (no ILP, no analogical generalization)

It implements exactly one thing: **frequency-based promotion of
repeated causal patterns in the existing graph into
`WorldModelCandidate` rules, surfaced for human review via the
review/promote/correct/reject lifecycle that already exists and is
fully wired** (`review_action` in `pipeline.py`, confirmed working
end-to-end — it was the *only* unused half of an otherwise-complete
feature).

Everything below is real, traceable to the actual codebase as read
during this conversation, and intentionally modest.

---

## What is missing today (confirmed by reading the code)

1. `WorldModelCandidate` (models.py) — schema exists, **zero code
   populates it**.
2. `self.world_model_candidates: list[WorldModelCandidate] = []`
   (pipeline.py, `__init__`) — initialized, **never appended to**.
3. `review_action` (pipeline.py) — fully implemented: handles
   `accept`/`promote`/`correct`/`reject`/`rollback` against
   `self.world_model_candidates`, writes audit signatures, calls
   `self.production.review_world_model_candidate(...)`. **This works
   today but has nothing to review**, because of (1) and (2).
4. `LatentWorldModelLayer.activate()` (runtime_layers.py) — already
   does `graph.outgoing_edges(entity, predicates={"causes"}, ...)`
   and reads `item.signature.structured.causal_chain` for every
   retrieved signature on every query. **This is the exact data
   source the promotion engine needs — it's already being computed,
   just not accumulated across queries.**
5. `world_model_confidence_avg=0.73` (autonomous_training_agent.py,
   line 431) — a **hardcoded constant** in a dataclass that's
   presented as a measurement. Needs to become a real computation
   once candidates exist.

---

## What this roadmap builds

A new, small module — `world_model_promotion.py` — plus four
targeted edits to existing files. The mechanism:

```
Every time LatentWorldModelLayer.activate() fires a causal
activation (e.g. "ServiceA causes ServiceB"), record it in a
frequency counter, keyed by the normalized rule string.

When a rule's count crosses a threshold (default 3, configurable)
AND its average confidence is above a floor (default 0.6),
promote it to a WorldModelCandidate with review_required=True.

Append to self.world_model_candidates (dedup by rule string).

A human reviews via the existing /review_action endpoint —
already fully functional — and accepts/corrects/rejects.

Accepted candidates (review_required=False) become available to
a new fast-path: before running the full pipeline, check if the
query's entity pair + relation matches an accepted
WorldModelCandidate. If so, answer directly from the rule —
deterministic, instant, zero model calls — same VCO/CSSE
verification wrapper as everything else, just skipping T1/T2
for that specific lookup.
```

This is the "promotion" mechanism from the conversation, scoped to
**frequency counting + human review**, not analogical generalization.

---

## What JimsAI becomes after this change

**Concretely, for the specific case of repeated causal queries**
("X causes Y" patterns the system has seen ≥3 times and a human has
approved):

- Answered via `graph.outgoing_edges`/dict lookup — microseconds,
  not the 1-15s pipeline round trip
- Zero model inference cost for that query
- 100% consistent (same input → same output, always)
- Fully auditable — every accepted rule has `provenance` pointing to
  the signatures it was derived from, plus a review event in
  `event_store`
- Multilingual "for free" — if the underlying entities/relations were
  extracted correctly regardless of input language (already true per
  the encoder), the rule fires regardless of what language the *new*
  query is phrased in, since matching happens on extracted
  entities/relations, not surface text

**For everything else — unchanged.** Novel causal claims, claims seen
fewer than 3 times, claims a human hasn't reviewed, and anything that
isn't a causal-relation lookup all go through the existing pipeline
exactly as before. The promotion engine is additive and fails open —
if `world_model_candidates` is empty (fresh install, or nothing has
crossed the threshold yet), behavior is identical to today.

### Comparison after this change

| | Repeated, approved causal query | Everything else |
|---|---|---|
| **JimsAI (after)** | Instant, free, deterministic, auditable | Same as JimsAI today — 1.7B/4B bounded |
| **JimsAI (before)** | Same as "everything else" — full pipeline | Same |
| **Frontier model** | Probabilistic circuit, ~1-5s, per-token cost, not separately auditable, may drift | Generally stronger reasoning, broader knowledge, no memory across sessions |

The honest framing: this makes JimsAI's **best case** (a pattern it's
verified repeatedly and a human has signed off on) strictly better
than frontier's best case on that *same* query — faster, free,
auditable. It does not change JimsAI's worst case (novel query),
which remains bounded by Qwen3-1.7B/4B exactly as discussed
throughout this conversation. No fine-tuning, no Tier 3, no new model
capability — purely making a narrow, already-computed signal durable
and reviewable instead of recomputed-and-discarded every query.

---

## Implementation

### New file: `prototype/jimsai/world_model_promotion.py`

```diff
--- /dev/null
+++ b/prototype/jimsai/world_model_promotion.py
@@ -0,0 +1,118 @@
+"""World Model Rule Promotion Engine.
+
+Frequency-based promotion of repeated causal patterns (observed via
+LatentWorldModelLayer activations across queries) into
+WorldModelCandidate rules for human review.
+
+Design constraints (deliberately scoped — see roadmap-doc-12.md):
+  - No analogical generalization. A rule is promoted only when the
+    EXACT (cause, effect) pair has been observed independently
+    enough times.
+  - No automatic acceptance. Every promoted candidate starts with
+    review_required=True and only becomes usable for the fast-path
+    after a human calls review_action(action="accept"/"promote").
+  - Stateless w.r.t. the LLM — this module never calls T1/T2/Tier3.
+    It only reads WorldModelActivation objects already produced by
+    LatentWorldModelLayer.activate(), which runs on every query
+    regardless of this module's existence.
+"""
+
+from __future__ import annotations
+
+import os
+import re
+from collections import defaultdict
+from dataclasses import dataclass, field
+
+from .models import WorldModelCandidate
+from .runtime_layers import WorldModelActivation
+
+
+def _normalize_rule(rule: str) -> str:
+    """Normalize 'X causes Y' strings for stable dedup keys.
+
+    Case-insensitive, collapses whitespace. Does NOT translate or
+    stem entity names — exact-match by design (see module docstring).
+    """
+    return re.sub(r"\s+", " ", rule.strip().lower())
+
+
+@dataclass
+class _RuleObservation:
+    rule: str  # original-cased rule string, first-seen form
+    count: int = 0
+    confidence_sum: float = 0.0
+    provenances: set[str] = field(default_factory=set)
+
+    @property
+    def avg_confidence(self) -> float:
+        return self.confidence_sum / self.count if self.count else 0.0
+
+
+class WorldModelPromotionEngine:
+    """Accumulates causal-rule observations across queries and
+    promotes repeated, sufficiently-confident ones to
+    WorldModelCandidate for review.
+
+    Thresholds are read from env vars so they can be tuned per
+    deployment without code changes:
+      JIMS_WM_PROMOTION_MIN_COUNT   (default 3)
+      JIMS_WM_PROMOTION_MIN_CONF    (default 0.6)
+    """
+
+    def __init__(self) -> None:
+        self._observations: dict[str, _RuleObservation] = {}
+        self._promoted_keys: set[str] = set()
+
+    def _min_count(self) -> int:
+        try:
+            return max(1, int(os.getenv("JIMS_WM_PROMOTION_MIN_COUNT", "3")))
+        except ValueError:
+            return 3
+
+    def _min_confidence(self) -> float:
+        try:
+            return min(1.0, max(0.0, float(os.getenv("JIMS_WM_PROMOTION_MIN_CONF", "0.6"))))
+        except ValueError:
+            return 0.6
+
+    def observe(self, activations: list[WorldModelActivation]) -> list[WorldModelCandidate]:
+        """Record activations from a single query's LatentWorldModelLayer
+        output. Returns any NEWLY promoted candidates (empty list if none).
+
+        Only activations whose rule matches "X causes Y" (the only
+        rule shape LatentWorldModelLayer currently produces) are
+        considered. This keeps the promotion engine in lockstep with
+        what the graph layer actually emits — no speculative rule
+        shapes are invented here.
+        """
+        newly_promoted: list[WorldModelCandidate] = []
+        for activation in activations:
+            if " causes " not in activation.rule:
+                continue
+            key = _normalize_rule(activation.rule)
+            obs = self._observations.get(key)
+            if obs is None:
+                obs = _RuleObservation(rule=activation.rule)
+                self._observations[key] = obs
+            obs.count += 1
+            obs.confidence_sum += float(activation.confidence)
+            if activation.source:
+                obs.provenances.add(str(activation.source))
+
+            if (
+                key not in self._promoted_keys
+                and obs.count >= self._min_count()
+                and obs.avg_confidence >= self._min_confidence()
+            ):
+                self._promoted_keys.add(key)
+                newly_promoted.append(
+                    WorldModelCandidate(
+                        rule=obs.rule,
+                        confidence=round(obs.avg_confidence, 4),
+                        provenance=",".join(sorted(obs.provenances)) or "unknown",
+                        review_required=True,
+                    )
+                )
+        return newly_promoted
+
+    def stats(self) -> dict[str, int | float]:
+        """Summary for diagnostics / world_model_confidence_avg."""
+        if not self._observations:
+            return {"observed_rules": 0, "promoted_rules": 0, "avg_confidence": 0.0}
+        confidences = [obs.avg_confidence for obs in self._observations.values()]
+        return {
+            "observed_rules": len(self._observations),
+            "promoted_rules": len(self._promoted_keys),
+            "avg_confidence": round(sum(confidences) / len(confidences), 4),
+        }
+
+
+class WorldModelFastPath:
+    """Lookup table of ACCEPTED (review_required=False) causal rules,
+    rebuilt from pipeline.world_model_candidates on demand.
+
+    Used for the deterministic fast-path: if a query's extracted
+    entities exactly match an accepted rule's cause/effect pair,
+    answer directly without invoking T1/T2.
+    """
+
+    def __init__(self) -> None:
+        self._accepted: dict[tuple[str, str], WorldModelCandidate] = {}
+
+    def rebuild(self, candidates: list[WorldModelCandidate]) -> None:
+        self._accepted.clear()
+        pattern = re.compile(r"^(.+?)\s+causes\s+(.+)$", re.IGNORECASE)
+        for candidate in candidates:
+            if candidate.review_required:
+                continue
+            match = pattern.match(candidate.rule.strip())
+            if not match:
+                continue
+            cause = match.group(1).strip().lower()
+            effect = match.group(2).strip().lower()
+            self._accepted[(cause, effect)] = candidate
+
+    def lookup(self, cause: str, effect: str) -> WorldModelCandidate | None:
+        return self._accepted.get((cause.strip().lower(), effect.strip().lower()))
+
+    def lookup_effects_of(self, cause: str) -> list[WorldModelCandidate]:
+        cause_norm = cause.strip().lower()
+        return [c for (cz, _), c in self._accepted.items() if cz == cause_norm]
+
+    def lookup_causes_of(self, effect: str) -> list[WorldModelCandidate]:
+        effect_norm = effect.strip().lower()
+        return [c for (_, ez), c in self._accepted.items() if ez == effect_norm]
```

### Edit 1: `prototype/jimsai/pipeline.py` — wire the promotion engine into `__init__`

```diff
--- a/prototype/jimsai/pipeline.py
+++ b/prototype/jimsai/pipeline.py
@@ -14,6 +14,7 @@
 from .graph import CausalGraphEngine
+from .world_model_promotion import WorldModelPromotionEngine, WorldModelFastPath
@@ -135,6 +136,8 @@
         self.world_model_layer = LatentWorldModelLayer(self.graph)
         self.reasoning_bridge_layer = ReasoningBridgeLayer(self.simulation, self.validator, self.planner, self.graph)
+        self.world_model_promotion = WorldModelPromotionEngine()
+        self.world_model_fast_path = WorldModelFastPath()
@@ -138,6 +141,7 @@
         self.world_model_candidates: list[WorldModelCandidate] = []
```

### Edit 2: `prototype/jimsai/pipeline.py` — feed activations to the promotion engine after `world_model_layer.activate()`

This is the line where `world_model_activations` is already produced
on every query (confirmed at line 490 of pipeline.py). We add three
lines immediately after it.

```diff
--- a/prototype/jimsai/pipeline.py
+++ b/prototype/jimsai/pipeline.py
@@ -488,6 +488,11 @@
         world_model_activations, graph_view, world_model_layer_result = self.world_model_layer.activate(ir, retrieved, activation)
         record(world_model_layer_result)
+        newly_promoted = self.world_model_promotion.observe(world_model_activations)
+        if newly_promoted:
+            existing_rules = {c.rule for c in self.world_model_candidates}
+            self.world_model_candidates.extend(c for c in newly_promoted if c.rule not in existing_rules)
+            self.world_model_fast_path.rebuild(self.world_model_candidates)
```

### Edit 3: `prototype/jimsai/pipeline.py` — rebuild fast-path after `review_action` changes acceptance state

`review_action` already mutates `self.world_model_candidates` for
`accept`/`promote`/`correct`/`reject`/`rollback`. We add a single
rebuild call at the end of each mutating branch so
`WorldModelFastPath` stays in sync. Simplest correct placement: right
before the final `event_store.append` / response construction, since
all branches converge there.

```diff
--- a/prototype/jimsai/pipeline.py
+++ b/prototype/jimsai/pipeline.py
@@ -1422,6 +1422,8 @@
         elif request.action == "rollback":
             candidate.review_required = True
             self.world_model_candidates[target_index] = candidate
+
+        self.world_model_fast_path.rebuild(self.world_model_candidates)
 
         event_payload = {
             "action": request.action,
```

### Edit 4: `prototype/jimsai/pipeline.py` — fast-path lookup, gated on causal `question_intent`

`LatentWorldModelLayer.activate()` already detects causal-direction
questions via `question_intent.get("relation") == "causes"` (line
649, runtime_layers.py) and extracts `entities` from
`ir.scope_constraints`. We reuse exactly that signal at the top of
the query method to attempt a fast-path answer **before** the
expensive retrieval/T1/T2 path runs, falling through to the normal
pipeline if no accepted rule matches.

This edit is intentionally placed as early as possible in `query()`
but after `ir` (the SemanticIR) is available, since `ir` is what
carries `scope_constraints.entities` and `question_intent`.

```diff
--- a/prototype/jimsai/pipeline.py
+++ b/prototype/jimsai/pipeline.py
@@ -395,6 +395,35 @@
         # ir: SemanticIR is available from this point onward
+        question_intent = ir.scope_constraints.get("question_intent", {})
+        entities = [str(e) for e in ir.scope_constraints.get("entities", [])]
+        if (
+            isinstance(question_intent, dict)
+            and question_intent.get("relation") == "causes"
+            and len(entities) >= 1
+            and self.world_model_fast_path._accepted
+        ):
+            direction = str(question_intent.get("direction") or "outgoing")
+            fast_matches: list[WorldModelCandidate] = []
+            for entity in entities[:3]:
+                if direction == "incoming":
+                    fast_matches.extend(self.world_model_fast_path.lookup_causes_of(entity))
+                else:
+                    fast_matches.extend(self.world_model_fast_path.lookup_effects_of(entity))
+            if fast_matches:
+                summary_lines = [f"{c.rule} (confidence {c.confidence:.2f}, verified rule)" for c in fast_matches[:5]]
+                fast_signature = self._write_result_signature(
+                    "world_model_fast_path",
+                    "solved",
+                    "Answered from a human-approved world model rule (deterministic, no model inference).",
+                    user_id=request.user_id,
+                    confidence=min((c.confidence for c in fast_matches), default=0.9),
+                    provenance=[p for c in fast_matches for p in c.provenance.split(",") if p],
+                    data={"matched_rules": [c.model_dump(mode="json") for c in fast_matches], "summary_lines": summary_lines},
+                )
+                # Render path: existing TransformerRenderInterface handles
+                # "solved" + deterministic data identically to the symbolic
+                # math fast-confirm path — no new render logic needed.
+                return await self._render_and_respond(fast_signature, request)
```

> **Note for the implementing agent**: `_render_and_respond` is a
> placeholder name for "whatever existing helper turns a
> `ResultSignature` into the final `PipelineResponse` via
> `render_layer.render(...)`" — locate the exact function by following
> the call chain from line ~515 (`self.render_layer.render(obj)`)
> backward to find its enclosing helper, or inline the equivalent
> 5-10 lines if no single helper exists. This is the one piece of this
> diff that depends on pipeline internals not fully traced in this
> conversation — **test this specific wiring first**, since an
> incorrect early-return shape here is the most likely integration
> bug.

### Edit 5: `prototype/jimsai/autonomous_training_agent.py` — replace hardcoded constant with real computation

```diff
--- a/prototype/jimsai/autonomous_training_agent.py
+++ b/prototype/jimsai/autonomous_training_agent.py
@@ -428,7 +428,9 @@
-            world_model_confidence_avg=0.73,
+            world_model_confidence_avg=(
+                self.pipeline.world_model_promotion.stats()["avg_confidence"]
+                if getattr(self, "pipeline", None) is not None
+                else 0.0
+            ),
```

> **Note for the implementing agent**: if `AutonomousTrainingAgent`
> does not currently hold a `self.pipeline` reference, this edit also
> requires threading a pipeline reference into the agent's
> `__init__` — locate the agent's constructor and the call site that
> instantiates it (likely alongside `JimsAIPipeline()` instantiation)
> and pass `pipeline=pipeline_instance`. If threading a live reference
> is impractical, an acceptable fallback is persisting
> `world_model_promotion.stats()` to the same store
> `_generate_world_model_candidates` already writes to, and reading it
> back here instead.

---

## Test plan

1. **Unit test `world_model_promotion.py` standalone** (no pipeline
   needed):
   - Feed `WorldModelPromotionEngine.observe()` the same
     `WorldModelActivation(rule="A causes B", confidence=0.8, source="sig1")`
     twice — assert `newly_promoted == []` (count=2 < default min 3).
   - Feed a third time with a different `source` — assert exactly one
     `WorldModelCandidate(rule="A causes B", review_required=True)` is
     returned, and `observe()` called again with the same rule returns
     `[]` (already promoted, no duplicate).
   - Feed `WorldModelActivation(rule="C causes D", confidence=0.3, ...)`
     three times — assert never promoted (below `JIMS_WM_PROMOTION_MIN_CONF`).

2. **`WorldModelFastPath` standalone**:
   - `rebuild([WorldModelCandidate(rule="A causes B", confidence=0.9, provenance="sig1", review_required=False)])`
   - `lookup_effects_of("A")` returns the candidate; `lookup_effects_of("A")` with `review_required=True` in the input list returns `[]`.

3. **Integration — promotion accumulates across real queries**:
   - Ingest 3 documents/conversations each independently stating or
     implying "ServiceA causes ServiceB" (or any domain pair) such
     that `LatentWorldModelLayer.activate()` fires a `causes`
     activation for each (this already works today per
     `runtime_layers.py` line 649-662 — verify with existing
     ingestion tests first if uncertain).
   - After the 3rd query, assert
     `len(pipeline.world_model_candidates) == 1` and
     `pipeline.world_model_candidates[0].review_required is True`.

4. **Integration — review lifecycle**:
   - Call `review_action(ReviewActionRequest(action="accept", rule="ServiceA causes ServiceB", provenance=<from candidate>))`.
   - Assert `pipeline.world_model_candidates[0].review_required is False`.
   - Assert `pipeline.world_model_fast_path.lookup("ServiceA", "ServiceB")` returns the candidate.

5. **Integration — fast path fires**:
   - Send a new query phrased differently — e.g. "What does ServiceA
     cause?" or its equivalent in another supported language (since
     entity extraction is language-agnostic per the encoder).
   - Assert the response's `data.matched_rules` is non-empty, the
     pipeline's total wall-clock for this query is dramatically lower
     than a comparable non-fast-path query (target: <100ms vs.
     several seconds), and `used_groq`/`used_qwen_render` is `False`
     (no LLM was invoked).

6. **Regression — fast path does NOT fire incorrectly**:
   - Send a causal query for an entity pair with **no** accepted rule
     — assert it falls through to the normal pipeline unchanged
     (compare response shape/confidence to pre-change baseline).
   - Send a non-causal query (e.g. "What is my name?") — assert the
     fast-path block is skipped entirely (gated on
     `question_intent.get("relation") == "causes"`).

7. **`autonomous_training_agent.py`**:
   - Assert `world_model_confidence_avg` is `0.0` on a fresh pipeline
     with no promoted rules (not `0.73`), and changes to a real
     average once candidates exist — i.e. assert it is *not* a
     constant across two different pipeline states.

---

## Explicit non-goals (do not let scope creep here)

- Do **not** add fuzzy/embedding-similarity matching to
  `WorldModelFastPath.lookup*` in this iteration — exact
  normalized-string match only. Fuzzy matching is the "analogical
  generalization" research problem explicitly out of scope per the
  conversation this roadmap derives from.
- Do **not** auto-accept candidates regardless of confidence, however
  high. `review_required=True` is the default and the only path to
  `False` is a human-initiated `review_action`.
- Do **not** extend rule shapes beyond `"X causes Y"` in this
  iteration — that's the only shape `LatentWorldModelLayer` currently
  emits, and matching the promotion engine's input contract to the
  emitter's actual output is what keeps this scoped and testable.
