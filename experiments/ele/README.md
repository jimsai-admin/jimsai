# ELE + Projection experiments (M0 / M0b)

Reproduces, in-repo and seeded, the experiment rows of
`ELE_CLL_Projection_Architecture_Spec.md` §2 — the evidence that previously
existed only in an uncommitted session. See
`docs/ele_cll_grounding_review.md` for the audit, milestone criteria, and the
recorded results of the first run.

## Run

```
.venv/Scripts/python.exe experiments/ele/run_all.py            # seeds 702945 1 4242 999999
.venv/Scripts/python.exe experiments/ele/run_all.py <seed>...  # any fresh seeds
.venv/Scripts/python.exe experiments/ele/bench_projection.py   # M0b scaling benchmark
```

Exit code is nonzero if any asserted property fails. Results are written to
`results/run_results.json` and `results/projection_bench.json`.

## What each check falsifies

| Check | Spec row | Property |
|---|---|---|
| R1 | 1 | constructions recovered from raw n-grams (no parser) |
| R2 | 2 | word categories from pure distribution — purity REPORTED, leakage expected |
| R3 | 3 | equal-budget ledger vs neural LM perplexity — REPORTED, never asserted |
| R4 | 4 | ledger ingestion is orders of magnitude cheaper than retraining |
| R5 | 5 | corrections retain both truths; "current truth" is a projection parameter |
| R6 | 6 | template renderer: exact + zero hallucination on held-out compositional combos |
| R7 | 7 | tiny neural renderer emits unlicensed tokens on the same combos — REPORTED |
| R8 | 8 | never-trained predicate renders via a known structural shape (verb is data) |
| R9 | 9 | unseen shape raises typed GapReport; naive nearest-shape silently drops args |
| R10 | 10 | known core + independently learned adjunct composes to close the gap |
| R11 | 11 | spread-only acceptance is provably insufficient (object slot passes spread) |
| R12 | 12 | concentration-amplifying spread_weighted ranks a verb-tied distractor #1 |
| R13 | 13 | 0.90 threshold misclassifies the 0.92-collocated adjunct; calibrated one doesn't |
| R13b | §3.1.3 | sparse evidence rejected conservatively; flips with more data, no code change |
| R14 | 14 | base-glued suffix keys score exactly 0.0 P/R; collapsed key generalizes |
| R15 | 15 | vacuous corpora (single fixed filler) are rejected, not silently passed |
| P0 | §3.1.1 | ledger-derived metrics and decisions invariant under insertion order |
| BRG | §3.2 | ELE→CLL contract: ambiguity sets recorded whole; refusal + audit preserved |

## Anti-hardcoding

- No word lists: all vocabulary is nonce, generated per seed at runtime.
- `OBLIG_THRESHOLD` is derived from the frozen calibration seed recorded in
  `classify.py` (`FROZEN_CALIBRATION_SEED`), then locked for all test seeds.
  Retuning it against a failing test is a protocol violation (E-Rule 2).
- Held-out compositional pairs are reserved *before* generation, so training
  can never see them.
- Rows 3 and 7 are REPORT, not PASS: equal-budget comparisons are evidence
  either way, and hiding a neural win would violate the spec's own §4.1.
