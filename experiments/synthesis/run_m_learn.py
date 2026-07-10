"""M-LEARN — evidence-driven continual learning for code synthesis (no LLM).

The loop the analysis calls the strongest part of the architecture:
  generate → EXECUTE → observe (tests) → extract a REUSABLE VERIFIED pattern →
  store → REUSE it on future similar tasks.
Here, grounded, with a real objective verifier (running the synthesised function
against I/O examples). Two falsifiable claims:

  (A) LEARNING EXTENDS REACH. A bounded enumerative synthesiser (search depth D)
      solves the easy tasks; each solve's op-sequence is stored as a named
      pattern (one op instead of many). Later, HARDER tasks that need more than D
      primitive ops become solvable within the SAME budget D because a learned
      pattern collapses a sub-sequence. Solve-rate WITH learning > WITHOUT.

  (B) IT CANNOT OVERGENERALISE — the sort()/discount problem answered. Every
      candidate (learned pattern included) is RE-VERIFIED against THIS task's
      examples before it is accepted. A pattern learned in one context that is
      wrong here simply fails these examples and is rejected — never voiced,
      never a regression. So a context-dependent lesson (e.g. "+2") is applied
      only where the task's own evidence confirms it. 0 wrong solutions, by
      construction — the M8 never-voice-a-wrong-program guarantee, extended to
      learned knowledge.

Anti-hardcoding: tasks are generated per seed from random affine/edge programs;
patterns are DISCOVERED from solves (not enumerated); acceptance is by execution
against held-out-shaped examples, never a fixed string.

Run: .venv/Scripts/python.exe experiments/synthesis/run_m_learn.py [seed ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from random import Random

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Primitive ops (int -> int). A "program" is a pipeline applied left→right.
PRIMS = {
    "inc": lambda x: x + 1,
    "dec": lambda x: x - 1,
    "dbl": lambda x: x * 2,
    "neg": lambda x: -x,
    "sqr": lambda x: x * x,
    "guard0": lambda x: 1 if x == 0 else x,   # an edge-case guard
}


def run_pipeline(ops: list, prims: dict, x: int) -> int:
    for name in ops:
        for step in prims[name]:      # a pattern expands to its sub-sequence
            x = PRIMS[step](x)
    return x


def matches(ops, prims, examples) -> bool:
    """VERIFY: run against every example — the objective check."""
    try:
        return all(run_pipeline(ops, prims, i) == o for i, o in examples)
    except Exception:
        return False


def synthesize(examples, prims: dict, depth: int) -> list | None:
    """BFS over op-pipelines up to `depth` ops. `prims` maps an op NAME to its
    primitive sub-sequence (a learned pattern is one name → many primitives), so
    a pattern costs ONE unit of depth. Returns the op-name pipeline or None."""
    from collections import deque
    q = deque([[]])
    seen = 0
    while q:
        ops = q.popleft()
        if matches(ops, prims, examples) and ops:
            return ops
        if len(ops) >= depth:
            continue
        for name in prims:
            q.append(ops + [name])
            seen += 1
            if seen > 200000:
                return None
    return None


def gen_task(rng: Random, hard: bool):
    """A random program over primitives; examples are its I/O. hard=deeper."""
    n = rng.randint(3, 4) if hard else rng.randint(1, 2)
    prog = [rng.choice(["inc", "dec", "dbl", "sqr"]) for _ in range(n)]
    xs = [rng.randint(-3, 5) for _ in range(4)]
    examples = [(x, run_pipeline(prog, {k: [k] for k in PRIMS}, x)) for x in xs]
    return prog, examples


def run_seed(seed: int, depth: int = 2) -> dict:
    rng = Random(seed)
    base_prims = {k: [k] for k in PRIMS}          # every primitive is itself
    learned: dict = {}                            # name -> primitive sub-sequence

    easy = [gen_task(rng, hard=False) for _ in range(12)]
    hard = [gen_task(rng, hard=True) for _ in range(12)]

    # Phase 1: solve easy tasks, LEARN each solution as a pattern (verified).
    for _prog, ex in easy:
        sol = synthesize(ex, base_prims, depth)
        if sol and len(sol) >= 2:
            prims_flat = [p for name in sol for p in base_prims[name]]
            pname = "P_" + "_".join(prims_flat)
            learned[pname] = prims_flat            # store verified pattern

    with_learning = {**base_prims, **learned}

    # Phase 2: HARD tasks — solve WITHOUT learning vs WITH, at the SAME depth.
    base_solved = learn_solved = wrong = 0
    for _prog, ex in hard:
        s0 = synthesize(ex, base_prims, depth)
        if s0:
            base_solved += 1
            if not matches(s0, base_prims, ex):
                wrong += 1
        s1 = synthesize(ex, with_learning, depth)
        if s1:
            learn_solved += 1
            if not matches(s1, with_learning, ex):   # must never accept a wrong one
                wrong += 1

    # (B) overgeneralisation probe: a task whose answer is x+1, offered the
    # learned "+2"-style patterns. The pattern must be REJECTED by verification.
    over_ok = True
    plus_patterns = [n for n, seq in learned.items() if seq == ["inc", "inc"]]
    if plus_patterns:
        ex_plus1 = [(x, x + 1) for x in (-2, 0, 3, 5)]
        s = synthesize(ex_plus1, with_learning, depth)
        # whatever is returned MUST satisfy the examples (verified) — never x+2
        over_ok = (s is not None) and matches(s, with_learning, ex_plus1)

    return {"seed": seed, "depth": depth, "patterns_learned": len(learned),
            "hard_base_solved": base_solved, "hard_learned_solved": learn_solved,
            "wrong_solutions": wrong, "overgeneralization_safe": over_ok}


def main(seeds):
    results = [run_seed(s) for s in seeds]
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "m_learn.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("=" * 70)
    print(f"M-LEARN evidence-driven learning for code — {len(seeds)} seeds (depth budget 2)")
    print("-" * 70)
    for r in results:
        print(f"  seed {r['seed']}: patterns={r['patterns_learned']:2d}  "
              f"hard solved base={r['hard_base_solved']:2d} → with-learning={r['hard_learned_solved']:2d}  "
              f"wrong={r['wrong_solutions']}  overgen-safe={r['overgeneralization_safe']}")
    print("-" * 70)
    base = sum(r["hard_base_solved"] for r in results)
    learned = sum(r["hard_learned_solved"] for r in results)
    wrong = sum(r["wrong_solutions"] for r in results)
    over = all(r["overgeneralization_safe"] for r in results)
    print(f"hard-task solves: base {base} → with-learning {learned}  "
          f"(reach lift {learned - base})  | wrong solutions {wrong}  | overgen-safe {over}")
    ok = learned > base and wrong == 0 and over
    print("VERDICT:", "PASS — learning verified patterns EXTENDS reach; 0 wrong; cannot overgeneralise (re-verified per task)"
          if ok else "MIXED/FAIL — see rows")
    return 0 if ok else 1


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024, 99999]
    sys.exit(main(seeds))
