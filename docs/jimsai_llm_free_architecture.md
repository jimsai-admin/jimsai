# JimsAI Without the LLM: A Grounded Architecture

Date: 2026-07-07
Basis: measured results in `experiments/ele/` (M0: 60/12/0 across 4 seeds; M0b: `results/projection_bench.json`), `experiments/concept_model/` (E1–E12, v1.1 shadow mode), the production v11 stack, and the VCO paradigm (`The_Prediction_Trap_Paper.md`).
Discipline: every design point below is tagged **[MEASURED]** (we have numbers, cited), **[PRODUCTION]** (already deployed in v11), or **[BET]** (a hypothesis with its falsifying test named). Nothing is asserted from elegance.

---

## 1. The design thesis

A transformer LLM is five machines fused into one set of weights: a language parser, a knowledge store, a reasoner, a planner, and a text generator. The Prediction Trap paper's argument is that the fusion is the problem. Our measurements now show the *decomposition is buildable*: each faculty has a specialized, CPU-bound, auditable implementation whose core mechanism we have run.

**What we borrow from the transformer is its functions, not its form:**

| What the LLM does | How it does it | The specialized organ in JimsAI | Evidence |
|---|---|---|---|
| Learns grammar from raw text | gradient descent on next-token loss | construction discovery over evidence ledgers (frequency + filler diversity) | **[MEASURED]** R1: 14/14 recovery; R13b: self-corrects with evidence, no code change |
| Learns word categories | embedding geometry | distributional clustering, held-out purity checks | **[MEASURED]** R2: 0.87 purity, leakage reported |
| Generalizes compositionally | attention over learned features | factorized rendering: core shapes × adjuncts × lexical fillers as frame DATA | **[MEASURED]** R8 (unseen verb renders), R10 (unseen 5-role combo renders) |
| Retrieves relevant context | attention = soft key-value lookup, O(n²), window-bounded | concept posting lists + typed graph + incremental projection views: content-addressable, unbounded | **[MEASURED]** M0b: 3–7µs cell queries FLAT from 100 → 100k events; E1: 9/9 cross-lingual exact retrieval |
| Knows facts | weights (uneditable, unauditable) | append-only semantic ledger + concept graph with per-edge provenance | **[MEASURED]** R5: correction visible in 0.02ms, both truths retained; E7: correction = graph edit |
| "Reasons" | chain-of-thought sampling | bounded multi-hop traversal: confidence compounds DOWN, non-composable relations REFUSE | **[MEASURED]** E10/BRG: 3-hop inference with per-hop provenance; refusal exactly where an LLM guesses |
| Follows instructions | instruction tuning | capability router + symbolic planner over a typed operation vocabulary | **[PRODUCTION]** v11 router (9 capabilities); **[BET]** long-tail decomposition — test: fallback-rate trend on live traffic |
| Generates fluent text | autoregressive sampling over full vocabulary | template realization (zero-invention) + constrained-decode polisher (§4.5) | **[MEASURED]** R6: 0/30 hallucinations vs neural 20–25/30 on identical inputs |
| Proposes the plausible | the whole model IS a proposal distribution | statistical priors (n-gram/construction ledgers, embeddings) RANK candidates; only verification ACCEPTS | **[MEASURED]** R3 regime note: count ledgers tie on regular text, lose on natural text — so prediction proposes, never decides |
| Improves from feedback | RLHF (offline, expensive, opaque) | SPPE pairs, review queues, promotion gates; tiny models retrained in minutes on CPU | **[PRODUCTION]** feedback loop; **[MEASURED]** R4: ledger ingest ms vs retrain seconds |

The last two rows are the deepest borrow: **an LLM is a magnificent proposal distribution. The Prediction Trap is letting proposals become answers.** The architecture keeps a proposal path everywhere (cheap, statistical, fallible) and an acceptance path everywhere (graph, solvers, provenance, execution) — and only acceptance ever reaches the user unflagged.

---

## 2. The five faculties

```
                       ┌─ FACULTY 1: LANGUAGE UNDERSTANDING ─┐
 text ──► LangID ──►  ELE constructions ──► CLL concepts/frames
                       (ambiguity sets w/ confidence — never one guess)
                                    │
                       ┌─ FACULTY 4: PLANNING ─┐
                       T1-mini intent (µs) ► capability plan ► sparse activation
                                    │
        ┌─ FACULTY 2: KNOWLEDGE ────┴────── FACULTY 3: REASONING ─┐
        concept postings ─ typed graph ─ semantic ledger    bounded traversal
        incremental projection views (µs, unbounded)        symbolic solvers
        embeddings as FALLBACK index only                    code sandbox
                                    │
                            VCO assembly
              (claims + provenance + gaps + deterministic confidence)
                                    │
                       ┌─ FACULTY 5: GENERATION ─┐
        coverage? ──yes──► ELE/CSSE template render (zero-invention)
                 └──no───► constrained-decode realizer / CLARIFY / REFUSE (§2.6)
                                    │
                     response + EVENTS ──► learning loop
        (lexicon candidates, construction ledgers, graph edits, SPPE pairs)
```

### 2.1 Faculty 1 — Language Understanding (ELE-parse + CLL-encode)

**Job:** surface text → constructions → concept IDs + literals + typed frames. **No world knowledge** — ambiguity that needs world knowledge is *exposed* (ambiguity sets), never resolved here. [MEASURED] BRG: the contract works against the real ConceptGraph; CLL v1: ambiguous surfaces emit top-3 candidates, retrieval intersection resolves.

- Lexicon: from-source (Wikidata/OMW/PanLex), 39k surface keys today, provenance-stamped. [MEASURED] E11: cross-lingual at scale; Rule 3: new language = data only, zero code.
- **Chaotic-input robustness without an LLM** [MEASURED 2026-07-07, `cll_shadow._typo_repair`]: misspelled content words recover via O(1) hashed lookups against the growing lexicon — a *skeleton* key (first char, last char, sorted interior letters: the psycholinguistic anchor effect — "proejct" → "project") and an *anagram* key for boundary transpositions. Fires only on a unique candidate; unknown-but-correct words stay soft literals rather than being guessed. Robustness grows with the lexicon, costs a dict lookup, and contains zero language data.
- **"Questions don't assert"** — one linguistic principle enforced at three layers [MEASURED 2026-07-07]: interrogative sentences are never voiced as claims (reasoning bridge), never count as assertive evidence (concept index weights declarative occurrences 2×), and never grant name evidence to their clause-initial capitals (colon = clause introducer). This single principle eliminated answer-echoes, ghost-entity leaks, and chat-noise flooding — three test failures, one mechanism, no per-case patches.
- Constructions: evidence-ledger discovery, order-independent (P0), conservative on sparse evidence (R13b).
- **The parse question, honestly [BET]:** parser-free discovery on real syntax (passives, fronting, subordination) is unproven — M3. The architecture does NOT depend on the bet: parsing is *perception*, and perception is allowed to be a commodity trained component (CLL hard truth 12 — same status as the vision encoder). If M3 fails, a small dependency parser becomes a bounded interface emitting candidate frames with confidence; knowledge never lives in it; it is replaceable without touching what the system knows. The claim we keep either way: **no knowledge in weights** — not "no weights anywhere."

### 2.2 Faculty 2 — Knowledge (the parameters replacement)

**Job:** everything the system knows, as data with provenance: append-only semantic ledger (events), typed concept graph (edges with source + confidence), concept posting-list index, and **incremental materialized projection views** — the M0b verdict made this binding: full recomputation is linear (~236ms @ 100k events, unusable per-query); the incremental view is O(1) per event and per query (µs, flat). Full recompute exists only for rebuild/audit.

- **No context window, by construction:** "context" is not a token buffer — it is a query-scoped subgraph assembled at answer time from indexed, unbounded memory. Conversation threads are event streams; long documents are ingested as graph substance, not stuffed into a prompt. Capacity grows with storage, cost stays flat [MEASURED M0b].
- Growth path (Gap 1): bulk-ingest Wikidata/ConceptNet slices — the world's knowledge already exists concept-shaped, licensed, with provenance. [BET] answerable-fraction grows monotonically per million edges — test: masked-edge property tests, generated questions, never enumerated (M5).
- Embeddings remain a *fallback similarity index* for what the lexicon doesn't cover (dual representation, already the spec's demand) — a bounded interface, swappable, never the store.

### 2.3 Faculty 3 — Reasoning (search + verification, never generation)

**Job:** derive what is not directly stored: bounded multi-hop traversal (confidence compounds down, per-hop provenance, refusal on non-composable predicates — composition rules are per-predicate DATA from ontology metadata), symbolic solvers (SymPy path [PRODUCTION]), sandbox execution for code, constraint validation. An LLM's chain-of-thought is replaced by an explicit path that can be audited hop by hop — and that says "no path" instead of confabulating one [MEASURED E10: reversed-edge honesty 200/200; BRG].

- [BET] Gap 3 — auditable generalization: co-occurrence statistics over the graph promote *candidate rules* with support counts, quarantined until reviewed (the world-model promotion engine generalized). This distills the LLM's distributional advantage into rules you can read, cite, and delete. Test: teach N generated instances of a pattern, assert a candidate rule appears with correct support and stays quarantined until accepted. This is the genuinely novel research in the whole program.

### 2.4 Faculty 4 — Planning

**Job:** typed intent → capability plan → sparse activation (only the needed faculties run — the energy win). T1-mini (concept-sequence classifier, ~11µs [MEASURED E8], trained from SPPE pairs in minutes on CPU) proposes intent; the deterministic compiler already skips T1 at high confidence [PRODUCTION]. Arbitrary instruction composition ("summarize as a haiku") decomposes into concept-level operations where the vocabulary covers it; where it doesn't, the Independence Policy applies (§2.6): clarify or refuse with the missing operation named, log the gap, grow the vocabulary. [BET] the clarify/refuse rate falls over time — test: M2 dashboard on live routed traffic against a frozen Qwen3-1.7B *baseline comparison* (measurement only — never in the answer path), including the v11 chaos list.

**Multi-attention-span [BET — design direction]:** a transformer attends to many places in a prompt simultaneously; the symbolic equivalent is *multiple parallel query foci* — the planner decomposes a multi-intent prompt (P5: "compute X, and also what does Y use?") into concurrent typed sub-queries, each with its own concept/literal focus, retrieval scope, and capability plan, whose results compose in one VCO. The ambiguity-set contract (§2.1) already carries multiple candidate frames; multi-span extends the same shape from *alternative* readings to *conjunctive* intents. Test: P5 multi-intent in the harness, then generated k-intent compositions (k sampled at runtime, never enumerated).

### 2.5 Faculty 5 — Generation (the part everyone assumes needs an LLM)

Two generation tiers — and **no LLM tier at all** (Independence Policy, §2.6):

1. **Template realization (ELE/CSSE):** learned shape templates + adjunct composition; can only voice content in the VCO — hallucination prevention by capacity starvation, not instruction. [MEASURED] R6: 30/30 exact, 0 unlicensed tokens; R7: an equal-scale neural renderer hallucinated on 20–25/30 of the same inputs. Coverage grows compositionally (R8/R10) and every template carries provenance (E-Rule 1).
2. **Constrained-decode realizer [BET — the T2 endgame]:** for fluency (morphology, agreement, ordering) beyond templates, a *small in-house* seq model (CPU-sized, trained on SPPE-approved pairs, our weights) decodes over a **content-licensed lattice**: the only open-class tokens legal at decode time are those licensed by the VCO; the model chooses function words, inflection, and order — it *cannot* introduce an entity, number, or claim. This is not an LLM fallback: it is a bounded fluency organ with zero-invention guaranteed *by construction of the decode space*. Test: content-fidelity (every content token traceable to a VCO claim — property-tested, generated inputs) + fluency judged against approved human-rated responses. This is M4b.

The scoreboard metric is **deterministic-share of live traffic** rising, with zero hallucinations inside it, and clarification/refusal rates (§2.6) falling as coverage grows.

### 2.6 The Independence Policy — no LLM fallback, even on hard cases

Directive (2026-07-07): the system must not fall back to Qwen or any external LLM. Outside coverage, a guess is never produced. The gap routes to exactly one of three honest behaviors:

1. **CLARIFY.** If the gap is an ambiguity (the ambiguity set holds multiple candidates above the evidence floor), ask the user one bounded question, *rendered deterministically from the candidates themselves* ("Did you mean X or Y?"). One round-trip converts a hard case into a covered case — and the answer is a labeled training signal (SPPE pair, lexicon candidate, or graph edit) for free. Hard cases are not a generation problem; they are a dialogue problem.
2. **REFUSE WITH THE GAP NAMED.** A typed `GapReport` rendered deterministically: what is missing (shape, concept, operation, knowledge edge), what evidence exists, and what would close it. This is R9's policy [MEASURED] generalized system-wide — the naive-fallback regression test is the permanent reminder of what silent guessing costs.
3. **GROW.** Every gap event lands in the coverage backlog (lexicon candidates, construction ledgers, template gaps, operation vocabulary, ingestion targets), prioritized by observed frequency; the autonomous training loop consumes it. The same request next week may be covered — and the dashboard proves it.

Consequences, stated plainly:
- The Qwen intent/render/reasoning services leave the loop entirely. The only trained components anywhere are bounded, in-house-replaceable interfaces (embedder, optional parser interface, T1-mini, the constrained realizer) — no knowledge in weights, no external generative model in the answer path.
- **The cost is visible honesty:** coverage gaps surface as questions and named refusals instead of fluent guesses. The quality bet is that a system which asks precise questions and refuses with reasons — while its deterministic share climbs weekly — earns more trust than one that always answers and sometimes lies. This is measurable: clarification rate and refusal rate must FALL over time on live traffic while task success rises; if they don't, the bet fails in public, on the dashboard.
- Creative writing / open-ended prose is **out of scope by policy** (refused with a named gap) until the constrained realizer can compose it from licensed content; it is never delegated to an external model.

### 2.7 Beyond prose — code, math, structured output, multimodal, and combos

The instinct that these need an LLM is backwards. An LLM produces code, formulas, and tables by *predicting characters* and hoping; a VCO system produces them by *serializing verified structure*. Formal outputs have grammars and checkers — they are the easy cases. Ranked from strongest to hardest:

**Mathematics and formulas — should beat frontier models outright.** The symbolic solver path [PRODUCTION] means an equation is an expression tree that was *executed*, and the rendered formula IS that tree (SymPy → LaTeX is a pure function). Sign errors and dropped terms — the classic LLM math failures — are structurally impossible: there is no generative step between verification and notation. Solution steps are solver traces rendered by templates. Planned adapters (units, calculus, statistics) extend coverage, not risk.

**Structured data — a freebie of being graph-native.** Tables, JSON, YAML, CSV are *serializations of VCO content* — deterministic emitters, one per format, zero invention possible. Diagrams are better still: the internal representation already IS nodes and edges, so a Mermaid/graphviz block is a *projection of a subgraph* — the architecture diagrams an LLM fakes from prose, this system emits from the actual graph. Charts follow the same path (data → declarative chart spec).

**Code — verification-first synthesis, honestly scoped.** Code is where the LLM's proposal power is most missed, so the decomposition matters:
- *Scaffolding and config* (project layout, CRUD, migrations, infra files): schema-driven templates — the majority of real requests by volume, fully deterministic.
- *Verified-pattern retrieval*: every sandbox-passed solution becomes a provenance-stamped, retrievable graph artifact [PRODUCTION sandbox + graph]. The library compounds — the system gets better at code by *shipping* code, not by retraining.
- *Small-function synthesis* [BET — M8]: enumerative/deductive search over a typed combinator vocabulary against input-output examples, verified in the sandbox (CEGIS-shape). Classic program synthesis, CPU-bound, honest metric: **verified-solve rate** per request class. Proposals are slower than an LLM's; every acceptance *ran*.
- *Novel large-scale synthesis*: outside coverage → CLARIFY (decompose with the user) or REFUSE with the gap named. No generated-but-unverified code is ever presented as an answer — which is precisely the LLM failure mode users pay for in debugging time.

**Multimodal input — already designed** (CLL §3b): perception models are bounded interfaces emitting (concept, confidence, region) — encoders, not generators; knowledge never in their weights; cross-modal retrieval and correction-as-graph-edit proved in miniature (E6/E7). Whisper transcribes locally.

**Multimodal output (image/audio/video generation) — the one honest carve-out.** Media synthesis is generative by nature. Two policy-consistent options, to be decided explicitly: (a) treat generative media models as **effectors, not cognition** — artifact factories invoked by the planner on explicit user request, whose outputs are marked generated-not-factual and never assert claims (the independence directive protects the *truth path*: understanding, knowledge, reasoning, claim rendering); or (b) refuse media generation entirely. Deterministic alternatives already cover the factual slice: charts, diagrams, and SVG compositions from data need no diffusion model.

**Combos — the document composer.** How one response mixes prose + code + table + math the way a frontier assistant does: the VCO already holds *typed* content (claims, expressions, code artifacts, table data, subgraphs). A response is a **document plan** — an ordered list of typed blocks — where each block routes to its specialized emitter (prose realizer §2.5, LaTeX, code serializer, table/Mermaid emitters) and the assembled output is Markdown, itself a formal language. Document plans are *discourse templates* learned from approved responses — the same construction-discovery machinery (ledger, frequency + diversity, provenance) applied at document scale instead of sentence scale [BET — M7]. One mechanism, two zoom levels. Property test: every block traceable to VCO content; no block type invented; unknown discourse need → CLARIFY/REFUSE per §2.6.

### 2.8 Dialogue management — the second brain in the conversation [BET — next faculty]

Directive (2026-07-07): JimsAI must hold natural multi-turn dialogue — language, code, any response type — as a *second brain in the conversation*, still with no LLM and no hardcoding. Decomposed into mechanisms, each with its judge:

- **Discourse focus as a projection.** A conversation thread is already an event stream (§2.2); the dialogue state is a *materialized view over it*: the stack of recently-discussed entities and concepts (from each turn's CLL encoding), decayed by recency. Underspecified follow-ups ("and what city is *it* in?", "what about *its* database?") resolve against this focus stack the same way ambiguous surfaces resolve in CLL — candidates emitted, retrieval intersection decides. No pronoun tables, no English: pronouns are simply *low-content tokens whose referent must come from focus*, in any language. Judge: **P8 dialogue property** in the generative harness — teach a fact, ask about it, then follow up with a generated underspecified reference; recall must survive the turn boundary (seeded, cross-family, cross-language).
- **Conversational acts, not just answers.** The Independence Policy's CLARIFY behavior (§2.6) makes dialogue *structural*: asking a bounded question, receiving the answer, and folding it into the ambiguity set is a dialogue-management loop the architecture already owns. Acknowledgments, corrections ("no, I meant X" → graph edit + focus update), and topic shifts are all typed events over the same substrate.
- **Naturalness without invention.** The robotic "*I believe this is right*" render gives way to: discourse templates discovered from approved responses (M7 — the document composer's sentence-level siblings, same construction-discovery machinery), realized through the constrained-decode realizer (M4b) so tone and flow are learned while content stays capacity-starved. Confidence phrasing maps deterministically from the VCO's measured confidence and gaps — the system *sounds* certain exactly when it is.
- **Code and mixed responses in dialogue** ride §2.7's typed emitters — a follow-up "now show me that as a table" is a document-plan operation over the *same VCO*, not a regeneration.

Build order: P8 property first (the judge) — ✅ DONE (P8 4/4, cold-thread honesty control passing); focus stack lives in the compiler's ACTIVE_OBJECT + concept-index name evidence; next is discourse-template discovery from the approved-response corpus.

### 2.9 Response planning — length, format, and structure as a projection [BET — next]

A frontier assistant decides *how* to answer — short vs long, prose vs list vs table vs code block, terse vs thorough — implicitly in its weights. JimsAI must decide it *explicitly and principled*, from the VCO, without a hardcoded rule per case:

- **Response shape is a projection of the VCO.** Claim count, gap count, intent type, and the presence of typed content (expressions, code artifacts, table data, subgraphs) determine the document plan: one verified fact → one sentence; a causal chain → an ordered walk; several claims of the same relation → a list; tabular content → a table; a how-to intent with steps → a numbered procedure. The mapping is a function of measured VCO structure, not a keyword rule.
- **Length is earned by content, never padded.** Short when the VCO has one claim; long when it genuinely has many verified claims, sub-questions, or a multi-step plan. "Explain X in depth" raises the *retrieval breadth and reasoning depth* (more hops, more related concepts), and length follows from how much verified material that surfaces — the system is physically unable to pad with invented filler (capacity starvation). This inverts the LLM failure mode of fluent-but-empty length.
- **Strict user format is a constraint on the document plan, not a re-generation.** "Answer in JSON", "as a table", "in three bullet points", "in French" are parsed (by the concept layer / construction grammar) into constraints — output schema, block type, item count, target language — applied deterministically to the *same VCO content* by the typed emitters (§2.7) and the constrained realizer (§2.5). The content is fixed by verification; only its serialization bends to the user's format. A format the system cannot honor is a named gap or a clarify, never a silent approximation.
- **Grammar, tense, capitalization, agreement** come from the construction grammar (discovered, §2.1) plus the constrained-decode realizer (§2.5): morphology and agreement are *learned* and chosen at decode time, but only over a content-licensed lattice, so correctness is a property of the grammar/decode space, not of a hardcoded rule table. Any language the lexicon+grammar cover, realized fluently; any it does not, a named coverage gap that the loop fills.
- **Multi-intent, complex, multilingual, chaotic** inputs decompose (multi-attention-span, §2.4) into concurrent typed sub-queries; each resolves independently; the document composer (M7) interleaves their typed results into one coherent, format-obeying response. Chaotic surface (typos, code-switching, missing words) is absorbed upstream by the O(1) skeleton/anagram repair and concept-native encoding [MEASURED: P3 100%], so the planner sees clean structured intent regardless of surface noise.

Judge: response-plan property tests in the harness (given a VCO of known shape and a format constraint, the rendered response has the right structure, length band, and language, with every content token VCO-traceable) plus the frozen-baseline fluency comparison.

---

## 3. The learning loop (real-time, no training runs)

Every resolved interaction emits events; each lands in the organ that owns it:

| Signal | Destination | Latency to effect | Evidence |
|---|---|---|---|
| unknown surface form | lexicon candidate → review queue | next query after approval | CLL Rule 1 path |
| recurring construction | evidence ledger count/diversity | promotion is a pure function of ledger | R1/R13b/P0 |
| user correction | graph edit with audit trail | **0.02ms** [MEASURED R5]; E7 at concept level | |
| resolved intent | SPPE pair → T1-mini retrain | minutes, CPU, tiny | R4 shape: ms ingest vs s retrain |
| repeated pattern | candidate rule + support count, quarantined | human gate | Gap-3 bet |
| render gap | GapReport → coverage backlog | drives template/adjunct growth | R9 policy |

The only things ever "trained" are tiny, commodity, replaceable interfaces (T1-mini, the polisher, embedders). Knowledge — the thing users correct, audit, and own — never enters weights. That is the architectural line that makes real-time improvement possible at all: **learning is data admission, not gradient descent.**

---

## 4. Why each requirement holds (or what it costs)

- **CPU-bound:** posting lists, tries, count ledgers, graph traversal, incremental views — µs–ms measured. The heaviest permanent components are a small embedder and tiny classifiers. GPU appears only in optional fallback tiers and offline artifact building.
- **No context window limit:** §2.2 — memory is content-addressable storage, assembled per query; M0b shows flat query cost as the ledger grows 1000×.
- **Less hallucination — structurally zero in the answer path:** measured 0/30 vs 20–25/30 inside coverage (R6/R7); provenance on every claim; refusal where composition isn't licensed (E10); outside coverage → clarify or refuse with the gap named (§2.6), never a guess (R9: the naive fallback that silently dropped an argument is a permanent regression test of what we refuse to ship).
- **Less energy:** sparse activation + deterministic share: a concept-index hit costs microseconds of CPU; the same query through a 4B-param model costs seconds of it. Energy falls as coverage grows — the inverse of the LLM cost curve. [Longitudinal dashboard: deterministic-path % — CLL claim 4.]
- **Real-time learning:** §3 — correction-to-effect in milliseconds against a fine-tune cycle.
- **Quality — the honest accounting:** inside the served distribution, quality = coverage × verification, and the scoreboard is the generative harness win-rate (accuracy × provenance × calibrated refusal) against a frozen LLM baseline on identical generated inputs. Expect immediate wins on P4-style properties, provenance, correction durability; expect open-domain creativity and long-tail instruction gymnastics to surface as *named refusals and clarifying questions* (Gaps 5–7, conceded — handled by the Independence Policy, never delegated to an external model). "As good as a frontier model" is claimable **per-distribution and measured** — never in the abstract; and the bet that honest questions beat fluent lies is itself on the dashboard (clarify/refuse rates must fall while task success rises).

---

## 5. Build order (continues the milestone roadmap)

1. **M1 — flip CLL on** (nearest win, blocked only on live services): shadow → agreement stats → `on`; P4 0%→>60%, P1–P3 unregressed.
2. **M2 — T1-mini v2 on live SPPE data**, benchmarked against a frozen Qwen3-1.7B for measurement; in production, low confidence routes to CLARIFY (§2.6), not to a model.
3. **M3 — discovery on real text** — ✅ DONE 2026-07-07 (`experiments/ele/m3_real_text.py`): discovery itself works parser-free on real prose (518 constructions, scaffolding 100% top-decile by frequency); but predicate identity and argument-structure units were silently supplied by the toy corpora — on real text they must come from L1 extraction or a bounded parser interface. The pre-declared re-scope applies: constructions supplement L1; obligatoriness/spread stay valid once those inputs exist.
4. **M4 — ELE render into CSSE** (deterministic-share metric live) and **M4b — the constrained-decode realizer**, property-tested for content fidelity — the T2 endgame under the Independence Policy.
5. **M5 — knowledge ingestion at scale** with answerable-fraction and refusal-calibration curves.
6. **M6 — de-LLM the loop:** remove Qwen intent/render/reasoning services from the answer path entirely, gated on dashboards: deterministic share, clarify/refuse rate trend, task success. External models survive only as *frozen measurement baselines* in the harness. (Embedding runs locally/CPU — verified 2026-07-07: URL-driven encoder + sentence-transformers present; Modal is not a dependency.)
7. **M7 — typed emitters + document composer** (§2.7): math/table/diagram/code-scaffold emitters over VCO content; discourse templates discovered from approved responses with the sentence-level machinery. Property: every block traceable to VCO content.
8. **M8 — verification-first code synthesis** (§2.7): verified-pattern library from sandbox passes + enumerative small-function synthesis (CEGIS-shape). Metric: verified-solve rate per request class; kill: if search cannot reach useful solve rates on small functions, code stays scaffolding + retrieval + clarify.
9. **Continuous:** equal-budget baselines (E-Rule 4), frozen-baseline win-rate, coverage dashboards, kill criteria enforced in writing.

## 6. Summary judgment

The transformer taught us that distributional learning, composition, content-addressable retrieval, and cheap proposal generation are the ingredients of linguistic intelligence. It also fused them into an unauditable blob. Everything measured so far says the ingredients survive separation: grammar can live in ledgers, knowledge in graphs, retrieval in indexes, reasoning in bounded search, fluency in capacity-starved realizers — each one inspectable, correctable in milliseconds, and CPU-cheap. The unproven parts are named, tested next, and pre-scoped so failure re-routes rather than refutes. That is the difference between building an alternative to the LLM and merely telling a story about one.
