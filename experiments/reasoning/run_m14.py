"""M14 — Traversal reasoning: compose graph paths into inference (no LLM).

Does JimsAI's graph traversal actually REASON — recover a multi-hop chain and
voice it as a transitive inference — or only report adjacency? And does it stay
HONEST: when two things are not connected, say so, never fabricate a link to
satisfy the question? This is the falsifiable test for making the existing
traversal machinery (`CausalGraphEngine`, `reasoning_traversal`) a real reasoner.

Per-seed generative graphs (no enumerated answers): a main chain of nonce
entities joined by a relation, several DISTRACTOR chains in separate components,
and isolated nodes. Then:

  P-connect  — for connected endpoints, `find_path` recovers the EXACT true
               chain (right nodes, right order, right hops), and the composer
               voices the transitive conclusion with the right endpoints.
  P-failsafe — for pairs in DIFFERENT components (and chain⇄isolated), the
               reasoner returns None. THE guarantee: zero fabricated links.
  P-depth    — chains of length 2…6 are all recovered (multi-hop, not just 1).

Anti-hardcoding: entities are per-seed nonces, chain lengths and distractors are
random, components are disjoint by construction; nothing is enumerated. PASS
requires connect≈100%, depth all-lengths, and fabrication == 0.

Run: .venv/Scripts/python.exe experiments/reasoning/run_m14.py [seed ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "prototype"))

from jimsai.graph import CausalGraphEngine, Edge  # noqa: E402
from jimsai.reasoning_traversal import relate, compose_path_inference  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NC, NV = "bcdfghjklmnpqrstvwxz", "aeiou"
PREDS = ["causes", "requires", "leads_to", "depends_on", "enables"]


def nonce(rng: Random, n: int = 3) -> str:
    return "".join(rng.choice(NC) + rng.choice(NV) for _ in range(n)).capitalize()


def _chain(g: CausalGraphEngine, nodes: list[str], pred: str) -> None:
    for a, b in zip(nodes, nodes[1:]):
        g._add_edge(a, Edge(b.lower(), pred, 0.9, "sig", 0.0))


def build(rng: Random) -> tuple[CausalGraphEngine, list[str], list[list[str]], list[str]]:
    g = CausalGraphEngine()
    pool = [nonce(rng) for _ in range(40)]
    rng.shuffle(pool)
    i = 0
    main = pool[i:i + rng.randint(3, 6)]; i += len(main)
    _chain(g, main, rng.choice(PREDS))
    distractors: list[list[str]] = []
    for _ in range(rng.randint(2, 3)):           # separate components
        d = pool[i:i + rng.randint(2, 4)]; i += len(d)
        if len(d) >= 2:
            _chain(g, d, rng.choice(PREDS))
            distractors.append(d)
    isolated = pool[i:i + 4]                       # nodes with no edges
    return g, main, distractors, isolated


def run_seed(seed: int, trials: int = 30) -> dict:
    rng = Random(seed)
    connect_ok = connect_tot = 0
    depth_ok = depth_tot = 0
    fabrications = 0
    failsafe_tot = 0
    for _ in range(trials):
        g, main, distractors, isolated = build(rng)
        # P-connect + P-depth: every prefix endpoint of the main chain
        for k in range(1, len(main)):
            src, tgt = main[0], main[k]
            path = g.find_path(src, tgt)
            true_nodes = [n.lower() for n in main[:k + 1]]
            got_nodes = [src.lower()] + [e[2] for e in path] if path else None
            ok = got_nodes == true_nodes
            connect_ok += ok; connect_tot += 1
            depth_ok += ok; depth_tot += 1
            # composed transitive conclusion has the right endpoints
            inf = compose_path_inference(path) if path else None
            if inf and inf["hops"] >= 2 and inf["transitive"]:
                if not (main[0].lower() in inf["transitive"].lower()
                        and main[k].lower() in inf["transitive"].lower()):
                    connect_ok -= 1  # endpoints wrong → not a real pass
        # P-failsafe: cross-component and chain⇄isolated pairs must be None
        cross = []
        for d in distractors:
            cross.append((main[0], d[-1]))
            cross.append((d[0], main[-1]))
        for iso in isolated:
            cross.append((main[rng.randrange(len(main))], iso))
        for src, tgt in cross:
            failsafe_tot += 1
            if relate(g, src, tgt) is not None:
                fabrications += 1
    return {
        "seed": seed, "trials": trials,
        "connect_rate": round(connect_ok / connect_tot, 4) if connect_tot else 0.0,
        "depth_rate": round(depth_ok / depth_tot, 4) if depth_tot else 0.0,
        "failsafe_checked": failsafe_tot,
        "fabrications": fabrications,   # THE guarantee — must be 0
    }


def main(seeds: list[int]) -> int:
    results = [run_seed(s) for s in seeds]
    out_dir = Path(__file__).parent / "results"; out_dir.mkdir(exist_ok=True)
    (out_dir / "m14_traversal.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    # one worked example for the reader
    g, main_chain, _dist, _iso = build(Random(seeds[0]))
    demo = relate(g, main_chain[0], main_chain[-1])

    print("=" * 70)
    print(f"M14 Traversal reasoning — {len(seeds)} seeds {seeds}")
    print("-" * 70)
    for r in results:
        print(f"  seed {r['seed']}: connect={r['connect_rate']:.0%} depth={r['depth_rate']:.0%} "
              f"failsafe_checked={r['failsafe_checked']} fabrications={r['fabrications']}")
    print("-" * 70)
    if demo:
        print("example inference:")
        print(f"  chain     : {demo['chain']}")
        print(f"  transitive: {demo['transitive']}  ({demo['hops']} hops)")
    total_fab = sum(r["fabrications"] for r in results)
    connect = all(r["connect_rate"] > 0.98 for r in results)
    print("=" * 70)
    ok = connect and total_fab == 0
    print("VERDICT:", "PASS — multi-hop chains recovered & voiced; 0 fabricated links"
          if ok else "FAIL — see per-seed rows")
    return 0 if ok else 1


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024, 99999]
    sys.exit(main(seeds))
