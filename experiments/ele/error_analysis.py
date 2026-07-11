"""Phase 11 — automatic error analysis: WHY does recall miss? (no LLM)

Turns the low F1 into quantified observations instead of anecdotes. For every KB
pair, classify the outcome of the discovered-trigger extractor into a taxonomy,
so the recall gap is attributed to concrete causes — which directly say whether
the fix is more CORPUS (Phase 4), more SURFACE FORMS (Phase 7 lexicon), better
ENTITY LINKING (coreference), or the KB:

  extracted_ok          – found, correct.
  no_cooccurrence       – the two entities never appear within the window in any
                          sentence → needs more text (Phase 4) / coreference.
  coref_alias_gap       – they never co-occur by full label, but ONE entity's
                          head token does appear near the other → a coreference /
                          alias miss (e.g. "Fuchs" for "Klaus Fuchs").
  cooccur_no_trigger    – they co-occur in-window but no discovered surface is
                          between them → a paraphrase the lexicon (Phase 7) must
                          learn.
  direction_error       – extracted but subject/object reversed.

Run: .venv/Scripts/python.exe experiments/ele/error_analysis.py [corpus.json]
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_relations import direction, load, sentences, toks  # noqa: E402
from adaptive_lexicon import discover_topk, entity_token_set  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def classify_relation(pid, r, extracts, exclude):
    trigs = discover_topk(r["rows"], 5, exclude)
    trig = {t for t, _c, _e in trigs}
    subj_left = direction(r["rows"], trigs[0][0]) if trigs else True

    # pairs that co-occur in-window (present in REL rows), and whether a trigger sits between
    in_window, has_trig = {}, {}
    for left, right, between, label, _sl in r["rows"]:
        if label == "REL":
            fp = frozenset((left, right))
            in_window[fp] = (left, right)
            if trig & set(between):
                has_trig[fp] = (left, right)

    # head tokens for coreference/alias detection (last token of a multiword name)
    head = {e: toks(e)[-1] for e in r["entities"] if toks(e)}
    lowered = {e: " " + e.lower() + " " for e in r["entities"]}

    out = Counter()
    for a, b in r["kb"]:
        fp = frozenset((a, b))
        if fp in has_trig:
            l, rr = has_trig[fp]
            s, o = (l, rr) if subj_left else (rr, l)
            out["extracted_ok" if (s, o) in r["kb"] or (r["symmetric"] and (o, s) in r["kb"])
                else "direction_error"] += 1
        elif fp in in_window:
            out["cooccur_no_trigger"] += 1
        else:
            # do their FULL labels ever share a sentence (beyond window)? and do heads co-occur?
            shares_sentence = heads_cooccur = False
            ha, hb = head.get(a), head.get(b)
            for text in extracts.values():
                low = text.lower()
                if a.lower() in low and b.lower() in low:
                    for sent in sentences(low):
                        if a.lower() in sent and b.lower() in sent:
                            shares_sentence = True
                        if ha and hb and (" " + ha + " ") in (" " + sent + " ") and (" " + hb + " ") in (" " + sent + " "):
                            heads_cooccur = True
                    if shares_sentence:
                        break
            if heads_cooccur and not shares_sentence:
                out["coref_alias_gap"] += 1
            else:
                out["no_cooccurrence"] += 1
    return out


def main() -> int:
    fname = sys.argv[1] if len(sys.argv) > 1 else "multi_relation.json"
    print(f"corpus: {fname}")
    extracts, rels = load(fname)
    exclude = entity_token_set(rels)
    total = Counter()
    print("=" * 76)
    print("PHASE 11 — error taxonomy over every KB pair (recall attribution)")
    print("-" * 76)
    for pid, r in rels.items():
        c = classify_relation(pid, r, extracts, exclude)
        total.update(c)
        n = sum(c.values())
        print(f"  {pid}: " + "  ".join(f"{k}={c[k]}" for k in
              ("extracted_ok", "direction_error", "cooccur_no_trigger", "coref_alias_gap", "no_cooccurrence")) + f"   (n={n})")
    print("-" * 76)
    N = sum(total.values())
    order = ["extracted_ok", "direction_error", "cooccur_no_trigger", "coref_alias_gap", "no_cooccurrence"]
    for k in order:
        print(f"  {k:20} {total[k]:5d}  {total[k] / N:6.1%}")
    print("-" * 76)
    fixable_corpus = total["no_cooccurrence"] / N
    fixable_lexicon = total["cooccur_no_trigger"] / N
    fixable_coref = total["coref_alias_gap"] / N
    print(f"  recall gap attribution → more CORPUS (Phase 4): {fixable_corpus:.0%} | "
          f"more SURFACES/lexicon (Phase 7): {fixable_lexicon:.0%} | coreference: {fixable_coref:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
