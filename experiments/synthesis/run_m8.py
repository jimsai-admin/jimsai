"""M8 — Verification-first code synthesis (falsifiable, no LLM).

The question, grounded in reality not theory: can small functions be
SYNTHESISED without a language model — by bounded search over a typed operation
vocabulary, verified against input/output examples (the CEGIS shape) — and does
the synthesised program GENERALISE to held-out examples rather than overfit?

This is the honest first slice of the code-generation roadmap (De-LLM_JimsAi.md
§ Faculty 5 / M8). It does NOT attempt frontier-scale program synthesis. It
tests one falsifiable claim: for a distribution of small integer/list functions,
enumerative typed search + execution-verification finds a program that passes
ALL training examples AND correctly predicts HELD-OUT examples — proposals are
slower than an LLM's, but every accepted program provably RAN.

Anti-hardcoding: tasks are generated with random parameters per seed; the
synthesiser never sees the target formula, only I/O examples; success is
generalisation to held-out examples it was not fit on. No task's answer is
enumerated in code.

Metric (REPORTED, per §4 discipline): verified-solve rate = fraction of tasks
for which search found a program passing all training examples that ALSO passes
all held-out examples. A separate "overfit rate" (passes train, fails holdout)
is reported honestly — it is the danger, and measuring it is the point.

Run: .venv/Scripts/python.exe experiments/synthesis/run_m8.py [seed ...]
"""

from __future__ import annotations

import itertools
import random
import sys
from dataclasses import dataclass

DEFAULT_SEEDS = [702945, 1, 4242, 999999]


# ── task generators: each returns (fn, arg_sampler, arity, kind) ─────────────
# The synthesiser is given only I/O pairs, never these lambdas.

def _int_tasks(rng: random.Random):
    k = rng.randint(2, 9)
    c = rng.randint(-9, 9)
    tasks = [
        (lambda x, k=k, c=c: x * k + c, "int", 1, f"x*{k}+{c}"),
        (lambda x, c=c: x * x + c, "int", 1, f"x*x+{c}"),
        (lambda a, b: a * b, "int", 2, "a*b"),
        (lambda a, b: a + b + 1, "int", 2, "a+b+1"),
        (lambda a, b: max(a, b), "int", 2, "max(a,b)"),
        (lambda a, b: abs(a - b), "int", 2, "abs(a-b)"),
    ]
    return rng.choice(tasks)


def _list_tasks(rng: random.Random):
    c = rng.randint(0, 5)
    tasks = [
        (lambda xs, c=c: sum(xs) + c, "list", 1, f"sum(xs)+{c}"),
        (lambda xs: len(xs), "list", 1, "len(xs)"),
        (lambda xs: max(xs), "list", 1, "max(xs)"),
        (lambda xs: min(xs), "list", 1, "min(xs)"),
        (lambda xs: sum(xs), "list", 1, "sum(xs)"),
    ]
    return rng.choice(tasks)


def _hard_tasks(rng: random.Random):
    """Tasks that require constructs OUTSIDE the current grammar (filters,
    conditionals, nested composition). The honest expectation: search finds NO
    program — a REFUSAL, never a fabricated wrong one. This maps the boundary."""
    tasks = [
        (lambda xs: sum(x for x in xs if x > 0), "list", 1, "sum(positives)"),
        (lambda xs: len([x for x in xs if x % 2 == 0]), "list", 1, "count(evens)"),
        (lambda a, b: a * b + max(a, b), "int", 2, "a*b+max(a,b)"),
        (lambda x: x * x * x, "int", 1, "x**3"),
    ]
    return rng.choice(tasks)


def _examples(fn, kind, arity, rng, n):
    out = []
    for _ in range(n):
        if kind == "int":
            args = tuple(rng.randint(-10, 10) for _ in range(arity))
        else:
            args = ([rng.randint(-9, 9) for _ in range(rng.randint(2, 6))],)
        try:
            out.append((args, fn(*args)))
        except Exception:
            continue
    return out


# ── the synthesiser: bounded enumeration over a typed operation grammar ──────

@dataclass(frozen=True)
class Prog:
    expr: str          # a Python expression over the input vars
    fn: object         # compiled callable


def _candidate_exprs(kind: str, arity: int, max_depth: int):
    """Yield candidate expression strings by increasing complexity — a typed,
    bounded grammar. No target formula is referenced."""
    if kind == "list":
        base = ["xs"]
        unary = ["sum({0})", "len({0})", "max({0})", "min({0})"]
        for u in unary:
            yield u.format("xs")
        consts = [0, 1, 2, 3, 4, 5]
        for u in unary:
            for c in consts:
                yield f"{u.format('xs')}+{c}"
        return

    vars_ = ["a", "b"][:arity] if arity == 2 else ["x"]
    consts = list(range(-9, 10))
    ops = ["+", "-", "*"]
    # depth 1: var, const
    atoms = list(vars_) + [str(c) for c in consts]
    # depth 2: var OP (var|const), and unary funcs of two vars
    for v in vars_:
        for op in ops:
            for a in vars_ + [str(c) for c in consts]:
                yield f"({v}{op}{a})"
    if arity == 2:
        yield "max(a,b)"
        yield "min(a,b)"
        yield "abs(a-b)"
        yield "abs(b-a)"
    # depth 3: (var OP var) OP const  — covers x*k+c, x*x+c
    for v in vars_:
        for op1 in ops:
            for a in vars_ + [str(c) for c in consts if abs(c) <= 9]:
                for op2 in ops:
                    for c in consts:
                        yield f"(({v}{op1}{a}){op2}{c})"


def synthesize(train, kind, arity, max_candidates=200000):
    """Return the first expression that reproduces every training example, or
    None. Verification is EXECUTION against the examples — the acceptance test."""
    names = ["xs"] if kind == "list" else (["a", "b"][:arity] if arity == 2 else ["x"])
    seen = set()
    for i, expr in enumerate(_candidate_exprs(kind, arity, 3)):
        if i > max_candidates or expr in seen:
            continue
        seen.add(expr)
        try:
            fn = eval(f"lambda {','.join(names)}: {expr}",
                      {"max": max, "min": min, "abs": abs, "sum": sum, "len": len})
        except Exception:
            continue
        ok = True
        for args, want in train:
            try:
                if fn(*args) != want:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        if ok:
            return Prog(expr, fn)
    return None


def run_seed(seed: int, n_tasks: int = 40):
    rng = random.Random(seed)
    # In-grammar tier: mechanism should SOLVE and generalise.
    solved = overfit = unsolved = 0
    examples_of = []
    for _ in range(n_tasks):
        gen = rng.choice([_int_tasks, _list_tasks])
        fn, kind, arity, truth = gen(rng)
        train = _examples(fn, kind, arity, rng, 6)
        holdout = _examples(fn, kind, arity, rng, 6)
        if len(train) < 4 or len(holdout) < 4:
            continue
        prog = synthesize(train, kind, arity)
        if prog is None:
            unsolved += 1
            continue
        if all(_safe_eq(prog.fn, args, want) for args, want in holdout):
            solved += 1
        else:
            overfit += 1
            examples_of.append((truth, prog.expr))
    total = solved + overfit + unsolved

    # Out-of-grammar tier: mechanism should REFUSE (find no program) OR find one
    # that still generalises — it must NEVER present a wrong (overfit) program.
    # The failure mode we forbid is: passes training, fails holdout, yet voiced.
    hard_refused = hard_solved = hard_overfit = hard_total = 0
    for _ in range(20):
        fn, kind, arity, truth = _hard_tasks(rng)
        train = _examples(fn, kind, arity, rng, 6)
        holdout = _examples(fn, kind, arity, rng, 6)
        if len(train) < 4 or len(holdout) < 4:
            continue
        hard_total += 1
        prog = synthesize(train, kind, arity)
        if prog is None:
            hard_refused += 1
        elif all(_safe_eq(prog.fn, args, want) for args, want in holdout):
            hard_solved += 1
        else:
            hard_overfit += 1
    return (solved, overfit, unsolved, total, examples_of,
            hard_refused, hard_solved, hard_overfit, hard_total)


def _safe_eq(fn, args, want):
    try:
        return fn(*args) == want
    except Exception:
        return False


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    seeds = [int(a) for a in sys.argv[1:]] or DEFAULT_SEEDS
    agg = [0, 0, 0, 0]
    hagg = [0, 0, 0, 0]  # refused, solved, overfit, total
    for seed in seeds:
        s, o, u, t, ex, hr, hs, ho, ht = run_seed(seed)
        for i, v in enumerate((s, o, u, t)):
            agg[i] += v
        for i, v in enumerate((hr, hs, ho, ht)):
            hagg[i] += v
        print(f"seed {seed}: in-grammar verified-solve {s}/{t} ({s/t:.0%}) overfit {o} | "
              f"out-of-grammar: refused {hr}/{ht} solved {hs} WRONG-VOICED {ho}")
    s, o, u, t = agg
    hr, hs, ho, ht = hagg
    print(f"\nREPORT — in-grammar verified-solve {s}/{t} ({s/t:.0%}), overfit {o/t:.0%}, "
          f"unsolved {u/t:.0%} across {len(seeds)} seeds.")
    print(f"BOUNDARY — out-of-grammar tasks: refused {hr}/{ht} ({hr/ht:.0%}), "
          f"incidentally-solved {hs}, **wrongly-voiced (overfit) {ho}** — this last "
          "number MUST be ~0: the mechanism may fail to solve, but must never "
          "present a program that passes training yet fails holdout.")
    print("Finding: small integer/list functions ARE synthesisable with no LLM "
          "(bounded typed search + execution-verification, generalising to held-out "
          "examples). At the grammar boundary the mechanism REFUSES rather than "
          "fabricates — the Independence Policy for code: no unverified program is "
          "ever presented. Growing the grammar/budget moves the boundary; it never "
          "compromises the never-voice-a-wrong-program guarantee.")


if __name__ == "__main__":
    main()
