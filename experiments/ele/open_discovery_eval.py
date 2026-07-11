"""Phase 5 — OPEN relation discovery, evaluated with standard clustering metrics.

The question: given ONLY entity pairs and the text between them (no relation
labels), can the system recover the relation structure? We cluster entity pairs
by the surface triggers that connect them, then score the clustering against the
KB relations as ground truth with the STANDARD unsupervised measures — Purity,
Normalized Mutual Information, Adjusted Rand Index — instead of an ad-hoc
best-match precision.

No relation name or trigger is coded; the KB is used ONLY to score, never to
cluster. Same REAL Wikidata + Wikipedia data.

Run: .venv/Scripts/python.exe experiments/ele/open_discovery_eval.py [corpus.json]
"""

from __future__ import annotations

import math
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_relations import load, toks  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MIN_SUPPORT = 4
JACCARD = 0.15


def _c2(n):
    return n * (n - 1) // 2


def purity(clusters, labels):
    N = sum(len(v) for v in clusters.values())
    return sum(max(Counter(labels[i] for i in items).values()) for items in clusters.values()) / N if N else 0.0


def nmi(clusters, labels):
    items = [i for v in clusters.values() for i in v]
    N = len(items)
    if N == 0:
        return 0.0
    cl = {i: c for c, v in clusters.items() for i in v}
    def H(assign):
        cnt = Counter(assign[i] for i in items)
        return -sum((c / N) * math.log(c / N) for c in cnt.values() if c)
    Hc, Hk = H(cl), H(labels)
    # mutual information
    joint = Counter((cl[i], labels[i]) for i in items)
    ci = Counter(cl[i] for i in items); ki = Counter(labels[i] for i in items)
    I = 0.0
    for (c, k), nck in joint.items():
        I += (nck / N) * math.log((nck * N) / (ci[c] * ki[k]))
    denom = math.sqrt(Hc * Hk)
    return I / denom if denom else 0.0


def adjusted_rand(clusters, labels):
    items = [i for v in clusters.values() for i in v]
    N = len(items)
    if N < 2:
        return 0.0
    cl = {i: c for c, v in clusters.items() for i in v}
    contingency = Counter((cl[i], labels[i]) for i in items)
    a = Counter(cl[i] for i in items); b = Counter(labels[i] for i in items)
    index = sum(_c2(n) for n in contingency.values())
    sa = sum(_c2(n) for n in a.values()); sb = sum(_c2(n) for n in b.values())
    expected = sa * sb / _c2(N) if _c2(N) else 0
    maxi = 0.5 * (sa + sb)
    return (index - expected) / (maxi - expected) if (maxi - expected) else 0.0


def cluster_pairs(rels):
    """Cluster entity PAIRS by the surface triggers connecting them (no labels)."""
    ent_tokens = {t for r in rels.values() for e in r["entities"] for t in toks(e)}
    pair_true, pair_trigs = {}, defaultdict(Counter)
    trig_pairs = defaultdict(set)
    for pid, r in rels.items():
        for p in r["kb"]:
            pair_true[frozenset(p)] = pid
        for left, right, between, label, _sl in r["rows"]:
            if label == "REL":
                fp = frozenset((left, right))
                for t in set(between):
                    if len(t) >= 4 and t not in ent_tokens:
                        pair_trigs[fp][t] += 1
                        trig_pairs[t].add(fp)
    # single-link cluster the TRIGGERS by shared-pair Jaccard → discovered relations
    trigs = [t for t, ps in trig_pairs.items() if len(ps) >= MIN_SUPPORT]
    parent = {t: t for t in trigs}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in combinations(trigs, 2):
        pa, pb = trig_pairs[a], trig_pairs[b]
        if len(pa & pb) / len(pa | pb) >= JACCARD:
            parent[find(a)] = find(b)
    trig_cluster = {t: find(t) for t in trigs}
    # assign each pair to the cluster of its highest-support in-vocab trigger
    clusters = defaultdict(list)
    labels = {}
    for fp, tc in pair_trigs.items():
        cand = [(t, c) for t, c in tc.items() if t in trig_cluster]
        if not cand or fp not in pair_true:
            continue
        top = max(cand, key=lambda x: x[1])[0]
        clusters[trig_cluster[top]].append(fp)
        labels[fp] = pair_true[fp]
    return clusters, labels


def main() -> int:
    fname = sys.argv[1] if len(sys.argv) > 1 else "multi_relation.json"
    print(f"corpus: {fname}")
    _extracts, rels = load(fname)
    clusters, labels = cluster_pairs(rels)
    n_items = sum(len(v) for v in clusters.values())
    n_true = len(set(labels.values()))
    n_disc = len(clusters)
    print("=" * 72)
    print("PHASE 5 — OPEN relation discovery vs KB (standard clustering metrics)")
    print("-" * 72)
    print(f"  entity pairs clustered : {n_items}")
    print(f"  true relations (KB)    : {n_true}")
    print(f"  discovered clusters    : {n_disc}")
    print(f"  Purity                 : {purity(clusters, labels):.3f}")
    print(f"  NMI                    : {nmi(clusters, labels):.3f}")
    print(f"  Adjusted Rand Index    : {adjusted_rand(clusters, labels):.3f}")
    print("-" * 72)
    # a random baseline: shuffle labels → NMI/ARI ≈ 0 expected
    import random
    rnd = list(labels.values()); random.Random(0).shuffle(rnd)
    rlabels = {k: v for k, v in zip(labels, rnd)}
    print(f"  (random-label control  : Purity {purity(clusters, rlabels):.3f}  "
          f"NMI {nmi(clusters, rlabels):.3f}  ARI {adjusted_rand(clusters, rlabels):.3f})")
    print("VERDICT:", "clustering recovers relation structure well above chance"
          if nmi(clusters, labels) > 0.3 else "weak recovery — see numbers (honest)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
