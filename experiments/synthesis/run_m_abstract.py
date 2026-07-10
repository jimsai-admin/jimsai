"""M-ABSTRACT — learning the RIGHT abstraction from evidence (no LLM).

The hard problem the analysis flags: from a failure+fix, what GENERAL lesson
should be learned? Too specific → never reused. Too general → regressions in
other contexts (the sort()/discount trap: "always reverse=True" breaks ascending
tasks). The right lesson is CONDITIONED on evidence: "apply transform T only
where condition C holds", where C is DISCOVERED from the data, not assumed.

Grounded test. Ground truth is a hidden rule: output = T(x) if C*(x) else x
(a transform applied only under a context). We observe labelled examples and
compare three abstraction strategies on HELD-OUT inputs:

  over-general — always apply T (learn no condition);
  over-specific — memorise seen (input→output) pairs only;
  evidence-bounded — DISCOVER the simplest predicate over inputs that separates
                     the T-cases from the rest (ELE frequency+diversity: promote
                     the most general condition CONSISTENT with the evidence),
                     then apply T iff that condition holds.

Claim: evidence-bounded abstraction transfers correctly (high held-out accuracy)
where over-general causes errors and over-specific never reuses — i.e. the RIGHT
level of abstraction is discoverable from evidence, with no hardcoded rule and no
LLM. Predicate/transform inventories are closed, general families (parity,
sign, threshold), not per-task answers.

Run: .venv/Scripts/python.exe experiments/synthesis/run_m_abstract.py [seed ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from random import Random

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Closed, general families — a nonce rule per seed is drawn from these, not enumerated.
PREDS = {
    "x<0": lambda x: x < 0, "x>0": lambda x: x > 0, "x==0": lambda x: x == 0,
    "even": lambda x: x % 2 == 0, "odd": lambda x: x % 2 == 1,
    "x>5": lambda x: x > 5, "x<-2": lambda x: x < -2, "div3": lambda x: x % 3 == 0,
}
TRANSFORMS = {"neg": lambda x: -x, "dbl": lambda x: x * 2, "inc": lambda x: x + 10, "sqr": lambda x: x * x}


def run_seed(seed: int, n_train: int = 40, n_test: int = 60) -> dict:
    rng = Random(seed)
    cstar = rng.choice(list(PREDS)); C = PREDS[cstar]
    tname = rng.choice(list(TRANSFORMS)); T = TRANSFORMS[tname]

    def gold(x):
        return T(x) if C(x) else x

    # Large input space so HELD-OUT inputs are almost all UNSEEN — the true test
    # of transfer: memorisation (over-specific) cannot cover it, only a learned
    # general condition can.
    xs_train = [rng.randint(-1000, 1000) for _ in range(n_train)]
    xs_test = [rng.randint(-1000, 1000) for _ in range(n_test)]
    train = [(x, gold(x)) for x in xs_train]

    # over-general: always apply T
    def over_general(x):
        return T(x)

    # over-specific: memorise; unknown → identity (no transfer)
    seen = dict(train)

    def over_specific(x):
        return seen.get(x, x)

    # evidence-bounded: discover the simplest predicate consistent with the data.
    # A candidate C' is consistent iff, for every training example, applying T
    # exactly when C'(x) reproduces the observed output. Pick one that fits;
    # prefer the one covering the MOST training points (most general supported).
    def consistent(pred):
        f = PREDS[pred]
        return all((T(x) if f(x) else x) == y for x, y in train)
    candidates = [p for p in PREDS if consistent(p)]
    # among consistent predicates, the most general = fires on the most inputs
    learned = max(candidates, key=lambda p: sum(1 for x in xs_train if PREDS[p](x))) if candidates else None

    def evidence_bounded(x):
        if learned is None:
            return x
        return T(x) if PREDS[learned](x) else x

    def acc(fn):
        return sum(fn(x) == gold(x) for x in xs_test) / len(xs_test)

    return {"seed": seed, "rule": f"{tname} if {cstar}", "learned_condition": learned,
            "over_general": round(acc(over_general), 3),
            "over_specific": round(acc(over_specific), 3),
            "evidence_bounded": round(acc(evidence_bounded), 3),
            "learned_correct": learned == cstar}


def main(seeds):
    results = [run_seed(s) for s in seeds]
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "m_abstract.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("=" * 74)
    print(f"M-ABSTRACT learning the right abstraction — {len(seeds)} seeds")
    print("-" * 74)
    print(f"{'rule (hidden)':22}{'over-gen':>10}{'over-spec':>11}{'evidence':>10}{'cond ok':>9}")
    for r in results:
        print(f"  {r['rule']:20}{r['over_general']:>10.0%}{r['over_specific']:>11.0%}"
              f"{r['evidence_bounded']:>10.0%}{str(r['learned_correct']):>9}")
    print("-" * 74)
    eg = sum(r["over_general"] for r in results) / len(results)
    es = sum(r["over_specific"] for r in results) / len(results)
    eb = sum(r["evidence_bounded"] for r in results) / len(results)
    cond = sum(r["learned_correct"] for r in results)
    print(f"mean held-out accuracy: over-general {eg:.0%} | over-specific {es:.0%} | "
          f"evidence-bounded {eb:.0%}  | conditions recovered {cond}/{len(results)}")
    ok = eb > 0.95 and eb > eg + 0.2 and eb > es + 0.2
    print("VERDICT:", "PASS — the RIGHT abstraction (evidence-bounded condition) transfers where over-general errs and over-specific can't reuse; no LLM"
          if ok else "MIXED/FAIL — see rows")
    return 0 if ok else 1


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024, 99999, 111, 555]
    sys.exit(main(seeds))
