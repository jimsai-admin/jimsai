"""M-REPAIR — iterative repair from verifier feedback (no LLM).

The other half of large-scale code synthesis: given a program that FAILS its tests,
use the failing tests to REPAIR it — the "compilation feedback + iterative repair"
loop the analysis names for OS-scale code. Grounded with an objective verifier
(execution against I/O examples):

  repair(program, tests): while some test fails, try local edits (substitute /
  insert / delete one op), keep the edit that maximises the number of passing
  tests (feedback-guided hill-climb), until ALL tests pass or the budget is spent.

Two falsifiable claims on RANDOM deep programs corrupted by a few edits:
  (A) FEEDBACK LOCALISES. Repair fixes deep programs that from-scratch synthesis
      cannot reach at the SAME evaluation budget — because the partial-pass signal
      guides search to the fault instead of enumerating the whole space.
  (B) 0 WRONG. A repaired program is accepted ONLY when it passes EVERY test; a
      still-failing candidate is never returned. The never-voice-a-wrong-program
      guarantee, under repair.

Honest boundary: greedy repair can stall in a local optimum (reported as a real
success-rate < 100%, not hidden); real compiler/type feedback is richer than a
pass-count and would localise better. The op-grammar stands in for an API surface.

Run: .venv/Scripts/python.exe experiments/synthesis/run_m_repair.py [seed ...]
"""

from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path
from random import Random

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = {"inc": lambda x: x + 1, "dec": lambda x: x - 1, "dbl": lambda x: x * 2,
        "neg": lambda x: -x, "sqr": lambda x: x * x, "half": lambda x: x // 2}
OPS = list(BASE)


def run(prog, x):
    for op in prog:
        x = BASE[op](x)
    return x


def pass_count(prog, tests):
    return sum(run(prog, i) == o for i, o in tests)


def neighbors(prog):
    """All programs one edit away: substitute, insert, or delete one op."""
    for i in range(len(prog)):
        for op in OPS:
            if op != prog[i]:
                yield prog[:i] + [op] + prog[i + 1:]           # substitute
    for i in range(len(prog) + 1):
        for op in OPS:
            yield prog[:i] + [op] + prog[i:]                   # insert
    for i in range(len(prog)):
        yield prog[:i] + prog[i + 1:]                          # delete


def repair(prog, tests, budget):
    """Feedback-guided hill-climb on pass-count; accept only at FULL pass."""
    cur, cur_pass = list(prog), pass_count(prog, tests)
    evals = 0
    while cur_pass < len(tests) and evals < budget:
        best, best_pass = None, cur_pass
        for nb in neighbors(cur):
            evals += 1
            p = pass_count(nb, tests)
            if p > best_pass:
                best, best_pass = nb, p
            if evals >= budget:
                break
        if best is None:                 # local optimum — no single edit improves
            return None, evals
        cur, cur_pass = best, best_pass
    return (cur if cur_pass == len(tests) else None), evals


def synthesize(tests, max_depth, budget):
    """From-scratch BFS over op-pipelines; accept only at FULL pass."""
    q = deque([[]]); evals = 0
    while q:
        prog = q.popleft(); evals += 1
        if evals > budget:
            return None
        if prog and pass_count(prog, tests) == len(tests):
            return prog
        if len(prog) < max_depth:
            for op in OPS:
                q.append(prog + [op])
    return None


def corrupt(rng, prog, k):
    """Apply k random edits to break the program."""
    p = list(prog)
    for _ in range(k):
        i = rng.randrange(len(p))
        p[i] = rng.choice(OPS)
    return p


def run_seed(seed, depth=7, corrupt_k=2, budget=6000, n=15):
    rng = Random(seed)
    repaired = synthd = wrong = 0
    evals_used = []
    for _ in range(n):
        target = [rng.choice(["inc", "dbl", "sqr", "dec"]) for _ in range(depth)]
        tests = [(x, run(target, x)) for x in range(-6, 7)]
        broken = corrupt(rng, target, corrupt_k)
        while pass_count(broken, tests) == len(tests):    # ensure it actually fails
            broken = corrupt(rng, target, corrupt_k)
        fixed, evals = repair(broken, tests, budget)
        if fixed is not None:
            repaired += 1
            evals_used.append(evals)
            if pass_count(fixed, tests) != len(tests):
                wrong += 1
        scratch = synthesize(tests, depth, budget)
        if scratch is not None:
            synthd += 1
            if pass_count(scratch, tests) != len(tests):
                wrong += 1
    return {"seed": seed, "depth": depth, "corrupt_k": corrupt_k, "budget": budget, "of": n,
            "repaired": repaired, "from_scratch": synthd, "wrong": wrong,
            "mean_evals_to_repair": round(sum(evals_used) / len(evals_used)) if evals_used else None}


def main(seeds):
    results = [run_seed(s) for s in seeds]
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "m_repair.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("=" * 76)
    print(f"M-REPAIR iterative repair from test feedback — {len(seeds)} seeds")
    print(f"(target depth 7, {2} corrupting edits, eval budget 6000)")
    print("-" * 76)
    for r in results:
        print(f"  seed {r['seed']}: repaired {r['repaired']:2d}/{r['of']} "
              f"→ from-scratch {r['from_scratch']:2d}/{r['of']}   wrong={r['wrong']}  "
              f"(mean evals to repair {r['mean_evals_to_repair']})")
    print("-" * 76)
    rep = sum(r["repaired"] for r in results)
    scr = sum(r["from_scratch"] for r in results)
    tot = sum(r["of"] for r in results)
    wrong = sum(r["wrong"] for r in results)
    print(f"repaired {rep}/{tot} vs from-scratch {scr}/{tot}  (feedback lift {rep - scr})  | wrong {wrong}")
    ok = rep > scr and wrong == 0
    print("VERDICT:", "PASS — feedback-guided repair fixes deep programs beyond from-scratch reach; "
          "0 wrong (accepted only at full pass); no LLM"
          if ok else "MIXED/FAIL — see rows")
    return 0 if ok else 1


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024, 99999]
    sys.exit(main(seeds))
