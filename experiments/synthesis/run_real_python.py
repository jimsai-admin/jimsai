"""REAL Python, REAL verifier — the plan/synth/verify/repair loop on ACTUAL code.

The earlier code experiments used a bounded int→int op-grammar to prove the
MECHANISM. This runs the SAME loop on genuine Python SOURCE with a genuine
verifier — the code is `exec`-uted and its behaviour checked against examples,
so "verified" means it actually RAN correctly, not that a toy grammar matched.

It grounds, honestly, both sides of the website question:
  CAN — generate + execute-verify + repair small, spec'd real functions with
        faithful comments (incl. the user's own divide() safe-division example).
  CANNOT (shown by construction) — search-synthesise arbitrary real code: the
        space explodes, which is exactly why this assembles from a KNOWN vocabulary
        and why a full website needs a learned pattern library + prose→spec
        understanding + iteration, none of which is one-shot or built at scale.

Run: .venv/Scripts/python.exe experiments/synthesis/run_real_python.py
"""

from __future__ import annotations

import sys
from itertools import product

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAISE = "RAISE_VALUEERROR"


def verify_python(source: str, func: str, tests: list) -> tuple[bool, str]:
    """REAL verifier: exec the source, run the function against examples."""
    ns: dict = {}
    try:
        exec(source, ns)                       # noqa: S102 — controlled, generated source
    except Exception as e:                      # a syntax/exec failure = fail
        return False, f"exec error: {e}"
    fn = ns.get(func)
    if not callable(fn):
        return False, "no function defined"
    passed = 0
    for args, expected in tests:
        try:
            result = fn(*args)
            ok = expected != RAISE and result == expected
        except ValueError:
            ok = expected == RAISE
        except Exception:
            ok = False
        passed += ok
    return passed == len(tests), f"{passed}/{len(tests)} examples"


# ── Case A: the divide() safe-division loop on REAL executed Python ───────────
def case_divide():
    print("A. divide() — generate → execute-test → REPAIR from the failure (real Python)")
    v1 = "def divide(a, b):\n    return a / b\n"
    tests = [((6, 2), 3.0), ((9, 3), 3.0), ((5, 0), RAISE)]     # b=0 must be guarded
    ok1, r1 = verify_python(v1, "divide", tests)
    print(f"   v1: {v1.strip()!r}  → verify {r1}  (ok={ok1})")
    # observed failure: divide(5,0) raises ZeroDivisionError, not the required
    # ValueError. The repair adds the guard — a VERIFIED pattern (safe-division).
    v2 = ('def divide(a, b):\n'
          '    # verified pattern: guard the denominator before dividing\n'
          '    if b == 0:\n'
          '        raise ValueError("Division by zero")\n'
          '    return a / b\n')
    ok2, r2 = verify_python(v2, "divide", tests)
    print(f"   v2 (repaired): guard added  → verify {r2}  (ok={ok2})")
    print(f"   FINAL real source:\n{_indent(v2)}")
    return ok1 is False and ok2 is True


# ── Case B: synthesise a small function from I/O examples in REAL Python ──────
EXPR = {"+1": "({x} + 1)", "-1": "({x} - 1)", "*2": "({x} * 2)", "sqr": "({x} * {x})"}


def synth_python(examples: list, depth: int = 3) -> str | None:
    """Compose REAL Python expressions to match examples; emit + exec-verify."""
    names = list(EXPR)
    for k in range(1, depth + 1):
        for combo in product(names, repeat=k):
            expr = "x"
            for op in combo:
                expr = EXPR[op].replace("{x}", expr)
            src = (f"def f(x):\n"
                   f"    # synthesised from {len(examples)} examples, verified by execution\n"
                   f"    return {expr}\n")
            ok, _r = verify_python(src, "f", [((i,), o) for i, o in examples])
            if ok:
                return src
    return None


def case_synth():
    print("\nB. synthesise a real Python function from I/O examples (execute-verified)")
    examples = [(2, 5), (3, 7), (4, 9), (-1, -1)]              # f(x) = 2x + 1
    src = synth_python(examples)
    print(f"   examples: {examples}")
    if src:
        print(f"   synthesised + verified real source:\n{_indent(src)}")
    return src is not None


def _indent(s: str) -> str:
    return "\n".join("      " + ln for ln in s.rstrip().splitlines())


def main() -> int:
    print("=" * 78)
    print("REAL Python + REAL verifier (exec) — the code loop on actual source, no LLM")
    print("-" * 78)
    a = case_divide()
    b = case_synth()
    print("\n" + "-" * 78)
    print("HONEST SCALE BOUNDARY (why NOT a full website in one shot without an LLM):")
    print("  • search-synthesis is tractable only over a KNOWN small vocabulary — arbitrary")
    print("    real code (frameworks, HTML/CSS/SQL/HTTP, 1000s of APIs) explodes the space;")
    print("    real code needs a LEARNED verified-pattern library (the training-agent's job),")
    print("    assembled + repaired — not blind search, and not built at web scale.")
    print("  • prose request → per-component specs/tests is the OPEN NL step (no LLM solves it here).")
    print("  • the loop is ITERATIVE (generate→verify→repair), not one-shot; correctness comes")
    print("    from verification, so 'in one goal' is not how it works.")
    print("  • structural architecture (layering, no circular deps) is plannable/verifiable;")
    print("    idiomatic 'good taste' + eloquent comments are the subjective surface (open).")
    ok = a and b
    print("VERDICT:", "PASS — the plan/synth/verify/repair loop is REAL on actual executed Python at SMALL, "
          "spec'd scale; a complete real-language website in one shot is NOT reachable (bounds above)."
          if ok else "MIXED — see cases")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
