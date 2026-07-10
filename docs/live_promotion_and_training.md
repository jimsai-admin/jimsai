# Live-Promotion Decisions & De-LLM Training-Agent Structure

Last updated 2026-07-10. Companion to `docs/ele_cll_grounding_review.md` (the measured ledger). Purpose: decide, grounded on a live-wiring audit and the messy-gauntlet numbers, **which proven mechanisms belong in the live answer path**, and formulate the **de-LLM training-agent structure** that enriches the base model and gates those promotions.

Rule for promotion: a mechanism goes live only when it **passes on MESSY input** (not clean templates) and **does not regress gap-honesty** (the cardinal no-fabrication principle). "Proven at toy/clean scale" ≠ "live-ready."

---

## 1. Style-as-constraint & content-selection — honest scoping

- **Content-selection / verbosity under a discourse goal is promotable now** — it is a pure VCO *projection*: choose *which* verified claims to voice for a target depth/length. Terse = the answer/values only; detailed = the full chain. **Zero fabrication by construction** (selection can only drop claims, never add). Already partly present (math terse-on-format, discourse ordering). Language-neutral (fewer vs more verified claims — no vocabulary).
- **Register-style (formal / casual / technical) is roadmap, NOT hardcodable.** Changing register is a *vocabulary/construction* choice that differs per language; doing it with a hardcoded English style-word list is exactly the anti-pattern. It must come from **discovered register-marked constructions** (ELE, per language) — the same "new language = data, not code" rule. Judge (when built): style-classifier accuracy × content-fidelity (meaning provably unchanged).
- **Decision:** ship goal-driven content-selection as a VCO projection; hold register-style until register constructions are discovered.

---

## 2. Promotion decisions (grounded on the live-wiring audit + messy numbers)

### Already live & validated on messy input — CONFIRM (keep, default-on)

| Mechanism | Where | Messy evidence | Decision |
|---|---|---|---|
| Case-independent names + common-vocab | `cll_shadow.py` | recall 0→4/5 (en) / 3/5 (pcm), **gap-honesty 5/5** | **Keep, `JIMS_OOV_NAMES` default on** |
| Symbolic math (implicit-mult, solve-target, notation steps) | `math_extract` / `execution_runtime` / `csse` | `a=F/m`, `t=(v-u)/a`, French `y=5`, detailed | **Keep** |
| Discourse ordering (M9) | `csse` → `discourse_composer` | language-universal, meaning-preserving, no English injected | **Keep** |
| Language-neutral chrome (math notation, `_localize`, decorative-English-only) | `csse` | French no longer leaks English hedge; math = notation | **Keep** |
| P8 fixes (world_knowledge cap, name-evidence focus, local_extraction skip) | `capability_router` / `pipeline` / `retrieval` | P8 families recall 2/2; no query-echo | **Keep** |

### Proven mechanism, NOT live — GATED (named blocker)

| Mechanism | Status | Blocker / promotion gate |
|---|---|---|
| **Traversal reasoner** (M14 `find_path` + `reasoning_traversal`) | SOUND: 100% chain recovery, **0 fabricated links** | **SAFETY GATE CLEARED (2026-07-10).** `grammar_relations` precision was ~45% on messy input; a language-universal fix (count sourced COMMON words in the predicate — ≥2 ⇒ abstain, catching passive/negation with no hardcoded list) lifted it to **100% precision, 0 direction-errors, 0 negation-false-positives** (`run_m14b_messy.py`). End-to-end, the reasoner GAPS on a passive chain rather than voicing a wrong one. So it is now **SAFE to promote** (never confidently wrong) — with the honest caveat that RECALL is low (**37%**: only clean active-binary relations extract; passive/negated/complex abstain). Full recall needs ELE construction discovery (positive/negated/passive per language) — the remaining work, but no longer the *safety* blocker. **Recommendation: promote as a precision-first, gaps-when-uncertain reasoner; recall grows with ELE discovery via the training loop.** |
| **M11 projection + verifier** | PASS: analogy computable, 0 false-accepts | Proven *substrate*; there is no live creative/analogy-generation capability to host it yet. **Gate: wire when a creative-generation route is added.** |
| **M8 code synthesis / M12 physical reality** | PASS at toy scale, never-voice-wrong guarantee | Frontier scale (multi-module code, real perception) is roadmap. Sandbox+graph already production; the *synthesis* mechanism promotes per request-class as the grammar/search budget grows. |

### Do NOT promote

| Mechanism | Why |
|---|---|
| **T1-mini (M2)** | Honest negative — concept-native transfers cross-lingually but loses same-language (81% vs 98%), hybrid has Latin-script interference. The `multilingual-e5` intent classifier is already CPU-local (not an LLM) and uniform. T1-mini stays a **fallback / cross-lingual booster**, not a replacement. |

---

## 3. De-LLM training-agent structure (how to make it better)

`autonomous_training_agent.py` has the right *shape* (continuous measure→ingest→re-measure) and the right *scoping* (`workspaces.py`: shared **base model** + per-workspace **personalization adapter**), but it is **not de-LLM** (a `synthetic_generation` source is `groq_generated`) and its ingestion is a **scaffold** — not wired to the real base artifacts. The rebuild is the exact pattern proven by hand this session.

### The loop (no LLM anywhere)

1. **MEASURE** — run `benchmarks/genuine_eval.py` **and the MESSY gauntlet** (`experiments/reasoning/messy_gauntlet.py`), producing a coverage vector per `{language, domain, capability, property}`. A *gap* is any property/language below threshold **on messy input** (the ideal-world harness alone hides the real gaps — proven).
2. **TARGET** — map each gap to a SOURCED, de-LLM ingestion action:
   - lexicon/language gap → `broaden_lexicon.py` (Wikidata concepts) + `fetch_common_words.py` (frequency lists) for that language.
   - construction/relation gap → **ELE construction discovery on real corpora** (this is what unblocks the gated traversal reasoner).
   - domain gap → domain corpus slice (Wikipedia) → concepts + constructions.
   - *(personalization is NOT the agent's job — it is the runtime learning loop.)*
3. **INGEST** — provenance-stamped, from public sources, no LLM. Enriches the **base model** only.
4. **RE-MEASURE + ROLL-BACK** — re-run the gauntlet; keep the ingestion **iff** it improves the target metric **and regresses nothing** (especially gap-honesty). Roll back otherwise. This is the guardrail the common-vocab work demonstrated (recall up, gap-honesty preserved — kept; noise-only version regressed gap-honesty — not shipped).
5. **PROMOTE (the new job)** — the agent also **gates mechanism promotion**: a gated mechanism (§2) auto-promotes to live when its messy-gauntlet metric clears the bar (e.g., traversal reasoner when relation-extraction precision ≥85%). Promotion becomes a *measured event*, not a manual guess.

**Drop the Groq source entirely.** SPPE pairs for the tiny classifiers come from **real resolved interactions** (the runtime feedback loop), never LLM-generated synthetic data.

### Base vs per-user (both already in code)

- **BASE model — everyone.** Shared lexicon (concepts + common words), ELE constructions, world-model rules, tiny classifiers. Trained by **JimsAI engineers + the de-LLM agent** from public sources, coverage-driven. This is what §2's promotions and the ingestion enrich.
- **PER-USER / WORKSPACE / AGENT model.** Facts, corrections, discourse focus, personalization adapter (`workspaces.py`). Grown by the **runtime learning loop** (facts/corrections at ~0.02 ms), isolated per workspace (scoping verified 5/5 on messy input). Served to chatbox / agent / API / frontend.

### Judge

Gap-closure on the **messy** gauntlet; **gap-honesty never regresses**; provenance on every ingested item; every promotion tied to a measured threshold. The training agent is the organ that turns "the world as it comes" into rising base-model coverage — de-LLM, auditable, roll-back-safe.
