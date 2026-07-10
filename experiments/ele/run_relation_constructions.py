"""ELE relation-construction discovery — lift extraction RECALL (no LLM).

The high-precision extractor (grammar_relations, common-word abstention) is SAFE
but only ~37% recall: it abstains on passive ("B is caused by A"), coordination
("A causes B and C"), and negation ("A does not cause B") instead of handling
them. This DISCOVERS those constructions from evidence — the ELE way — and
applies the learned transformation, so passive extracts with the RIGHT direction,
coordination yields both edges, and negation still yields none. No hardcoded verb
or marker list: a construction is a FRAME (the closed-class/function-word pattern
around the entity slots), and its transformation (which slot is subject/object,
and polarity) is LEARNED from labelled examples and promoted when consistent —
exactly ELE's evidence-ledger promotion, applied to relations.

Token classes are distributional, not lexical: E = a proper-noun entity
(title-case, out-of-vocabulary), F = a COMMON word (the sourced common-vocabulary
set — data), V = any other content token (the verb). A frame is the class
sequence with the F words kept literal, so it generalises over verbs but
distinguishes "…is V by…" from "…V…and…".

PASS: on HELD-OUT sentences, discovered constructions lift recall well above the
abstain-only baseline (0.37) while keeping precision high (≥0.9) and NEVER
emitting an edge from a negated sentence (0 negation-false-positives).

Run: .venv/Scripts/python.exe experiments/ele/run_relation_constructions.py [seed ...]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "prototype"))
import os  # noqa: E402

os.environ.setdefault("JIMS_CONCEPT_INDEX", "on")
from jimsai.cll_shadow import get_shadow, surface_key  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NC, NV = "bcdfghjklmnpqrstvwxz", "aeiou"


def nonce(rng, n=3):
    return "".join(rng.choice(NC) + rng.choice(NV) for _ in range(n)).capitalize()


def gen(rng):
    """A sentence + its ground-truth positive relations (subject, object)."""
    A, B, C = nonce(rng), nonce(rng), nonce(rng)
    verb = rng.choice(["causes", "drives", "triggers", "produces", "governs"])
    k = rng.choice(["active", "active", "passive", "negated", "coordinated"])
    a, b, c = A.lower(), B.lower(), C.lower()
    if k == "active":
        return f"{A} {verb} {B}.", [(a, b)]
    if k == "passive":
        return f"{B} is {verb.rstrip('s')}d by {A}.", [(a, b)]     # truth A→B
    if k == "negated":
        return f"{A} does not {verb.rstrip('s')} {B}.", []          # no edge
    return f"{A} {verb} {B} and {C}.", [(a, b), (a, c)]             # coordination


def classify(sentence, common):
    """Token stream as (class, token). E=title-case OOV entity, F=common word,
    V=other content token. Entities keep their surface for output."""
    out = []
    for w in sentence.rstrip(".").split():
        wl = w.lower()
        if surface_key(wl) in common:
            out.append(("F", wl))
        elif w[:1].isupper():
            out.append(("E", wl))
        else:
            out.append(("V", wl))
    return out


def frame_of(tokens):
    """Frame signature: F words literal, E/V as class slots. Entity slot indices
    recorded so a learned transformation can point at them."""
    sig, ent_slots = [], []
    for i, (c, tok) in enumerate(tokens):
        if c == "E":
            sig.append("E")
            ent_slots.append(i)
        elif c == "F":
            sig.append(f"F:{tok}")
        else:
            sig.append("V")
    return tuple(sig), ent_slots


def discover(train, common):
    """Learn frame → list of (subj_slot_ordinal, obj_slot_ordinal) or [] for
    negation, from ground truth; promote a frame when a MAJORITY of its examples
    agree (evidence-ledger promotion)."""
    votes: dict[tuple, list] = defaultdict(list)
    for sentence, truth in train:
        toks = classify(sentence, common)
        sig, ent_slots = frame_of(toks)
        pos = {ent_slots.index(i): j for j, i in enumerate(ent_slots)}  # slot ordinal
        # express truth as ordinal (subj_ord, obj_ord) pairs over entity slots
        surf = [toks[i][1] for i in ent_slots]
        rel_ords = []
        for s, o in truth:
            if s in surf and o in surf:
                rel_ords.append((surf.index(s), surf.index(o)))
        votes[sig].append(tuple(sorted(rel_ords)))
    grammar = {}
    for sig, obs in votes.items():
        best = max(set(obs), key=obs.count)
        if obs.count(best) >= max(2, len(obs) // 2):     # promoted
            grammar[sig] = best
    return grammar


def apply_grammar(sentence, grammar, common):
    toks = classify(sentence, common)
    sig, ent_slots = frame_of(toks)
    if sig not in grammar:
        return None                     # unknown construction → abstain
    surf = [toks[i][1] for i in ent_slots]
    rels = []
    for s_ord, o_ord in grammar[sig]:
        if s_ord < len(surf) and o_ord < len(surf):
            rels.append((surf[s_ord], surf[o_ord]))
    return rels                          # [] for a negation frame (learned)


def run_seed(seed, n_train=200, n_test=120):
    rng = Random(seed)
    common = getattr(get_shadow(), "_common_words", set())
    train = [gen(rng) for _ in range(n_train)]
    test = [gen(rng) for _ in range(n_test)]
    grammar = discover(train, common)

    tp = fp = fn = neg_fp = abstain = 0
    for sentence, truth in test:
        truth_set = set(truth)
        got = apply_grammar(sentence, grammar, common)
        if got is None:
            abstain += 1
            fn += len(truth_set)
            continue
        got_set = set(got)
        tp += len(got_set & truth_set)
        fp += len(got_set - truth_set)
        fn += len(truth_set - got_set)
        if not truth_set:
            neg_fp += len(got_set)      # edge from a negated sentence — dangerous
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    return {"seed": seed, "constructions_discovered": len(grammar),
            "recall": round(recall, 3), "precision": round(prec, 3),
            "negation_false_positives": neg_fp, "abstained": abstain}


def main(seeds):
    results = [run_seed(s) for s in seeds]
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "relation_constructions.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("=" * 72)
    print(f"ELE relation-construction discovery — {len(seeds)} seeds")
    print("-" * 72)
    for r in results:
        print(f"  seed {r['seed']}: constructions={r['constructions_discovered']} "
              f"recall={r['recall']:.0%} precision={r['precision']:.0%} "
              f"neg_fp={r['negation_false_positives']} abstained={r['abstained']}")
    print("-" * 72)
    mr = sum(r["recall"] for r in results) / len(results)
    mp = sum(r["precision"] for r in results) / len(results)
    nf = sum(r["negation_false_positives"] for r in results)
    print(f"mean recall {mr:.0%} (abstain-only baseline 37%) | mean precision {mp:.0%} | negation-FP {nf}")
    ok = mr > 0.7 and mp >= 0.9 and nf == 0
    print("VERDICT:", "PASS — discovered constructions lift recall, keep precision, 0 negation edges; no LLM, no marker list"
          if ok else "MIXED/FAIL — see rows (recorded)")
    return 0 if ok else 1


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024, 99999]
    sys.exit(main(seeds))
