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
| **Round-trip fidelity guard on realization (M-GEN, promoted 2026-07-11)** | `construction_realizer.py` → wired in `csse._realize_language` | 12/12 live checks: a realization that drops/corrupts a verified entity or number is rejected → falls back to the faithful source; faithful transforms pass; English no-op | **Keep, default-on** — generation can never voice a surface that changes a verified value; language-independent, no LLM |

### Proven mechanism, NOT live — GATED (named blocker)

| Mechanism | Status | Blocker / promotion gate |
|---|---|---|
| **Traversal reasoner** (M14 `find_path` + `reasoning_traversal`) | SOUND: 100% chain recovery, **0 fabricated links** | **SAFETY GATE CLEARED (2026-07-10).** `grammar_relations` precision was ~45% on messy input; a language-universal fix (count sourced COMMON words in the predicate — ≥2 ⇒ abstain, catching passive/negation with no hardcoded list) lifted it to **100% precision, 0 direction-errors, 0 negation-false-positives** (`run_m14b_messy.py`). End-to-end, the reasoner GAPS on a passive chain rather than voicing a wrong one. So it is now **SAFE to promote** (never confidently wrong) — with the honest caveat that RECALL is low (**37%**: only clean active-binary relations extract; passive/negated/complex abstain). Full recall needs ELE construction discovery (positive/negated/passive per language) — the remaining work, but no longer the *safety* blocker. **Recommendation: promote as a precision-first, gaps-when-uncertain reasoner; recall grows with ELE discovery via the training loop.** **ELE-on-real-corpora now demonstrated (2026-07-10):** `run_relation_real_corpus.py` — self-supervised distant-supervision discovery on REAL Wikipedia prose, held out by entity, lifts relation-extraction recall from the abstain-only **0% → 71% (en) / 43% (fr) at 100% precision**, with the trigger LEARNED per language (`capital`/`capitale`, no hardcoded marker). So the recall path is grounded on real text, not just templates; the reasoner's never-voice-a-wrong-edge property is preserved while recall becomes useful. Remaining: more relation types, open-world entities, cross-sentence pairs. |
| **M11 projection + verifier** | PASS: analogy computable, 0 false-accepts | Proven *substrate*; there is no live creative/analogy-generation capability to host it yet. **Gate: wire when a creative-generation route is added.** |
| **M8 code synthesis / M12 physical reality** | PASS at toy scale, never-voice-wrong guarantee | Frontier scale (multi-module code, real perception) is roadmap. Sandbox+graph already production; the *synthesis* mechanism promotes per request-class as the grammar/search budget grows. |

### Do NOT promote

| Mechanism | Why |
|---|---|
| **T1-mini (M2)** | Honest negative — concept-native transfers cross-lingually but loses same-language (81% vs 98%), hybrid has Latin-script interference. The `multilingual-e5` intent classifier is already CPU-local (not an LLM) and uniform. T1-mini stays a **fallback / cross-lingual booster**, not a replacement. |

---

## 3. De-LLM training-agent structure (how to make it better)

`autonomous_training_agent.py` has the right *shape* (continuous measure→ingest→re-measure) and the right *scoping* (`workspaces.py`: shared **base model** + per-workspace **personalization adapter**). As of 2026-07-10 its **core loop is wired to real measurements** (below); what remains scaffold is only the neural-weight (SPPE/Kaggle) path, now honestly labelled as such.

### WIRED — 2026-07-10 (the fabrication is gone)

The agent previously **fabricated** its metrics: `_evaluate_system_state` returned invented scores (0.88 stability, per-language 0.45/0.52, domain 0.62…), `_ingest_source` said *"Simulate ingestion… placeholder"* with a fake 95% success rate, and `_measure_improvement` returned hardcoded deltas (+0.02/+0.03/+0.04). That is exactly the make-the-numbers-look-good anti-pattern the directives forbid. It is now replaced by the **validated de-LLM loop**, extracted from `experiments/training/run_train_loop.py` (VERDICT PASS) into a reusable production module `prototype/jimsai/de_llm_training_loop.py`:

- **MEASURE is real.** `_evaluate_system_state` calls `measure_language()` — the CLL's actual messy-extraction precision/recall on nonce, un-memorisable probes (en/fr/pcm), offline, milliseconds, no backend. Metrics with no offline harness yet (intent-stability, retrieval-accuracy, provider-dependency) are returned as **`None` = "unmeasured"**, and gap detection **skips** them — the agent reports what it knows and is honest about what it does not, never a placeholder float.
- **INGEST is real.** For `common_vocabulary`, `_ingest_source` runs `train_all()`: measure the gap-state → ingest sourced common vocabulary → re-measure → **KEEP iff precision improved AND recall did not regress**, else **ROLL BACK**. Sources not yet wired offline return an honest **zero** with `status="not_implemented_offline"` — never a fabricated success rate.
- **IMPROVEMENT is real.** `_measure_improvement` reports the measured per-language before→after deltas from the loop that actually ran this cycle, plus `recall_never_regressed` (the gap-honesty guard).
- **Verified end-to-end (one real cycle):** `en` precision 50%→**100%**, `fr` 50%→**86%** (both KEPT, recall held at 100%), `pcm` already **86%** via the general OOV-name mechanism (no per-language source needed — the anti-hardcoding thesis in action); 0 gaps after ingest; SPPE pairs 0 and training-not-triggered (**honest** — offline can't produce weight-training pairs).
- **Still scaffold, now labelled:** the SPPE→Kaggle→human-gate→weight-deploy path (steps 7–10) requires ≥1000 **real** SPPE pairs (from the runtime feedback loop, not producible offline) and a real SPPE quality scorer; its `avg_quality`/quality-band numbers are marked `PLACEHOLDER` in-code and are inert at 0 input.

The section below is the target loop; the WIRED list above is how much of it is now genuinely running.

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

**Groq source dropped (done).** `data_sources` no longer contains `synthetic_generation`; SPPE pairs for the tiny classifiers come from **real resolved interactions** (the runtime feedback loop), never LLM-generated synthetic data.

### Base vs per-user (both already in code)

- **BASE model — everyone.** Shared lexicon (concepts + common words), ELE constructions, world-model rules, tiny classifiers. Trained by **JimsAI engineers + the de-LLM agent** from public sources, coverage-driven. This is what §2's promotions and the ingestion enrich.
- **PER-USER / WORKSPACE / AGENT model.** Facts, corrections, discourse focus, personalization adapter (`workspaces.py`). Grown by the **runtime learning loop** (facts/corrections at ~0.02 ms), isolated per workspace (scoping verified 5/5 on messy input). Served to chatbox / agent / API / frontend.

### Judge

Gap-closure on the **messy** gauntlet; **gap-honesty never regresses**; provenance on every ingested item; every promotion tied to a measured threshold. The training agent is the organ that turns "the world as it comes" into rising base-model coverage — de-LLM, auditable, roll-back-safe.
