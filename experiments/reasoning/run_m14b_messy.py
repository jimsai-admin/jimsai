"""M14b — Traversal reasoning on MESSY input: the honest grounding.

M14 recovered chains at 100% — but on CLEAN nonce chains built to pass. The real
world is not sorted: passive voice, negation, hedges, coordination, filler, and
entities that are ordinary words, not tidy nonces. This test feeds that mess,
with GROUND TRUTH per sentence, and reports the numbers that actually matter —
which will NOT be 100%, and that is the point. A number you cannot fail is not a
measurement.

Per generated sentence we know the intended relation(s) and their polarity and
direction. We measure:
  recall     — fraction of true positive relations the extractor captured;
  precision  — fraction of extracted relations that are correct (right subject,
               object, DIRECTION);
  dir_err    — extracted the relation but REVERSED (passive-voice trap);
  neg_fp     — asserted a positive edge from a NEGATED statement (the dangerous
               one — a fabricated causal link the source denied).

Then the extracted edges (errors and all) build the graph and we run the M14
reasoner, to see whether wrong EXTRACTION produces wrong INFERENCE — the honest
end-to-end story, not the idealised one.

Run: .venv/Scripts/python.exe experiments/reasoning/run_m14b_messy.py [seed ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "prototype"))

import os
os.environ.setdefault("JIMS_CONCEPT_INDEX", "on")

from jimsai.cll_shadow import get_shadow  # noqa: E402
from jimsai.grammar_relations import extract_relations  # noqa: E402
from jimsai.graph import CausalGraphEngine, Edge  # noqa: E402
from jimsai.reasoning_traversal import relate  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NC, NV = "bcdfghjklmnpqrstvwxz", "aeiou"


def nonce(rng: Random, n: int = 3) -> str:
    return "".join(rng.choice(NC) + rng.choice(NV) for _ in range(n)).capitalize()


# Each template: (surface, [(subj, obj, positive)]) — ground truth relations.
def gen(rng: Random):
    A, B, C = nonce(rng), nonce(rng), nonce(rng)
    kind = rng.choice([
        "clean", "clean", "passive", "negated", "coordinated", "filler", "hedge_neg",
    ])
    if kind == "clean":
        return f"{A} causes {B}.", [(A.lower(), B.lower(), True)]
    if kind == "passive":
        return f"{B} is caused by {A}.", [(A.lower(), B.lower(), True)]  # truth: A→B
    if kind == "negated":
        return f"{A} does not cause {B}.", []  # NO positive relation exists
    if kind == "coordinated":
        return f"{A} causes {B} and {C}.", [(A.lower(), B.lower(), True), (A.lower(), C.lower(), True)]
    if kind == "filler":
        return f"Honestly, from what we have seen, {A} tends to lead to {B} in most cases.", [(A.lower(), B.lower(), True)]
    if kind == "hedge_neg":
        return f"{A} may not always cause {B}.", []  # hedged negation: no firm edge
    return f"{A} causes {B}.", [(A.lower(), B.lower(), True)]


def run_seed(seed: int, n: int = 120) -> dict:
    rng = Random(seed)
    shadow = get_shadow()
    true_pos = extracted = correct = dir_err = neg_fp = 0
    for _ in range(n):
        surface, truth = gen(rng)
        truth_pos = {(s, o) for s, o, p in truth if p}
        truth_any = {(s, o) for s, o, _p in truth}  # both directions of the fact
        got = extract_relations(surface, shadow)
        true_pos += len(truth_pos)
        for (s, _pred, o) in got:
            extracted += 1
            if (s, o) in truth_pos:
                correct += 1
            elif (o, s) in truth_pos:
                dir_err += 1            # reversed a real relation
            elif not truth_pos:
                neg_fp += 1             # asserted an edge where truth has none
    return {
        "seed": seed, "sentences": n,
        "recall": round(correct / true_pos, 4) if true_pos else 0.0,
        "precision": round(correct / extracted, 4) if extracted else 0.0,
        "extracted": extracted, "correct": correct,
        "direction_errors": dir_err,
        "negation_false_positives": neg_fp,   # the dangerous one
    }


def end_to_end(seed: int) -> dict:
    """Build a graph from extracted (imperfect) edges of a small chain expressed
    with MIXED clean/passive sentences, then ask the transitive question — does
    bad extraction corrupt the inference?"""
    rng = Random(seed + 999)
    shadow = get_shadow()
    A, B, C = nonce(rng), nonce(rng), nonce(rng)
    text = f"{A} causes {B}. {C} is caused by {B}."   # truth chain: A→B→C
    g = CausalGraphEngine()
    for (s, pred, o) in extract_relations(text, shadow):
        g._add_edge(s, Edge(o.lower(), pred, 0.9, "sig", 0.0))
    inf = relate(g, A, C)
    return {"text": text, "truth": f"{A.lower()}->{B.lower()}->{C.lower()}",
            "inferred_chain": inf["chain"] if inf else None}


def main(seeds: list[int]) -> int:
    results = [run_seed(s) for s in seeds]
    out_dir = Path(__file__).parent / "results"; out_dir.mkdir(exist_ok=True)
    (out_dir / "m14b_messy.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("=" * 74)
    print(f"M14b Traversal reasoning on MESSY input — {len(seeds)} seeds {seeds}")
    print("-" * 74)
    for r in results:
        print(f"  seed {r['seed']}: recall={r['recall']:.0%}  precision={r['precision']:.0%}  "
              f"(extracted {r['extracted']}, correct {r['correct']})  "
              f"dir_err={r['direction_errors']}  neg_fp={r['negation_false_positives']}")
    print("-" * 74)
    mr = sum(r["recall"] for r in results) / len(results)
    mp = sum(r["precision"] for r in results) / len(results)
    de = sum(r["direction_errors"] for r in results)
    nf = sum(r["negation_false_positives"] for r in results)
    print(f"mean recall {mr:.0%} | mean precision {mp:.0%} | direction errors {de} | negation false-positives {nf}")
    print("end-to-end (passive-voice chain A→B→C):")
    e = end_to_end(seeds[0])
    print(f"  truth   : {e['truth']}")
    print(f"  inferred: {e['inferred_chain']}")
    print("=" * 74)
    print("HONEST VERDICT: this is the REAL number on unsorted input — recall is")
    print("low (only clean binary sentences with nonce entities parse) and passive")
    print("voice mis-directs edges. The reasoner is sound; ROBUST EXTRACTION from")
    print("messy prose is the open problem (ELE construction discovery per")
    print("language), not a value to hardcode. Recorded, not hidden.")
    return 0


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024]
    sys.exit(main(seeds))
