"""M11 — Projection + verifier: analogy/creativity is computable (no LLM).

The claim under test (docs/generation_decomposition.md §9): novel composition —
analogy, metaphor — is PROJECTION of known relational structure onto a new
domain, ACCEPTED by a verifier, not sampling randomness. Structure-mapping
(Gentner): a good analogy preserves RELATIONS ("the atom is like the solar
system" because nucleus:electron :: sun:planet under 'attracts'/'orbits'/
'heavier-than'), a bad one does not. If a structural-alignment score cleanly
separates coherent projections from incoherent ones — and NEVER accepts an
incoherent projection as coherent — then creativity has a verifiable substrate
and need not be delegated to an external model.

Per-seed generative relational structures (no enumerated analogies). For each:
a SOURCE graph; an ANALOGOUS target (same relational pattern, different
entities — an isomorphism exists); a PARTIAL target (half the relations kept);
and an INCOHERENT target (relations randomised). The projector finds the entity
mapping that maximises preserved relations; the verifier thresholds the score.

PASS: analogous ≈ 1.0, incoherent low, clean separation, and ZERO incoherent
projections accepted as coherent (the fail-safe — a bad analogy is refused, not
voiced). Kill: if the score cannot separate, structure-mapping is the wrong
model at this scope — recorded.

Run: .venv/Scripts/python.exe experiments/creativity/run_m11.py [seed ...]
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from random import Random

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PREDS = ["attracts", "orbits", "heavier_than", "causes", "part_of", "flows_to"]
NC, NV = "bcdfghjklmnpqrstvwxz", "aeiou"


def nonce(rng: Random, n: int = 3) -> str:
    return "".join(rng.choice(NC) + rng.choice(NV) for _ in range(n)).capitalize()


def gen_source(rng: Random, n_ent: int, n_rel: int) -> tuple[list[str], set[tuple[str, str, str]]]:
    ents = [nonce(rng) for _ in range(n_ent)]
    rels: set[tuple[str, str, str]] = set()
    tries = 0
    while len(rels) < n_rel and tries < 200:
        s, o = rng.sample(ents, 2)
        rels.add((s, rng.choice(PREDS), o))
        tries += 1
    return ents, rels


def relabel(ents, rels, rng, keep_frac=1.0, randomize=False):
    """Analogous target = isomorphic relabel; partial = keep a fraction;
    incoherent = same entity set, randomised relations."""
    new_ents = [nonce(rng) for _ in ents]
    m = dict(zip(ents, new_ents))
    if randomize:
        preds = [p for _s, p, _o in rels]
        out = set()
        while len(out) < len(rels):
            s, o = rng.sample(new_ents, 2)
            out.add((s, rng.choice(preds or PREDS), o))
        return new_ents, out
    mapped = [(m[s], p, m[o]) for s, p, o in rels]
    if keep_frac < 1.0:
        k = max(1, int(len(mapped) * keep_frac))
        mapped = rng.sample(mapped, k)
    return new_ents, set(mapped)


def _largest_connected(preserved: list[tuple[str, str, str]]) -> int:
    """Edge count of the largest CONNECTED component of the preserved relations
    (entities are nodes). Gentner systematicity: a real analogy preserves ONE
    connected relational structure; coincidental matches are scattered edges."""
    if not preserved:
        return 0
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for s, _p, o in preserved:
        parent[find(s)] = find(o)
    from collections import Counter
    comp_edges: Counter = Counter()
    for s, _p, o in preserved:
        comp_edges[find(s)] += 1
    return max(comp_edges.values())


def align(src_ents, src_rels, tgt_ents, tgt_rels):
    """Best entity mapping source→target, scored by SYSTEMATIC alignment: the
    size of the largest connected component of preserved relations / |source|.
    A source relation (s,p,o) is preserved iff (map(s),p,map(o)) ∈ target.
    Brute force over injections for small graphs; maximise the systematic score
    (not raw count) so scattered coincidental matches do not win."""
    if not src_rels:
        return 0.0, {}
    src_rels = list(src_rels)
    best_score, best_map = 0.0, {}
    for perm in itertools.permutations(tgt_ents, len(src_ents)) if len(tgt_ents) >= len(src_ents) else []:
        m = dict(zip(src_ents, perm))
        preserved = [(s, p, o) for (s, p, o) in src_rels if (m[s], p, m[o]) in tgt_rels]
        score = _largest_connected(preserved) / len(src_rels)
        if score > best_score:
            best_score, best_map = score, m
        if best_score == 1.0:
            break
    return best_score, best_map


def run_seed(seed: int, trials: int = 30, threshold: float = 0.7) -> dict:
    rng = Random(seed)
    ana, par, inc = [], [], []
    false_accept = missed = 0
    sample = None
    for t in range(trials):
        n_ent = rng.randint(5, 6)
        ents, rels = gen_source(rng, n_ent, rng.randint(7, 9))  # richer structure
        a_e, a_r = relabel(ents, rels, rng)
        p_e, p_r = relabel(ents, rels, rng, keep_frac=0.5)
        i_e, i_r = relabel(ents, rels, rng, randomize=True)
        sa, ma = align(ents, rels, a_e, a_r)
        sp, _ = align(ents, rels, p_e, p_r)
        si, _ = align(ents, rels, i_e, i_r)
        ana.append(sa); par.append(sp); inc.append(si)
        if si >= threshold:
            false_accept += 1          # accepted an INCOHERENT projection — unsafe
        if sa < threshold:
            missed += 1                # rejected a real analogy
        if t == 0:
            sample = {"source": sorted(f"{s} {p} {o}" for s, p, o in rels),
                      "analogy_score": round(sa, 3),
                      "mapping": {k: v for k, v in list(ma.items())[:4]}}
    n = len(ana)
    return {"seed": seed, "trials": trials, "threshold": threshold,
            "analogous_mean": round(sum(ana) / n, 3),
            "partial_mean": round(sum(par) / n, 3),
            "incoherent_mean": round(sum(inc) / n, 3),
            "false_accepts": false_accept, "missed_analogies": missed,
            "sample": sample}


def main(seeds: list[int]) -> int:
    results = [run_seed(s) for s in seeds]
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "m11_projection.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("=" * 72)
    print(f"M11 Projection + verifier (structure-mapping) — {len(seeds)} seeds")
    print("-" * 72)
    for r in results:
        print(f" seed {r['seed']}: analogous={r['analogous_mean']:.2f} "
              f"partial={r['partial_mean']:.2f} incoherent={r['incoherent_mean']:.2f} "
              f"| false_accepts={r['false_accepts']} missed={r['missed_analogies']}")
    s = results[0]["sample"]
    print("-" * 72)
    print("example projection (seed", results[0]["seed"], "):")
    print("  source relations:", s["source"][:4])
    print(f"  best analogy score: {s['analogy_score']}  mapping: {s['mapping']}")
    print("-" * 72)
    ana = sum(r["analogous_mean"] for r in results) / len(results)
    inc = sum(r["incoherent_mean"] for r in results) / len(results)
    fa = sum(r["false_accepts"] for r in results)
    ok = ana > 0.95 and inc < 0.5 and (ana - inc) > 0.4 and fa == 0
    print(f"analogous≈{ana:.2f}  incoherent≈{inc:.2f}  separation={ana - inc:.2f}  false_accepts={fa}")
    print("VERDICT:", "PASS — coherent projections accepted, incoherent refused; analogy is computable, no LLM"
          if ok else "MIXED/FAIL — see rows (recorded)")
    return 0 if ok else 1


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024, 99999]
    sys.exit(main(seeds))
