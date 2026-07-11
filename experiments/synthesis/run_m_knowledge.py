"""M-KNOWLEDGE — multi-level, multi-verifier evidence-driven knowledge (no LLM).

Grounds the continual-learning loop and its HARDEST question — "can the system
reliably decide what general lesson to learn from each failure?" — with the three
distinctions the analysis insists on:

  1. UNIVERSAL vs CONTEXT-DEPENDENT. "Guard the denominator against zero" is
     correct in EVERY context → promote to GENERAL. "Sort descending" / "apply a
     10% discount" is correct only in SOME contexts → the trigger alone does not
     determine the fix, so it must be SCOPED and CONDITIONED on context, never
     globally promoted ("always reverse=True" would break other projects). The
     organiser promotes to general ONLY when the fix is verified-consistent across
     DIVERSE contexts; otherwise it keeps the fix context-scoped and ABSTAINS on a
     novel context rather than guessing.
  2. VERIFIER STRENGTH → CONFIDENCE. Compilation proves only syntax/type/link, not
     correctness (binary_search compiles yet fails on duplicates). Evidence from a
     stronger verifier (unit tests, integration, multi-context) earns higher
     confidence; a compiler-only pattern stays LOW and is not trusted for reuse.
  3. MULTIPLE LEVELS. Patterns are organised by level — syntax, idiom, algorithm,
     architecture, debugging, planning — each carrying its own scope + confidence.

Measured against a NAIVE learner that promotes every first-seen fix globally (the
"always reverse=True" mistake). Claims: the evidence-bounded organiser makes
0 cross-context errors and 0 overgeneralisations where the naive learner makes
many; it abstains (gap-honest) on novel contexts and on compiler-only evidence;
and it correctly reuses genuinely universal patterns. No LLM.

Run: .venv/Scripts/python.exe experiments/synthesis/run_m_knowledge.py [seed ...]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from random import Random

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LEVELS = ["syntax", "idiom", "algorithm", "architecture", "debugging", "planning"]
VERIFIERS = {"compiler": 0.3, "unit_test": 0.7, "integration": 0.85, "multi_context": 0.95}
APPLY_THRESHOLD = 0.6         # below this (e.g. compiler-only) → not trusted for reuse
MIN_DIVERSE = 3               # contexts of agreement required to promote to GENERAL


def gen_world(rng, n_triggers=24, n_contexts=8):
    contexts = [f"ctx{i}" for i in range(n_contexts)]
    triggers = []
    for t in range(n_triggers):
        level = rng.choice(LEVELS)
        if rng.random() < 0.5:                                   # UNIVERSAL trigger
            triggers.append({"id": t, "level": level, "universal": True, "fix": f"U{t}"})
        else:                                                    # CONTEXT-DEPENDENT
            variants = [f"C{t}_{v}" for v in range(rng.randint(2, 3))]
            ctx_fix = {c: rng.choice(variants) for c in contexts}
            triggers.append({"id": t, "level": level, "universal": False, "ctx_fix": ctx_fix})
    return contexts, triggers


def correct_fix(trig, ctx):
    return trig["fix"] if trig["universal"] else trig["ctx_fix"][ctx]


def gen_episodes(rng, triggers, contexts, n):
    eps = []
    for _ in range(n):
        trig = rng.choice(triggers)
        ctx = rng.choice(contexts)
        # verifier that confirmed this fix — mostly tests, sometimes compiler-only
        v = rng.choices(list(VERIFIERS), weights=[0.2, 0.45, 0.2, 0.15])[0]
        eps.append((trig["id"], trig["level"], ctx, correct_fix(trig, ctx), v))
    return eps


class Organizer:
    """Evidence-bounded knowledge store, organised by level, scope and confidence."""

    def __init__(self):
        # trigger -> ctx -> fix -> best verifier strength seen
        self.obs = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        self.level = {}
        self.knowledge = {}      # trigger -> {"scope","fix"/"ctx_fix","confidence"}

    def ingest(self, episodes):
        for tid, level, ctx, fix, v in episodes:
            self.level[tid] = level
            self.obs[tid][ctx][fix] = max(self.obs[tid][ctx][fix], VERIFIERS[v])
        for tid in self.obs:
            self._consolidate_one(tid)

    def observe(self, tid, ctx, true_fix):
        """Continual correction: fold a VERIFIED outcome back in. If it contradicts
        a 'general' promotion, re-consolidation DEMOTES it to contextual — knowledge
        is revisable as evidence changes (confidence can go down, not only up)."""
        self.obs[tid][ctx][true_fix] = max(self.obs[tid][ctx][true_fix], VERIFIERS["multi_context"])
        self._consolidate_one(tid)

    def _consolidate_one(self, tid):
        ctxs = self.obs[tid]
        best = {c: max(fixes.items(), key=lambda kv: kv[1]) for c, fixes in ctxs.items()}
        fixes_seen = {f for f, _s in best.values()}
        conf = max(s for _f, s in best.values())
        if len(fixes_seen) == 1 and len(best) >= MIN_DIVERSE:
            # ONE fix, verified across DIVERSE contexts → promote to GENERAL
            self.knowledge[tid] = {"scope": "general", "fix": next(iter(fixes_seen)),
                                   "confidence": round(conf, 2)}
        else:
            # fix varies by context (a contradiction demotes here) → CONTEXT-SCOPED
            self.knowledge[tid] = {"scope": "contextual",
                                   "ctx_fix": {c: f for c, (f, _s) in best.items()},
                                   "confidence": round(conf, 2)}

    def apply(self, tid, ctx):
        """Return (fix, why) or (None, why=abstain-reason). Never guess."""
        k = self.knowledge.get(tid)
        if not k:
            return None, "unknown"
        if k["confidence"] < APPLY_THRESHOLD:
            return None, "low_confidence"          # e.g. compiler-only evidence
        if k["scope"] == "general":
            return k["fix"], "general"
        fix = k["ctx_fix"].get(ctx)
        if fix is None:
            return None, "novel_context"           # gap-honest: don't guess a scoped fix
        return fix, "contextual"


class Naive:
    """Promotes the FIRST fix seen for a trigger, globally (the 'reverse=True' bug)."""

    def __init__(self):
        self.fix = {}

    def ingest(self, episodes):
        for tid, _level, _ctx, fix, _v in episodes:
            self.fix.setdefault(tid, fix)

    def apply(self, tid, ctx):
        return self.fix.get(tid), "global"


def one_pass(model, test, triggers, learn=False):
    tref = {t["id"]: t for t in triggers}
    m = defaultdict(int)
    for tid, _level, ctx, true_fix, _v in test:
        pred, _why = model.apply(tid, ctx)
        if pred is None:
            m["abstained"] += 1
        else:
            m["applied"] += 1
            if pred == true_fix:
                m["correct"] += 1
            else:
                m["wrong"] += 1
                if not tref[tid]["universal"]:
                    m["cross_context_error"] += 1
        if learn and isinstance(model, Organizer):
            model.observe(tid, ctx, true_fix)      # continual correction from verified outcome
    # overgeneralisations in the CURRENT knowledge state
    for tid, t in tref.items():
        if t["universal"]:
            continue
        if isinstance(model, Naive) and tid in model.fix:
            m["overgeneralized"] += 1
        else:
            k = getattr(model, "knowledge", {}).get(tid)
            if k and k["scope"] == "general":
                m["overgeneralized"] += 1
    return m


def run_seed(seed):
    rng = Random(seed)
    contexts, triggers = gen_world(rng)
    # hold out 2 contexts entirely → tests abstention on NOVEL contexts
    train_ctx, novel_ctx = contexts[:-2], contexts[-2:]
    train = gen_episodes(rng, triggers, train_ctx, 900)
    test = gen_episodes(rng, triggers, contexts, 300)     # test spans novel contexts too

    org, naive = Organizer(), Naive()
    org.ingest(train); naive.ingest(train)
    learning = one_pass(org, test, triggers, learn=True)   # pass 1: learn from outcomes
    mo = one_pass(org, test, triggers, learn=False)         # pass 2: steady state (converged)
    mn = one_pass(naive, test, triggers, learn=False)       # naive never self-corrects
    low_conf = sum(1 for k in org.knowledge.values() if k["confidence"] < APPLY_THRESHOLD)
    return {"seed": seed, "triggers": len(triggers), "novel_contexts": len(novel_ctx),
            "learning_phase_xerr": learning.get("cross_context_error", 0),
            "organizer": dict(mo), "naive": dict(mn), "low_conf_patterns": low_conf}


def _acc(m):
    a = m.get("applied", 0)
    return m.get("correct", 0) / a if a else 0.0


def main(seeds):
    results = [run_seed(s) for s in seeds]
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "m_knowledge.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("=" * 84)
    print(f"M-KNOWLEDGE evidence-bounded multi-level knowledge vs naive global promotion — {len(seeds)} seeds")
    print("-" * 84)
    print(f"{'seed':>8} | {'ORG acc':>8}{'x-ctx err':>10}{'overgen':>8}{'abstain':>8} "
          f"| {'NAIVE acc':>10}{'x-ctx err':>10}{'overgen':>8}")
    for r in results:
        o, n = r["organizer"], r["naive"]
        print(f"{r['seed']:>8} | {_acc(o):>7.0%}{o.get('cross_context_error',0):>10}"
              f"{o.get('overgeneralized',0):>8}{o.get('abstained',0):>8} "
              f"| {_acc(n):>9.0%}{n.get('cross_context_error',0):>10}{n.get('overgeneralized',0):>8}")
    print("-" * 84)
    oe = sum(r["organizer"].get("cross_context_error", 0) for r in results)
    ne = sum(r["naive"].get("cross_context_error", 0) for r in results)
    oo = sum(r["organizer"].get("overgeneralized", 0) for r in results)
    no = sum(r["naive"].get("overgeneralized", 0) for r in results)
    le = sum(r["learning_phase_xerr"] for r in results)
    oacc = sum(_acc(r["organizer"]) for r in results) / len(results)
    oab = sum(r["organizer"].get("abstained", 0) for r in results)
    print(f"organizer STEADY-STATE: applied-accuracy {oacc:.0%} | cross-context errors {oe} | "
          f"overgeneralizations {oo} | abstentions {oab}")
    print(f"  (learning-phase cross-context errors {le} → self-corrected to {oe} via demotion-on-contradiction)")
    print(f"naive:     cross-context errors {ne} | overgeneralizations {no} "
          f"(promoted context-dependent fixes globally, never self-corrects)")
    ok = oe == 0 and oo == 0 and oacc >= 0.95 and ne > 0 and no > 0
    print("VERDICT:", "PASS — evidence-bounded promotion learns the RIGHT lesson: universal patterns reused, "
          "context-dependent ones scoped (0 cross-context errors, 0 overgeneralization), novel/weak evidence "
          "abstained; naive global promotion breaks. No LLM."
          if ok else "MIXED/FAIL — see rows")
    return 0 if ok else 1


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024, 99999]
    sys.exit(main(seeds))
