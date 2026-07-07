# ELE + CLL + Projection — Grounding Review and Falsifiable Roadmap

Date: 2026-07-06
Companion to: `ELE_CLL_Projection_Architecture_Spec.md` (the spec), `docs/concept_language_layer.md` (CLL living doc), `The_Prediction_Trap_Paper.md` (VCO paradigm), `docs/JimsAI_Complete_Specification_v10.md` / `v11.md` (production state).

Purpose: audit the spec's grounding against what actually exists in this repository, state honestly what "quality as good as frontier LLMs" can and cannot mean for this architecture, and define the falsifiable milestone path — under the same anti-hardcoding constraints that govern `benchmarks/genuine_eval.py` and CLL Rules 1–6.

---

## 1. Audit: what the spec claims vs what the repo contains

| Component | Spec status | Repo reality (2026-07-06) |
|---|---|---|
| CLL concept model (E1–E12) | referenced as prior art | **REPRODUCIBLE** — `experiments/concept_model/` with code, from-source lexicon (26,268 entries, provenance-stamped), seeds recorded in the design doc |
| CLL shadow mode | live | **CONFIRMED** — `prototype/jimsai/cll_shadow.py`, wired into `MultiIndexRetrievalEngine.retrieve` behind `JIMS_CONCEPT_INDEX=shadow`, zero-behavior-change by construction |
| Generative acceptance harness | assumed | **CONFIRMED** — `benchmarks/genuine_eval.py` (fresh seeds, live services, P1–P4 properties) |
| ELE evidence ledger, construction discovery, obligatoriness, shape renderer (§2 rows 1–15) | [PROVEN]/[PARTIAL] | **NOT IN REPO.** No `experiments/ele/`. No corpora, no seeds, no regression tests. The experiments ran in a session whose code was never committed |
| Projection engine | [PROVEN at toy scale] | **NOT IN REPO** (same session) |
| Negative-control corpora (§2 rows 11–12) | "reuse as regression tests" (§6.1) | **NOT IN REPO** |

**Consequence:** every [PROVEN] row for ELE and Projection is currently an *unreproducible claim*. By the spec's own §0 rule ("every module ships with the test that would falsify it"), rows 1–15 must be treated as [UNKNOWN-UNTIL-RECOMMITTED]. This is the single largest grounding defect and it blocks everything downstream of it. Milestone M0 exists to cure it.

---

## 2. Scope corrections (what replaces what)

The spec's title says "Replacing T1 and T2." The production interfaces (per v11) are more specific, and the mapping needs to be exact or we will build the wrong thing:

1. **Production T1** = intent classification of chaotic, multilingual prompts into a `SemanticIR` + 9-capability routing (Qwen3-1.7B, already skippable at compiler confidence ≥ 0.60).
   - The nearest replacement is **CLL's T1-mini** (concept-sequence classifier — E8: 12/12 cross-lingual on toy intents at ~11µs), *not* ELE.
   - **ELE's frames feed L1** (structured extraction: entities, relations, roles). ELE is an L1-upgrade and an ambiguity-exposer; CLL resolves what needs world knowledge. The spec's §7 question ("do layers consume ambiguity sets?") must be answered *before* integration: the contract is **ambiguity sets with confidence** (multiple candidate frames), because the pipeline downstream (L6 retrieval intersection, L8/L9) is what disambiguates — this mirrors the CLL v1 finding that ambiguous surfaces emit top-3 candidates and retrieval intersection resolves the sense.
2. **Production T2** = rendering a full VCO (reasoning chain, gaps, confidence, Markdown, multi-claim composition) — Qwen3-4B, already skipped at confidence ≥ 0.95 with zero gaps via the CSSE.
   - ELE render mode is **not** a wholesale T2 replacement. It is an **expansion of the CSSE's deterministic share**: shape-template + adjunct composition renders single-claim factual content with architecturally-zero hallucination (spec row 6); everything outside coverage raises `GapReport` and routes to Qwen3-4B, flagged unverified.
   - The metric that matters is therefore **deterministic-render share of live traffic** (rising over time) and **zero hallucinations within the deterministic share**, not "did we delete the render model." Deleting Qwen3-4B is the *asymptote*, not the milestone.

---

## 3. Honest framing: "quality as good as frontier LLMs"

The paper (§2) and the spec (§1, §5) both already concede the correct scope. Stated precisely, so nobody builds toward the wrong claim:

- **Not achievable (and explicitly non-goal):** raw parity with frontier models on open-domain generation, unconstrained instruction-following, or knowledge breadth from a cold start. Spec row 3 is the permanent reminder: a 20K-param transformer beat the 526-construction ledger by ~6× on perplexity. Do not re-litigate this; do not hide it.
- **Achievable and defensible (the home turf, per CLL §7):** on the **served distribution** of a workspace, match or beat an LLM baseline per query on **accuracy × provenance × calibrated refusal**, at a fraction of the cost, with correction latency in milliseconds instead of a fine-tune cycle. Frontier models structurally cannot offer pixel/region provenance, zero-retraining correction, or auditable inference (Prediction Trap §2.3).
- **The path to "feels frontier-quality" is coverage growth, not model growth:** deterministic share of traffic grows as lexicon + constructions + ingested graph grow; the honest fallback (bounded LLM, flagged) covers the shrinking remainder. Quality is measured continuously by the generative harness against a frozen LLM baseline on identical generated inputs — win-rate per property, never a vibe.

**The "trillions of prompts" constraint is a distribution claim, not a test-count claim.** No finite test set proves it. What proves it is mechanism-shape:
- every behavior is a general function of *data with provenance* (lexicon entries, discovered constructions, ledger observations, graph edges) — never an enumerated case;
- every test samples its vocabulary/inputs from the data source at runtime with fresh seeds (CLL Rule 2), so the system cannot be tuned to a fixed set;
- everything outside coverage fails **loudly and typed** (`GapReport`, `GAP_UNRESOLVED`) into a fallback or review queue — so novel inputs degrade to honest, never to silent-wrong.

---

## 4. Anti-hardcoding rules extended to ELE (binding)

CLL Rules 1–6 (`docs/concept_language_layer.md` §5) apply to ELE verbatim, plus these ELE-specific instantiations:

- **E-Rule 1 — No hand-registered constructions or templates.** The repo contains discovery code, never construction data. Every construction/shape template in a production artifact must carry provenance: the corpus slice and ledger observations it was discovered from, with counts. A developer hand-adding a `SHAPE_TEMPLATES` entry to fix a failing render has no legal path — the legal paths are (a) more corpus evidence, (b) the review queue. (The spec's illustrative Python dicts are pedagogy, not implementation.)
- **E-Rule 2 — Thresholds are calibrated on a frozen set, then locked** (spec §5 already requires this). `OBLIG_THRESHOLD`, `SPREAD_THRESHOLD`, `MIN_FRAME_COUNT`, `MIN_FILLER_DIVERSITY` get derived from a calibration corpus committed to the repo, recorded in the spec with the derivation script, and gated on minimum per-verb sample size. Retuning against a failing test is a violation.
- **E-Rule 3 — Negative controls are built before looking at the target test set** (spec §4.2 — this methodology found the two real bugs; it is not optional).
- **E-Rule 4 — Equal-budget neural baseline runs as a permanent regression** (spec §4.1). Any "as good as neural" claim for a symbolic mechanism ships with the comparison that could falsify it.
- **E-Rule 5 — The production judge is `benchmarks/genuine_eval.py`**, extended with ELE properties (below). ELE never gets a friendly benchmark as its acceptance gate.

---

## 5. Falsifiable milestone roadmap

Ordered so that the biggest untested assumptions die first. Every milestone has a kill/blocked criterion — a milestone without one is not on this list.

### M0 — Recommit the evidence (blocks everything) — ✅ DONE 2026-07-06
Recreate ELE + Projection experiments **in this repo** as `experiments/ele/`: evidence ledger (append-only invariant, order-independence property test), construction discovery, core/adjunct classification with obligatoriness, shape+adjunct renderer with `GapReport`, and the negative-control corpora of §2 rows 11–13 as seeded regression tests.
- **Pass:** every §2 row 1–15 reproduces from `python experiments/ele/run_all.py <seed>` across ≥4 seeds; the two [BUG FOUND] rows exist as regression tests that fail on the buggy implementation.
- **Kill:** any row that cannot be reproduced gets downgraded in the spec to [UNKNOWN] — in writing.

**Result (2026-07-06, seeds 702945 / 1 / 4242 / 999999): 60 PASS / 12 REPORT / 0 FAIL.** Suite: `experiments/ele/run_all.py`; raw output in `experiments/ele/results/run_results.json`. Notes for the record:
- `OBLIG_THRESHOLD = 0.9583`, **derived** from frozen calibration seed `20260706` (recorded in `classify.py`), then locked — the spec's §7 open question on threshold derivation is closed by mechanism, not by a chosen constant. The 0.92-collocated adjunct edge case misclassifies at 0.90 and classifies correctly at the derived value, reproducing row 13 exactly.
- Rows 11/12/14/15 (the bug-shape rows) are regression tests that demonstrably fail on the buggy implementations (spread-only acceptance, concentration-amplifying `spread_weighted`, base-glued suffix keys → exact 0.0/0.0, vacuous single-filler corpora).
- Row 3 reproduced as methodology, with an honest regime note: on the near-trigram-deterministic nonce grammar the ledger predictor and the tiny neural LM are comparable (~4.9 vs ~4.7 ppl); the original 6× neural win was on natural-ish text. The equal-budget comparison stays a permanent regression either way (E-Rule 4).
- Row 7 reproduced strongly: 20–25/30 held-out neural renders contained unlicensed tokens vs 0 by construction for the template renderer.
- The ELE→CLL bridge contract (ambiguity sets recorded whole, non-composable refusal, correction-as-audited-edit) runs against the real `experiments/concept_model/ConceptGraph` — no duplicate graph code.

### M0b — Projection scaling benchmark (the spec's own biggest unknown, §3.3) — ✅ DONE 2026-07-06
Latency/memory vs ledger size, 100 → 100,000+ events, for each projection type (temporal, trust, contradiction, domain).
- **Pass:** p95 view-computation latency and memory growth curves published in the spec; a snapshot/incremental-view design exists for anything super-linear.
- **Kill:** if projection cannot serve L6-scale volumes even with snapshots, CLL integration proceeds **without** the ledger-projection substrate (concept index + existing retrieval), and Projection is re-scoped to low-volume layers (trust/contradiction), not retrieval.

**Result (2026-07-06, `experiments/ele/bench_projection.py`, JSON in `experiments/ele/results/projection_bench.json`):**

| events | full recompute p50/p95 (ms) | incremental apply p50/p95 (µs) | cell query p50/p95 (µs) | peak MB |
|---|---|---|---|---|
| 100 | 0.23 / 0.33 | 0.8 / 2.3 | 4.0 / 7.4 | 0.02 |
| 1,000 | 2.3 / 3.2 | 0.5 / 1.3 | 6.9 / 11.3 | 0.14 |
| 10,000 | 15.9 / 20.7 | 0.4 / 0.6 | 4.6 / 11.1 | 1.5 |
| 100,000 | 235.9 / 329.7 | 0.8 / 1.2 | 3.1 / 5.5 | 15.4 |

**Verdict:** full recomputation is linear in ledger size — **not viable per-query at L6 volumes** (~236ms p50 at 100k events). The incremental materialized view is O(1) per event and per cell query (µs-level, flat across sizes). Binding design consequence: **production projection uses the incremental view; full recomputation is reserved for rebuild/audit paths.** The equivalence of the two is property-tested in the suite (R5) and must remain so.

### M1 — CLL shadow → on (nearest win; already planned in CLL doc)
Run the live generative harness with `JIMS_CONCEPT_INDEX=shadow`, collect agreement stats, then flip to `on`.
- **Pass:** P4 multilingual 0% → >60%, P1–P3 unregressed, on fresh seeds.
- **Kill:** if shadow agreement analysis shows concept retrieval systematically disagrees with correct production results (not just adds recall), the encoder/lexicon gap is characterized and fixed before `on` is attempted.

**Status 2026-07-07 (updated): UNBLOCKED without Modal.** The Modal 429 quota block was routed around by going fully local, which the Independence Policy demanded anyway: local embedding service (e5-small, CPU, `services/embedding-service` on :8090 — the encoder is URL-driven), all LLM/classifier endpoints black-holed to an instantly-refused port, `JIMS_T1_SKIP_CONFIDENCE=0` (T1 never invoked), CSSE-only rendering, `JIMS_CONCEPT_INDEX=shadow` with a durable JSONL evidence sink added to `cll_shadow.py` (`JIMS_CLL_SHADOW_LOG` — agreement records persist independent of logger config).

**De-LLM baseline (run 1, seed 2371, fully local models — the honest "what were the LLMs actually doing" measurement):**

| Property | de-LLM local (2026-07-07) | with Qwen T1/T2 + Modal classifier (2026-07-03) |
|---|---|---|
| P1 learning | 67% | 100% |
| P2 gap honesty | 0% (ghost queries leaked neighbor facts) | (open issue then too — entity gate) |
| P3 robustness | 56% | 100% |
| P4 multilingual | 0% | 0% (CLL's target, unchanged) |
| P5 multi-intent | 0% (recall ok, math missed) | — |
| P6 math | 0% | 100% |
| P7 scoping | 100% | 100% |

What the deltas actually localize (these are M-targets now, not mysteries):
- **Routing:** every failed P1/P3 case is one fact family (`device_codename`) misrouted to `coding`/`video_generation` at conf 0.35 — identifier-heavy prompts without the zero-shot classifier or T1. This is precisely M2's job (T1-mini) and, under the Independence Policy, low-confidence routes should CLARIFY rather than misroute — the 0.35-confidence misroutes are exactly the cases the policy converts to bounded questions.
- **P6 math 0%:** the deterministic solver is fine; what vanished was Qwen's messy-text → expression normalization. Needs a deterministic normalization layer (concept/structure-driven) or CLARIFY on unparseable expressions — never an LLM.
- **P2 leaks** (`leaked_other_fact=True` on ghost entities): the entity-scope evidence gate is not filtering under the local configuration — needs investigation; CLL `on` (literal gating at the index) is the designed structural fix.
- Latency ~20–38s/query fully local on CPU (vs ~113s median with Modal cold starts) — dominated by cloud persistence round-trips (Supabase/Vectorize/Neo4j), not model inference.

**M1 shadow evidence (run 2, seed 124591, `benchmarks/results/cll_shadow_m1.jsonl`, 31 observations):** on the cross-lingual queries where production recall failed 0/8, the shadow concept index would have retrieved the English-taught record on **4/8 (50%)** — French ✓, Yoruba 2/3, Chinese 0/3. The 4 misses are two named, mechanistic defects (both anticipated by the CLL doc's own findings, now confirmed on live pipeline traffic):
1. **zh lexicon coverage** — 项目/数据库/使用 absent from the 22k-key lexicon (the concept exists: English "project" → `C:Q170584`; its simplified-zh surface doesn't — the traditional/simplified variant-folding gap, CLL v1 finding 4). Fix: data (OpenCC variant tables + deeper zh alias ingestion), zero code.
2. **Doc-side sentence-initial entity suppression → hard-literal-gate veto** — the v1.1 orthography rule (only mid-sentence capitals are name-like) fixed the French "Quelle" false positive but drops sentence-initial entities at INDEXING time ("Tepogi is in…" → no `L:tepogi` on the record), so a query carrying the literal vetoes the correct record. Fix shape (general): asymmetric literal policy — index-side recall-first (sentence-initial capitals index as literals), query-side gating stays strict.
Per the M1 kill criterion these two are the characterized encoder/lexicon gaps to fix **before** `JIMS_CONCEPT_INDEX=on` is attempted; the 50% shadow recovery where production scores 0% is the strongest live evidence yet that the concept index is the right mechanism for P4.

**M1 on-mode iterations (2026-07-07, all fully local/de-LLM):**
- *Fixes applied:* lexicon enriched from Wikidata (+9,191 zh / +4,194 fr surfaces incl. variant codes; 22k→39k keys; `experiments/concept_model/enrich_lexicon.py`, full provenance); asymmetric literal policy in `cll_shadow.py` (documents index sentence-initial entities recall-first; queries promote sentence-initial capitals only on corpus memory); `JIMS_CONCEPT_INDEX=on` implemented in `retrieval.py`.
- *Iteration 1 (post-rank prepend, seed 211770):* P4 0%→33% — the first P4 passes ever, including zh — but prepending bypassed production scoring: chat-question records flooded the top (sentence-initial "What"/"Which" became promotable literals via a feedback loop through indexed chat records), regressing P3 filler cases and keeping P2 at 0%.
- *Iteration 2 (candidate-level injection + rare-literal gate, seed 933508):* P3 restored to 78%, ghost-query veto works (concept index returns [] on unseen literals) — but P4 back to 0% for a newly-localized reason: the df-ratio rarity test wrongly blocks literal promotion for *frequently-discussed* entities (rarity conflates function words with popular entities; the correct name-evidence signal is "capitalized mid-sentence anywhere in the corpus"), and where the fact DID reach final results (confirmed in `cll_shadow_m1_on2.jsonl`: the zh queries' finals contain the English-taught fact sig), **the CSSE answer builder still failed** — it voices top memory excerpts regardless of whether they answer the question.
- *Controlled probe (clean workspace):* teach one fact → English AND Chinese queries both voice it end-to-end. **The de-LLM cross-lingual chain works when ranking is clean.** The harness failure mode is accumulated chat-noise records outranking the taught fact by P4 time — and the answer builder voicing a question-record as a claim ("I believe this is right" on an echo), which is also P2's leak source and precisely the fluent-wrong failure the Independence Policy §2.6 forbids.
- **Remaining work to close M1, precisely scoped:** (a) ranking discipline — trust/provenance-aware reranking so prior-query and answer-echo records rank below taught facts (the hybrid-scoring trust term from spec v10, applied in this path); (b) answer-selection honesty in the CSSE — voice only claims whose structured relation matches the query's target, else emit a gap (this is M4's ELE-render/CSSE work arriving on schedule); (c) replace the df-ratio promotion test with mid-sentence capitalization evidence. All three are general mechanisms; the harness stays the judge.

**M1 — ✅ CLOSED 2026-07-07 (judgment run 3, seed 58533, fully de-LLM/local): P4 0% → 67% (bar >60%), P2 gap honesty 0% → 100%, P1 100%, P3 78% (unregressed), P7 100%.** The closing fixes were one principle applied at three layers — **"questions don't assert"** — plus entity scope and concept-level relevance:
- Reasoning bridge (`runtime_layers._memory_excerpt_steps`): interrogative sentences are never voiced as claims (killed the answer-echo); a claim must share a query entity (killed ghost leaks — P2 to 100%); sentence relevance adds CONCEPT overlap via the CLL encoder, so cross-lingual claims pass the relevance minimum at meaning level. The "supports intent" filler-claim fallback is deleted: no assertive match → named gap + HEDGE (Independence Policy §2.6 in code).
- Concept index (`cll_shadow`): per-sentence assertive indexing — declarative occurrences of a key weigh 2× interrogative mentions, so records that STATE things about an entity outrank records that ASK about it (killed the tie-flood); mid-sentence-capitalization name memory replaces the df-ratio test (popular entities stay promotable; colon = clause introducer, so `prompt:`-prefixed question words gain no false name evidence); unknown gate literal → the index ABSTAINS (ghost honesty as an index property).
- Chaotic-input robustness (user-directed mechanism): O(1) skeleton/anagram typo repair over the growing lexicon (`_typo_repair`) — "proejct"→"project" by letter anchors, unique-candidate-only, zero language data.
- Notably: `device_codename_zh` passed *despite being misrouted* to video_generation — the concept index carried it. The 3 remaining P4 misses: 1 router misroute (M2) and 2 Yoruba cases (yo lexicon 1.8k entries vs 17k zh — same `enrich_lexicon.py` path, more yo alias sources; data work, no code).
- Every fix above is a general mechanism stated as a principle; none references a test case, a fact family, or a language. P5/P6 (routing decomposition + math normalization) remain 0% and belong to M2 — deliberately untouched.
- **Production config note:** the winning run used `JIMS_CONCEPT_INDEX=on`, local embedding service, `JIMS_T1_SKIP_CONFIDENCE=0`, and black-holed LLM endpoints — this is the de-LLM deployment configuration to promote into `.env`/deploy manifests (M6).

### M2 progress — routing + math without any LLM — ✅ MAJOR MOVEMENT 2026-07-07
Two runs (seeds 889948, 83097), fully de-LLM/local. Final scoreboard: **P1 100% · P2 100% · P3 89% · P4 78% · P5 50% · P6 100% · P7 100%.**
- **P6 math 0% → 100%** — `prototype/jimsai/math_extract.py`: math notation treated as the formal language it is (NFKC fold, maximal balanced spans, variables admitted only by operator adjacency, `^`→`**`). Verified offline on arithmetic/equations/CJK-embedded/chaotic text and correctly extracts *nothing* from recall prose. The Qwen extraction bridge is now a dead legacy fallback. Line 922's `# T1 bridge handles extraction` era is over.
- **Device-family misroutes eliminated** — workspace-literal routing evidence: a query naming an entity the workspace memory already knows (CLL postings) is a memory question, whatever its wording resembles ("codename of the device…" ≠ coding when 'Bevorno' is a taught entity). Data-driven, no vocabulary; structural signals (code fences, math syntax) stay dominant.
- **P5 multi-intent 0% → 50%** (first pass ever) — union entity scope: a multi-intent prompt carries several foci (numbers for the math span, names for the recall span), and a claim may serve any of them. The multi-attention-span principle landing in the claim gate. Remaining miss: person-family recall under the math route — next diagnosis.
- **P3 89%** — skeleton-tolerant entity matching (the typo-repair anchor principle applied at the claim gate: 'Pujvuu' finds 'Pujuvu'); the single P3 failure was an HTTP 500 from a transient 5s embedding timeout hitting the by-design hard-fail — an infra item (raise `JIMS_EMBEDDING_TIMEOUT`, add one retry), not logic.
- **P4 78%** — both misses remain the Yoruba lexicon-coverage data item (yo: 1.8k entries; fix = `enrich_lexicon.py` with OMW/PanLex yo sources; zero code).
Every mechanism above is stated as a principle (formal-language extraction; workspace knowledge as routing evidence; multi-focus claim scope; letter-anchor matching); none references a test case, family, or language.

**Namespace extension (2026-07-07, user-directed):** the extractor now admits long identifiers by lookup against the solver's GROWING symbol namespaces — physics constants (`k_B*300`, `E=m*c**2`, `F=5*g`, `P=R*300/0.05` all verified) and chemical formulas decomposed against the element table (`H2SO4` admits iff every element symbol exists in the data and a digit is present). Physics/chemistry/engineering notation rides the same grammar with zero per-domain code; the namespaces live with the solver (to be sourced from CODATA/periodic-table data). Honest boundary: word problems ("how many moles in 98 g of H2SO4") correctly extract *nothing* — mole arithmetic requires domain reasoning (concept layer), not span extraction; that is a solver-capability roadmap item, not an extraction gap.

### Dialogue (P8) + natural responses + streaming — 2026-07-07

- **P8 dialogue property added** to `genuine_eval.py` (the judge, built first): an underspecified follow-up ("And what database does *it* use?") in the same thread must resolve via discourse focus, and a COLD thread (no prior turn) must honestly fail to resolve the same follow-up. Cross-family, seeded.
- **Root cause found and fixed — a real defect, not a test gap:** `ProductionRuntime.save_session` silently no-ops when Redis is unavailable (`if self.celery and ...available`), so dialogue focus evaporated between turns whenever the external cache was down. Fixed in `pipeline._load_session/_save_session`: dialogue state is now core conversational memory with an **always-available in-process tier** plus best-effort cloud durability — a dropped cache write can never erase the conversation's focus. Verified: follow-up now inherits `['vorbani']` and answers end-to-end (opener→follow-up) fully de-LLM.
- **Discourse-focus source unified with the concept layer:** when L1 extraction yields no entity for the opener, `ACTIVE_OBJECT` falls back to CLL name-evidenced literals from the same query — one name-evidence machinery everywhere, any language. Inherited focus also feeds the router's workspace-literal probe so dialogue follow-ups route to memory, not a misread capability.
- **Removed a hardcoded heuristic that blocked dialogue:** the `uses_/has_/is_` prefix guard on focus inheritance (a vocabulary list) is deleted — inheritance is now an ambiguity candidate that downstream evidence (retrieval intersection, entity-scoped claims, 15-min topic decay, gap honesty) validates.
- **Natural responses — robotic leaks removed at the source:**
  - The stock "*I believe this is right.*" footer stamped on every answer is gone; certainty is conveyed by answering plainly, and only genuine uncertainty (tier 4) adds a brief woven sentence. No italic meta-footer.
  - Internal diagnostic gaps ("no assertive claim matched…", "Coding provider unavailable…") are now **typed `[internal]` at emission** and stripped structurally by the renderer — not caught by a growing substring blocklist. Users get the natural gap response ("Share a file or describe what you're building…") instead of raw internal status.
- **De-LLM streaming:** `/v1/query/stream` now streams the deterministic CSSE render itself in natural word-chunks (`pipeline._stream_chunks`) when no T2 LLM is present — genuine progressive token delivery with zero model, exact text reconstruction, language-agnostic. Verified: 9 word-chunks reconstruct the exact answer.
- **Removed the load-bearing hardcoded heuristic (`_looks_like_structural_identifier`):** it only recognized camelCase/dotted code identifiers, never plain proper nouns — so openers didn't extract their entity, and entity-less ghost queries INHERITED stale dialogue focus and leaked neighbor facts (the P2 regression). Replaced with the CLL name-evidence mechanism (mid-sentence capitalization, any language, no word list) — one heuristic removed, three failures fixed: P2 leak, device dialogue routing, and clean entity scope. Inherited (lowercased) dialogue entities are checked against concept-index postings directly (`shadow.known_terms`) since they no longer re-tokenize as literals.

**FINAL BOARD (2026-07-07, seed 724613, fully de-LLM/local): P1 100 · P2 100 · P3 100 · P4 78 · P5 50 · P6 100 · P7 100 · P8 100.** P8 dialogue 4/4 including the cold-thread honesty control (a follow-up in a thread with no prior turn correctly refuses to resolve "it"). Remaining 3 failures are all known, non-regression: 2 Yoruba P4 (lexicon data — yo 1.8k entries; `enrich_lexicon.py` + OMW/PanLex) and 1 P5 person-recall-under-math-route. Six of eight properties at 100%, fully de-LLM, on fresh seeds — the strongest result of the program.

### M2 — T1-mini v2 (the real T1 replacement)
Export SPPE pairs as (concept sequence → intent); train the tiny classifier; benchmark against Qwen3-1.7B **on the same routed live queries**, including the v11 chaos list (typos, code-switching, pasted logs, multi-intent).
- **Pass:** ≥ T1 parity accuracy at <1% latency; ships behind a flag with confidence-gated LLM fallback; fallback rate reported on a dashboard, expected to fall over time.
- **Kill:** if concept-native classification plateaus materially below Qwen accuracy on live chaos (not toy prompts), T1 stays; T1-mini becomes a pre-filter that skips T1 only above a calibrated confidence — still a cost win, honestly scoped.

### M3 — ELE discovery on real text (the "verb = 2nd token" reckoning, spec §7) — ✅ DONE 2026-07-07
Stress the discovery pipeline against fronted adjuncts, passives, subordinate clauses, questions — sampled from real corpora (Rule 2 style), not constructed sentences.
- **Pass:** discovery works from surface distribution alone, or the spec records exactly which structural signals had been silently supplied by the toy heuristic and what replaces them (this is a *finding*, either way).
- **Kill:** if construction discovery fundamentally requires parser-grade structure on real text, ELE's parse side is re-scoped: frames come from L1's existing extraction + discovered constructions as a *supplement*, and the "parser-free" claim is retired.

**Result (2026-07-07, `experiments/ele/m3_real_text.py`, real prose sampled at runtime from this repo's documentation; JSON in `experiments/ele/results/m3_real_text.json`):**
- **M3a PASS — discovery itself is parser-free on real text:** 518 constructions promoted from 418 real sentences; the top frames' fixed tokens sit 100% in the corpus's top-decile frequency stratum — function-word scaffolding (`the %`, `% is`, `of %`, …) identified distributionally, with no stopword list anywhere.
- **M3b FINDING — the classifier's *inputs* do not come from position heuristics.** Two artifacts were found and controlled for: (1) any predicate rule that picks tokens from the sentence saturates obligatoriness to 1.0 on self-matching tails (confound guard added); (2) random predicate assignment fragments evidence below the sample gate (controls: 60/60 UNPROVEN), so agreement comparisons cannot certify the heuristic. Decisively: the tails discovery surfaces on real text are determiner/copula scaffolding — not argument-structure units — so classifying them as CORE/ADJUNCT is a category error regardless of predicate rule.
- **Conclusion (the pre-declared re-scope applies):** the toy corpora silently supplied *two* structural gifts — predicate identity and meaningful candidate argument units. On real text both must come from L1's structured extraction or a bounded parser interface (perception-grade trained component, knowledge-free, per CLL hard truth 12). Obligatoriness/spread classification remains valid *once those inputs exist* (proven in the seeded suite, R11–R13b). The "parser-free discovery" claim survives; the "parser-free argument-structure classification" claim is retired, in writing, here.

### M4b — constrained-decode realizer (the T2 endgame mechanism) — ✅ MECHANISM PROVEN 2026-07-07
`experiments/ele/realizer.py`, seeds 702945 / 4242 / 1 / 999999, JSON in `experiments/ele/results/m4b_realizer.json`. A ~22k-param in-house neural realizer decodes over a content-licensed lattice and must LEARN agreement (article form = f(noun class, number)) and plural morphology — the fluency decisions templates would need precomputed upstream.

- **F1 — zero invention is a property of the decode space:** at an undertrained checkpoint, the *same weights* hallucinate unlicensed content on 18–23/24 held-out frames unconstrained, and on **0/24 constrained** — across all seeds and both languages. Training quality cannot break the guarantee.
- **F2 — fluency beyond templates:** 100% held-out agreement and 100% exact match (all seeds, both languages) on compositional (agent, object) × number frames reserved before generation.
- **F3 — new language = data only:** a second grammar (fresh function words, SOV order — word order is grammar *data*) met F1+F2 with the identical class; no language branch exists in the file.
- **Finding (earned through two real failures):** closed-class vocabulary must be defined *frequency-free*: a token is closed-class iff it never appears as a frame value AND is not a (value + mined suffix) variant. Two frequency-based definitions failed first — unbalanced noun classes pushed rare plural articles below any frequency bar, masking the correct form out of the lattice (agreement 0.50, then 0.75, then 1.00 after the fix). The failure history is preserved in the module docstring.
- **Scope honesty:** proven at nonce-grammar scale with two fluency phenomena. The production path (real SPPE pairs, real morphology across languages, VCO-scale content licensing) is M4b-production, judged by content-fidelity property tests + fluency comparison against approved human-rated responses.

### Directive update (2026-07-07): full LLM independence
Per project direction, the architecture drops LLM fallback entirely — even on hard cases. See `docs/jimsai_llm_free_architecture.md` §2.6 (Independence Policy): outside coverage the system CLARIFIES (bounded question rendered from the ambiguity set), REFUSES with the gap named (typed GapReport), or GROWS (gap → coverage backlog). External models survive only as frozen measurement baselines in the harness (M6). The measurable bet: clarify/refuse rates fall over time while task success rises — tracked on the dashboard, falsifiable in public.

### M4 — ELE render as CSSE expansion (T2 deterministic share)
Wire the shape+adjunct renderer into the CSSE path with `GapReport` → Qwen3-4B fallback (flagged unverified). Templates derived from M3 discovery output per E-Rule 1.
- **Pass:** deterministic-render share measurably rises on live traffic; **zero hallucinations within the deterministic share** on generated held-out compositional combos (the row-6 property, at production scale, fresh seeds); fluency judged acceptable on the factual/structured slice.
- **Kill:** if deterministic share stalls at a trivial fraction (<~10% of renderable responses) after coverage growth, the renderer remains a CSSE feature and the "T2 replacement" framing is dropped from the spec.

### M5 — Knowledge breadth (CLL Gap 1; makes the system *feel* capable)
Bulk-ingest Wikidata/ConceptNet slices as provenance-stamped graph substance; property test = mask held-out edges, ask generated questions (never enumerated).
- **Pass:** answerable-fraction grows monotonically per million edges ingested; refusal stays calibrated (reversed-edge honesty stays ≥ the v1.1 bar).
- **Kill:** if answerable-fraction saturates early, the bottleneck (inference depth vs coverage vs disambiguation) is identified by ablation before more ingestion is bought.

### Continuous (never "done")
- Equal-budget neural baseline regression (E-Rule 4) on every ELE mechanism claim.
- Weekly coverage dashboards (CLL Rule 4): % tokens → concept per language, deterministic-render share, T1-mini fallback rate, refusal calibration.
- LLM-baseline win-rate on the generative harness: same generated inputs to JimsAI and a frozen frontier-model baseline; report accuracy × provenance × calibrated-refusal per property. This is the only legitimate scoreboard for the "quality as good as frontier" ambition — per-distribution, measured, and it will show losses honestly (expect to lose Gaps 5–7 indefinitely; expect to win P4-style properties immediately).

---

## 6. Summary judgment

The architecture's honesty infrastructure is genuinely unusual and is the thing to protect: labeled evidence, committed negative results, anti-hardcoding rules with no legal path around them, and a generative harness as the only judge. The CLL side is real, committed, and one flag-flip away from its first production win (M1). The ELE side is currently *a well-written memory of experiments that no longer exist* — M0 is not bureaucracy, it is the difference between an engineering program and a story. Frontier-quality is reachable only as a per-distribution, measured claim — coverage growth plus honest fallback — and the roadmap above is the shortest falsifiable path to it.
