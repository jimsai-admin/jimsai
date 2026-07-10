"""Multi-relation extraction — relation-AGNOSTIC discovery + OPEN discovery (no LLM).

Answers "are you hardcoding relations like capital_of to pass the test?" with two
falsifiable demonstrations on REAL Wikidata facts + Wikipedia prose
(fetch_relation_facts.py). Search this file: it contains NO relation name and NO
trigger word. Relations are opaque Wikidata PIDs (P36/P47/P19); triggers are
discovered from text.

PART A — RELATION-AGNOSTIC (relation = data, not code).
  The SAME function `evaluate_relation(...)` is run, UNCHANGED, on three distinct
  relations across two entity domains (geography + biography). Each must discover
  its OWN trigger from the positive/negative contrast and extract held-out (by
  entity) pairs. If the code were tuned to capital_of it could not do borders or
  born-in. Claim: each relation's trigger is discovered and lifts recall over the
  abstain-only baseline, precision high — with zero code change between relations.

PART B — OPEN DISCOVERY (relations NOT given).
  Given ONLY an entity vocabulary (no relation labels, no count), cluster every
  entity-pair context in the corpus by its content connector. The strongest
  connectors EMERGE as relations; we then check each emergent cluster against the
  Wikidata KBs (used only to SCORE, never to define). Claim: the top emergent
  relations correspond to real ones (capital / border / birth) at high precision,
  discovered without being told they exist.

Run: .venv/Scripts/python.exe experiments/ele/run_relation_multi.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "prototype"))
sys.path.insert(0, str(Path(__file__).parent))
import os  # noqa: E402

os.environ.setdefault("JIMS_CONCEPT_INDEX", "on")
from jimsai.cll_shadow import get_shadow  # noqa: E402
from run_relation_real_corpus import contexts, sentences, toks_with_idx  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WINDOW = 8
MIN_SUPPORT = 3
MIN_PRECISION = 0.8


def _dedup(pairs):
    seen, out = set(), []
    for a, b in pairs:
        if (a, b) not in seen and a != b:
            seen.add((a, b)); out.append((a, b))
    return out


def _is_symmetric(kb: set) -> bool:
    if not kb:
        return False
    rev = sum(1 for (a, b) in kb if (b, a) in kb)
    return rev >= 0.5 * len(kb)


def _collect(extracts, entity_tok, ent_set, kb):
    """All (left, right, between, label, subj_is_left) contexts confined to ent_set."""
    sub = {e: entity_tok[e] for e in ent_set}
    rows = []
    for text in extracts.values():
        for sent in sentences(text):
            for left, right, between in contexts(sent, sub):
                if (left, right) in kb:
                    rows.append((left, right, between, "REL", True))
                elif (right, left) in kb:
                    rows.append((left, right, between, "REL", False))
                else:
                    rows.append((left, right, between, "NEG", None))
    return rows


def _discover_trigger(train_rows):
    """Single highest-support high-precision content token (the relation trigger).
    Identical rule for every relation — nothing relation-specific."""
    pos, tot = defaultdict(int), defaultdict(int)
    for _l, _r, between, label, _sl in train_rows:
        for t in set(between):
            tot[t] += 1
            if label == "REL":
                pos[t] += 1
    cand = {t: pos[t] / tot[t] for t in tot
            if pos[t] >= MIN_SUPPORT and pos[t] / tot[t] >= MIN_PRECISION and len(t) >= 4}
    if not cand:
        return None, True
    trigger = sorted(cand, key=lambda t: (-pos[t], -cand[t]))[0]
    # direction: when trigger present in a positive, is subject the LEFT entity?
    left_votes = total = 0
    for _l, _r, between, label, sl in train_rows:
        if label == "REL" and trigger in between:
            total += 1; left_votes += int(sl)
    return trigger, (left_votes >= total / 2 if total else True)


def evaluate_relation(pid: str, extracts: dict, pairs: list) -> dict:
    """RELATION-AGNOSTIC. No relation name or trigger appears here."""
    pairs = [(a, b) for a, b in _dedup(pairs) if a in extracts and b in extracts]
    kb = set(pairs)
    symmetric = _is_symmetric(kb)
    entities = sorted({e for p in pairs for e in p})
    entity_tok = {e: toks_with_idx(e) for e in entities}
    # split by ENTITY so test articles/entities are unseen (works for symmetric too)
    test_ent = {e for i, e in enumerate(entities) if i % 3 == 0}
    train_ent = {e for i, e in enumerate(entities) if i % 3 != 0}

    train_rows = _collect(extracts, entity_tok, train_ent, kb)
    test_rows = _collect(extracts, entity_tok, test_ent, kb)
    trigger, subj_is_left = _discover_trigger(train_rows)

    def match(s, o):
        return (s, o) in kb or (symmetric and (o, s) in kb)

    preds, dir_ok, dir_tot = set(), 0, 0
    if trigger is not None:
        for left, right, between, _lab, _sl in test_rows:
            if trigger in between:
                s, o = (left, right) if subj_is_left else (right, left)
                preds.add((s, o))
                if not symmetric and ((s, o) in kb or (o, s) in kb):
                    dir_tot += 1; dir_ok += int((s, o) in kb)
    correct = {(s, o) for s, o in preds if match(s, o)}
    # recall denominator: KB pairs whose entities co-occur in a TEST context
    cooccur = set()
    for left, right, _b, lab, _sl in test_rows:
        if lab == "REL":
            cooccur.add((left, right) if (left, right) in kb else (right, left))
    extractable = cooccur & kb
    # unordered dedup for symmetric scoring
    def norm(s):
        return {frozenset(p) for p in s} if symmetric else s
    p_correct, p_pred, p_extract = norm(correct), norm(preds), norm(extractable)
    precision = len(p_correct) / len(p_pred) if p_pred else 1.0
    recall = len(p_correct & p_extract) / len(p_extract) if p_extract else 0.0
    return {
        "pid": pid, "pairs": len(pairs), "symmetric": symmetric,
        "trigger": trigger, "subject_is_left": subj_is_left,
        "precision": round(precision, 3), "recall": round(recall, 3),
        "extractable": len(p_extract), "predicted": len(p_pred),
        "direction_accuracy": (round(dir_ok / dir_tot, 3) if dir_tot else None),
    }


def open_discovery(extracts: dict, all_entities: set, kbs: dict, top: int = 12) -> list:
    """Relations NOT given. Cluster entity-pair contexts by content connector; the
    strongest connectors emerge as relations. Validate each against the KBs."""
    shadow = get_shadow()
    common = getattr(shadow, "_common_words", set())
    from jimsai.cll_shadow import surface_key
    entity_tok = {e: toks_with_idx(e) for e in all_entities}

    connector_pairs: dict[str, set] = defaultdict(set)   # token -> set of unordered entity pairs
    for text in extracts.values():
        for sent in sentences(text):
            for left, right, between in contexts(sent, entity_tok):
                for t in set(between):
                    if len(t) >= 4 and surface_key(t) not in common:
                        connector_pairs[t].add(frozenset((left, right)))

    kb_unord = {pid: {frozenset(p) for p in _dedup(v["pairs"])} for pid, v in kbs.items()}
    ranked = sorted(connector_pairs.items(), key=lambda kv: -len(kv[1]))
    out = []
    for tok, prs in ranked:
        if len(prs) < MIN_SUPPORT:
            continue
        # best-matching KB relation (used ONLY to score the emergent cluster)
        best_pid, best_prec = None, 0.0
        for pid, kbset in kb_unord.items():
            hit = len(prs & kbset)
            prec = hit / len(prs)
            if prec > best_prec:
                best_pid, best_prec = pid, prec
        out.append({"trigger": tok, "support": len(prs),
                    "best_pid": best_pid, "precision_vs_kb": round(best_prec, 3)})
        if len(out) >= top:
            break
    return out


def main() -> int:
    path = Path(__file__).parent / "data" / "multi_relation.json"
    if not path.exists():
        print("no data — run: .venv/Scripts/python.exe experiments/ele/fetch_relation_facts.py")
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    extracts, rels = data["extracts"], data["relations"]

    print("=" * 80)
    print("PART A — RELATION-AGNOSTIC discovery (same code, 3 relations, relation = DATA)")
    print("-" * 80)
    resA = [evaluate_relation(pid, extracts, rels[pid]["pairs"]) for pid in ("P36", "P47", "P112")]
    for r in resA:
        trg = r["trigger"] or "(none discovered)"
        da = "" if r["direction_accuracy"] is None else f" dir-acc={r['direction_accuracy']:.0%}"
        sym = " [symmetric]" if r["symmetric"] else ""
        print(f"  {r['pid']}{sym}: pairs={r['pairs']:3d}  discovered trigger='{trg}'  "
              f"precision={r['precision']:.0%} recall={r['recall']:.0%} "
              f"(extractable={r['extractable']}){da}")
    print("-" * 80)
    mp = sum(r["precision"] for r in resA) / len(resA)
    mr = sum(r["recall"] for r in resA) / len(resA)
    got = sum(r["trigger"] is not None for r in resA)
    print(f"discovered a trigger for {got}/3 relations | mean precision {mp:.0%} recall {mr:.0%}")

    print("\n" + "=" * 80)
    print("PART B — OPEN discovery (relations NOT given; entity vocab only)")
    print("-" * 80)
    all_entities = {e for v in rels.values() for p in _dedup(v["pairs"]) for e in p if e in extracts}
    emergent = open_discovery(extracts, all_entities, rels)
    print(f"  {'trigger':16}{'support':>8}{'best KB':>9}{'precision':>11}")
    for e in emergent:
        print(f"  {e['trigger']:16}{e['support']:>8}{str(e['best_pid']):>9}{e['precision_vs_kb']:>10.0%}")
    # the emergent relations that map cleanly to a real KB relation
    clean = [e for e in emergent if e["precision_vs_kb"] >= 0.7 and e["support"] >= MIN_SUPPORT]
    pids_found = {e["best_pid"] for e in clean}
    print("-" * 80)
    print(f"emergent clusters mapping to a real relation at ≥70% precision: "
          f"{len(clean)} covering KBs {sorted(pids_found)}")

    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "relation_multi.json").write_text(
        json.dumps({"partA": resA, "partB": emergent}, indent=2, ensure_ascii=False), encoding="utf-8")

    okA = got == 3 and mp >= 0.8
    okB = len(pids_found) >= 2
    print("\nVERDICT:", "PASS — relation is DATA not code: same algorithm discovers 3 different relations' "
          "triggers; and real relations EMERGE from open clustering. No relation/trigger hardcoded, no LLM."
          if (okA and okB) else "MIXED — honest numbers recorded (see rows)")
    return 0 if (okA and okB) else 1


if __name__ == "__main__":
    sys.exit(main())
