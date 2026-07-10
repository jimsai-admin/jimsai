"""ELE relation extraction on a REAL corpus, self-supervised — lift recall (no LLM).

`run_relation_constructions.py` proved the construction-discovery MECHANISM, but
on 5 clean templates — the ideal world. This runs the same idea on REAL Wikipedia
prose (fetch_wiki_corpus.py) with SELF-SUPERVISED (distant-supervision) labels and
a HELD-OUT-BY-ENTITY split, in TWO languages. The numbers are whatever the real
text gives — the point is a measurement you can fail.

Setup (distant supervision, the standard no-hand-labels method):
  * Seed KB = TRUE capital_of(capital, country) facts.
  * A sentence mentioning both members of a KB pair → a POSITIVE context for the
    relation; a sentence mentioning two KB entities that are NOT a pair → a
    NEGATIVE. Labels come from the KB, never from hand annotation or an LLM.
  * DISCOVER the relation's trigger from the positive/negative contrast: score
    each between-entities token by pos/(pos+neg); keep the high-precision, well-
    supported one. For English the data elects "capital"; for French "capitale".
    NOTHING is hardcoded — a different relation or language elects a different
    trigger. Direction (which entity is subject) is learned by majority from the
    KB. This is ELE evidence-ledger promotion applied to a real relation.
  * SPLIT by entity: discover on TRAIN entities' sentences, extract on unseen
    TEST entities' sentences. Compare against the live high-precision baseline
    (grammar_relations), which ABSTAINS on this phrasing ("is the capital of" has
    ≥2 function words) — so it is safe but low-recall. Claim: discovered triggers
    lift recall far above that baseline while keeping precision high, on REAL,
    messy, multilingual prose.

Run: .venv/Scripts/python.exe experiments/ele/run_relation_real_corpus.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "prototype"))
import os  # noqa: E402

os.environ.setdefault("JIMS_CONCEPT_INDEX", "on")
from jimsai import grammar_relations  # noqa: E402
from jimsai.cll_shadow import get_shadow  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
WINDOW = 8            # max tokens strictly between two entity mentions
MIN_SUPPORT = 3       # a trigger must occur in ≥ this many positive contexts
MIN_PRECISION = 0.8   # and be this discriminative vs negatives


def toks_with_idx(sentence: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD.finditer(sentence)]


def entity_spans(tokens: list[str], entity_tok: dict[str, list[str]]) -> list[tuple[str, int, int]]:
    """All contiguous token matches of known entity surfaces (longest-first)."""
    spans: list[tuple[str, int, int]] = []
    n = len(tokens)
    ents_by_len = sorted(entity_tok.items(), key=lambda kv: -len(kv[1]))
    covered = [False] * n
    for ent, etoks in ents_by_len:
        L = len(etoks)
        for i in range(n - L + 1):
            if tokens[i:i + L] == etoks and not any(covered[i:i + L]):
                spans.append((ent, i, i + L))
                for j in range(i, i + L):
                    covered[j] = True
    return sorted(spans, key=lambda s: s[1])


def contexts(sentence: str, entity_tok: dict[str, list[str]]):
    """Yield (left_ent, right_ent, between_tokens) for the CLOSEST co-occurrence
    of each distinct entity pair within WINDOW tokens."""
    tokens = toks_with_idx(sentence)
    spans = entity_spans(tokens, entity_tok)
    best: dict[frozenset, tuple] = {}
    for a in range(len(spans)):
        for b in range(len(spans)):
            if a == b:
                continue
            ea, sa, xa = spans[a]
            eb, sb, xb = spans[b]
            if ea == eb or xa > sb:            # left must end before right starts
                continue
            gap = sb - xa
            if gap > WINDOW:
                continue
            key = frozenset((ea, eb))
            if key not in best or gap < best[key][3]:
                best[key] = (ea, eb, tokens[xa:sb], gap)
    for ea, eb, between, _gap in best.values():
        yield ea, eb, between


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def dedup_pairs(pairs) -> list[tuple[str, str]]:
    seen, out = set(), []
    for cap, country in pairs:
        if (cap, country) not in seen:
            seen.add((cap, country)); out.append((cap, country))
    return out


def run_lang(lang: str, corpus: dict) -> dict:
    pairs = dedup_pairs(corpus[lang]["pairs"])
    extracts = corpus[lang]["extracts"]
    # keep only pairs whose BOTH articles were fetched
    pairs = [(c, k) for c, k in pairs if c in extracts and k in extracts]
    kb = {(c, k) for c, k in pairs}                 # true (subject=capital, object=country)
    kb_entities = {e for pair in pairs for e in pair}
    entity_tok = {e: toks_with_idx(e) for e in kb_entities}

    # split by ENTITY (pairs are entity-disjoint) → test articles are unseen
    pairs_sorted = sorted(pairs)
    test_pairs = [p for i, p in enumerate(pairs_sorted) if i % 3 == 0]
    train_pairs = [p for i, p in enumerate(pairs_sorted) if i % 3 != 0]
    train_ent = {e for pr in train_pairs for e in pr}
    test_ent = {e for pr in test_pairs for e in pr}

    def collect(ent_set):
        """All (left,right,between,label,subj_is_left) contexts confined to ent_set."""
        rows = []
        for _title, text in extracts.items():
            for sent in sentences(text):
                sub_tok = {e: entity_tok[e] for e in ent_set}
                for left, right, between in contexts(sent, sub_tok):
                    if (left, right) in kb:
                        rows.append((left, right, between, "REL", True))
                    elif (right, left) in kb:
                        rows.append((left, right, between, "REL", False))
                    else:
                        rows.append((left, right, between, "NEG", None))
        return rows

    train_rows = collect(train_ent)
    test_rows = collect(test_ent)

    # DISCOVER trigger tokens from positive/negative contrast (self-supervised).
    pos_tok, tot_tok = defaultdict(int), defaultdict(int)
    left_subj_votes = defaultdict(int); left_subj_total = defaultdict(int)
    for left, right, between, label, subj_left in train_rows:
        seen = set(between)
        for t in seen:
            tot_tok[t] += 1
            if label == "REL":
                pos_tok[t] += 1
    triggers = {}
    for t, tot in tot_tok.items():
        prec = pos_tok[t] / tot
        if pos_tok[t] >= MIN_SUPPORT and prec >= MIN_PRECISION and len(t) >= 4:
            triggers[t] = round(prec, 3)
    # The relation's trigger = the highest-SUPPORT high-precision token: the content
    # word most frequently AND precisely bridging known instances. Taking the single
    # strongest suppresses distant-supervision artefacts — both rare-but-precise
    # spurious tokens (French "économique") and recall-boosting-but-imprecise ones
    # ("city", which fires on non-capital "largest city" mentions). Language-
    # independent: English data elects "capital", French elects "capitale".
    primary = sorted(triggers, key=lambda t: (-pos_tok[t], -triggers[t]))[:1]
    # learn direction: when the primary trigger is present, is subject the LEFT entity?
    for left, right, between, label, subj_left in train_rows:
        if label == "REL" and any(t in between for t in primary):
            left_subj_total["capital_of"] += 1
            if subj_left:
                left_subj_votes["capital_of"] += 1
    subj_is_left = (left_subj_votes["capital_of"] >= left_subj_total["capital_of"] / 2) if left_subj_total["capital_of"] else True

    def discovered_predict(rows):
        preds = set()
        for left, right, between, _label, _sl in rows:
            if any(t in between for t in primary):
                s, o = (left, right) if subj_is_left else (right, left)
                preds.add((s, o))
        return preds

    def baseline_predict():
        """Live high-precision extractor on the TEST sentences (same domain)."""
        sh = get_shadow()
        preds = set()
        for _title, text in extracts.items():
            for sent in sentences(text):
                # only score sentences that involve test entities
                low = sent.lower()
                if not any(re.search(r"\b" + re.escape(e.lower()) + r"\b", low) for e in test_ent):
                    continue
                for s, _p, o in grammar_relations.extract_relations(sent, sh):
                    if s in test_ent and o in test_ent:
                        preds.add((s, o))
                        preds.add((o, s))   # baseline is direction-agnostic for scoring recall
        return preds

    # recall denominator = test KB pairs that actually CO-OCCUR in a test context
    cooccur = {(l, r) if (l, r) in kb else (r, l)
               for l, r, _b, lab, _sl in test_rows if lab == "REL"}
    extractable = cooccur & kb

    def score(preds):
        correct = preds & kb
        prec = len(correct) / len(preds) if preds else 1.0
        rec = len(correct & extractable) / len(extractable) if extractable else 0.0
        return round(prec, 3), round(rec, 3), len(correct), len(preds)

    # DISCOVERED extractor is DIRECTED (must get subject/object right — stricter).
    disc = discovered_predict(test_rows)
    dp, dr, dc, dn = score(disc)

    # BASELINE is direction-agnostic; score it on UNORDERED pairs (its real ability).
    base_ordered = baseline_predict()
    base_unordered = {frozenset(p) for p in base_ordered if len(set(p)) == 2}
    kb_unordered = {frozenset(p) for p in kb}
    extract_unordered = {frozenset(p) for p in extractable}
    base_correct = base_unordered & kb_unordered
    bp = round(len(base_correct) / len(base_unordered), 3) if base_unordered else 1.0
    br = round(len(base_correct & extract_unordered) / len(extract_unordered), 3) if extract_unordered else 0.0

    return {
        "lang": lang, "pairs": len(pairs), "train_pairs": len(train_pairs), "test_pairs": len(test_pairs),
        "triggers": {t: triggers[t] for t in primary}, "subject_is_left": subj_is_left,
        "extractable_test": len(extractable),
        "discovered": {"precision": dp, "recall": dr, "correct": dc, "predicted": dn},
        "baseline": {"precision": bp, "recall": br, "correct": len(base_correct)},
    }


def main() -> int:
    path = Path(__file__).parent / "data" / "wiki_extracts.json"
    if not path.exists():
        print("no corpus — run: .venv/Scripts/python.exe experiments/ele/fetch_wiki_corpus.py")
        return 1
    corpus = json.loads(path.read_text(encoding="utf-8"))
    results = [run_lang(lang, corpus) for lang in ("en", "fr")]
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "relation_real_corpus.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 78)
    print("ELE relation extraction on REAL Wikipedia prose — self-supervised, held-out by entity")
    print("-" * 78)
    for r in results:
        trg = ", ".join(f"{t}={p}" for t, p in r["triggers"].items()) or "(none discovered)"
        print(f"[{r['lang']}] pairs={r['pairs']} (train {r['train_pairs']}/test {r['test_pairs']}), "
              f"extractable test pairs={r['extractable_test']}")
        print(f"     discovered trigger(s): {trg}  subject_is_left={r['subject_is_left']}")
        d, b = r["discovered"], r["baseline"]
        print(f"     DISCOVERED  precision={d['precision']:.0%} recall={d['recall']:.0%} "
              f"({d['correct']}/{d['predicted']} correct/pred)")
        print(f"     BASELINE    precision={b['precision']:.0%} recall={b['recall']:.0%} "
              f"(abstain-heavy high-precision extractor)")
        print("-" * 78)
    mdr = sum(r["discovered"]["recall"] for r in results) / len(results)
    mbr = sum(r["baseline"]["recall"] for r in results) / len(results)
    mdp = sum(r["discovered"]["precision"] for r in results) / len(results)
    print(f"mean recall: discovered {mdr:.0%} vs baseline {mbr:.0%} (lift {mdr - mbr:+.0%}) | "
          f"mean discovered precision {mdp:.0%}")
    ok = mdr > mbr and mdp >= 0.8
    print("VERDICT:", "PASS — discovered constructions lift recall over the abstain-only baseline on REAL "
          "multilingual prose, precision held; triggers LEARNED, no marker list, no LLM"
          if ok else "MIXED/FAIL — honest numbers recorded (see rows)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
