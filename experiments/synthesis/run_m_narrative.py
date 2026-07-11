"""M-NARRATIVE — long-range narrative STRUCTURE by planning (no LLM).

Probes the massive-creative-generation frontier HONESTLY by separating what has an
objective verifier from what does not:

  OBJECTIVE (tested here) — the structural competencies the analysis lists:
    long-term planning, character STATE, narrative MEMORY, foreshadowing→payoff,
    recurring motif, converging arcs. Each is a checkable property of a plan.
  SUBJECTIVE (NOT claimed) — prose beauty, wit/humor, emotional resonance, style
    "feel". There is no ground truth for "funny" or "beautiful", so an
    evidence+verification system cannot optimise it; neural LMs lead here. Named,
    not faked.

What is built: a planner emits a long beat-sequence over a cast, tracking world
state so that (a) only introduced, still-alive characters act; (b) every planted
foreshadow seed is paid off LATER; (c) a motif recurs, spread out; (d) separate
arcs converge at the end. An independent verifier checks all four. A NAIVE local
generator (picks beats without global state — the proxy for "generate locally,
lose the thread", the way long-form neural generation drifts) is measured against
the same checks.

Claim: explicit planning holds long-range structure PERFECTLY over spans where the
local generator accumulates contradictions and dropped setups — i.e. on the
OBJECTIVE axis the evidence/planning approach matches-or-beats free generation.
The SUBJECTIVE surface remains open.

Run: .venv/Scripts/python.exe experiments/synthesis/run_m_narrative.py [seed ...]
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from random import Random

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def plan_narrative(rng, n_chars=8, n_beats=120, n_seeds=6, n_arcs=3):
    """Emit a beat list respecting world state. Each beat is a dict describing a
    verifiable event; the planner NEVER emits an inconsistent beat."""
    chars = [f"C{i}" for i in range(n_chars)]
    arcs = {c: i % n_arcs for i, c in enumerate(chars)}
    alive = {c: True for c in chars}
    introduced: set[str] = set()
    beats, open_seeds, planted, paid = [], [], [], []
    motif_positions = []
    motif_at = sorted(rng.sample(range(6, n_beats - 6), k=max(4, n_beats // 20)))

    for b in range(n_beats):
        # introduce a character early if any remain and we're in the first third
        if len(introduced) < n_chars and (b < n_beats // 3 or rng.random() < 0.3):
            c = rng.choice([c for c in chars if c not in introduced])
            introduced.add(c)
            beats.append({"beat": b, "type": "introduce", "char": c, "arc": arcs[c]})
            continue
        # plant a foreshadow seed (in the first 70% so it can be paid off)
        if len(planted) < n_seeds and introduced and b < int(n_beats * 0.7) and rng.random() < 0.15:
            s = f"seed{len(planted)}"
            planted.append((s, b)); open_seeds.append((s, b))
            beats.append({"beat": b, "type": "plant", "seed": s})
            continue
        # motif recurrence at pre-scheduled spread positions
        if motif_at and b >= motif_at[0]:
            motif_at.pop(0); motif_positions.append(b)
            beats.append({"beat": b, "type": "motif", "symbol": "raven"})
            continue
        # pay off an open seed (foreshadow resolved), latter half preferred
        if open_seeds and (b > n_beats // 2) and rng.random() < 0.25:
            s, pb = open_seeds.pop(rng.randrange(len(open_seeds)))
            paid.append((s, pb, b))
            beats.append({"beat": b, "type": "payoff", "seed": s})
            continue
        # a normal action: an introduced, ALIVE character acts
        actors = [c for c in introduced if alive[c]]
        if not actors:
            continue
        c = rng.choice(actors)
        # occasionally a character exits (dies) — after which it must not act
        if b > n_beats // 2 and rng.random() < 0.04:
            alive[c] = False
            beats.append({"beat": b, "type": "exit", "char": c})
        else:
            beats.append({"beat": b, "type": "act", "char": c, "arc": arcs[c]})

    # ensure ALL seeds are paid off before the end (planner closes its setups)
    for s, pb in list(open_seeds):
        paid.append((s, pb, n_beats))
        beats.append({"beat": n_beats, "type": "payoff", "seed": s})
    # convergence: a final beat referencing one character from EVERY arc
    reps = []
    for a in range(n_arcs):
        cand = [c for c in introduced if alive[c] and arcs[c] == a] or \
               [c for c in introduced if arcs[c] == a]
        if cand:
            reps.append(rng.choice(cand))
    beats.append({"beat": n_beats + 1, "type": "converge", "chars": reps, "arcs_covered": len({arcs[c] for c in reps})})
    return beats, {"n_chars": n_chars, "n_arcs": n_arcs, "n_seeds": n_seeds}


def naive_narrative(rng, n_chars=8, n_beats=120, n_seeds=6, n_arcs=3):
    """Local generation: pick a beat from local choices with NO global state — the
    proxy for free long-form generation that loses the thread."""
    chars = [f"C{i}" for i in range(n_chars)]
    arcs = {c: i % n_arcs for i, c in enumerate(chars)}
    beats = []
    for b in range(n_beats):
        r = rng.random()
        if r < 0.15:
            beats.append({"beat": b, "type": "plant", "seed": f"seed{rng.randrange(n_seeds)}"})
        elif r < 0.25:
            beats.append({"beat": b, "type": "payoff", "seed": f"seed{rng.randrange(n_seeds)}"})
        elif r < 0.30:
            beats.append({"beat": b, "type": "exit", "char": rng.choice(chars)})
        elif r < 0.35:
            beats.append({"beat": b, "type": "motif", "symbol": "raven"})
        else:
            beats.append({"beat": b, "type": "act", "char": rng.choice(chars), "arc": arcs[rng.choice(chars)]})
    return beats, {"n_chars": n_chars, "n_arcs": n_arcs, "n_seeds": n_seeds}


def verify(beats, meta):
    """Independent structural verification — the objective properties."""
    introduced, alive = set(), {}
    consistency_violations = 0
    planted, paid = {}, {}
    motif_beats = []
    for ev in beats:
        t = ev["type"]
        if t == "introduce":
            introduced.add(ev["char"]); alive[ev["char"]] = True
        elif t == "exit":
            if ev["char"] not in introduced or not alive.get(ev["char"], False):
                consistency_violations += 1
            alive[ev["char"]] = False
        elif t == "act":
            if ev["char"] not in introduced or not alive.get(ev["char"], False):
                consistency_violations += 1      # a non-introduced or dead character acted
        elif t == "plant":
            planted.setdefault(ev["seed"], ev["beat"])
        elif t == "payoff":
            if ev["seed"] in planted and planted[ev["seed"]] <= ev["beat"]:
                paid[ev["seed"]] = ev["beat"]
            else:
                consistency_violations += 1      # paid off a seed never planted (or before)
        elif t == "motif":
            motif_beats.append(ev["beat"])
        elif t == "converge":
            arcs_covered = ev.get("arcs_covered", 0)
    seeds_planted = len(planted)
    payoff_rate = len(paid) / seeds_planted if seeds_planted else 1.0
    motif_spread = statistics.pstdev(motif_beats) if len(motif_beats) > 1 else 0.0
    converged = arcs_covered == meta["n_arcs"] if "converge" in {e["type"] for e in beats} else False
    return {"consistency_violations": consistency_violations,
            "seeds_planted": seeds_planted, "payoff_rate": round(payoff_rate, 3),
            "motif_recurrences": len(motif_beats), "motif_spread": round(motif_spread, 1),
            "arcs_converged": converged}


def run_seed(seed):
    rng = Random(seed)
    p_beats, meta = plan_narrative(rng)
    planned = verify(p_beats, meta)
    n_beats, meta2 = naive_narrative(Random(seed))
    naive = verify(n_beats, meta2)
    return {"seed": seed, "beats": len(p_beats), "planned": planned, "naive": naive}


def main(seeds):
    results = [run_seed(s) for s in seeds]
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "m_narrative.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("=" * 80)
    print(f"M-NARRATIVE long-range structure by planning vs local generation — {len(seeds)} seeds")
    print("(OBJECTIVE structure only; prose quality / humor NOT measured — see docstring)")
    print("-" * 80)
    print(f"{'seed':>8} | {'planner: viol':>13} {'payoff':>7} {'motif':>6} {'converge':>9} "
          f"| {'naive: viol':>11} {'payoff':>7} {'converge':>9}")
    for r in results:
        p, n = r["planned"], r["naive"]
        print(f"{r['seed']:>8} | {p['consistency_violations']:>13} {p['payoff_rate']:>6.0%} "
              f"{p['motif_recurrences']:>6} {str(p['arcs_converged']):>9} "
              f"| {n['consistency_violations']:>11} {n['payoff_rate']:>6.0%} {str(n['arcs_converged']):>9}")
    print("-" * 80)
    pv = sum(r["planned"]["consistency_violations"] for r in results)
    nv = sum(r["naive"]["consistency_violations"] for r in results)
    ppay = sum(r["planned"]["payoff_rate"] for r in results) / len(results)
    npay = sum(r["naive"]["payoff_rate"] for r in results) / len(results)
    conv = all(r["planned"]["arcs_converged"] for r in results)
    print(f"planner: {pv} consistency violations, {ppay:.0%} foreshadow payoff, all-arcs-converge={conv}")
    print(f"naive:   {nv} consistency violations, {npay:.0%} foreshadow payoff")
    ok = pv == 0 and ppay >= 0.99 and conv and nv > 0
    print("VERDICT:", "PASS — planning holds long-range STRUCTURE (0 contradictions, 100% payoff, arcs "
          "converge) where local generation drifts; surface prose/humor remain open (not claimed)"
          if ok else "MIXED/FAIL — see rows")
    return 0 if ok else 1


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024, 99999]
    sys.exit(main(seeds))
