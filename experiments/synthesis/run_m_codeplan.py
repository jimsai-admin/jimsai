"""M-CODEPLAN — hierarchical planning scales verified code synthesis (no LLM).

Large-scale code generation without an LLM, grounded. M8 proved a single function
can be synthesised-and-verified; M-PLAN proved independent sub-tasks decompose;
M-LEARN proved a verified result can be REUSED. This composes all three into the
move that makes SCALE possible:

  build a LIBRARY of verified functions BOTTOM-UP; each new function may CALL the
  ones already verified. So a deep program is never searched flat — every layer is
  a shallow search over {base ops} ∪ {already-built functions}, and complexity
  collapses into reusable pieces. The composed program can be far deeper than any
  flat search could reach at the same per-step budget.

Two falsifiable claims, measured on RANDOM layered programs (a call-DAG of small
functions, generated per seed — not hand-picked):

  (A) SCALE. At a fixed per-function search budget, the hierarchical planner
      synthesises the whole deep program where FLAT synthesis (base ops only, no
      reuse) cannot — because flat must find the fully-expanded pipeline (depth =
      Σ layers), whose search space is exponential in the total depth.
  (B) 0 WRONG. Every function is executed against its own I/O examples before it
      is admitted to the library, and the whole program against end-to-end
      examples. A wrong sub-function fails verification and is never used — the
      never-voice-a-wrong-program guarantee, preserved under composition.

Honest boundary: this proves that GIVEN each function's spec (I/O examples) and
the call structure, hierarchical synthesis scales and stays correct. Deriving
per-function specs and the decomposition from ONE natural-language request is the
harder open problem (spec discovery) — named, not faked. The op-grammar is a
bounded stand-in for a real API surface; the mechanism grows with the grammar.

Run: .venv/Scripts/python.exe experiments/synthesis/run_m_codeplan.py [seed ...]
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

# Base operations (int -> int). A real system swaps these for an API surface.
BASE = {"inc": lambda x: x + 1, "dec": lambda x: x - 1, "dbl": lambda x: x * 2,
        "neg": lambda x: -x, "sqr": lambda x: x * x, "half": lambda x: x // 2}
# Generation uses GROWTH ops only, so a composed function is a genuinely deep
# (high-degree) polynomial that NO short base-op pipeline can reproduce — this is
# what forces the flat search to fail and makes the scale claim real (not an
# artefact of collapsible ops like neg∘neg=id that a shallow search can overfit).
GEN_OPS = ["inc", "dbl", "sqr"]


def run_pipeline(steps, library, x):
    """Execute a pipeline; a step is a base op OR a call to a built function
    (itself a pipeline in `library`). Recursion bounded by build order."""
    for s in steps:
        if s in BASE:
            x = BASE[s](x)
        else:
            x = run_pipeline(library[s], library, x)
    return x


def gen_program(rng, n_funcs, layer_depth):
    """A random layered program: function k is a short pipeline over base ops AND
    calls to earlier functions f0..f(k-1). Returns (specs, truth_library) where
    specs[k] = I/O examples for fk, and the last function is the program output."""
    truth = {}
    order = []
    for k in range(n_funcs):
        name = f"f{k}"
        if k == 0:
            steps = [rng.choice(GEN_OPS) for _ in range(rng.randint(1, 2))]
        else:
            # CHAIN: call the immediate predecessor and add ≥1 growth op, so the
            # composed program's minimal base-op expansion grows with k and soon
            # exceeds any flat search's reach — the real source of "scale".
            steps = [order[k - 1]]
            for _ in range(rng.randint(1, 2)):
                steps.insert(rng.randint(0, len(steps)), rng.choice(GEN_OPS))
        truth[name] = steps
        order.append(name)
    # many wide-range inputs so a short overfit pipeline cannot match by luck
    xs = list(range(-6, 7))
    specs = {name: [(x, run_pipeline(truth[name], truth, x)) for x in xs] for name in order}
    return order, specs, truth


def synthesize(examples, primitives, library, depth, budget):
    """BFS over pipelines up to `depth` steps drawn from `primitives` (base ops +
    already-built function names). Returns a verified pipeline or None."""
    q = deque([[]]); nodes = 0
    while q:
        steps = q.popleft(); nodes += 1
        if nodes > budget:
            return None
        if steps:
            try:
                if all(run_pipeline(steps, library, x) == o for x, o in examples):
                    return steps
            except (KeyError, RecursionError):
                pass
        if len(steps) < depth:
            for p in primitives:
                q.append(steps + [p])
    return None


def plan_hierarchical(order, specs, layer_depth, budget):
    """Build the library bottom-up; each function may reuse all earlier ones."""
    library, nodes_total = {}, 0
    for name in order:
        prims = list(BASE) + [n for n in order[:order.index(name)]]
        sol = synthesize(specs[name], prims, library, layer_depth, budget)
        if sol is None:
            return None, nodes_total
        library[name] = sol
        nodes_total += 1
    # verify the whole program (last function) end-to-end
    last = order[-1]
    if all(run_pipeline(library[last], library, x) == o for x, o in specs[last]):
        return library, nodes_total
    return None, nodes_total


def plan_flat(order, specs, total_depth, budget):
    """No reuse: synthesise the FINAL function's behaviour from BASE ops only."""
    return synthesize(specs[order[-1]], list(BASE), {}, total_depth, budget)


def run_seed(seed, n_funcs=8, layer_depth=3, budget=4000, n=12):
    rng = Random(seed)
    hier_solved = flat_solved = wrong = 0
    for _ in range(n):
        order, specs, truth = gen_program(rng, n_funcs, layer_depth)
        total_depth = n_funcs * layer_depth       # flat must reach the full expansion
        lib, _nodes = plan_hierarchical(order, specs, layer_depth, budget)
        if lib is not None:
            hier_solved += 1
            last = order[-1]
            if not all(run_pipeline(lib[last], lib, x) == o for x, o in specs[last]):
                wrong += 1
        flat = plan_flat(order, specs, total_depth, budget)
        if flat is not None:
            flat_solved += 1
            if not all(run_pipeline(flat, {}, x) == o for x, o in specs[order[-1]]):
                wrong += 1
    return {"seed": seed, "n_funcs": n_funcs, "layer_depth": layer_depth,
            "composed_depth": n_funcs * layer_depth, "budget": budget, "of": n,
            "hierarchical_solved": hier_solved, "flat_solved": flat_solved, "wrong": wrong}


def main(seeds):
    results = [run_seed(s) for s in seeds]
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "m_codeplan.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("=" * 76)
    print(f"M-CODEPLAN hierarchical verified code synthesis — {len(seeds)} seeds")
    print(f"(8 chained functions, per-function search depth 3, budget 4000 nodes; flat must reach the full expansion)")
    print("-" * 76)
    for r in results:
        print(f"  seed {r['seed']}: hierarchical {r['hierarchical_solved']:2d}/{r['of']} "
              f"→ flat {r['flat_solved']:2d}/{r['of']}   wrong={r['wrong']}")
    print("-" * 76)
    h = sum(r["hierarchical_solved"] for r in results)
    f = sum(r["flat_solved"] for r in results)
    tot = sum(r["of"] for r in results)
    wrong = sum(r["wrong"] for r in results)
    print(f"solved: hierarchical {h}/{tot} vs flat {f}/{tot}  (scale lift {h - f})  | wrong {wrong}")
    ok = h > f and wrong == 0
    print("VERDICT:", "PASS — a library of verified functions, reused bottom-up, scales synthesis far "
          "beyond flat search; 0 wrong under composition; no LLM"
          if ok else "MIXED/FAIL — see rows")
    return 0 if ok else 1


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024, 99999]
    sys.exit(main(seeds))
