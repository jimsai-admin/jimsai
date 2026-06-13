# JimsAI Roadmap: Causal-Shape Abstraction Layer (Doc 13)

## Status

This is a scoped, buildable extension to roadmap-doc-12.md (literal
causal-pair promotion). It addresses the specific gap the revised
Prediction Trap paper names explicitly:

> "X causes Y" and "X leads to Y" are treated as different rules.
> Cross-domain structural analogy ... is explicitly out of scope for
> the current architecture and requires research beyond
> frequency-based promotion.

This document does **not** solve cross-domain analogy in general
(still out of scope, still an open research problem — see the ILP/
Neural-Logic-Machines discussion earlier in this conversation). It
adds one bounded, human-governed mechanism: **a small, fixed taxonomy
of causal "shapes"** that T1 tags alongside its existing literal
(cause, effect) extraction. Literal pairs that share no surface
similarity but share a *shape* (e.g. "increase in A → increase in
risk of B") become connected at a second, more abstract promotion
tier — without claiming the system has learned that A and B are
"the same kind of thing" in any deep sense. It has learned that two
*relationships* have the same *type signature*, which is a much
narrower and more tractable claim.

---

## Why this is scoped correctly (read before building)

- **The taxonomy is closed and human-authored.** ~20 shapes, defined
  once, in this document. T1 classifies into this fixed set — it does
  not invent new shapes. Expanding the taxonomy is a human edit to a
  constant, reviewed like any other code change.
- **T1 does the classification, not the generalization.** T1 is
  already proven (via `extract_structured_relations`) to reliably
  extract `(cause, effect, confidence)` triples in any language. Adding
  "and also: which of these 20 shapes does this relationship match,
  if any" is the same kind of task — classification against a
  provided list — not novel reasoning.
- **Shape-matches are never presented as facts.** They are presented
  as "pattern-based inference" with explicit provenance ("verified
  in N other domains, not verified for this specific pair") — a third
  response category, distinct from "verified fact" and "no
  information."
- **Promotion to shape-rules requires the same review gate** as
  literal-pair promotion (`review_required=True`, human
  accept/reject via the existing `review_action` lifecycle).

---

## The causal-shape taxonomy

A new constant, `CAUSAL_SHAPES`, defined once. Each shape has an id,
a human-readable description, and the *typed slots* a (cause, effect)
pair must fill to match it.

```python
CAUSAL_SHAPES: dict[str, dict[str, str]] = {
    "increase_increase": {
        "description": "An increase in X causes an increase in Y",
        "cause_pattern": "increase/rise/growth in {quantity}",
        "effect_pattern": "increase/rise/growth in {quantity_or_risk}",
    },
    "increase_decrease": {
        "description": "An increase in X causes a decrease in Y",
        "cause_pattern": "increase/rise/growth in {quantity}",
        "effect_pattern": "decrease/reduction/decline in {quantity}",
    },
    "decrease_increase": {
        "description": "A decrease in X causes an increase in Y",
        "cause_pattern": "decrease/reduction/loss of {quantity}",
        "effect_pattern": "increase/rise/growth in {quantity_or_risk}",
    },
    "decrease_decrease": {
        "description": "A decrease in X causes a decrease in Y",
        "cause_pattern": "decrease/reduction/loss of {quantity}",
        "effect_pattern": "decrease/reduction/decline in {quantity}",
    },
    "threshold_trigger": {
        "description": "X crossing a threshold/limit triggers Y (discrete state change)",
        "cause_pattern": "{quantity} exceeds/crosses/reaches {threshold}",
        "effect_pattern": "{state_change} occurs (e.g. failure, shutdown, alarm)",
    },
    "depletion_failure": {
        "description": "Exhaustion/depletion of a resource causes a failure or stop",
        "cause_pattern": "{resource} runs out / is depleted / is exhausted",
        "effect_pattern": "{system_or_process} fails/stops/halts",
    },
    "presence_enablement": {
        "description": "The presence of X enables/permits Y to occur",
        "cause_pattern": "{condition_or_entity} is present",
        "effect_pattern": "{action_or_state} becomes possible",
    },
    "absence_prevention": {
        "description": "The absence of X prevents/blocks Y",
        "cause_pattern": "{condition_or_entity} is absent/missing",
        "effect_pattern": "{action_or_state} is prevented/blocked",
    },
    "feedback_amplifying": {
        "description": "X causes more of itself via Y (positive feedback loop)",
        "cause_pattern": "{quantity} increases",
        "effect_pattern": "{same_quantity_or_driver} increases further via {mechanism}",
    },
    "feedback_dampening": {
        "description": "X causes less of itself via Y (negative feedback loop)",
        "cause_pattern": "{quantity} increases",
        "effect_pattern": "{same_quantity_or_driver} decreases via {mechanism}",
    },
    "delay_accumulation": {
        "description": "Repeated/sustained X accumulates to cause Y over time",
        "cause_pattern": "{condition} persists or repeats over time",
        "effect_pattern": "{cumulative_outcome} eventually occurs",
    },
    "substitution_displacement": {
        "description": "X replacing/displacing Y causes Z",
        "cause_pattern": "{entity_A} replaces/displaces {entity_B}",
        "effect_pattern": "{consequence} results",
    },
    "exposure_risk": {
        "description": "Exposure to/contact with X causes elevated risk of Y",
        "cause_pattern": "exposure to / intake of / contact with {agent}",
        "effect_pattern": "elevated risk or incidence of {outcome}",
    },
    "imbalance_dysfunction": {
        "description": "An imbalance between X and Y causes dysfunction Z",
        "cause_pattern": "{quantity_A} and {quantity_B} become imbalanced",
        "effect_pattern": "{dysfunction} occurs in {system}",
    },
    "dependency_cascade": {
        "description": "Failure/change in X propagates to dependents Y",
        "cause_pattern": "{component} fails/changes",
        "effect_pattern": "{dependent_components} are affected",
    },
    "input_output_transformation": {
        "description": "X is processed/transformed into Y",
        "cause_pattern": "{input} undergoes {process}",
        "effect_pattern": "{output} is produced",
    },
    "competition_reduction": {
        "description": "Increased competition for X reduces availability/share of X",
        "cause_pattern": "demand for / competition over {resource} increases",
        "effect_pattern": "availability/share of {resource} per participant decreases",
    },
    "regulation_correction": {
        "description": "A regulatory/control mechanism corrects a deviation in X",
        "cause_pattern": "{quantity} deviates from {target}",
        "effect_pattern": "{control_mechanism} adjusts {quantity} toward {target}",
    },
    "timing_misalignment": {
        "description": "X occurring at the wrong time relative to Y causes Z",
        "cause_pattern": "{event_A} occurs before/after {event_B} unexpectedly",
        "effect_pattern": "{problem} results from the misalignment",
    },
    "no_shape_match": {
        "description": "The relationship does not clearly match any defined shape",
        "cause_pattern": "",
        "effect_pattern": "",
    },
}
```

`no_shape_match` is always a valid, expected output — most causal
pairs may not cleanly fit a shape, and that's fine. This is an
*additive* layer; pairs that don't match a shape still work exactly
as in roadmap-doc-12 (literal-pair promotion only).

---

## Implementation

### Edit 1: `model_bridge.py` — extend `extract_structured_relations`'s prompt

Add shape classification to the existing causal extraction call —
same API call, no new round trip.

```diff
--- a/prototype/jimsai/model_bridge.py
+++ b/prototype/jimsai/model_bridge.py
@@ async def extract_structured_relations(self, text, modality="text"):
+        shape_list = "\n".join(
+            f"  - {shape_id}: {info['description']}"
+            for shape_id, info in CAUSAL_SHAPES.items()
+            if shape_id != "no_shape_match"
+        )
         system = (
             "You are a structured-extraction engine for JimsAI. Return only JSON. "
             "Read the text in ANY language and extract: "
             "(1) entities — named things (services, people, chemicals, concepts, code symbols), "
             "(2) relations — subject-predicate-object triples using snake_case predicates "
             "(depends_on, is_a, has_field, means, etc.), "
             "(3) causal — ONLY explicit cause-effect pairs where one stated thing "
             "directly causes another stated thing. Do not extract a causal pair from "
             "a sentence fragment, a single noun phrase, or a partial match — both "
             "cause and effect must be complete, meaningful entities/concepts as they "
             "appear in the text. If a sentence has no clear causal claim, emit nothing "
             "for it, even if it contains a word like 'causes'. "
-            "confidence 0.0-1.0 per item. "
+            "confidence 0.0-1.0 per item. "
+            "For each causal item, ALSO classify its abstract relationship 'shape' "
+            "from this fixed list (use 'no_shape_match' if none clearly fits — this "
+            "is a common and expected answer, do not force a match):\n"
+            f"{shape_list}\n"
+            "Add a 'shape' field (one of the ids above) and 'shape_confidence' "
+            "(0.0-1.0) to each causal item. shape_confidence reflects how clearly "
+            "the pair fits that shape, independent of the causal confidence itself. "
             "Example: 'A net force causes acceleration. Friction causes deceleration.' -> "
-            "causal: [{\"cause\": \"net force\", \"effect\": \"acceleration\", \"confidence\": 0.92}, "
-            "{\"cause\": \"friction\", \"effect\": \"deceleration\", \"confidence\": 0.94}] "
+            "causal: [{\"cause\": \"net force\", \"effect\": \"acceleration\", \"confidence\": 0.92, "
+            "\"shape\": \"increase_increase\", \"shape_confidence\": 0.85}, "
+            "{\"cause\": \"friction\", \"effect\": \"deceleration\", \"confidence\": 0.94, "
+            "\"shape\": \"increase_decrease\", \"shape_confidence\": 0.8}] "
             "NOT {\"cause\": \"net\", \"effect\": \"causes\"} or {\"cause\": \"force\", \"effect\": \"causes\"}."
         )
```

> **Note for implementing agent**: `CAUSAL_SHAPES` should be defined
> in a new module `causal_shapes.py` and imported into
> `model_bridge.py` and `world_model_promotion.py` (avoid duplicating
> the dict).

### Edit 2: `models.py` — add shape fields to `CausalLink` and a new `CausalShapeCandidate`

```diff
--- a/prototype/jimsai/models.py
+++ b/prototype/jimsai/models.py
@@ class CausalLink(BaseModel):
     cause: str
     effect: str
     confidence: float
+    shape: str | None = None
+    shape_confidence: float | None = None
```

```diff
+class CausalShapeCandidate(BaseModel):
+    """A promoted abstraction: 'relationships of this shape have been
+    independently verified across N domains'. Distinct from
+    WorldModelCandidate (which is a single literal cause→effect rule).
+
+    review_required follows the same governance pattern — a shape
+    candidate only becomes usable for pattern-based-inference responses
+    after human acceptance.
+    """
+    shape: str
+    description: str
+    example_pairs: list[tuple[str, str]]  # (cause, effect) instances observed
+    domains_observed: list[str]           # e.g. ["physics", "medicine", "economics"]
+    avg_confidence: float
+    review_required: bool = True
```

### Edit 3: `dual_encoder.py` — pass shape fields through to `CausalLink`

```diff
--- a/prototype/jimsai/encoder/dual_encoder.py
+++ b/prototype/jimsai/encoder/dual_encoder.py
@@ in _extract, the causal-link construction inside add_relation
-            if predicate == "causes":
-                link = CausalLink(cause=subject, effect=obj, confidence=confidence)
-                if link not in causal:
-                    causal.append(link)
+            if predicate == "causes":
+                link = CausalLink(
+                    cause=subject, effect=obj, confidence=confidence,
+                    shape=shape, shape_confidence=shape_confidence,
+                )
+                if link not in causal:
+                    causal.append(link)
```

```diff
@@ in _extract, where t1_data causal items are iterated
         for link in t1_data.get("causal", []):
             if not isinstance(link, dict):
                 continue
             cause = clean_ref(str(link.get("cause", "")))
             effect = clean_ref(str(link.get("effect", "")))
             if not cause or not effect:
                 continue
             try:
                 conf = float(link.get("confidence", 0.8))
             except (TypeError, ValueError):
                 conf = 0.8
-            add_relation(cause, "causes", effect, max(0.0, min(1.0, conf)))
+            shape = str(link.get("shape") or "no_shape_match")
+            if shape not in CAUSAL_SHAPES:
+                shape = "no_shape_match"
+            try:
+                shape_conf = float(link.get("shape_confidence", 0.0))
+            except (TypeError, ValueError):
+                shape_conf = 0.0
+            add_relation(
+                cause, "causes", effect, max(0.0, min(1.0, conf)),
+                shape=shape, shape_confidence=max(0.0, min(1.0, shape_conf)),
+            )
```

> `add_relation`'s signature gains two optional kwargs
> (`shape: str | None = None, shape_confidence: float | None = None`),
> threaded through to the `CausalLink` construction above. The
> non-causal `Relation` object is unaffected — shapes apply only to
> `CausalLink`.

### New file: `prototype/jimsai/causal_shapes.py`

Contains only the `CAUSAL_SHAPES` dict from this document, plus a
helper:

```python
def is_valid_shape(shape: str | None) -> bool:
    return shape in CAUSAL_SHAPES and shape != "no_shape_match"
```

### Edit 4: `world_model_promotion.py` — second promotion track

```diff
--- a/prototype/jimsai/world_model_promotion.py
+++ b/prototype/jimsai/world_model_promotion.py
@@
-from .models import WorldModelActivation, WorldModelCandidate
+from .causal_shapes import CAUSAL_SHAPES, is_valid_shape
+from .models import CausalShapeCandidate, WorldModelActivation, WorldModelCandidate
```

```diff
+@dataclass
+class _ShapeObservation:
+    shape: str
+    pairs: dict[tuple[str, str], float] = field(default_factory=dict)  # (cause, effect) -> confidence
+    domains: set[str] = field(default_factory=set)  # provenance/workspace tags, used as a coarse domain proxy
+
+    @property
+    def avg_confidence(self) -> float:
+        if not self.pairs:
+            return 0.0
+        return sum(self.pairs.values()) / len(self.pairs)
```

```diff
 class WorldModelPromotionEngine:
     def __init__(self) -> None:
         self._observations: dict[str, _RuleObservation] = {}
         self._promoted_keys: set[str] = set()
+        self._shape_observations: dict[str, _ShapeObservation] = {}
+        self._promoted_shapes: set[str] = set()
+
+    def _shape_min_pairs(self) -> int:
+        """Minimum distinct (cause, effect) pairs across distinct domains
+        before a shape is promoted. Higher than literal-pair threshold —
+        a shape candidate is a stronger claim (cross-domain pattern)."""
+        try:
+            return max(2, int(os.getenv("JIMS_WM_SHAPE_PROMOTION_MIN_PAIRS", "3")))
+        except ValueError:
+            return 3
+
+    def _shape_min_domains(self) -> int:
+        try:
+            return max(2, int(os.getenv("JIMS_WM_SHAPE_PROMOTION_MIN_DOMAINS", "2")))
+        except ValueError:
+            return 2
```

```diff
     def observe(self, activations: list[WorldModelActivation]) -> list[WorldModelCandidate]:
         ...  # UNCHANGED literal-pair logic from roadmap-doc-12
+        return newly_promoted
+
+    def observe_causal_links(
+        self, causal_links: list, domain_hint: str = "unknown"
+    ) -> list[CausalShapeCandidate]:
+        """Second promotion track. Call this at ingestion time (not query
+        time) with the CausalLink objects produced by the encoder for a
+        signature — each link may carry .shape and .shape_confidence.
+
+        domain_hint: a coarse label for "what kind of source is this" —
+        e.g. the ingestion request's declared domain/tag, or
+        signature.workspace_id, or the top abstraction_tag. Used only to
+        diversify domains_observed; does not affect the shape match itself.
+
+        Returns newly-promoted CausalShapeCandidate objects (empty if none).
+        """
+        newly_promoted: list[CausalShapeCandidate] = []
+        for link in causal_links:
+            shape = getattr(link, "shape", None)
+            shape_conf = getattr(link, "shape_confidence", None) or 0.0
+            if not is_valid_shape(shape) or shape_conf < 0.6:
+                continue
+            obs = self._shape_observations.setdefault(shape, _ShapeObservation(shape=shape))
+            pair = (link.cause.strip().lower(), link.effect.strip().lower())
+            obs.pairs[pair] = max(obs.pairs.get(pair, 0.0), float(link.confidence))
+            obs.domains.add(domain_hint)
+
+            if (
+                shape not in self._promoted_shapes
+                and len(obs.pairs) >= self._shape_min_pairs()
+                and len(obs.domains) >= self._shape_min_domains()
+            ):
+                self._promoted_shapes.add(shape)
+                newly_promoted.append(
+                    CausalShapeCandidate(
+                        shape=shape,
+                        description=CAUSAL_SHAPES[shape]["description"],
+                        example_pairs=[(c, e) for c, e in obs.pairs.keys()],
+                        domains_observed=sorted(obs.domains),
+                        avg_confidence=round(obs.avg_confidence, 4),
+                        review_required=True,
+                    )
+                )
+        return newly_promoted
```

```diff
+class CausalShapeFastPath:
+    """Lookup of ACCEPTED (review_required=False) CausalShapeCandidates,
+    keyed by shape id. Used to answer novel queries with explicit
+    pattern-based inference when no literal fact matches.
+    """
+    def __init__(self) -> None:
+        self._accepted: dict[str, CausalShapeCandidate] = {}
+
+    def rebuild(self, candidates: list[CausalShapeCandidate]) -> None:
+        self._accepted = {c.shape: c for c in candidates if not c.review_required}
+
+    def lookup(self, shape: str) -> CausalShapeCandidate | None:
+        return self._accepted.get(shape)
```

### Edit 5: `pipeline.py` — wire shape observation at ingestion, shape fast-path for novel queries

```diff
--- a/prototype/jimsai/pipeline.py
+++ b/prototype/jimsai/pipeline.py
@@ __init__
         self.world_model_promotion = WorldModelPromotionEngine()
         self.world_model_fast_path = WorldModelFastPath()
+        self.causal_shape_fast_path = CausalShapeFastPath()
+        self.causal_shape_candidates: list[CausalShapeCandidate] = []
```

```diff
@@ ingestion path, after encoder.encode() produces `signature`
         # existing roadmap-doc-12 literal promotion happens at query time
         # via world_model_layer activations; shape promotion happens here,
         # at ingestion time, directly from the encoder's causal_chain —
         # no need to wait for a query to traverse the graph.
+        domain_hint = (signature.abstraction_tags[0] if signature.abstraction_tags else "unknown")
+        newly_promoted_shapes = self.world_model_promotion.observe_causal_links(
+            signature.structured.causal_chain, domain_hint=domain_hint
+        )
+        if newly_promoted_shapes:
+            existing = {c.shape for c in self.causal_shape_candidates}
+            self.causal_shape_candidates.extend(c for c in newly_promoted_shapes if c.shape not in existing)
+            self.causal_shape_fast_path.rebuild(self.causal_shape_candidates)
```

```diff
@@ in review_action, extend action handling to cover shape candidates
+        # review_action gains an optional `candidate_type: "literal" | "shape"`
+        # field (default "literal" for backward compatibility). When "shape",
+        # operate on self.causal_shape_candidates instead of
+        # self.world_model_candidates, then call
+        # self.causal_shape_fast_path.rebuild(self.causal_shape_candidates).
```

```diff
@@ query path — AFTER the existing world_model_fast_path check (Edit 4 of
   roadmap-doc-12) and AFTER normal retrieval has run and found sources == 0
   (i.e. this is the LAST resort before the existing "withhold, gap" response):
+        if (
+            isinstance(question_intent, dict)
+            and question_intent.get("relation") == "causes"
+            and not sources  # normal retrieval found nothing
+        ):
+            # Ask T1 to classify THIS query's causal shape (cheap, same
+            # call shape as extract_structured_relations, just on the
+            # query text instead of ingested content).
+            query_shape_data = await self.bridge.extract_structured_relations(request.query, "text")
+            query_shape = None
+            if query_shape_data:
+                for link in query_shape_data.get("causal", []):
+                    if isinstance(link, dict) and link.get("shape_confidence", 0) >= 0.6:
+                        query_shape = link.get("shape")
+                        break
+            shape_candidate = self.causal_shape_fast_path.lookup(query_shape) if query_shape else None
+            if shape_candidate:
+                examples = ", ".join(f"{c}->{e}" for c, e in shape_candidate.example_pairs[:3])
+                pattern_signature = self._write_result_signature(
+                    "causal_shape_pattern_inference", "pattern_inferred",
+                    f"No verified fact for this specific relationship. However, relationships of "
+                    f"this type ({shape_candidate.description}) have been independently verified "
+                    f"across {len(shape_candidate.domains_observed)} domains "
+                    f"({', '.join(shape_candidate.domains_observed)}), e.g.: {examples}. "
+                    f"This suggests a SIMILAR relationship MAY hold here, but this specific "
+                    f"claim is NOT independently verified.",
+                    user_id=request.user_id,
+                    confidence=min(0.5, shape_candidate.avg_confidence * 0.6),  # deliberately capped below "verified" range
+                    provenance=[],
+                    data={
+                        "shape": shape_candidate.shape,
+                        "pattern_based": True,
+                        "verified_fact": False,
+                        "example_pairs": shape_candidate.example_pairs[:5],
+                        "domains_observed": shape_candidate.domains_observed,
+                    },
+                )
+                return await self._render_and_respond(pattern_signature, request)
+            # else: fall through to existing gap/withholding behavior, unchanged
```

> The confidence cap (`min(0.5, avg_confidence * 0.6)`) is deliberate
> and important — pattern-based inference must NEVER score in the
> "verified fact" confidence range, so it can never be confused with
> or silently override a real retrieved fact, and so T2's render
> (per Patch B from earlier in this conversation) treats it as
> explicitly provisional.

---

## Test plan

1. **Shape classification unit test**: feed
   `extract_structured_relations` two lexically unrelated sentences —
   "High blood pressure increases the risk of stroke" (medicine) and
   "Rising inflation increases the cost of borrowing" (economics).
   Assert both causal items get `shape="increase_increase"` (or
   another *shared* shape) with `shape_confidence >= 0.6`. This is
   the core claim of the whole mechanism — if T1 can't reliably
   co-classify these, the rest doesn't matter, so test this FIRST in
   isolation before building anything downstream.

2. **No-match is common and fine**: feed several causal sentences that
   genuinely don't fit any shape (e.g. highly specific mechanistic
   claims). Assert a meaningful fraction return `"no_shape_match"` —
   if T1 *never* returns `no_shape_match`, the classification is
   over-eager and the prompt needs tightening (forcing matches is
   worse than not matching).

3. **Shape promotion threshold**: ingest 3+ signatures from 2+
   different `domain_hint`s, each containing a causal link classified
   to the same shape with `shape_confidence >= 0.6`. Assert
   `pipeline.causal_shape_candidates` contains exactly one
   `CausalShapeCandidate` for that shape, `review_required=True`,
   `domains_observed` has ≥2 entries.

4. **Review and fast-path activation**: accept the shape candidate via
   `review_action(candidate_type="shape", action="accept", ...)`.
   Assert `causal_shape_fast_path.lookup(shape)` returns it.

5. **Novel query gets pattern-based inference, not a gap or hallucination**:
   send a query about a *third* domain's causal relationship that (a)
   has zero retrieved sources (genuinely novel to memory) and (b) T1
   classifies as matching the accepted shape with `shape_confidence >=
   0.6`. Assert the response's `data.pattern_based == True`,
   `data.verified_fact == False`, `confidence <= 0.5`, and the
   rendered text explicitly distinguishes "this pattern has been seen
   elsewhere" from "this specific fact is verified."

6. **Regression — does not leak into verified-fact responses**: for a
   query where normal retrieval DOES find sources, assert the shape
   fast-path block is never reached (gated on `not sources`) and the
   response is unaffected by this entire feature.

7. **Regression — T2 doesn't upgrade pattern inference to fact**: with
   Patch B's anti-hallucination rule extended to recognize
   `data.verified_fact == False`, assert T2's rendered response
   contains hedging language ("may", "similar", "not verified for
   this specific case") and never states the inferred relationship as
   settled fact.

---

## What this does and does not claim, restated

**Does**: gives JimsAI a third response category — "I haven't verified
this specific fact, but I've verified that relationships shaped like
this one hold across N other domains" — for a bounded, human-reviewed,
explicitly-labeled set of ~20 relationship shapes. This is a genuine,
if modest, capability beyond pure literal-fact retrieval, and it is
the most honest version of "JimsAI attempts something on novel
questions" that doesn't require pretending the 4B ceiling or the
open analogical-generalization problem don't exist.

**Does not**: discover new shapes, generalize to relationships outside
the fixed taxonomy, replace the small model's own knowledge for novel
queries that don't have a causal-shape structure at all (most
"explain X" or "write Y" requests aren't causal pairs), or make any
claim about the *correctness* of a shape-matched inference for a
specific new pair — only that the *pattern* has precedent. Every
shape-based response should read, to the user, as visibly different
in kind from a verified-fact response — that distinction in the
render is the feature, not a caveat to hide.
