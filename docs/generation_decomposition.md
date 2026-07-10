# Decomposing Generation — Fluent Language as Evidence + Projection

Date: 2026-07-08
Status: design + falsifiable roadmap. Companion to `docs/jimsai_llm_free_architecture.md`, `De-LLM_JimsAi.md`, `docs/concept_language_layer.md`.

**The overall goal, stated plainly:** build everything an LLM does — understanding, knowledge, reasoning, planning, and fluent generation of language, code, and structured output — but as **separate, independently-measurable modules**, driven by *data we keep* (ledgers, concept graphs, discovered patterns) rather than opaque *weights*. This document decomposes the last and largest remaining block — generation — the same aggressive way retrieval and evidence were already decomposed.

---

## 1. First principle — "generation" is not one block

An LLM does not "know how to write." Inside one network it performs, simultaneously and inseparably:

```
Input → Understand → Retrieve → Reason → Plan → Compose → Revise → Output
```

Because these live in one weight matrix they *look* like one capability. The research question is whether they are actually **separable**. The evidence so far says yes: ELE separated construction-learning from weights (into evidence ledgers), CLL separated concept-mapping (into a provenance-stamped lexicon), Projection separated current-truth (into views over an append-only ledger). Generation is the continuation.

**The reframed pipeline — generation disappears, becoming planning + realization:**

```
Prompt → Intent → Knowledge → Planner → Discourse Planner → Paragraph Planner
       → Sentence Planner → Language Realizer (in the ASKED language) → Verifier → Response
```

## 2. The one operation, at five zoom levels

The unifying insight: every layer of this system runs **the same algorithm** —

> Discover recurring structure from evidence (append-only ledger + frequency + filler-diversity), then project it onto new input, with a verifier gating the novelty.

| Zoom level | Unit | Mechanism (status) |
|---|---|---|
| Construction | sentence-internal frame | ELE ledger discovery — **[BUILT]** (M0, 14/14 recovery) |
| Concept | cross-lingual surface → ID | CLL from-source lexicon — **[BUILT]** (E1–E12, 39k keys) |
| Rule | causal/world-model generalization | promotion engine, quarantined — **[ROADMAP]** |
| **Discourse move** | paragraph/document ordering + transitions | **Discourse Engine — [ROADMAP] M9** |
| Morphology / surface | meaning → inflected words, per language | constrained realizer — **[BUILT mechanism]** (M4b) |

Generation is not a new capability. It is this operation applied at units **larger than a sentence** (discourse) and a **verifier** applied to composition (projection). That is why it decomposes.

## 3. The 12 "generation" capabilities collapse to 3 mechanisms

Sorted by which mechanism each reduces to — two of the three already have working skeletons:

- **Planning family** → search + ordering over the concept graph, producing a discourse plan: *relevance selection, organizing ideas, coherence, fiction structure (characters→goals→conflict→resolution), code architecture (requirements→architecture→components→dependencies→plan→verify→integrate)*. **The genuinely new module (Discourse Engine).**
- **Realization family** → the constrained-decode realizer scaled up, style as a lattice constraint, **in the query's language**: *wording, style, fluent language, tense/agreement/morphology/punctuation/idioms*. **[BUILT mechanism]** M4b.
- **Projection family** → the projection primitive (novel composition of known structures) **plus a verifier**: *creativity (dragon+submarine→underwater dragon), metaphor (river→time), humor (expectation→violation→resolution)*.

## 4. What already stands toward it

The Discourse Engine is not from zero:

- **Conversational state / inbound reference** — the discourse-focus stack (`ACTIVE_OBJECT`), P8 dialogue passing incl. the cold-thread honesty control. **[BUILT]**
- **Paragraph/document plan** — ordered typed blocks sketch (§2.7/§2.9 of the architecture doc). **[partial]**
- **Surface Realizer** — M4b constrained realizer, meaning→surface over a content-licensed lattice. **[BUILT mechanism]**
- **Response formats** — deterministic table/JSON/bullet emitters over the same claims. **[BUILT]** P10.

The precise gap is the *middle*: discourse ordering, transitions, and **referring-expression generation** (outbound anaphora), and the **realization language** (§6).

## 5. Where the hard problem actually is (honest correction)

Difficulty is *not* concentrated in metaphor/humor/creativity (those are rare and safely refusable). The true frontier is two duller things:

1. **Content selection under a discourse goal > ordering.** "Explain recursion *simply*" is deciding *which subgraph and at what depth* for *this audience* — not ordering nodes you've already chosen. The scoring function (relevance × audience-model × depth) is the whole problem, and it likely needs a feedback signal to be data-driven.
2. **Referring-expression generation** — *when* to say "it"/"the former"/"this approach" vs re-naming (Centering Theory). Get it wrong and fluent text becomes ambiguous or stilted. This is what separates "grammatical" from "reads like a person wrote it."

And one omission to fix explicitly: **creativity/metaphor/humor need a verifier.** Projection generates "underwater dragon" *and* a thousand incoherent combinations. The missing half is the same proposal/acceptance split used everywhere: projection *proposes*, a **structural-alignment / plausibility check accepts**. Metaphor "time is a river" works because the source's relational structure (flow, direction, irreversibility) maps onto the target; most projections fail that check. Without the verifier, the projection family produces noise.

**The assumption most likely to break:** a straight pipeline (plan fully → realize) hits the NLG **generation gap** — you sometimes cannot know what to say until you try to say it. The honest shape is a **loop**: realize → detect a gap (`GapReport`) → re-plan. The architecture already has this loop shape; bake it in from the start.

## 6. Response language — realize in the language ASKED (new requirement, 2026-07-08)

**Requirement:** the language of the *response* is the language of the *question*, independent of the language the knowledge was stored in. A fact taught in English, asked about in French, must be **answered in French**; asked in Chinese, answered in Chinese; asked in Yoruba, answered in Yoruba.

This is a clean separation the architecture already implies but does not yet honor:

- **Knowledge is language-agnostic** — it lives at concept IDs (CLL). A fact stored once is retrievable in any covered language (already **[BUILT]**, P4).
- **Realization is language-specific** — the Surface Realizer takes the *meaning* (the verified VCO claims as concept structures) and emits surface text in a **target language = the detected query language**. Different languages are different *realizers over the same meaning*, never different reasoning.

**Current gap (exposed by the production stress test):** a French/Chinese query correctly *retrieves* the English-taught fact, but the response is rendered in **English** (the CSSE voices the raw stored excerpt). Retrieval is cross-lingual; realization is not yet. This is the Surface Realizer's job:

```
verified claims (concept structures)  +  target language (query LangID)
        → Discourse plan (language-neutral order)
        → per-language Surface Realizer (reverse-lexicon surface + grammar + morphology)
        → response in the asked language
```

The mechanism exists in miniature — CLL's `realize()` / T2-mini voiced one concept claim in en/fr/zh/yo from the reverse lexicon (E9). Production realization at VCO scale is the build. Creative/long-form fluency stays gated behind the constrained realizer (M4b), never an external model.

**The judge (add as harness property P11):** teach a fact in English; query it in fr/yo/zh; assert (a) the response **contains the taught value** (already checked by P4) AND (b) the response is **in the query's language** — detectable without an LLM by script/character-set for zh (CJK range) and by function-word / concept-surface language ID for fr/yo (the same CLL LangID that routes encoding). Currently P11 would FAIL (responses are English) — which is the correct, honest state: judge first, then build.

## 7. The Discourse Engine — module spec [ROADMAP M9+]

**Job:** Intent → Plan → Paragraphs → Transitions → References → Flow. Turns an unordered set of verified claims into a coherent, ordered, connected response — language-neutrally (order and reference decisions are about *meaning*, realized into the target language afterward by §6).

Sub-modules, each independently measurable:

- **Relevance/content selector** — score concept-graph nodes for inclusion by query relevance × audience/depth signal; the scoring function is the research crux (§5.1).
- **Idea organizer** — order selected claims by discovered discourse-move patterns (definition→elaboration→example→conclusion, etc.), an ordering algorithm over the idea graph.
- **Transition generator** — insert connectives/discourse markers between moves, from discovered transition patterns.
- **Referring-expression generator** — decide pronominalize-vs-name per mention (Centering Theory), the second research crux (§5.2).
- **Coherence/consistency tracker** — topic continuity across paragraphs; no drift.

## 8. The falsifiable first experiment — M9: Discourse-Structure Discovery

Deliberately the *smallest* falsifiable slice, structured exactly like M0 (`experiments/ele/`). The crux hypothesis: **discourse structure can be discovered as accumulated evidence and projected into new responses, the way constructions (ELE) and concepts (CLL) already are.**

- **Mechanism:** mine **discourse-move sequences** from a corpus of real multi-sentence text (start with this repo's docs, then approved Q&A). A "move" is a *structurally* inferred type (define/elaborate/contrast/exemplify/conclude) — from entity continuity between sentences, connective presence, and given-vs-new information — **not** an LLM label. Promote recurring move-sequences by the ELE ledger rule (frequency + diversity). Store as an inspectable discourse-pattern ledger.
- **Projection test:** given a set of verified VCO claims (unordered), **order + connect** them using the discovered patterns.
- **The judge (no LLM):** coherence is computable — **Centering-Theory transition scoring** (fraction of sentence-to-sentence transitions that are CONTINUE/RETAIN vs disruptive SHIFT) plus entity-continuity. Assert discovered-pattern ordering **beats baselines** (random order; original retrieval order) on held-out claim sets, seeded, across ≥4 seeds.
- **Kill criterion:** if discovered discourse patterns don't beat baselines on computable coherence, discourse structure is **not** learnable-as-evidence at document scale; re-scope to hand-specified discourse schemas (the honest fallback, as M3 re-scoped the parser). Recorded in writing.

If M9 passes, discourse joins constructions and concepts as *discovered evidence, not weights*, and every downstream module (style constraints, referring-expression generator, projection+verifier for metaphor, per-language realization) becomes an independently-measurable property with its own harness judge.

## 9. Roadmap additions (each with a judge)

- **P11 (harness) — response language matches query language.** Judge defined (§6). Build: per-language Surface Realizer over VCO claims.
- **M9 — Discourse-Structure Discovery** (§8): the miner, the Centering-Theory coherence judge, the seeded corpus, the projection test. `experiments/discourse/`.
- **M10 — Referring-expression generation** (Centering Theory): pronominalize-vs-name, judged by ambiguity-free reference resolution on generated text.
- **M11 — Projection + verifier for metaphor/creativity**: structural-alignment acceptance over projected compositions; judged by alignment-score separation of coherent vs incoherent projections.
- **Style-as-constraint** on the M4b realizer (formal/casual/etc. as lattice + selection constraints over the same meaning), judged by style-classifier accuracy × content-fidelity.
- **Content selection under discourse goal** (§5.1) — the depth/audience scorer, judged by answerable-subgraph coverage vs a target depth.

## 10. Why this stays data-driven, not weight-driven

At every level the *learned object* is an **inspectable structure** — construction ledger, concept graph, discourse-pattern ledger, style constraint set, realization rules — derived and refined from evidence, correctable in milliseconds, deletable, auditable. The "writing ability" an LLM buries in billions of opaque parameters becomes explicit representations a person can read, cite, and fix. That is the whole bet, extended from memory to generation:

> Don't lock writing ability into weights. Observe discourse, style, transitions in a corpus; store evidence; learn discourse structures; project into new responses — realized in the language asked, verified before voiced.

## 11. Media (image / audio / video / 3D) — the same spine, honestly scoped (2026-07-09)

The proposal: don't bolt a diffusion model onto the side. Extend the ONE spine — evidence → reusable structure → projection → **verify** → realize — into every modality, so the renderer is a **Media Realization Engine** governed by a **Physical Reality Engine** whose job is not to draw but to *ensure reality* ("is physically consistent," not "looks right"). The philosophy is right and worth pursuing. What matters, per this project's discipline, is separating what is **already grounded** from what is a **research bet**, and never letting the second wear the clothes of the first.

**What is already grounded (measured proof points, not theory):**

- **The verify-before-realize spine is modality-general.** `experiments/media/run_m12_reality.py` (M12) built a miniature Physical Reality Engine that DISCOVERS physical invariants from evidence (shadow direction/length laws, support, occlusion — and rejects a spurious decoy law), then on held-out scenes accepts every physically-consistent composition, refuses every impossibility with the law NAMED, and accepts **0 impossibilities** across 4 seeds. This is the same refusal contract as M8 (code: never voice a wrong program) and the Independence Policy (text: CLARIFY/REFUSE/GROW). *The guarantee that protects text and code protects media.*
- **"One concept, many realizations" is real for the realizations we have.** The CLL pivot is modality-independent by construction (a concept ID doesn't know it's text). Cross-lingual realization already proves the pivot: one city concept (C:Q515) realizes as `city`/`cité`/`城市`/`Ìlú` (measured, P4/P11). M12 extends the *same* verified structure to a second modality — deterministic SVG **and** a sentence from one scene graph. Two realizations, one meaning, no model.
- **Projection composes without copying.** M12 accepts novel scenes assembled from independently-known parameters it never trained on — the "snowy castle at dawn with fog from parts never seen together" claim, in the tractable slice.

**What is a research bet (named, not hidden):**

- **Perceptual construction discovery ("ELE for vision/audio").** M12's hypothesis space is hand-specified (as M8's operation grammar is). Discovering visual/acoustic constructions (lighting, pose, material, prosody) from real image/audio corpora — rather than from a supplied relation library — is unbuilt and is the load-bearing unknown. It is the vision's biggest claim and its least proven.
- **Frontier perceptual quality.** M12 renders correct *structure*, not photoreal pixels. Whether evidence-composed media can match diffusion-model fidelity is genuinely open — the user's own framing. The defensible near-term win is not "prettier" but **auditable + physically-guaranteed + correctable**: media that carries provenance and cannot violate a discovered law, which monolithic samplers structurally cannot offer.
- **Temporal/physical richness** (video continuity, contact dynamics, momentum) multiplies the state to verify; M12 covers a static, low-DOF slice.

**The falsifiable next experiment (M13):** point a discoverer at a corpus of *rendered* scenes (labels withheld) and test whether it recovers the M12 laws from perception alone — no supplied relation library. Pass = it re-derives the invariants and keeps the 0-impossibility guarantee; kill = perceptual construction discovery needs supervision the "parser-free/model-free" claim can't provide (the same honest fork M3 forced for language). Until M13 runs, the multimodal claim is: *spine proven modality-general (M8 code, M12 media); perceptual discovery unproven.*
