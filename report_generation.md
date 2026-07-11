# JimsAI Generation — Real Prompt/Response Stress Test

_Generated 2026-07-11 by `experiments/generation/stress_test.py` — every response below is a REAL captured output from the actual generation mechanisms (no LLM anywhere). Re-run the harness to regenerate._

**7/7 cases behaved as intended** (PASS = works; EXPECTED CANNOT = correctly abstains on the subjective frontier). Nothing here is hand-written or idealised.

## What this stresses
- Faithful realization of verified content, in **three languages** (EN/FR/Pidgin)
- The **fidelity guard** under adversarial value/entity corruption
- **Gap-honesty** — abstaining rather than guessing
- **Verified code synthesis** and **iterative repair** (0 wrong)
- **Long-range narrative structure** (foreshadowing, arcs)
- The **honest boundary**: subjective surface (humor) → abstain, never fabricate

---

## Case 1. Faithful realization of a verified fact in 3 languages

**Verdict:** `PASS`

**Prompt / input**
```
content = ('Zorvenqia', 'capital_of', 'Trelvax')  (structured, verified)
```
**Real response / output**
```
[en] Zorvenqia is the capital of Trelvax
[fr] Zorvenqia est la capitale de Trelvax
[pcm] Zorvenqia na the capital of Trelvax
```
> Same mechanism, per-language constructions (data). Every entity survives → 0 fabrication.

---

## Case 2. Fidelity guard rejects a value/entity corruption (adversarial)

**Verdict:** `PASS`

**Prompt / input**
```
verified: 'the projected total is 4200 units'
         a downstream realizer tries: 'the projected total is 4300 units'
verified: 'the database we chose is PoziDB'
         a downstream realizer tries: 'the database we chose is MySQL'
```
**Real response / output**
```
emitted: 'the projected total is 4200 units'
emitted: 'the database we chose is PoziDB'
```
> The guard re-checks every anchor; a changed number (4200→4300) or swapped entity (PoziDB→MySQL) is REJECTED → the verified source is kept. Generation cannot voice a wrong value.

---

## Case 3. Gap-honesty: abstain on content it cannot faithfully realize

**Verdict:** `PASS`

**Prompt / input**
```
content = (Aurora, rivals, Meridian)  — relation has NO discovered construction
content = (Aurora, capital_of, Meridian) — construction exists
```
**Real response / output**
```
(rivals)     → None   [abstained — no guess]
(capital_of) → 'Aurora is the capital of Meridian'
```
> With no attested way to say it, the realizer returns nothing rather than inventing a surface.

---

## Case 4. Verified code synthesis from I/O examples (a function library)

**Verdict:** `PASS (0 wrong)`

**Prompt / input**
```
spec: build a program matching examples of the top function — -6→200000000, -5→33554432, -4→3359232, -3→131072, -2→512
```
**Real response / output**
```
synthesised, each function verified against its own examples:
f0 = ['sqr'] | f1 = ['sqr', 'sqr'] | f2 = ['dbl', 'sqr', 'f1'] | f3 = ['inc', 'f2', 'dbl']
```
> Bottom-up library; later functions reuse earlier verified ones. Op-grammar stands in for a real API.

---

## Case 5. Iterative repair from failing tests

**Verdict:** `PASS (8/12, 0 wrong)`

**Prompt / input**
```
12 regressed programs (each a correct 6-op program with 2 corrupting edits)
```
**Real response / output**
```
repaired 8/12 to a FULLY-passing program, 0 wrong (accepted only at full pass).
example: broken ['neg', 'dec', 'dbl', 'dbl', 'sqr', 'dec'] passed 3/11 → repaired in 78 evals → ['sqr', 'dec', 'dbl', 'dbl', 'sqr', 'dec'] (passes 11/11)
```
> Feedback-guided edits, accepted only at FULL pass (never voices a still-failing program). Greedy repair stalls in a local optimum on the rest — the honest ~60% ceiling; richer compiler/type feedback would localise better.

---

## Case 6. Long narrative structure with foreshadowing + arcs (120 beats, 8 characters)

**Verdict:** `PASS`

**Prompt / input**
```
request: a long story with consistent characters, planted-and-paid-off foreshadowing, recurring motif, and converging arcs
```
**Real response / output**
```
plan (first 10 of 121 beats): b0:introduce(C1); b1:introduce(C3); b2:introduce(C6); b3:introduce(C0); b4:introduce(C4); b5:introduce(C2); b6:introduce(C5); b7:introduce(C7); b8:act(C5); b9:plant(seed0) …
verified: 0 contradictions · 100% foreshadow payoff · 6 motif recurrences · arcs converge = True
```
> Structure only. Turning these beats into artful prose is the subjective surface — see case 7.

---

## Case 7. Subjective request (humor/beauty) → honest gap, NOT fabrication

**Verdict:** `EXPECTED CANNOT`

**Prompt / input**
```
content = (this, is_funny, joke) — a request for wit/humor: no objective verifier, no construction
```
**Real response / output**
```
→ None   [abstained — the system does not invent a 'funny' surface it cannot verify]
```
> This is the honest boundary: there is no compiler for 'funny'. JimsAI realizes VERIFIED content faithfully; artful/subjective surface is named-open, and it abstains rather than fake it.

---

## Honest bottom line

On **objective axes** — faithfulness, correctness, structure, multilingual realization, gap-honesty — the generation does exactly what it claims, verified, in more than one language. On the **subjective surface** — wit, humour, artful prose — it **abstains** rather than fabricate (Case 7). That boundary is the measured, honest state of JimsAI generation: *trustworthy on what it can verify, silent on what it cannot* — no hardcoded fixes, not English-only.
