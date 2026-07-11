"""Scientific validation of trigger-discovery relation extraction (no LLM).

Not more heuristics — MEASUREMENT. Runs the SAME relation-agnostic discovery under
rigorous protocols so the method's generality is evidenced, not asserted.

  Phase 1  k-fold ENTITY-DISJOINT cross-validation → mean ± 95% CI (t) for
           precision / recall / F1 (no single lucky split).
  Phase 2  BASELINES for trigger selection, all on the identical content-token
           candidate set (so the comparison isolates the RANKING signal):
             random · most-frequent-connector · frequency-only (ignore negatives)
             · PMI(token;positive) · TF-IDF   vs   our positive/negative CONTRAST.
  Phase 6  ABLATION of the contrast method: remove negatives / precision threshold
           / support threshold / direction inference / stop-word removal / symmetry
           detection — F1 delta shows which idea actually contributes.

Everything is measured on REAL Wikidata facts + Wikipedia prose
(fetch_relation_facts.py), entity-disjoint, with complete KBs. No relation name or
trigger word appears in this file.

Run: .venv/Scripts/python.exe experiments/ele/validate_relations.py
"""

from __future__ import annotations

import json
import math
import re
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

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
WINDOW = 8
MIN_SUPPORT = 3
MIN_PRECISION = 0.8
KFOLD = 5
# two-sided 95% t-values by degrees of freedom (fallback 1.96 for large df)
_T95 = {1: 12.71, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 14: 2.145, 19: 2.093, 29: 2.045}

_COMMON = None


def common_words() -> set:
    global _COMMON
    if _COMMON is None:
        _COMMON = set(getattr(get_shadow(), "_common_words", set()))
    return _COMMON


def toks(s: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD.finditer(s)]


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def is_content(t: str) -> bool:
    return len(t) >= 4 and surface_key(t) not in common_words()


def build_rows(extracts: dict, entities: set, kb: set) -> list:
    """All (left, right, between, label, subj_is_left) contexts over the corpus.
    Efficient entity spans via a first-token index."""
    etok = {e: toks(e) for e in entities}
    by_first = defaultdict(list)
    for e, tk in etok.items():
        if tk:
            by_first[tk[0]].append((e, tk))
    rows = []
    for text in extracts.values():
        for sent in sentences(text):
            tokens = toks(sent)
            spans = []  # (entity, start, end)
            covered = [False] * len(tokens)
            i = 0
            while i < len(tokens):
                best = None
                for e, tk in by_first.get(tokens[i], ()):
                    L = len(tk)
                    if tokens[i:i + L] == tk and not any(covered[i:i + L]):
                        if best is None or L > len(best[1]):
                            best = (e, tk)
                if best is not None:
                    L = len(best[1])
                    spans.append((best[0], i, i + L))
                    for j in range(i, i + L):
                        covered[j] = True
                    i += L
                else:
                    i += 1
            # closest co-occurrence of each distinct entity pair within WINDOW
            best_pair = {}
            for a in range(len(spans)):
                for b in range(len(spans)):
                    if a == b:
                        continue
                    ea, sa, xa = spans[a]; eb, sb, xb = spans[b]
                    if ea == eb or xa > sb:
                        continue
                    gap = sb - xa
                    if gap > WINDOW:
                        continue
                    key = (ea, eb)
                    if key not in best_pair or gap < best_pair[key][1]:
                        best_pair[key] = (tokens[xa:sb], gap)
            for (ea, eb), (between, _g) in best_pair.items():
                if (ea, eb) in kb:
                    rows.append((ea, eb, between, "REL", True))
                elif (eb, ea) in kb:
                    rows.append((ea, eb, between, "REL", False))
                else:
                    rows.append((ea, eb, between, "NEG", None))
    return rows


def _counts(rows, content_only=True):
    pos, tot = defaultdict(int), defaultdict(int)
    for _l, _r, between, label, _sl in rows:
        for t in set(between):
            if not content_only or is_content(t):
                tot[t] += 1
                if label == "REL":
                    pos[t] += 1
    return pos, tot


# ---- trigger-selection methods (each returns a token or None) -----------------
def m_contrast(rows, rng, *, use_neg=True, prec_thr=MIN_PRECISION, sup_thr=MIN_SUPPORT, content_only=True):
    pos, tot = _counts(rows, content_only)
    cand = {}
    for t, tt in tot.items():
        prec = pos[t] / tt if use_neg else 1.0
        if pos[t] >= sup_thr and prec >= prec_thr:
            cand[t] = (pos[t], prec)
    if not cand:
        return None
    return sorted(cand, key=lambda t: (-cand[t][0], -cand[t][1]))[0]


def m_random(rows, rng):
    pos, _ = _counts(rows)
    pool = [t for t, c in pos.items() if c >= 1]
    return rng.choice(pool) if pool else None


def m_most_frequent(rows, rng):
    _pos, tot = _counts(rows)
    return max(tot, key=lambda t: tot[t]) if tot else None


def m_frequency_only(rows, rng):
    pos, _ = _counts(rows)
    pos = {t: c for t, c in pos.items() if c >= MIN_SUPPORT}
    return max(pos, key=lambda t: pos[t]) if pos else None


def m_pmi(rows, rng):
    pos, tot = _counts(rows)
    n_all = sum(tot.values()) or 1
    n_pos = sum(pos.values()) or 1
    best, best_s = None, -1e9
    for t in tot:
        if pos[t] < MIN_SUPPORT:
            continue
        pmi = math.log((pos[t] / n_pos) / (tot[t] / n_all))
        if pmi > best_s:
            best, best_s = t, pmi
    return best


def m_tfidf(rows, rng):
    pos, tot = _counts(rows)
    n_ctx = len(rows) or 1
    best, best_s = None, -1e9
    for t in tot:
        if pos[t] < MIN_SUPPORT:
            continue
        score = pos[t] * math.log(n_ctx / (1 + tot[t]))
        if score > best_s:
            best, best_s = t, score
    return best


METHODS = {"contrast(ours)": m_contrast, "random": m_random,
           "most_frequent": m_most_frequent, "frequency_only": m_frequency_only,
           "PMI": m_pmi, "TF-IDF": m_tfidf}


def direction(rows, trigger):
    lv = tot = 0
    for _l, _r, between, label, sl in rows:
        if label == "REL" and trigger in between:
            tot += 1; lv += int(sl)
    return lv >= tot / 2 if tot else True


def evaluate(test_rows, trigger, subj_left, kb, symmetric, *, use_dir=True, use_sym=True):
    """Return COUNTS (n_correct, n_pred, n_extractable) so folds can be POOLED
    (micro-average) — far more stable than averaging tiny per-fold F1 scores."""
    sym = symmetric and use_sym
    preds = set()
    if trigger is not None:
        for left, right, between, _lab, _sl in test_rows:
            if trigger in between:
                s, o = (left, right) if (subj_left or not use_dir) else (right, left)
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


def micro_prf(nc, npred, nextract):
    P = nc / npred if npred else (1.0 if not nextract else 0.0)
    R = nc / nextract if nextract else 0.0
    F = 2 * P * R / (P + R) if (P + R) else 0.0
    return P, R, F


def is_symmetric(kb):
    return bool(kb) and sum((b, a) in kb for a, b in kb) >= 0.5 * len(kb)


def kfold_entities(entities, k, seed=0):
    ents = sorted(entities)
    Random(seed).shuffle(ents)
    return [set(ents[i::k]) for i in range(k)]


def cv_method(rows, entities, kb, symmetric, method, *, seed=0, **eval_kw):
    """Entity-disjoint k-fold; POOL fold counts → one micro-averaged (P,R,F1) per
    relation. Also returns total extractable test pairs (statistical weight)."""
    folds = kfold_entities(entities, KFOLD, seed)
    rng = Random(seed)
    NC = NP = NE = 0
    for i, test_ent in enumerate(folds):
        train_ent = set().union(*[f for j, f in enumerate(folds) if j != i])
        train_rows = [r for r in rows if r[0] in train_ent and r[1] in train_ent]
        test_rows = [r for r in rows if r[0] in test_ent and r[1] in test_ent]
        trig = method(train_rows, rng)
        sd = direction(train_rows, trig) if trig else True
        nc, npred, ne = evaluate(test_rows, trig, sd, kb, symmetric, **eval_kw)
        NC += nc; NP += npred; NE += ne
    return micro_prf(NC, NP, NE), NE


def agg(vals):
    """mean, std, 95% CI half-width over a list of scalars."""
    n = len(vals)
    if n == 0:
        return None
    m = sum(vals) / n
    if n == 1:
        return m, 0.0, 0.0
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    sd = math.sqrt(var)
    t = _T95.get(n - 1, 1.96)
    return m, sd, t * sd / math.sqrt(n)


def load(fname="multi_relation.json"):
    path = Path(__file__).parent / "data" / fname
    data = json.loads(path.read_text(encoding="utf-8"))
    extracts = data["extracts"]
    rels = {}
    for pid, rel in data["relations"].items():
        pairs = [(a, b) for a, b in rel["pairs"] if a in extracts and b in extracts and a != b]
        kb = set(pairs)
        entities = {e for p in pairs for e in p}
        rels[pid] = {"kb": kb, "entities": entities, "symmetric": is_symmetric(kb),
                     "rows": build_rows(extracts, entities, kb)}
    return extracts, rels


def main() -> int:
    fname = sys.argv[1] if len(sys.argv) > 1 else "multi_relation.json"
    print(f"corpus: {fname}")
    extracts, rels = load(fname)
    pids = list(rels)

    print("=" * 88)
    print(f"PHASE 1+2 — {KFOLD}-fold ENTITY-DISJOINT CV, MICRO-averaged F1 per relation")
    print("(pooled fold counts). Methods share the content-token candidate set; only the")
    print("RANKING differs. Macro-mean ±95% CI is over relations. REAL Wikidata+Wikipedia.")
    print("-" * 88)
    header = f"{'relation':8}{'sym':>4}{'pairs':>6}{'ext':>5}  " + "".join(f"{m:>15}" for m in METHODS)
    print(header)
    per_method_F = defaultdict(list)
    for pid in pids:
        r = rels[pid]
        cells, ext = [], 0
        for mname, mfn in METHODS.items():
            (P, R, F), NE = cv_method(r["rows"], r["entities"], r["kb"], r["symmetric"], mfn)
            ext = NE
            cells.append(f"{F:>14.0%}")
            per_method_F[mname].append(F)
        print(f"{pid:8}{('Y' if r['symmetric'] else 'N'):>4}{len(r['kb']):>6}{ext:>5}  " + "".join(cells))
    print("-" * 88)
    macro = []
    for mname in METHODS:
        a = agg(per_method_F[mname])
        macro.append((mname, a[0]))
        print(f"  macro-mean F1  {mname:16} {a[0]:>6.1%}  ±{a[2]:.1%} (95% CI over {len(pids)} relations)")
    best_base = max((m for n, m in macro if n != "contrast(ours)"), default=0)
    ours = dict(macro)["contrast(ours)"]
    print(f"\n  → contrast(ours) {ours:.1%} vs best baseline {best_base:.1%} "
          f"(lift {ours - best_base:+.1%})")

    print("\n" + "=" * 88)
    print("PHASE 6 — ABLATION of contrast(ours): macro-mean F1 when a component is removed")
    print("-" * 88)
    ablations = {
        "full": dict(),
        "-negatives": dict(method_kw=dict(use_neg=False)),
        "-precision_thr": dict(method_kw=dict(prec_thr=0.0)),
        "-support_thr": dict(method_kw=dict(sup_thr=1)),
        "-direction": dict(eval_kw=dict(use_dir=False)),
        "-symmetry": dict(eval_kw=dict(use_sym=False)),
        "-stopword_rm": dict(method_kw=dict(content_only=False)),
    }
    full_f1 = None
    for aname, cfg in ablations.items():
        mkw = cfg.get("method_kw", {}); ekw = cfg.get("eval_kw", {})
        def method(rows, rng, _mkw=mkw):
            return m_contrast(rows, rng, **_mkw)
        vals = []
        for pid in pids:
            r = rels[pid]
            (P, R, F), _NE = cv_method(r["rows"], r["entities"], r["kb"], r["symmetric"], method, **ekw)
            vals.append(F)
        m = sum(vals) / len(vals) if vals else 0.0
        if aname == "full":
            full_f1 = m
        delta = "" if full_f1 is None or aname == "full" else f"  (Δ {m - full_f1:+.1%})"
        print(f"  {aname:16} macro-F1 {m:>6.1%}{delta}")

    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "validate_relations.json").write_text(json.dumps(
        {"methods_macro_F1": dict(macro)}, indent=2), encoding="utf-8")
    print("\nVERDICT:", "PASS — contrast beats every simple baseline under entity-disjoint CV"
          if ours >= best_base else "MIXED — see table")
    return 0


if __name__ == "__main__":
    sys.exit(main())
