"""M-PLAN — planning by decomposition scales verified synthesis (no LLM).

The move needed for large code / massive generation: decompose a big request
into INDEPENDENTLY VERIFIABLE sub-tasks, solve each with the verified loop
(M8/M-LEARN), compose. Here, grounded: a task computes several outputs from an
input (a function returning a tuple — each field is a natural sub-goal). We
compare, at the SAME search budget:

  monolithic — search the JOINT space of all fields' programs at once
               (combinatorial: |ops|^D per field, product over fields);
  decomposed — solve each output field independently (|ops|^D each), compose.

Claims:
  (A) decomposition SOLVES tasks monolithic cannot at a fixed node budget
      (the search space is a product for monolithic, a sum for decomposed);
  (B) 0 wrong — every field program is executed against its examples, and the
      composed function against the whole-tuple examples, before acceptance.
      A wrong sub-solution fails verification and is rejected — the never-voice-
      a-wrong-program guarantee, preserved under composition.

Honest boundary: this shows that GIVEN a decomposition, verified synthesis
scales. Automatically DISCOVERING good decompositions for arbitrary prose specs
is the harder open problem (the planning analogue of ELE construction discovery)
— named, not faked. Multi-output structure is one real, common decomposition.

Run: .venv/Scripts/python.exe experiments/synthesis/run_m_plan.py [seed ...]
"""

from __future__ import annotations

import json
import sys
from collections import deque
from itertools import product
from pathlib import Path
from random import Random

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PRIMS = {"inc": lambda x: x + 1, "dec": lambda x: x - 1, "dbl": lambda x: x * 2,
         "neg": lambda x: -x, "sqr": lambda x: x * x, "half": lambda x: x // 2}


def run_prog(prog, x):
    for op in prog:
        x = PRIMS[op](x)
    return x


def enum_progs(depth):
    """All op-pipelines up to `depth` (incl. empty = identity)."""
    progs = [[]]
    for d in range(1, depth + 1):
        for combo in product(PRIMS, repeat=d):
            progs.append(list(combo))
    return progs


def field_ok(prog, examples_field):
    try:
        return all(run_prog(prog, x) == o for x, o in examples_field)
    except Exception:
        return False


def solve_field(examples_field, depth, budget):
    """BFS a single field; returns (prog|None, nodes_used)."""
    q = deque([[]]); nodes = 0
    while q:
        prog = q.popleft(); nodes += 1
        if nodes > budget:
            return None, nodes
        if field_ok(prog, examples_field):
            return prog, nodes
        if len(prog) < depth:
            for op in PRIMS:
                q.append(prog + [op])
    return None, nodes


def solve_monolithic(examples, k, depth, budget):
    """Search the JOINT space: a candidate is a tuple of k programs; verify the
    whole tuple at once. Combinatorial — the product of the per-field spaces."""
    per_field = enum_progs(depth)
    nodes = 0
    for combo in product(per_field, repeat=k):
        nodes += 1
        if nodes > budget:
            return None, nodes
        if all(tuple(run_prog(combo[j], x) for j in range(k)) == outs
               for x, outs in examples):
            return combo, nodes
    return None, nodes


def solve_decomposed(examples, k, depth, budget):
    """Solve each output field independently (sum of per-field spaces), then
    verify the COMPOSITION against the whole-tuple examples."""
    per_field_budget = budget // k
    progs, total_nodes = [], 0
    for j in range(k):
        ex_j = [(x, outs[j]) for x, outs in examples]
        p, nodes = solve_field(ex_j, depth, per_field_budget)
        total_nodes += nodes
        if p is None:
            return None, total_nodes
        progs.append(p)
    # verify the composition (must hold for the whole tuple)
    if all(tuple(run_prog(progs[j], x) for j in range(k)) == outs for x, outs in examples):
        return progs, total_nodes
    return None, total_nodes


def gen_task(rng, k, depth):
    field_progs = [[rng.choice(list(PRIMS)) for _ in range(rng.randint(1, depth))] for _ in range(k)]
    xs = [rng.randint(-2, 4) for _ in range(4)]
    examples = [(x, tuple(run_prog(fp, x) for fp in field_progs)) for x in xs]
    return examples


def run_seed(seed, k=3, depth=2, budget=6000, n=15):
    rng = Random(seed)
    mono_solved = deco_solved = wrong = 0
    for _ in range(n):
        ex = gen_task(rng, k, depth)
        m, _ = solve_monolithic(ex, k, depth, budget)
        if m is not None:
            mono_solved += 1
            if not all(tuple(run_prog(m[j], x) for j in range(k)) == o for x, o in ex):
                wrong += 1
        d, _ = solve_decomposed(ex, k, depth, budget)
        if d is not None:
            deco_solved += 1
            if not all(tuple(run_prog(d[j], x) for j in range(k)) == o for x, o in ex):
                wrong += 1
    return {"seed": seed, "k_outputs": k, "depth": depth, "budget": budget,
            "monolithic_solved": mono_solved, "decomposed_solved": deco_solved,
            "of": n, "wrong": wrong}


def main(seeds):
    results = [run_seed(s) for s in seeds]
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "m_plan.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("=" * 70)
    print(f"M-PLAN planning-by-decomposition — {len(seeds)} seeds "
          f"(k=3 outputs, depth 2, budget 6000 nodes)")
    print("-" * 70)
    for r in results:
        print(f"  seed {r['seed']}: monolithic {r['monolithic_solved']:2d}/{r['of']} "
              f"→ decomposed {r['decomposed_solved']:2d}/{r['of']}   wrong={r['wrong']}")
    print("-" * 70)
    mono = sum(r["monolithic_solved"] for r in results)
    deco = sum(r["decomposed_solved"] for r in results)
    tot = sum(r["of"] for r in results)
    wrong = sum(r["wrong"] for r in results)
    print(f"solved: monolithic {mono}/{tot} → decomposed {deco}/{tot}  "
          f"(reach lift {deco - mono})  | wrong {wrong}")
    ok = deco > mono and wrong == 0
    print("VERDICT:", "PASS — decomposition scales verified synthesis beyond monolithic search; 0 wrong under composition"
          if ok else "MIXED/FAIL — see rows")
    return 0 if ok else 1


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024, 99999]
    sys.exit(main(seeds))
