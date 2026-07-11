"""Phase 7 + the biggest improvement — an EVIDENCE-DRIVEN adaptive lexicon (no LLM).

The single-trigger extractor has low recall because a relation has MANY surface
forms ("borders" / "bordered" / "bordering" / "shares a border" / "neighbour").
This learns them ALL from evidence and clusters them into a relation's trigger
vocabulary — each surface stored with a CONFIDENCE and an EVIDENCE count, never a
hand-written synonym list. Two deliverables:

  (A) RECALL@k — discover the top-k high-precision triggers (not just top-1); fire
      if ANY is present. Measured under the SAME entity-disjoint CV. Shows the
      recall lift (and the precision cost) of multi-surface triggers.

  (B) THE LEXICON ARTIFACT — for each relation (opaque PID), the discovered
      surface vocabulary with confidence (= precision against the pos/neg
      contrast) and evidence (= support). This is the border → {borders,
      bordered, …} semantic-network entry the architecture consults to normalise
      paraphrases before reasoning — built from data, downgradable as evidence
      changes. Plus an UNSUPERVISED check: cluster surfaces by the entity-pair
      distribution they share (Jaccard) and measure how purely each cluster maps
      to one KB relation — synonymy emerging without the KB defining it.

Run: .venv/Scripts/python.exe experiments/ele/adaptive_lexicon.py [corpus.json]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_relations import (  # noqa: E402
    KFOLD, MIN_PRECISION, MIN_SUPPORT, _counts, agg, direction, is_symmetric,
    kfold_entities, load, micro_prf, toks,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def entity_token_set(rels) -> set:
    """Every token that is part of an entity name — these are NOT triggers."""
    ent = set()
    for r in rels.values():
        for e in r["entities"]:
            ent.update(toks(e))
    return ent


def discover_topk(rows, k, exclude=frozenset(), prec_thr=MIN_PRECISION, sup_thr=MIN_SUPPORT):
    """Top-k surfaces ranked by EVIDENCE (support) among high-precision candidates —
    the relation's trigger vocabulary. Ranking by support (not precision-first)
    surfaces real frequent triggers over rare spurious ones, matching the
    validation finding that frequency-in-positives is the strong signal. Entity
    tokens are excluded (an entity name is not a relation trigger).
    Returns [(surface, confidence, evidence_count), …]."""
    pos, tot = _counts(rows)
    cand = {t: (pos[t] / tot[t], pos[t]) for t in tot
            if t not in exclude and pos[t] >= sup_thr and pos[t] / tot[t] >= prec_thr}
    ranked = sorted(cand, key=lambda t: (-cand[t][1], -cand[t][0]))
    return [(t, round(cand[t][0], 3), cand[t][1]) for t in ranked[:k]]


def evaluate_multi(test_rows, triggers, subj_left, kb, symmetric):
    sym = symmetric
    trig = {t for t, _c, _e in triggers}
    preds = set()
    for left, right, between, _lab, _sl in test_rows:
        if trig & set(between):
            s, o = (left, right) if subj_left else (right, left)
            preds.add((s, o))

    def match(s, o):
        return (s, o) in kb or (sym and (o, s) in kb)
    correct = {(s, o) for s, o in preds if match(s, o)}
    cooccur = set()
    for l, r, _b, lab, _sl in test_rows:
        if lab == "REL":
            cooccur.add((l, r) if (l, r) in kb else (r, l))
    extractable = cooccur & kb

    def norm(x):
        return {frozenset(p) for p in x} if sym else x
    return len(norm(correct)), len(norm(preds)), len(norm(extractable))


def recall_at_k(rels, exclude, ks=(1, 3, 5)):
    """CV recall/precision/F1 as the trigger vocabulary grows top-1 → top-k."""
    print("=" * 84)
    print(f"(A) RECALL@k — multi-surface triggers under {KFOLD}-fold entity-disjoint CV")
    print("-" * 84)
    print(f"{'relation':9}{'pairs':>6}   " + "".join(f"{'R@'+str(k):>8}{'P@'+str(k):>8}{'F@'+str(k):>8}" for k in ks))
    macro = {k: [] for k in ks}
    for pid, r in rels.items():
        cells = []
        for k in ks:
            folds = kfold_entities(r["entities"], KFOLD, 0)
            NC = NP = NE = 0
            for i, test_ent in enumerate(folds):
                train_ent = set().union(*[f for j, f in enumerate(folds) if j != i])
                tr = [x for x in r["rows"] if x[0] in train_ent and x[1] in train_ent]
                te = [x for x in r["rows"] if x[0] in test_ent and x[1] in test_ent]
                trigs = discover_topk(tr, k, exclude)
                sd = direction(tr, trigs[0][0]) if trigs else True
                nc, npred, ne = evaluate_multi(te, trigs, sd, r["kb"], r["symmetric"])
                NC += nc; NP += npred; NE += ne
            P, R, F = micro_prf(NC, NP, NE)
            macro[k].append((P, R, F))
            cells.append(f"{R:>7.0%}{P:>8.0%}{F:>8.0%}")
        print(f"{pid:9}{len(r['kb']):>6}   " + "".join(cells))
    print("-" * 84)
    for k in ks:
        vals = macro[k]
        mR = sum(v[1] for v in vals) / len(vals)
        mP = sum(v[0] for v in vals) / len(vals)
        mF = sum(v[2] for v in vals) / len(vals)
        print(f"  macro @{k}: recall {mR:.1%}  precision {mP:.1%}  F1 {mF:.1%}")
    r1 = sum(v[1] for v in macro[ks[0]]) / len(macro[ks[0]])
    rK = sum(v[1] for v in macro[ks[-1]]) / len(macro[ks[-1]])
    print(f"\n  → recall lift top-1 → top-{ks[-1]}: {r1:.1%} → {rK:.1%} ({rK - r1:+.1%})")


def build_lexicon(rels, exclude, k=8):
    """(B) The artifact: each relation's surface vocabulary with confidence+evidence,
    learned from ALL evidence (no split — this is the stored lexicon)."""
    print("\n" + "=" * 84)
    print("(B) ADAPTIVE LEXICON — discovered surface vocabulary per relation (confidence · evidence)")
    print("-" * 84)
    lexicon = {}
    for pid, r in rels.items():
        vocab = discover_topk(r["rows"], k, exclude)
        lexicon[pid] = [{"surface": t, "confidence": c, "evidence": e} for t, c, e in vocab]
        shown = ", ".join(f"{t}({c:.2f}·{e})" for t, c, e in vocab) or "(none)"
        print(f"  {pid}: {shown}")
    return lexicon


def synonym_clusters(rels, exclude, min_support=4, jac=0.15):
    """Unsupervised: cluster surfaces by the entity-pair distribution they share;
    measure how purely each cluster maps to a single KB relation (synonymy that
    emerges WITHOUT the KB defining it)."""
    print("\n" + "=" * 84)
    print("(C) UNSUPERVISED synonymy — surfaces clustered by shared entity-pair distribution")
    print("-" * 84)
    # surface -> set of unordered pairs it connects (across ALL relations' corpora)
    surf_pairs = defaultdict(set)
    surf_rel = defaultdict(lambda: defaultdict(int))   # surface -> pid -> count (for purity)
    for pid, r in rels.items():
        for left, right, between, label, _sl in r["rows"]:
            if label == "REL":
                for t in set(between):
                    if len(t) >= 4 and t not in exclude:
                        surf_pairs[t].add(frozenset((left, right)))
                        surf_rel[t][pid] += 1
    surfaces = [s for s in surf_pairs if len(surf_pairs[s]) >= min_support]
    # greedy single-link clustering by Jaccard of pair sets
    parent = {s: s for s in surfaces}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for i, a in enumerate(surfaces):
        for b in surfaces[i + 1:]:
            pa, pb = surf_pairs[a], surf_pairs[b]
            j = len(pa & pb) / len(pa | pb) if (pa | pb) else 0
            if j >= jac:
                parent[find(a)] = find(b)
    clusters = defaultdict(list)
    for s in surfaces:
        clusters[find(s)].append(s)
    # purity: fraction of a cluster's surfaces whose dominant relation is the same
    pures, sizes = [], []
    shown = 0
    for members in sorted(clusters.values(), key=len, reverse=True):
        if len(members) < 2:
            continue
        dom = defaultdict(int)
        for s in members:
            best = max(surf_rel[s], key=lambda p: surf_rel[s][p])
            dom[best] += 1
        purity = max(dom.values()) / len(members)
        pures.append(purity); sizes.append(len(members))
        if shown < 8:
            top_pid = max(dom, key=lambda p: dom[p])
            print(f"  {top_pid} ⟵ {{{', '.join(sorted(members))}}}  (purity {purity:.0%})")
            shown += 1
    if pures:
        wmean = sum(p * s for p, s in zip(pures, sizes)) / sum(sizes)
        print(f"  weighted mean cluster purity: {wmean:.0%} over {len(pures)} multi-surface clusters")


def main() -> int:
    fname = sys.argv[1] if len(sys.argv) > 1 else "multi_relation.json"
    print(f"corpus: {fname}")
    _extracts, rels = load(fname)
    exclude = entity_token_set(rels)
    recall_at_k(rels, exclude)
    lexicon = build_lexicon(rels, exclude)
    synonym_clusters(rels, exclude)
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "adaptive_lexicon.json").write_text(json.dumps(lexicon, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nsaved lexicon → results/adaptive_lexicon.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
