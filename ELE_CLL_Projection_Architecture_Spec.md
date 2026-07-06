# ELE + CLL + Projection Architecture
## Engineering Specification for Replacing T1 (Intent Classification) and T2 (Language Rendering)

**Status**: Draft for implementation
**Audience**: Coding agent (Claude Code / Opus 4.8)
**Purpose**: Replace the current T1 (intent → structured IR) and T2 (VCO → natural language) LLM-based components with a modular, auditable, continuously-learning system: ELE (language engine) + CLL (concept/meaning layer) + a shared Projection runtime.

---

## 0. How to use this document

Every claim below is labeled:
- **[PROVEN]** — demonstrated in a real, code-executed experiment, with numbers. Build on these with confidence.
- **[PARTIAL]** — some evidence, real limitations found, do not assume it generalizes.
- **[UNKNOWN]** — never tested. Treat as a hypothesis to validate, not a design assumption.
- **[BUG FOUND]** — a specific implementation mistake was found and should not be repeated.

Do not upgrade an [UNKNOWN] to [PROVEN] in your own reasoning just because the architecture is elegant. Every module below should ship with the test that would falsify it, and that test should run before the module is considered done.

---

## 1. Why this architecture, and what it is NOT claiming

Modern LLM-based T1/T2 components compress language understanding, world knowledge, reasoning, and generation into one set of weights. This is expensive, hard to audit, and requires retraining to update.

The proposed alternative separates concerns:

```
Input language
      │
      ▼
   ELE (Expert Language Engine)
      │   -- discovers/recognizes constructions, produces structured frames
      │   -- NO world knowledge
      ▼
   CLL (Concept/Meaning Layer)
      │   -- maps frames to operational concepts, feeds L1/L6/L8/L9
      │   -- NOT a parser, NOT a language model
      ▼
Semantic Ledger (append-only) ──▶ Projection Engine ──▶ current views
      │
      ▼
   ELE (render mode)
      │   -- turns a verified structured object (VCO) back into fluent text
      │   -- NEVER invents content not present in the VCO
      ▼
Natural language output
```

**[PROVEN]** This separation is not just diagram — see §3 for the actual experiments.

**What this system is NOT claiming (do not build toward these):**
- It is **not** claiming to replace a general-purpose LLM for open-domain reasoning, world knowledge, or unconstrained generation. **[UNKNOWN]**, and probably false at current scale.
- It is **not** claiming ELE alone can do open-domain parsing of arbitrary English. **[UNKNOWN]**.
- It is **not** claiming the ledger scales to millions of events with no efficiency loss. **[UNKNOWN]** — never tested past a few thousand.

**What it IS a defensible claim for:** replacing T1 (closed-schema intent/structure extraction) and T2 (rendering an already-verified fact object into text) with something smaller, auditable, and incrementally updatable, in a bounded domain.

---

## 2. Grounding summary — what has actually been shown

| # | Claim | Status | Evidence |
|---|---|---|---|
| 1 | Constructions can be discovered from raw text with no parser | **[PROVEN]** | Frequency+diversity thresholds recovered `how is % feeling ?`, `finally % slept all day`, `% saw a %` from raw sentences |
| 2 | Word categories (roles) emerge from pure distribution | **[PARTIAL]** | OBJECT cluster purity 1.00 (10/10), ADJECTIVE cluster purity 1.00, but SUBJECT cluster leaked in the verb "saw" (purity 0.67) |
| 3 | A small symbolic ledger beats a small transformer on next-token prediction | **[DISPROVEN at this scale]** | Ledger (526 constructions): test perplexity 15.53. Tiny transformer (20,594 params): test perplexity 2.58. The transformer won by ~6x |
| 4 | Ledger updates are cheaper than retraining | **[PROVEN]** | New-data ingestion: ledger ~10ms vs transformer ~35+ seconds to retrain |
| 5 | Ledger corrections are auditable; neural corrections are not | **[PROVEN, with a gap]** | Ledger retained both `{'reptiles': 20, 'mammals': 20}` after correction, 0.16ms, fully inspectable — but does NOT automatically resolve which is current truth. That requires a versioning/override layer not yet built |
| 6 | A template-based renderer (ELE as T2) can achieve zero hallucination | **[PROVEN, architecturally]** | 100% match, 0/30 hallucinations on held-out compositional combos, because there is no generative step over vocabulary — only slot substitution |
| 7 | A small neural renderer can hallucinate even at toy scale | **[PROVEN]** | A 42K-param renderer got 96.7% right but on one case invented an unlisted recipient role: input `SEE(agent=alice, object=ball)` → output `"alice gave alice a ball ."` |
| 8 | ELE can generalize to a new predicate type via a known structural shape | **[PROVEN]** | A "TELL" type never registered with ELE rendered correctly because verb/article were frame *data*, not baked into the template, and the ditransitive shape was already known from "GIVE" |
| 9 | A genuinely new shape should fail safely, not guess | **[PROVEN]** | An unseen 5-role shape correctly raised an explicit `GAP_UNRESOLVED` instead of guessing. A naive nearest-shape fallback silently dropped an entire argument ("at the park" vanished with no warning) — the failure mode explicit gaps are meant to prevent |
| 10 | Composing core-shape + independently-learned adjuncts closes shape gaps | **[PROVEN]** | The 5-role case above rendered correctly once "location" was treated as a separately-learned adjunct that composes onto any core shape |
| 11 | Cross-verb spread alone is not sufficient to separate adjuncts from core arguments | **[PROVEN, real bug found]** | On an independently-built negative control, the direct-object slot `a %` passed a `spread >= 3` filter meant to catch only adjuncts (determiners generalize across verbs too) |
| 12 | Evidence-weighted spread (a real, uploaded implementation) amplifies concentrated evidence, including negative controls | **[PROVEN — reproduces the implementers' own documented finding]** | A verb-tied distractor ("with enthusiasm", tied only to one verb) ranked #1 by spread_weighted (5.518), above every genuine adjunct |
| 13 | Obligatoriness (does a slot appear in ~100% vs a minority of a verb's sentences) fixes #11 and #12 | **[PROVEN, with calibration caveat]** | Correctly classified all 4 original cases; correctly classified 2 harder edge cases after tightening the threshold from 0.9 to ≥0.95 |
| 14 | A specific implementation bug in an existing morphology-handling benchmark | **[BUG FOUND]** | Tail keys like `('park', 'LOC-SUFFIX')` never collapse to a generalized `LOC-SUFFIX`, so precision/recall on that test is always 0.0/0.0/0.0 regardless of algorithm quality — the base word stays glued to the suffix in the tail key |
| 15 | Several benchmark subtests are structurally vacuous | **[BUG FOUND]** | Tests using a single fixed filler word per slot cannot trigger the wildcard/diversity-based discovery mechanism at all — they return near-zero results independent of whether the discovery logic works |

**Rule for the coding agent:** do not re-derive #3 as a reason to abandon the architecture, and do not treat #6/#8/#10/#13 as proof the whole system works end-to-end. Each row is a narrow, falsifiable claim about one mechanism, tested in isolation, at toy scale.

---

## 3. Component specifications

### 3.1 ELE — Expert Language Engine

**Responsibility:** discover and recognize constructions; parse input into structured frames; render structured frames (VCOs) into fluent text. No world knowledge.

#### 3.1.1 Evidence Ledger (data model)

Use an append-only ledger per construction candidate. Do not deviate from this invariant:

> **Invariant**: the Evidence Ledger is the only mutable state. All behavioral metrics, confidence values, and acceptance decisions must be derivable purely as a function of the ledger contents. Recomputing from the same ledger must always produce identical results regardless of insertion order.

```python
@dataclass
class Observation:
    predicate: str                    # the verb/head token co-occurring with this candidate
    attachment_position: str          # e.g. "final", "medial"
    participant_slots: List[Dict]     # lightweight slot metadata
    language: str
    timestamp: str

@dataclass
class EvidenceLedger:
    observations: List[Observation]
    provenance: Dict[str, Any]

    def add_observation(self, obs: Observation):
        self.observations.append(obs)   # ONLY mutation allowed
```

All of BehavioralProfile, GeneralizationProfile, EvidenceQuality must be pure functions of `EvidenceLedger.observations`. Do not cache mutable derived state that can drift from the ledger.

#### 3.1.2 Construction discovery (parser-free)

Method **[PROVEN]** to work on toy corpora:
1. Mine n-grams (n=3..6). For each n-gram, mask one position at a time to form a candidate frame (fixed tokens + one wildcard).
2. A frame is promoted to a construction if it recurs ≥ `MIN_FRAME_COUNT` times with ≥ `MIN_FILLER_DIVERSITY` distinct fillers in the wildcard position.
3. Confidence is a simple smoothed function of count: `count / (count + k)`.

**Known limitation [PARTIAL]:** distributional clustering of filler words into categories (e.g., subject-nouns vs verbs) is not fully reliable — expect some cross-category leakage (a frequent verb can leak into a noun cluster via shared slot contexts). Do not assume clean unsupervised categories without a held-out purity check.

#### 3.1.3 Core-shape vs. adjunct discovery (the hard part)

This is the mechanism most likely to be under-engineered if copied naively. Do not use cross-predicate spread as the only signal — it is provably insufficient.

**Required criteria (conjunctive, not a single score):**

1. **Cross-verb spread**: number of distinct predicates (verbs) a candidate tail co-occurs with. `spread >= 3` as a starting threshold, but see calibration note below.
2. **Obligatoriness** — **this is the criterion that fixes the false positives found in testing**:
   ```
   obligatoriness(tail, verb) = (# sentences with verb containing tail ANYWHERE in the sentence)
                                 / (total # sentences with that verb)
   ```
   Scan the **whole sentence**, not just the trailing tokens — a core argument can be pushed out of final position by an attached adjunct, and a suffix-only scan will misread it as "detachable."

   Classification:
   ```
   if max_obligatoriness_across_verbs >= OBLIG_THRESHOLD:
       → CORE_ARGUMENT (reject as adjunct)
   elif cross_verb_spread >= SPREAD_THRESHOLD:
       → ADJUNCT (accept)
   else:
       → VERB_TIED (reject — likely a distractor / insufficiently evidenced)
   ```

**Calibration warning [PROVEN via edge case testing]:**
- `OBLIG_THRESHOLD = 0.9` is too loose. A true adjunct with strong (but not categorical) collocation to one verb — e.g., 92% co-occurrence by preference, not grammatical requirement — will be misclassified as CORE_ARGUMENT at 0.9. Raising to **≥0.95** fixed this in testing without breaking the correctly-classified core-argument cases (which sit at a clean 1.000 with thousands of samples).
- This threshold should ultimately be tied to an evidence-quantity/confidence measure, not a fixed constant — with sparse data, a genuinely-required argument and a strong collocation can look statistically identical. Do not ship a fixed threshold without also gating on minimum sample size per verb.
- A real adjunct observed with too few distinct verbs (e.g., only 2, below `SPREAD_THRESHOLD`) will be correctly rejected as unproven — this is **acceptable, conservative behavior**, not a bug. It should self-correct as more data arrives (verified: adding a 3rd verb's worth of evidence flipped the decision from rejected to accepted with no code change).

**Do not repeat this bug [BUG FOUND]:** when generalizing morphological suffixes (e.g., "-loc" as a location marker), make sure the tail key used for grouping actually strips the base word — a bug was found where `('park', 'LOC-SUFFIX')` and `('school', 'LOC-SUFFIX')` were tracked as two separate constructions instead of collapsing to one generalized `LOC-SUFFIX` type, silently breaking precision/recall to exactly 0.0.

#### 3.1.4 Rendering (T2 replacement)

**Core design principle [PROVEN to work, and to matter]:** the verb and any lexical choice (e.g., article "a" vs "the") must be **fields on the input frame (data)**, not baked into a per-type template. This is what let a never-registered predicate ("TELL") render correctly by reusing an existing structural shape ("GIVE"'s ditransitive shape).

```python
SHAPE_TEMPLATES = {
    ("agent","verb","recipient","object"): "{agent} {verb} {recipient} {article} {object} .",
    ("agent","verb","object"):             "{agent} {verb} {article} {object} .",
}

def render(frame):
    shape = frame["shape"]
    if shape not in SHAPE_TEMPLATES:
        raise GapReport(shape)   # explicit failure -- do NOT guess or silently drop content
    return SHAPE_TEMPLATES[shape].format(**frame)
```

**Adjunct composition [PROVEN]:** do not try to enumerate every possible shape (core args + every combination of adjuncts) as one giant template set — this doesn't scale and won't generalize to unseen combinations. Instead:
```python
CORE_ROLES = {"agent","verb","recipient","object","article"}
ADJUNCTS = {"location": " at {location}", "time": " {time}"}

def render_v2(frame):
    core_roles = tuple(r for r in frame["shape"] if r in CORE_ROLES)
    adjunct_roles = [r for r in frame["shape"] if r not in CORE_ROLES]
    if core_roles not in SHAPE_TEMPLATES:
        raise GapReport(core_roles)
    base = SHAPE_TEMPLATES[core_roles].format(**frame).rstrip(" .")
    for role in adjunct_roles:
        if role not in ADJUNCTS:
            raise GapReport((core_roles, "unknown_adjunct:"+role))
        base += ADJUNCTS[role].format(**frame)
    return base + " ."
```
This let a 5-role frame the system had never seen as a whole render correctly, by combining an already-known 4-role core with an independently-learned "location" adjunct.

**Gap handling policy — do not deviate:**
- A missing core shape or unknown adjunct must raise an explicit, typed error (e.g., `GapReport`), never fall back to a "closest" template silently. A naive nearest-shape fallback was tested and found to silently drop entire arguments (a location phrase vanished with no signal). Route gaps to a fallback renderer (which may be a general LLM, clearly flagged as unverified) or a human review queue — never to a silent best-guess from ELE itself.

### 3.2 CLL — Concept/Meaning Layer

**Responsibility:** map ELE's structured frames to operational concepts and feed L1/L6/L8/L9. **[UNKNOWN — not yet built or tested in this thread.]** Everything below is design guidance, not a validated result.

- CLL should consume ELE's frame output (typed roles: agent, verb, recipient, object, adjuncts) and produce concept-graph nodes/edges, not raw text.
- CLL is the layer that should resolve genuine ambiguity requiring world knowledge (e.g., pronoun resolution like "the trophy didn't fit in the suitcase because it was too big") — **ELE should not attempt this.** ELE's job is to expose the ambiguity (e.g., multiple candidate parses/referents), CLL's job is to resolve it using the ledger/world model.
- Before building CLL's integration with L1/L6/L8/L9, confirm the projection primitive (§3.3) actually scales to the data volumes those layers imply (thousands to millions of events) — this has only been tested at toy scale (a few hundred events) and is flagged **[UNKNOWN]** at production scale.

### 3.3 Projection Engine

**Responsibility:** compute current views (meaning, trust, time, domain) from the append-only semantic ledger without mutating it.

**[PROVEN at toy scale]:** the same computational pattern (store event → compute view via projection parameters) worked across multiple different problems: temporal reasoning, trust filtering, quotation/contradiction handling, domain-sensitive interpretation. This is the strongest-evidenced piece of the whole architecture, but strength here means "the mechanism is real and reusable," not "it scales."

**[UNKNOWN]:** whether projection remains efficient (in latency and memory) as the ledger grows past a few hundred/thousand events toward the scale a production memory/reasoning layer would need. This should be the first thing benchmarked before committing to this as the retrieval mechanism for L6.

---

## 4. Required test methodology (do not skip these)

Every new mechanism you build must ship with:

1. **An equal-resource baseline.** Do not report a symbolic mechanism's success without comparing it against a neural approach at a comparable parameter/compute budget. (See row 3 in §2 — the ledger lost badly on raw perplexity at equal-ish scale. Report negative results as clearly as positive ones.)
2. **A negative control built independently of the acceptance criteria being tested.** The most valuable finding in this project (row 12, §2) came from building a distractor corpus *before* looking at the target implementation's gold-standard test set — this avoids the circularity of a system passing tests it was tuned against.
3. **Edge cases at the threshold boundary**, not just clean-cut cases. Silent misclassification near a threshold (row 13, §2 — the 92%-collocation adjunct) is a realistic failure mode, not a contrived one.
4. **Explicit failure/gap tests**, not just success-path tests. Confirm the system fails loudly (typed exception, audit-logged) rather than guessing, whenever it's outside its known coverage.
5. **Held-out compositional combinations**, not just held-out sentences — test whether the system generalizes to *new combinations* of things it has individually seen (e.g., a (agent, object) pair that never co-occurred in training), not just memorized sentences with new noise.

---

## 5. Explicit non-goals (do not build these without a separate design doc)

- Open-domain parsing across arbitrary English syntax.
- Long-form narrative generation, discourse planning, multi-turn dialogue management.
- Any claim that this system "replaces" a general LLM rather than replacing bounded T1/T2 roles.
- Retuning acceptance thresholds informally during development — thresholds should be derived from a frozen calibration set and then frozen, per the R1.2b methodology, with the actual numeric values recorded in this document once derived.
- Semantic role labeling beyond the lightweight participant-slot tracking already in R1 (this is explicitly deferred to a future representation phase).

---

## 6. Suggested build order

1. Get the Evidence Ledger + core-shape/adjunct discovery + obligatoriness criterion running on a synthetic corpus with known ground truth (reuse the corpora described in §2, rows 11-13, as regression tests — they already caught 2 real bugs).
2. Get the renderer (§3.1.4) working against the discovery output from step 1, with explicit gap-handling wired to a fallback path (not silent).
3. Only then attempt CLL's frame→concept mapping, on a small closed domain.
4. Before wiring CLL into L1/L6/L8/L9, run a standalone projection-scaling benchmark (latency/memory vs. ledger size, from 100 to 100,000+ events) — this is the biggest untested assumption in the whole stack.
5. At every step, keep the perplexity/equal-budget baseline test (§4.1) running as a regression check — if a future version of ELE's discovery+render pipeline is claimed to be "as good as" a neural approach for some task, that claim needs the same kind of test that produced row 3 in §2, not an assumption.

---

## 7. Open questions to resolve before scaling up

- What is the actual, data-derived value for `OBLIG_THRESHOLD` and `SPREAD_THRESHOLD`? (Currently illustrative constants from toy-corpus testing, not calibrated from a real distribution.)
- Does the "verb = 2nd token" heuristic used throughout this testing generalize to real text, or was it silently doing the job of a parser? This should be explicitly stress-tested against sentences with fronted adjuncts, passive voice, or subordinate clauses before being trusted.
- What is CLL's actual interface contract with L1/L6/L8/L9 — do those layers consume single resolved structures, or do they need to consume ambiguity sets (multiple candidate frames with confidence) from ELE? The latter is architecturally implied but never implemented or tested here.
- How does the system decide, at correction time, which of two contradictory ledger entries is "current truth" — this was explicitly flagged as an unbuilt gap (row 5, §2).

---

**End of specification.**
