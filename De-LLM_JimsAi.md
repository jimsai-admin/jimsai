# De-LLM JimsAI — How It Works, Start to Finish

**A memory-centric neuro-symbolic AI that understands, reasons, plans, and generates language, code, and structured output — with no LLM in the answer path.**

Author: JIMS-AI Research (Ajibewa Johnson Irekanmi) · Living document, last updated 2026-07-07

This document is the single place to understand what JimsAI is and how it works end to end. It is written so a reader new to the project can follow a request from the moment it arrives to the moment a response is delivered, understand every organ it passes through, and see exactly which parts are **measured and working today** versus **principled but not yet built**.

Every claim is tagged:

- **[BUILT]** — implemented and passing its test, with the measurement cited.
- **[PRODUCTION]** — deployed in the v11 runtime.
- **[ROADMAP]** — designed, judge defined, not yet built. Never presented as working.

Companion documents: `docs/jimsai_llm_free_architecture.md` (the architecture rationale), `docs/ele_cll_grounding_review.md` (the measured milestone ledger), `The_Prediction_Trap_Paper.md` (the paradigm), `docs/concept_language_layer.md` (the concept layer), `experiments/ele/` (the reproducible mechanism proofs).

---

## Part 1 — The idea in one page

### 1.1 The problem JimsAI exists to solve

A modern LLM is **one** neural network asked to be **five** things at once: a language parser, a knowledge store, a reasoner, a planner, and a text generator. The Prediction Trap paper's argument is that this *fusion* is the root defect, not the Transformer itself. When one weight matrix does memory, verification, planning, execution, and generation through next-token prediction, **none of the five can be independently audited, corrected, or improved**, and the system will sound correct while having no durable or verifiable reasoning substrate. Scale makes it more fluent, not more reliable.

### 1.2 The bet

Separate the five faculties into specialized, auditable, CPU-cheap organs. Borrow from the transformer *what it does* — distributional learning, composition, content-addressable retrieval, cheap proposal generation — but never *how it does it* (one opaque blob). The deepest borrow, stated as a single sentence:

> **An LLM is a magnificent proposal distribution. The Prediction Trap is letting proposals become answers.**

So JimsAI keeps a cheap statistical **proposal** path everywhere (concept index, embeddings, count ledgers, tiny classifiers) and a **verification** path everywhere (typed graph, symbolic solvers, provenance, sandbox execution) — and **only verified content ever reaches the user unflagged**.

### 1.3 The unit of intelligence: the Verified Cognitive Object (VCO)

The atom of the system is not a sentence — it is a **VCO**: a structured record produced per request containing the semantic intent, a reasoning chain (each claim with confidence, source, and provenance class), constraint checks, simulation results, an explicit list of knowledge gaps, the capability plan, and the activation record of every stage. A VCO satisfies four properties: **Groundedness** (every claim is sourced or marked a gap), **Auditability** (full provenance reconstructable), **Scoped confidence** (a deterministic function of measured outputs, not a self-reported number), and **Durability** (persists, improves future answers). The user-facing response is just *one derived rendering* of the VCO.

### 1.4 Two governing rules

1. **The Independence Policy** — no external LLM anywhere in the answer path, even on hard cases. Outside coverage the system **CLARIFIES** (asks one bounded question), **REFUSES** (names the gap), or **GROWS** (logs the gap for the learning loop). It never guesses. External models survive only as *frozen measurement baselines* in the test harness.
2. **The Anti-Hardcoding Protocol** — the repository contains *build scripts and mechanisms, never enumerated answer data*. Every behavior is a general function of provenance-stamped data (lexicon entries, discovered constructions, graph edges), tests sample their inputs from the data source at runtime with fresh seeds, and out-of-coverage inputs fail loudly. A developer hand-adding a case to pass a test has no legal path.

---

## Part 2 — The five faculties

```
                    ┌─ FACULTY 1: LANGUAGE UNDERSTANDING ─┐
 input text ──► LangID ──► ELE constructions ──► CLL concepts/frames
                          (ambiguity sets with confidence — never one guess)
                                     │
                    ┌─ FACULTY 4: PLANNING ─┐
                    T1-mini intent (µs) ► capability plan ► sparse activation
                                     │
       ┌─ FACULTY 2: KNOWLEDGE ──────┴────── FACULTY 3: REASONING ─┐
       concept postings · typed graph · semantic ledger      bounded traversal
       incremental projection views (µs, unbounded)          symbolic solvers
       embeddings as FALLBACK index only                     code sandbox
                                     │
                             VCO assembly
              (claims + provenance + gaps + deterministic confidence)
                                     │
                    ┌─ FACULTY 5: GENERATION ─┐
       coverage? ──yes──► typed emitters + template/constrained realizer
                └──no───► CLARIFY / REFUSE (§ Independence Policy)
                                     │
                     response (streamable) + EVENTS ──► learning loop
```

### Faculty 1 — Language understanding (ELE + CLL)

**Job:** turn surface text, in any language, into concept IDs, literals, and typed frames. **No world knowledge here** — ambiguity that needs world knowledge is *exposed as candidates*, never resolved.

- **CLL (Concept Language Layer)** maps `(language, surface) → concept ID`. "dog" (en), "ajá" (yo), "chien" (fr), "狗" (zh) all resolve to one canonical concept, so a fact taught in one language is retrievable in any covered language by exact index lookup — no translation pairs, no multilingual fine-tuning. **[BUILT]** from-source lexicon (Wikidata QRank + labels/aliases), **39,104 surface keys** across en/fr/zh/sw/yo, every entry provenance-stamped; experiments E1–E12 passing; `prototype/jimsai/cll_shadow.py` live in the retrieval path.
- **ELE (Expert Language Engine)** discovers grammatical constructions from raw text with no parser (n-gram frames promoted by frequency + filler diversity), stored in append-only evidence ledgers. **[BUILT]** `experiments/ele/` reproduces this across seeds: 14/14 construction recovery on generated corpora.
- **Chaotic input is absorbed here.** Misspelled words recover via O(1) hashed lookups — a *skeleton* key (first char, last char, sorted interior letters: "proejct" → "project") and an *anagram* key — against the growing lexicon, unique-candidate-only. **[BUILT]** `cll_shadow._typo_repair`; contributes to P3 robustness **100%**.
- **The parser question, honestly.** Parser-free construction *discovery* works on real text; but assigning argument structure (which token is the predicate, which the argument) needs more than surface position — on real prose those signals must come from L1 structured extraction or a bounded parser interface. **[BUILT — finding recorded]** (M3, `experiments/ele/m3_real_text.py`). The architectural claim that survives is **"no knowledge in weights,"** not "no weights anywhere": a parser, like a vision encoder, is a replaceable *perception* component; what the system *knows* never lives in it.

### Faculty 2 — Knowledge (the parameters replacement)

**Job:** be everything the system knows, as **data with provenance** — never as opaque weights.

- **Append-only semantic ledger** — assertions, retractions, and quotations are *events*; nothing is ever mutated or deleted.
- **Typed concept graph** — edges carry source + confidence; multi-hop composition rules are per-predicate *data* from ontology metadata.
- **Concept posting-list index** — exact cross-lingual retrieval by concept/literal intersection.
- **Incremental materialized projection views** — the current state (meaning, trust, time, domain) is a *view* computed from the ledger. **[BUILT]** the M0b benchmark settled the design: full recomputation is linear (~236 ms at 100k events, unusable per query), but the incremental view is **O(1) per event and per query (µs, flat across 100 → 100,000 events)**. Production uses the incremental view; full recompute is for rebuild/audit only.
- **No context window, by construction.** "Context" is not a token buffer — it is a query-scoped subgraph assembled at answer time from unbounded, indexed memory. Long documents become graph substance, not prompt stuffing; conversation threads are event streams. Capacity grows with storage; per-query cost stays flat (measured, M0b).
- **Embeddings** remain only a *fallback similarity index* for what the lexicon does not cover — a bounded, swappable interface, never the store. Runs on CPU (multilingual-e5-small). **[BUILT]** local embedding service, no cloud dependency.

### Faculty 3 — Reasoning (search + verification, never generation)

**Job:** derive what is not directly stored, and refuse when it cannot.

- **Bounded multi-hop graph traversal** — confidence compounds *down* (uncertainty never inflates), every hop keeps provenance, and non-composable predicates **refuse to chain** — exactly where an LLM produces a fluent guess. **[BUILT]** E10 / bridge tests: reversed-edge honesty 200/200.
- **Symbolic solvers** — arithmetic, algebra, equations via SymPy; the answer is an expression tree that was *executed*. **[PRODUCTION]**
- **Sandbox execution + constraint validation** for code and verifiable claims. **[PRODUCTION]**
- **[ROADMAP] Auditable generalization** (the genuinely novel research): co-occurrence statistics over the graph promote *candidate rules* with support counts, quarantined until reviewed — the LLM's distributional advantage distilled into rules you can read, cite, and delete.

### Faculty 4 — Planning

**Job:** typed intent → capability plan → *sparse activation* (only the faculties a query needs actually run — the energy win).

- **Capability router** combines structural signals (code fences, math syntax), semantic-prototype embedding similarity, and **workspace-literal evidence**: a query naming an entity the workspace memory already knows is a memory question, whatever its wording resembles. **[BUILT]** this eliminated the identifier-prompt misroutes; feeds P1/P4/P8.
- **T1-mini** — intent classification over concept sequences (naive Bayes over concept IDs, ~11 µs, trainable from feedback in minutes on CPU). **[BUILT in miniature]** (E8: English-trained → 12/12 cross-lingual); **[ROADMAP]** production benchmark vs a frozen baseline (M2).
- **[ROADMAP] Multi-attention-span** — a multi-intent prompt decomposes into concurrent typed sub-queries (numbers for a math span, names for a recall span), each with its own focus and plan, composed into one VCO. The ambiguity-set contract already carries multiple candidate frames; this extends it from *alternative* readings to *conjunctive* intents.
- **[ROADMAP] Response planning** (§2.9 of the architecture doc): response shape, length, and strict user format are a *projection of the VCO* — one claim → one sentence; many claims → a list or table; a format constraint ("as JSON", "in three bullets", "in French") is applied deterministically to the same verified content; length is earned by verified material, never padded.

### Faculty 5 — Generation (the part everyone assumes needs an LLM)

The instinct that generation needs an LLM is backwards: **formal outputs have grammars and checkers, so they can be produced by construction and accepted by verification** — which, inside coverage, beats generation-by-prediction. Two tiers, and **no LLM tier at all**:

1. **Template realization (CSSE/ELE)** — learned shape templates + adjunct composition; can only voice content present in the VCO. Hallucination prevention by *capacity starvation*, not instruction. **[BUILT]** R6: 30/30 held-out compositional renders exact, **0 hallucinations**, versus an equal-scale neural renderer that hallucinated on 20–25/30 of the same inputs (R7).
2. **Constrained-decode realizer** — for fluency beyond templates (morphology, agreement, word order), a small in-house model decodes over a **content-licensed lattice**: the only tokens legal at each step are function words plus the VCO's own content values and their mined morphological variants. The model chooses inflection and order; it **cannot** introduce an entity, number, or claim. **[BUILT — mechanism proven]** M4b (`experiments/ele/realizer.py`): the *same undertrained weights* hallucinate on 18–23/24 held-out frames when decoded freely and on **0/24** when constrained; 100% held-out agreement and exact match across two synthetic languages and four seeds; a second grammar with new function words and different word order passes identically ("new language = data only"). **[ROADMAP]** production scale on real SPPE pairs.

**By response type** (the full generation vision):

| Output | How it is produced (no LLM) | Status |
|---|---|---|
| Verified facts | claim from the reasoning chain, realized by template/constrained realizer | **[BUILT]** P1/P4/P8 |
| Math / formulas | expression extracted by **grammar** (formal language, not model), solved by SymPy, rendered from the executed tree | **[BUILT]** P6 100%, `math_extract.py` |
| Physics / chemistry / engineering | same grammar, admitting symbols by lookup against the solver's constant + element namespaces (data tables, no per-domain code) | **[BUILT]** namespace extension |
| Tables / JSON / YAML / CSV | deterministic serialization of VCO content, one emitter per format | **[ROADMAP]** M7 |
| Diagrams / charts | projection of an actual subgraph → Mermaid/graphviz/chart spec (the diagram an LLM fakes from prose, emitted from the real graph) | **[ROADMAP]** M7 |
| Code + comments | scaffolding from schema templates; retrieval of *verified* (sandbox-passed) patterns; small-function synthesis by bounded search verified in the sandbox (CEGIS-shape) | **[ROADMAP]** M8; sandbox+graph **[PRODUCTION]** |
| Mixed responses (prose+code+table+math) | a **document plan** — an ordered list of typed blocks, each routed to its emitter, assembled as Markdown; discourse templates discovered by the same construction machinery at document scale | **[ROADMAP]** M7 |
| Dialogue / follow-ups | discourse focus resolves "it"/"she" against the conversation; underspecified follow-ups inherit the focus entity | **[BUILT]** P8 100% incl. cold-thread honesty control |
| Creative / open-ended prose | out of scope by policy until the constrained realizer composes it from licensed content; never delegated to an external model | **[ROADMAP]** |
| Media generation (image/audio/video) | the one honest carve-out: generative by nature — either an *effector* invoked on explicit request and marked generated-not-factual, or refused. The truth path is never delegated | decision pending |

---

## Part 3 — A request from start to finish

Here is one query's full journey through the deployed pipeline (`prototype/jimsai/pipeline.py`), fully de-LLM. Follow "*And what database does it use?*" arriving as the second turn of a conversation.

1. **Ingress & session.** The request (`user_id`, `query`, `workspace_id`, `thread_id`) is accepted. The **dialogue session** for this thread is loaded. Dialogue state is core memory: it lives in an always-available in-process tier plus best-effort durable storage, so the conversation's focus can never silently evaporate when an external cache is down. **[BUILT]** (this was a real defect, now fixed). A 15-minute inactivity check clears stale focus (topic decay).

2. **Faculty 1 — understanding (T1 / semantic compiler).** The query is compiled into a `SemanticIR`. Entities are extracted by the **CLL name-evidence mechanism** — mid-sentence capitalization / digits, any language — *not* a hardcoded identifier pattern. "it" carries no entity, so the IR inherits the conversation's **discourse focus** (`ACTIVE_OBJECT`) as a candidate. **[BUILT]** No external model is called; the deterministic compiler carries the flow (`JIMS_T1_SKIP_CONFIDENCE=0` skips the Qwen T1 entirely).

3. **Faculty 4 — planning (capability router + sparse activation).** The router scores capabilities from structural, semantic, and **workspace-literal** evidence — the inherited focus entity is checked directly against the concept-index postings, so a dialogue follow-up about a known workspace entity routes to memory, not to a misread capability. Sparse activation selects the bounded route; only needed faculties run.

4. **Faculty 2 — retrieval.** The `MultiIndexRetrievalEngine` runs. With `JIMS_CONCEPT_INDEX=on`, the **concept posting-list index** injects cross-lingual concept/literal matches as ranked candidates *before* scoring, so production evidence (relations, trust, prompt-excerpt hazards) still orders them. Assertive (declarative) occurrences outweigh interrogative mentions 2× — records that *state* things about the entity outrank records that *ask* about it. Ghost entities (unknown literals) make the index **abstain**, so gap honesty is an index property. **[BUILT]** P2 100%, P4 78%.

5. **Faculty 3 — reasoning (L9 bridge).** The reasoning chain is assembled from retrieved verified signatures. Two honesty rules gate every claim, driven by one principle — **"questions don't assert"**: an interrogative sentence is never voiced as a claim, and a claim must share a query entity (else it is filtered). Relevance is scored at the **concept level**, so a cross-lingual claim proves relevance by meaning when surface terms cannot overlap. If nothing assertive matches, the chain is a *named gap*, never a "supports intent" filler. **[BUILT]** eliminated answer-echoes and ghost leaks.

6. **VCO assembly.** Claims, constraint checks, simulation results, knowledge gaps, capability plan, and per-stage activation record are packed into the Verified Cognitive Object, with a deterministic aggregate confidence.

7. **Faculty 5 — rendering (CSSE).** The VCO is rendered into natural language. Certainty is conveyed by *answering plainly* — no stock "I believe this is right" footer; only genuine uncertainty adds a brief woven note. Internal diagnostics ("no assertive claim matched…", provider-status strings) are typed `[internal]` at their source and stripped structurally, so the user sees a natural gap ("Share a file or describe what you're building…"), never raw internals. **[BUILT]**

8. **Delivery.** The response returns whole, or **streams**: `/v1/query/stream` emits the deterministic render in natural word-chunks for progressive display — genuine token-by-token delivery with **zero model**, exact text reconstruction. **[BUILT]** verified 9 chunks reconstruct the exact answer.

9. **Learning.** The resolved exchange emits events: the answered entity updates the discourse focus; new surface forms become lexicon review candidates; recurring constructions accumulate in evidence ledgers; corrections are graph edits (visible in the next query, ~0.02 ms to take effect); resolved intents become SPPE training pairs; render gaps enter the coverage backlog. **Learning is data admission, not gradient descent** — which is why it is real-time and auditable.

---

## Part 4 — The learning loop (real-time, no training runs)

Every resolved interaction emits events; each lands in the organ that owns it. The only components ever "trained" are tiny, commodity, replaceable interfaces (embedder, optional parser, T1-mini, the realizer) — **knowledge never enters their weights**, which is the architectural line that makes real-time improvement possible at all.

| Signal | Destination | Latency to effect |
|---|---|---|
| unknown surface form | lexicon review queue | next query after approval |
| recurring construction | evidence ledger (pure function of contents) | immediate |
| user correction | graph edit with audit trail | **~0.02 ms** [BUILT] |
| resolved intent | SPPE pair → tiny-classifier retrain | minutes, CPU |
| repeated pattern | candidate rule + support count, quarantined | human gate [ROADMAP] |
| render / format gap | coverage backlog, frequency-prioritized | drives growth |

---

## Part 5 — How each requirement is met

- **CPU-bound:** posting lists, tries, count ledgers, graph traversal, incremental views — µs–ms measured. Heaviest permanent parts are a small embedder and tiny classifiers. GPU appears only in optional media effectors and offline artifact builds.
- **No context-window limit:** memory is content-addressable storage assembled per query; M0b shows flat query cost as the ledger grows 1000×.
- **Less hallucination — structurally zero in the answer path:** measured 0/30 vs 20–25/30 inside coverage (R6/R7); provenance on every claim; refusal where composition is not licensed; outside coverage → clarify or refuse with the gap named, never a guess.
- **Less energy:** sparse activation + rising deterministic share. A concept-index hit costs microseconds of CPU; the same query through a 4B-param model costs seconds. Energy *falls* as coverage grows — the inverse of the LLM cost curve.
- **Real-time learning:** correction-to-effect in milliseconds vs a fine-tune cycle.
- **Quality, honestly accounted:** inside the served distribution, quality = coverage × verification, scored by the generative harness against a *frozen* LLM baseline on identical generated inputs. Immediate wins on provenance, correction durability, multilingual recall; open-domain creativity and long-tail instruction gymnastics surface as *named refusals and clarifying questions* (never delegated). "As good as a frontier model" is claimable **per-distribution and measured**, never in the abstract.

---

## Part 6 — How it is proven (the anti-hardcoding discipline)

JimsAI is judged by **`benchmarks/genuine_eval.py`** — a property-based, generative harness. Each run generates *nonce* facts (guaranteed absent from any corpus), teaches them, and asserts properties with fresh seeds. No answer can be hardcoded because no answer exists until runtime. Properties:

- **P1 learning** — teach → recall.
- **P2 gap honesty** — an untaught entity must produce a gap, not a fabrication.
- **P3 robustness** — typo/casing/chat-noise perturbations must still recall.
- **P4 multilingual** — a fact taught in English recalled in fr/yo/zh.
- **P5 multi-intent** — math + recall in one prompt.
- **P6 math** — generated problems vs local ground truth.
- **P7 scoping** — workspace A facts must not leak into workspace B.
- **P8 dialogue** — an underspecified follow-up resolves via discourse focus; a cold thread honestly fails to resolve it.

The mechanism-level proofs live in `experiments/ele/run_all.py` (ELE + Projection, 60 pass / 12 report / 0 fail across 4 seeds) and `experiments/ele/realizer.py` (the constrained realizer). Reports (rows are REPORT, not PASS, for equal-budget neural comparisons) are recorded honestly — a neural win is never hidden.

### Current measured board (fully de-LLM / local, fresh seed 724613, 2026-07-07)

| Property | Result |
|---|---|
| P1 learning | **100%** |
| P2 gap honesty | **100%** |
| P3 robustness | **100%** |
| P4 multilingual | 78% (2 Yoruba — lexicon data, not code) |
| P5 multi-intent | 50% |
| P6 math | **100%** |
| P7 scoping | **100%** |
| P8 dialogue | **100%** (incl. cold-thread honesty control) |

Six of eight properties at 100%, fully de-LLM, on fresh seeds. The two remaining gaps are a lexicon-data item (Yoruba coverage: 1.8k entries vs 17k for Chinese — closed by the same provenance-stamped enrichment script, no code) and one multi-intent recall case.

---

## Part 7 — Running it de-LLM

The deployment configuration that removes every external model from the answer path (persistence services from `.env` — Supabase/Vectorize/Neo4j/Redis — are databases, not models, and stay):

```bash
# 1. Local CPU embedding service (bounded interface, not the store)
cd services/embedding-service
JIMS_RENDER_AGENT_TOKEN=$JIMS_MODAL_API_KEY \
  python -m uvicorn app.main:app --port 8090

# 2. Backend, de-LLM: local embeddings, concept index ON, T1 always skipped,
#    LLM/classifier endpoints black-holed so any residual call fails fast and
#    the deterministic path carries the flow.
JIMS_EMBEDDING_SERVICE_URL=http://127.0.0.1:8090/v1 \
JIMS_INTENT_SERVICE_URL=http://127.0.0.1:9 \
JIMS_RENDERER_SERVICE_URL=http://127.0.0.1:9 \
JIMS_REASONING_SERVICE_URL=http://127.0.0.1:9 \
JIMS_CLASSIFICATION_SERVICE_URL=http://127.0.0.1:9 \
JIMS_T1_SKIP_CONFIDENCE=0 \
JIMS_CONCEPT_INDEX=on \
  python -m uvicorn prototype.app:app --port 8000

# 3. Judge it
JIMS_EVAL_PASSWORD=... python benchmarks/genuine_eval.py --facts 3 --languages fr,yo,zh
```

`JIMS_CONCEPT_INDEX=on` merges the concept index into retrieval; `JIMS_T1_SKIP_CONFIDENCE=0` skips the Qwen T1 entirely; the black-holed URLs guarantee no external generative model is ever in the answer path.

---

## Part 8 — Roadmap (what is principled but not yet built)

Ordered so the biggest untested assumptions die first; every milestone has an explicit kill criterion in `docs/ele_cll_grounding_review.md`.

- **M2 — T1-mini v2** on live feedback data, benchmarked against a frozen baseline; low-confidence routes CLARIFY, never guess.
- **M4b-production — constrained realizer** on real SPPE pairs at VCO scale; content-fidelity property tests + fluency vs approved human-rated responses.
- **M5 — knowledge ingestion at scale** (Wikidata/ConceptNet slices) with answerable-fraction and refusal-calibration curves.
- **M7 — typed emitters + document composer**: math/LaTeX, table, diagram, code-scaffold emitters over VCO content; discourse and document-plan templates discovered by the sentence-level construction machinery. Response planning (length/format/structure as a projection).
- **M8 — verification-first code synthesis**: verified-pattern library from sandbox passes + enumerative small-function synthesis; metric = verified-solve rate per request class.
- **M6 — de-LLM the loop permanently**: remove the Qwen services from the deployed answer path, gated on dashboards (deterministic share, clarify/refuse trend, task success). External models survive only as frozen measurement baselines.
- **Continuous:** equal-budget baselines, frozen-baseline win-rate, weekly coverage dashboards, kill criteria enforced in writing.

---

## Part 9 — Summary judgment

The transformer taught us that distributional learning, composition, content-addressable retrieval, and cheap proposal generation are the ingredients of linguistic intelligence — then fused them into an unauditable blob. Everything measured here says the ingredients survive separation: grammar lives in ledgers, knowledge in graphs, retrieval in indexes, reasoning in bounded search, fluency in a capacity-starved realizer — each inspectable, correctable in milliseconds, and CPU-cheap. Six of eight generative-harness properties are at 100% fully de-LLM; a system holds a real multilingual conversation, does verified math, recalls across languages, and refuses honestly — with no model in the answer path. The unbuilt parts (rich code/diagram/document generation, production-scale fluency) are named, judged, and pre-scoped so failure re-routes rather than refutes. That is the difference between building a genuine alternative to the LLM and telling a story about one.
