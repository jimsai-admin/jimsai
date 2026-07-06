# Concept Language Layer (CLL) — Living Design Document

Status: brainstorm → v0 prototype. This document records the concept, the hard truths,
and every experiment we run. Nothing here is settled; entries are dated and kept even
when superseded, so the idea's evolution stays auditable (VCO thinking applied to our
own design process).

---

## 1. The core idea (2026-07-03)

Language surface forms differ; the concepts they name are stable. "Dog" (en), "ajá" (yo),
"chien" (fr), "狗" (zh) all name one concept. If every language's words resolve to one
canonical **concept ID** before anything is stored or reasoned about, then:

- **Memory becomes language-agnostic at the index.** A fact taught in English and a
  question asked in Yoruba intersect at the same concept IDs — cross-lingual retrieval is
  an exact lookup, not an embedding approximation.
- **Training data becomes an intersecting graph, not weights.** Every ingested sentence
  is a set/sequence of concept nodes; sentences intersect where they share concepts
  ("My dog is big" ∩ "My father bought me a dog when I lost my cat" = {C:my, C:dog}).
  Knowledge stays sourced, linked, deletable, and correctable — never locked into a
  frozen parameter blob.
- **T1 shrinks.** Intent classification over a closed vocabulary of ~10⁵ concept IDs can
  be a tiny model (or partially deterministic pattern matching) instead of a 1.7B LLM —
  CPU-fast, trainable by our own SPPE loop.
- **T2 stays a fluency layer.** The CSSE can deterministically realize concept-level
  answers in the query's language for a growing share of responses; the render model
  polishes, never invents.

### Evolution note — from letter-numbers to concept IDs

The first sketch encoded characters as numbers (D→4, o→15, g→7 so dog = (4,15,7)).
We rejected it after inspection: a spelling code carries no meaning. "dog" (4,15,7) and
"dig" (4,9,7) are near-identical tuples with unrelated meanings; "dog" and "puppy" share
nothing. Meaning does not live in spelling. The upgrade that preserves the intent:
encode **which concept a word names**, not how it is spelled. The cross-language mapping
the sketch wanted ("look up the Yoruba form of dog") becomes: surface form → concept ID →
target-language surface form. Same idea, one level up, and it survives polysemy and
morphology (see hard truths).

---

## 2. Hard truths we must not paper over

1. **Interlingua MT lost, historically.** Rule-based interlingua translation was beaten
   by statistical and then neural methods because *full* meaning (tense, aspect, register,
   metaphor, pragmatics) never fit a discrete inventory. Lesson: the concept layer must
   not carry everything. It is the exact/fast/auditable path; multilingual embeddings stay
   as the fallback for what the lexicon doesn't cover. Deterministic share grows with use;
   it never has to reach 100% to be valuable.
2. **Polysemy is the norm, not the exception.** "Bank" is ≥2 concepts; Yoruba "ọjà" and
   English "run" (100+ senses) are worse. Sense selection needs context — this is a
   bounded disambiguation task (small model or concept-context voting), not free generation.
3. **Word-to-word mapping doesn't exist.** Multi-word expressions ("kick the bucket",
   "iṣẹ́ akanṣe" = project), morphology (agglutination, tone), and segmentation (Chinese
   has no spaces) mean the lexicon must map *lemmas and phrases*, not words, and each
   language needs its own tokenizer front-end.
4. **Word order carries meaning the concept-set loses.** {C:dog, C:bite, C:man} is both
   "dog bites man" and "man bites dog". The concept layer needs the *sequence* retained
   and, for reasoning, typed relations (subject/object) — which JimsAI's L1 structured
   extraction already produces. Concept sets index; relations disambiguate.
5. **Coverage is a grind.** Seeding from open data (Wikidata lexemes, Open Multilingual
   WordNet, PanLex) gets ~10⁴–10⁵ lemmas per major language, but low-resource languages
   (Yoruba included) have thin coverage. The growth loop must be governed: unknown form →
   candidate mapping (embedding-suggested) → human review → accepted lexicon entry. Same
   pattern as the world-model promotion engine.
6. **Named entities and novel terms must pass through as literals.** "Rovuku" is not in
   any lexicon and never will be — it stays a literal token, shared across languages
   as-is. (Our eval harness's nonce entities already prove literals cross language
   boundaries: the entity name is the one part of a French query that matches an English
   memory lexically.)
7. **Homographs across languages collide.** "Chat" is a cat in French and a conversation
   in English — the lexicon key must be (language, surface), never surface alone. Language
   identification of the query is therefore load-bearing and must be honest about
   uncertainty (code-switching exists: "abeg send the invoice sharp sharp").
8. **This does not replace generation for open-ended fluency.** Concept-to-surface
   realization handles factual/structured answers; creative writing and nuanced prose
   still route through T2. CLL narrows T2's job; it doesn't delete it.

---

## 3. Architecture sketch (how it lands in JimsAI)

```
query text
  │  language ID (+ uncertainty)
  ▼
Tokenizer front-end (per script: latin lemmatize, CJK longest-match, diacritic normalize)
  ▼
ConceptLexicon: (lang, lemma/phrase) → concept candidates
  ▼
Sense disambiguation: context voting over neighboring concepts (bounded model later)
  ▼
Concept sequence: [C:my, C:dog, C:be, C:big] + literals [L:rovuku] + relations from L1
  ├─► Inverted concept index (posting lists) ── exact cross-lingual retrieval, IDF-weighted
  ├─► Sentence graph: records intersect at shared concepts (spreading activation)
  ├─► T1-mini: intent classifier over concept sequences (tiny, CPU)
  └─► CSSE realization: concept answer → surface text in query language (T2 polishes)
```

Integration points: L1 `DualRepresentationEncoder` gains a concept channel;
`MultiIndexRetrievalEngine` gains a concept posting-list index consulted before scoring;
the entity-scope gate becomes an index property (literals must intersect). Embedding
retrieval stays as fallback — dual representation, as the spec already demands.

---

## 3b. Multimodal extension (2026-07-03)

The concept layer is not a language trick — it is a **grounding layer**, and
non-text modalities plug into it the same way languages do. A photo of a dog,
the word "dog", "ajá", and "狗" all resolve to `C:dog`. Consequences:

- **Cross-modal, cross-lingual retrieval is one mechanism.** An image ingested
  once is retrievable by a text query in any language, because both sides meet
  at concept IDs in the same inverted index. No paired translation data, no
  per-language captioning.
- **Perception models become bounded interfaces — the T1/T2 pattern again.**
  A vision encoder's job is to emit concept candidates with confidence and a
  source region (bounding box / timestamp), never free-form text shown to users.
  Its output is a discrete, auditable, correctable record. A user can say "that's
  not a dog, it's a fox" and the correction is a graph edit — no retraining.
- **Provenance gets stronger, not weaker.** A concept extracted from an image
  carries its region; from video, its time span. A VCO claim grounded in an
  image can point at the exact pixels — provenance frontier models structurally
  cannot offer.
- **Video is concept sequences over time.** Frames/shots emit concept sets;
  events are typed relations with temporal edges (`C:dog —chases→ C:cat` @
  00:12–00:19). The same E5 lesson applies: bags of concepts index, relations
  carry meaning.

### Hard truths for multimodal

9. **Perception is probabilistic and open-vocabulary.** Detectors mislabel and
   miss; novel objects have no concept yet. Same answer as language: confidence
   thresholds, embedding fallback for the unknown, human-reviewed promotion of
   new concepts. Perception confidence must flow into VCO confidence — an
   image-grounded claim is only as strong as its detection score.
10. **Scenes are relations, not bags.** "Dog on sofa" vs "sofa on dog" — spatial
    and action relations must ride along with the concept set (the E5 lesson,
    again, in 2D).
11. **Granularity is worse in vision.** Is it `C:dog`, `C:golden_retriever`, or
    `C:animal`? Detectors answer at their training granularity; taxonomy edges
    (open question 2) stop granularity mismatch from breaking retrieval.
12. **We do not escape trained weights — we demote them.** The vision encoder,
    the multilingual embedder, and the sense disambiguator are all
    backprop-trained components. CLL's claim is narrower and defensible:
    **knowledge never lives in those weights.** They are replaceable commodity
    perception/interface parts; what the system *knows* is the concept graph —
    inspectable, editable, deletable, growing in real time without a training
    run. Swap the vision encoder tomorrow; the knowledge survives untouched.
    "Training data is never thrown away" is realized as: every datum becomes
    graph substance that future queries traverse, not gradient dust.
13. **Retrieval is not thinking.** The graph makes evidence cheap to find;
    abstract reasoning over it (analogy, composition, counterfactuals) is the
    job of the existing L5/L8/L9 layers. CLL feeds them better evidence; it does
    not replace them.

---

## 4. Experiment log

### v0 — offline mini-prototype (2026-07-03)

Goal: falsify or support the core claims with zero infrastructure — pure Python, no
services, no network. Code: `experiments/concept_model/`.

Claims under test (generative, seeded — same anti-hardcoding rules as
`benchmarks/genuine_eval.py`):

- **E1 cross-lingual recall:** teach generated nonce facts in English; recall queries in
  fr / yo / zh must retrieve the right record via concept + literal intersection.
- **E2 gap honesty:** ghost nonce entity → zero results (literal gate at the index).
- **E3 polysemy:** "bank" resolves to different concepts in money vs river contexts via
  neighbor voting.
- **E4 graph intersection:** the dog/cat two-sentence example — related-record discovery
  through shared concepts, IDF-weighted so C:my doesn't dominate.
- **E5 order sensitivity (honesty check):** concept-set retrieval alone CANNOT
  distinguish "dog bites man" from "man bites dog" — asserted as a documented limitation,
  proving why relations must ride along.

Results: see bottom of this section after each run (the test prints a table; paste it in).

**v0 results (run 2026-07-03; seeds 702945, 1, 4242, 999999 — all pass):**

```
E1 cross-lingual recall  : PASS 9/9 top-1 (fr/yo/zh × 3 fact families; nonce
                           entities matched as shared literals + concept overlap,
                           e.g. shared=[C:database, C:project, C:use, L:fupame])
E2 gap honesty           : PASS 3/3 (ghost entities → zero results — the literal
                           gate is an index property, not a scoring heuristic)
E3 polysemy              : PASS (bank→C:bank_finance under money context,
                           bank→C:riverbank under river context, by neighbor vote)
E4 graph intersection    : PASS (d2 reachable from d1 via C:dog;
                           idf(C:dog)=1.386 > idf(C:my)=1.099 — common concepts damped)
E5 order sensitivity     : CONFIRMED LIMITATION (concept sets identical for
                           "dog bites man"/"man bites dog"; sequences differ —
                           typed relations required for role disambiguation)
```

Reproduce: `python experiments/concept_model/test_concept_model.py [seed]`.

Interpretation: the index-level claims hold in miniature — notably, exactly the
mechanism that fails in production today (P4 cross-lingual recall = 0% in
`genuine_eval.py`) passes 9/9 here. The two load-bearing assumptions v0 does NOT
test: (a) lexicon coverage at scale — the demo lexicon is ~120 hand-seeded lemmas,
production needs 10⁴–10⁵ from Wikidata/OMW/PanLex; (b) sense disambiguation
quality on real chaotic text — E3 is one easy case. Also untested: code-switching
(v0 falls back to the English lexicon per token, a placeholder for real per-token
language ID), and Yoruba tone loss under diacritic normalization (v0 normalizes
aggressively; real Yoruba homographs will collide).

### v0.1 — multimodal extension (2026-07-03, seeds 910348, 1, 4242, 999999 — all pass)

Added: `MockPerceptionInterface` (pins the perception contract: bounded interface
emitting (concept, confidence, region) — no free text), `add_media`,
`correct_media_concept`.

```
E6 cross-modal grounding   : PASS — one ingested image found by "a dog by the
                             river" (en), "ajá" (yo), "狗" (zh); sub-threshold
                             detection (C:cat @0.22) never indexed; C:dog carries
                             its bounding box as provenance
E7 correction as graph edit: PASS — relabel dog→fox: dog-queries stop matching
                             instantly, river-queries still match (image still
                             shows a river), audit trail keeps corrected_from
```

**Two design lessons discovered by the tests (why mini-implementations beat theory):**

- **E6 first FAILED** because OOV "by" became a gating literal and vetoed the
  image match. Fix now in the design: unknown tokens split into **hard literals**
  (name-like: capitalized/digit-bearing — these gate, they're entities) vs
  **soft literals** (ordinary words missing from the lexicon — they index and
  score but never veto). Lexicon coverage gaps must degrade recall gracefully,
  never gate it.
- **E7's first assertion was wrong**: after dog→fox correction, a "dog by the
  river" query still matched the image — *via C:river*, which is correct (the
  image still shows a river). Lesson: corrections are per-concept edits, and
  tests must assert per-concept effects, not whole-record erasure.

### v0.2 — T1-mini and T2-mini (2026-07-03, 5 seeds — all pass)

The redesign claim under test: **T1 and T2 do not need to be regular LLMs** once
the input/output is concept-native. Added `TinyIntentClassifier` (naive Bayes
over concept-ID features, a few KB of counts) and `realize()` (reverse-lexicon
surface selection — derived data, not a maintained table).

```
E8 T1-mini: trained on ENGLISH templates only → 12/12 correct intent on
            French / Yoruba / Chinese / chaotic-typo-English test prompts,
            ~11µs per classification (the Modal Qwen3-1.7B T1 call measures
            in seconds warm, minutes cold). Cross-lingual generalization came
            from the concept encoding, not from the classifier — zero
            per-language code or training data.
E9 T2-mini: one concept claim voiced in 4 languages from the derived
            reverse lexicon:
              en: Tagupo project uses Zotix database
              fr: Tagupo projet utilise Zotix base de donnees
              zh: Tagupo项目使用Zotix数据库
              yo: Tagupo ise akanse lo Zotix database
            Knowledge-free by construction: the realizer can only voice
            concepts it is handed — hallucination prevention by capacity
            starvation, not prompt instruction.
```

Honesty limits: E8 is 3 intents / 12 test prompts, not 9 capabilities on live
traffic (v2 scales it with SPPE data); E9 output is structurally correct but
not fluent prose (no morphology/agreement — the v1 grammar problem; T2-LLM
polish remains for fluency until a small learned realizer replaces it).

### v0.3 — bounded inference with refusal (2026-07-03, 4 seeds — all pass)

`ConceptGraph`: typed relations with per-predicate composition rules declared as
DATA (a predicate composes across hops only if the schema says so — "causes"
chains with 0.9/hop decay, "chases" does not; production sources these
declarations from ontology metadata, e.g. Wikidata property constraints).

```
E10: 3-hop causal chain (taught pairwise, never stated end-to-end) inferred
     with joint confidence 0.59 (< any single hop — uncertainty compounds,
     never inflates) and full per-hop provenance [rec_0, rec_1, rec_2].
     Unknown target → no path → honest gap.
     "A chases B, B chases C" → "A chases C" REFUSED (1-hop still answers) —
     exactly where an LLM would produce a fluent guess.
```

### v1 — FROM-SOURCE lexicon, real Wikidata data (2026-07-03 — ALL PASS)

Built by `build_lexicon.py`: concept ranking from **Wikimedia QRank** (CC0, real
page-view popularity — not even vocabulary selection lives in our repo), labels +
aliases + P279 claims from the **Wikidata API**. 3,000 top concepts →
**26,268 lexicon entries** (en 8.3k / zh 7.9k / fr 6.5k / sw 2.1k / yo 1.5k) +
965 subclass edges, every entry carrying source/license/timestamp.

```
Rule 1 provenance      : PASS — 26,268/26,268 entries carry source+license+time
Rule 3 zero-code lang  : PASS — Swahili works with "sw" appearing NOWHERE in
                         concept_model.py (asserted against the source file)
E11 cross-lingual scale: PASS — vocabulary sampled from source at runtime,
                         40 concepts/pair: en↔fr 40/40, en↔sw 40/40,
                         en↔yo 40/40, en↔zh 37–39/40
E12 real-ontology infer: PASS — reversed-edge honesty 200/200 refused;
                         multi-hop redundancy only 1–2/300 (see finding 3)
```

**Findings from real data (each first FAILED, then got a general fix):**

1. Wikidata labels fragment naive tokenization: Yoruba combining marks broke
   tokens mid-word ('Dọ́là' → 'do'+'la'); hyphens/apostrophes made keys and
   queries drift ('Zeta-Jones', "O'Neal"); CJK interpuncts split runs
   ('唐纳德·特朗普'). Fixed by ONE invariant: `surface_key()` and the segmenter
   apply identical canonicalization — keys and queries cannot drift by
   construction. zh went 29/40 → 37/40, yo 33/40 → 40/40.
2. Ambiguous surfaces with no disambiguating context now emit top-3 candidate
   concepts (source-popularity order) instead of committing blindly —
   recall-first; retrieval intersection resolves which sense memory supports.
3. The P279 graph at top-3000 popularity is nearly tree-shaped (1–2/300 edges
   have redundant multi-hop paths) — masked-edge *recovery* needs a deeper
   ontology crawl (fetch P279 chains upward), queued for v1.1. The honesty
   half is solid: 200/200 reversed edges refused.
4. Residual zh misses are mixed-script labels (波音787) and traditional/
   simplified variant folding — data-driven variant mapping (OpenCC tables),
   v1.1.

Segmentation windows (max phrase length, max CJK key length) now derive from
the lexicon data itself — no language-specific constants remain in code.

### v1.1 — deep ontology crawl + production shadow mode (2026-07-03 — ALL PASS)

- **Upward P279 crawl** (`--crawl-depth 3`): subclass chains run through
  concepts too abstract to rank on page views; crawling them grew the graph
  965 → **4,717 edges** (+2,101 nodes). True masked-edge recovery (edge
  REMOVED, then re-derived from the remaining graph): **0.3% → 12–14%**, every
  recovery with full per-hop provenance; reversed-edge honesty ≥198/199.
  Recovery rate measures ontology density — it will keep climbing with depth
  and breadth, and is REPORTED, never asserted.
- **Shadow mode is live in the production pipeline**: `prototype/jimsai/cll_shadow.py`,
  hooked into `MultiIndexRetrievalEngine.retrieve` behind `JIMS_CONCEPT_INDEX=shadow`
  (default off; failures can never affect production retrieval). It logs, per
  query: concept/literal counts and the agreement/diff between concept-index
  retrieval and the production result. Smoke-tested cross-lingually against
  live lexicon data: French question → English memory, 尼日利亚 → English
  Nigeria record, Yoruba "Ere bọọlu alapẹrẹ" → English basketball record.
- **Live-discovered fix:** sentence-initial capitalization created spurious
  gating literals (French "Quelle …" vetoed a correct match). Rule now: only
  digits or MID-sentence capitals mark a token as name-like. Orthography is
  not name evidence.

Next: run the live generative harness with shadow logging enabled to collect
agreement stats on real traffic, then flip `JIMS_CONCEPT_INDEX=on` for the P4
judgment (0% → >60% bar, P1–P3 unregressed).

- Seed lexicon from Wikidata lexemes + OMW dumps (en/fr/yo/ar/zh), measure coverage on
  real chat logs per language.
- Wire a concept posting-list index into `MultiIndexRetrievalEngine` behind
  `JIMS_CONCEPT_INDEX=shadow` — log would-have-retrieved vs actual, no behavior change.
- Success metric: P4 multilingual property in `genuine_eval.py` goes 0% → >60% when the
  flag flips to `on`, with P1–P3 unregressed.

### Planned v2 — T1-mini feasibility

- Export SPPE pairs as (concept sequence → intent) training data; train a tiny classifier
  (logistic regression / small transformer over concept vocab); benchmark accuracy and
  latency against the Qwen3-1.7B T1 on the same routed queries.

---

## 5. Anti-hardcoding protocol (2026-07-03)

The v0 demo lexicon is hand-seeded — acceptable for a mechanism test, **forbidden
beyond v0**. The danger is real: a lexicon maintained by developers editing a
Python dict is exactly the "growing hardcoded list" this project exists to avoid.
The protocol that prevents it:

### Rule 1 — Every lexicon entry has machine-checkable provenance

The repo contains **build scripts, never lexicon data**. `build_lexicon.py`
compiles the lexicon from authoritative dumps — Wikidata lexemes, Open
Multilingual WordNet, PanLex — and every entry records `source`, `source_id`
(e.g. Wikidata QID), `license`, and `build_version`. A CI check fails the build
if any entry lacks source provenance. The only other legal path into the lexicon
is the runtime review queue: unknown form → embedding-suggested candidate →
human approval → entry stamped `source: reviewed, reviewer, date`. A developer
hand-adding an entry to make a test pass has no legal path.

### Rule 2 — Tests sample their vocabulary from the source, not from the test file

The eval never enumerates words to check. Each run: sample N random lemmas per
language *from the built lexicon itself*, generate nonce entities for unknowns,
compose facts and queries from templates, assert the properties (recall, gap,
cross-modal). If someone deletes half the lexicon, the test doesn't break — the
coverage metric (Rule 4) drops. If someone stuffs the lexicon with junk to game
coverage, recall precision drops. The metrics triangulate.

### Rule 3 — The new-language test: data only, zero code change

Groundbreaking-or-not is decided here. Adding language N+1 (e.g. Swahili,
Hausa, Igbo) must require **only** pointing the build script at that language's
OMW/PanLex data. If any Python file needs editing to support a new language,
the layer is hardcoded and the test fails by construction. (v0 already honors
this shape: `SEED_LEXICON` is data keyed by language; the encoder has no
language-specific branches except script segmentation, which is Unicode-range
driven, not language-list driven.)

### Rule 4 — Coverage is measured on external text, reported, never asserted

Weekly job: sample real text per language (Wikipedia/OSCAR), report
`% tokens → concept`, `% soft literal`, `% hard literal`. These are dashboard
numbers feeding the autonomous agent's gap targeting ("Yoruba coverage 41% —
prioritize Yoruba lexeme ingestion"), not pass/fail gates a developer can chase.

### Rule 5 — Ablation tests prove the mechanism, not the luck

- Remove the lexicon → cross-lingual recall must collapse to literal-only.
- Remove IDF weighting → ranking quality must measurably degrade.
- Remove context voting → polysemy accuracy must drop to first-sense baseline.
If an ablation does NOT hurt, the mechanism is dead weight and gets cut.

### Rule 6 — The production judge is the existing generative harness

CLL ships behind `JIMS_CONCEPT_INDEX=off|shadow|on`. The bar: P4 multilingual
in `benchmarks/genuine_eval.py` (fresh seeds, live services) goes 0% → >60%
with P1–P3 unregressed. CLL never gets its own friendly benchmark as the
acceptance gate — it must pass the harness that today proves the system fails.

## 6. What would make CLL genuinely groundbreaking (claims to prove)

Each claim is falsifiable and none is available to a frontier LLM:

1. **Zero-parallel-data cross-lingual memory:** a fact stored once is retrievable
   in any lexicon-covered language with exact provenance — no translation pairs,
   no multilingual fine-tuning. (Proof: Rule 3 test + P4.)
2. **Pixel-level provenance:** an answer grounded in an image cites the region;
   in video, the timespan. (Proof: E6-style tests with a real detector in v1.)
3. **Zero-retraining correction:** any user correction is a graph edit visible
   in the next query, with an audit trail. (Proof: E7 at production scale —
   correction-to-effect latency in milliseconds vs a fine-tune cycle.)
4. **Cost that falls with knowledge:** concept-index hits cost microseconds;
   the deterministic share of traffic grows as the lexicon/graph grow. (Proof:
   longitudinal dashboard — deterministic-path % over time.)
5. **Tiny-T1 feasibility:** intent classification over concept sequences matches
   Qwen3-1.7B accuracy at <1% of its latency. (Proof: v2 benchmark on SPPE data.)

## 7. Gap analysis: CLL + JimsAI layers vs frontier LLMs (2026-07-03)

Where the architecture still loses to a frontier model, and the testable
solution for each. Ordered by how load-bearing the gap is.

### Gap 1 — Knowledge breadth (the biggest one)

A frontier model "knows" millions of facts nobody ever wrote into a graph.
A fresh JimsAI knows nothing. The paper concedes this (§7: capability compounds
with ingestion); CLL makes the fix *cheaper* because the world's knowledge
already exists as graphs: Wikidata (~100M items), ConceptNet (commonsense
edges), WordNet — all concept-shaped, all with provenance, all license-open.
**Testable solution:** bulk-ingest a Wikidata/ConceptNet slice; property test =
mask held-out edges and ask (generated, seeded, never enumerated). Metric:
answerable-fraction growth per million edges ingested.

### Gap 2 — Inference over unstated knowledge

An LLM blends facts implicitly ("glass breaks on concrete, not carpet") —
JimsAI must traverse explicit hops. **v0.3 (E10) shows the shape of the fix:**
bounded multi-hop inference with per-hop provenance, compounding uncertainty,
and — critically — *refusal to compose non-composable relations*, exactly where
an LLM guesses fluently. What's still missing vs frontier: analogy and
cross-domain structural transfer (paper already declares this out of scope).
**Next test:** inference chains over real ingested edges (Gap 1 data), measured
against an LLM baseline on the same held-out questions — win condition is not
raw accuracy but accuracy × provenance × calibrated refusal.

### Gap 3 — Distributional/commonsense generalization

LLMs absorb "banks are usually open on weekdays" from corpus statistics without
anyone stating it. CLL only knows what's extractable. **Testable solution:**
generalize the existing world-model promotion engine — co-occurrence statistics
over the concept graph promote *candidate generalizations* ("C:dog —chases→
C:cat observed 10⁴× across sources" → rule with confidence + review gate).
This is the LLM's distributional advantage, distilled into auditable rules
instead of weights. Test: teach N instances of a generated pattern, assert a
candidate rule appears with correct support count and stays quarantined until
accepted.

### Gap 4 — Paraphrase depth beyond the lexicon

"My pooch is enormous" only works if pooch→C:dog, enormous→C:big are covered.
Embeddings do this softly today; the lexicon does it exactly or not at all.
**Testable solution:** lexicon coverage growth (Gap 1 sources include synonym
sets) + the embedding fallback already in the dual representation. Property
test: synonym-substituted recall (substitutions sampled from WordNet at
runtime, not enumerated).

### Gap 5 — Open-ended generation quality

Frontier models write beautiful long-form prose; T2-mini produces structurally
correct stubs and Qwen3-4B is mid. This gap is partially conceded by design
(paper §7) — but it splits in two:
- *Factual long-form* (reports, summaries, explanations): composition from
  verified retrieved content + learned grammar-only realizer. Testable with
  content-fidelity metrics (every sentence traceable to a claim) + fluency
  judge.
- *Creative writing*: stays generative, stays behind the CREATIVE_TEXT route,
  full stop. CLL does not compete there and should not pretend to.

### Gap 6 — Instruction-following flexibility

"Summarize this as a haiku in pirate voice" — arbitrary novel task composition
is where frontier models shine. The capability taxonomy is fixed; arbitrary
transformations are not. **Testable solution:** instruction decomposition into
concept-level operations (summarize=C:summarize + style=C:haiku…) handled by
the planner; accept LLM fallback for the long tail, logged as gaps that grow
the operation vocabulary. Honest expectation: this gap narrows slowly and
never fully closes.

### Gap 7 — Code generation quality

The sandbox verifies, MCTS retries — but candidate quality is bounded by the
generator (Qwen3-8B ≪ frontier). **Testable solution:** verification-first
amplification (pass@k with sandbox feedback loops vs raw one-shot) + retrieval
of previously *verified* code patterns from the graph as few-shot context.
Metric: verified-solve rate per compute dollar, not per attempt.

### Summary judgment

The architecture doesn't need to beat frontier models at being frontier models.
It needs Gaps 1–4 closed to be *better* on its home turf — verified, personal,
multilingual, real-time-learning, cheap — and Gaps 5–7 managed with honest
fallbacks. Gap 1 is pure engineering (ingestion at scale). Gaps 2–3 are where
the genuinely novel research lives: **auditable inference and auditable
generalization** — things no frontier model can offer at any scale.

## 8. Open questions (discussion queue)

1. **Relations in the graph:** store typed edges (C:dog —agent→ C:bite —patient→ C:man)?
   L1 already extracts relations; do concept IDs become the node vocabulary of the causal
   graph engine? (Strong candidate — unifies two subsystems.)
2. **Concept granularity:** is C:dog one node or a taxonomy (C:animal > C:canine > C:dog)?
   Hypernym edges from WordNet give abstraction-level retrieval nearly free — but
   granularity mismatches across languages are real (Yoruba kinship terms don't map 1:1
   to English ones). Proposal: concepts are language-neutral but granularity-honest —
   when a language lexicalizes finer, the finer concept exists and links to the coarser.
3. **Who owns concept ID minting?** Wikidata QIDs where they exist; JimsAI-local IDs
   (reviewed) where they don't. Collision/merge policy needed.
4. **Code-switching and mixed-script prompts:** per-token language ID rather than
   per-query? The tokenizer front-end likely needs to try all active lexicons and let
   context voting settle it.
5. **Does the concept sequence replace or accompany the raw text in memory?** Accompany —
   raw text is provenance; concepts are index. Never destroy the source (P4 of the VCO).
