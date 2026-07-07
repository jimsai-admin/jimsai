"""Core-argument vs adjunct vs verb-tied classification (spec §3.1.3).

Conjunctive criteria — never a single score:
  1. obligatoriness(tail, verb): fraction of the verb's sentences containing
     the tail ANYWHERE in the sentence (whole-sentence scan, per spec).
  2. cross-verb spread: distinct predicates the tail co-occurs with.

  if max obligatoriness across sufficiently-sampled verbs >= OBLIG_THRESHOLD:
      CORE_ARGUMENT
  elif spread >= SPREAD_THRESHOLD: ADJUNCT
  else: VERB_TIED

OBLIG_THRESHOLD is NOT a hand-tuned constant (E-Rule 2): it is derived from a
calibration corpus generated with a FROZEN, recorded seed, then locked and
applied to test corpora built from fresh seeds.

`spread_weighted` reconstructs the row-12 finding: a score that amplifies
concentrated evidence ranks a verb-tied distractor above every genuine adjunct.
It exists as a negative control — the bug we must not reintroduce — not as a
mechanism. (Reconstruction of the finding's shape; the original formula was in
an uncommitted session.)
"""

from __future__ import annotations

from collections import Counter, defaultdict

from corpus import ADJUNCT, CORE, VERB_TIED, Sentence

SPREAD_THRESHOLD = 3
MIN_SAMPLES_PER_VERB = 30
FROZEN_CALIBRATION_SEED = 20260706  # recorded per E-Rule 2; never resampled

Tail = tuple[str, str]  # (marker_token, "%")


def tail_candidates(promoted_frames: dict[tuple[str, ...], float]) -> list[Tail]:
    """Detachable-tail candidates = promoted bigram frames (fixed, %)."""
    return [f for f in promoted_frames if len(f) == 2 and f[1] == "%" and f[0] != "%"]


def _contains(tokens: list[str], tail: Tail) -> bool:
    marker = tail[0]
    return any(tokens[i] == marker for i in range(len(tokens) - 1))


def tail_stats(tail: Tail, sentences: list[Sentence]) -> dict:
    by_verb_total: Counter = Counter()
    by_verb_with: Counter = Counter()
    for s in sentences:
        by_verb_total[s.verb] += 1
        if _contains(s.tokens, tail):
            by_verb_with[s.verb] += 1
    oblig = {v: by_verb_with[v] / by_verb_total[v]
             for v in by_verb_total if by_verb_with[v]}
    return {
        "obligatoriness": oblig,
        "spread": len(by_verb_with),
        "samples": {v: by_verb_total[v] for v in oblig},
        "occurrences": sum(by_verb_with.values()),
    }


def spread_weighted(tail: Tail, sentences: list[Sentence]) -> float:
    """Concentration-amplifying score (the row-12 bug shape): sum over verbs of
    squared occurrence share x total evidence. Concentrated (single-verb) tails
    score HIGHER than genuinely spread adjuncts — which is exactly backwards,
    and why this must never be the acceptance criterion."""
    stats = tail_stats(tail, sentences)
    total = stats["occurrences"]
    if not total:
        return 0.0
    by_verb = defaultdict(int)
    for s in sentences:
        if _contains(s.tokens, tail):
            by_verb[s.verb] += 1
    concentration = sum((c / total) ** 2 for c in by_verb.values())
    import math
    return concentration * math.log(1 + total)


def classify(tail: Tail, sentences: list[Sentence], oblig_threshold: float,
             spread_threshold: int = SPREAD_THRESHOLD,
             min_samples: int = MIN_SAMPLES_PER_VERB) -> tuple[str, dict]:
    stats = tail_stats(tail, sentences)
    gated = {v: o for v, o in stats["obligatoriness"].items()
             if stats["samples"][v] >= min_samples}
    if not gated:
        return "UNPROVEN", stats  # conservative: too little evidence (spec §3.1.3)
    if max(gated.values()) >= oblig_threshold:
        return CORE, stats
    if stats["spread"] >= spread_threshold:
        return ADJUNCT, stats
    return VERB_TIED, stats


def calibrate_oblig_threshold(cal_sentences: list[Sentence], cal_grammar,
                              min_samples: int = MIN_SAMPLES_PER_VERB) -> float:
    """Derive OBLIG_THRESHOLD from the frozen calibration corpus: midpoint of
    the gap between the highest non-core obligatoriness and the lowest core
    obligatoriness observed with adequate samples. Fails loudly if the classes
    are not separable on calibration data."""
    core_lows: list[float] = []
    noncore_highs: list[float] = []
    for tail, truth in cal_grammar.truth_tails.items():
        stats = tail_stats(tail, cal_sentences)
        gated = [o for v, o in stats["obligatoriness"].items()
                 if stats["samples"][v] >= min_samples]
        if not gated:
            continue
        if truth == CORE:
            core_lows.append(min(gated))
        else:
            noncore_highs.append(max(gated))
    if not core_lows or not noncore_highs:
        raise AssertionError("calibration corpus lacks core or non-core tails")
    lo, hi = max(noncore_highs), min(core_lows)
    if lo >= hi:
        raise AssertionError(
            f"calibration classes not separable: max non-core oblig {lo:.3f} >= "
            f"min core oblig {hi:.3f}")
    return round((lo + hi) / 2, 4)


# ── row 14: morphological suffix generalization ──

def mine_suffixes(token_lists: list[list[str]], min_stems: int = 3,
                  max_len: int = 3) -> dict[str, set[str]]:
    """Data-driven suffix candidates from FINAL-position tokens (attachment
    position, same notion the Evidence Ledger records): trailing substrings
    shared by >= min_stems distinct stems. No suffix string is hardcoded."""
    vocab = {toks[-2] for toks in token_lists
             if len(toks) >= 2 and toks[-1] == "." and len(toks[-2]) > max_len}
    out: dict[str, set[str]] = defaultdict(set)
    for length in range(1, max_len + 1):
        for tok in vocab:
            out[tok[-length:]].add(tok[:-length])
    return {sfx: stems for sfx, stems in out.items() if len(stems) >= min_stems}


def generalize_suffix(token_lists: list[list[str]], suffix: str,
                      collapse: bool, min_count: int = 5,
                      min_diversity: int = 3) -> set[str]:
    """Return the set of tokens recognized as suffix-generalized.

    collapse=False reproduces the row-14 BUG: the tail key keeps the base word
    glued to the suffix — ('park', 'LOC-SUFFIX') style — so every key has
    filler diversity 1, nothing generalizes, and precision/recall are 0.0
    regardless of algorithm quality. collapse=True is the fix: one generalized
    key per suffix, fillers = the stems."""
    keys: dict[tuple[str, str] | str, set[str]] = defaultdict(set)
    counts: Counter = Counter()
    matches: set[str] = set()
    for toks in token_lists:
        if len(toks) < 2 or toks[-1] != ".":
            continue
        tok = toks[-2]  # final attachment position — where the morph corpus marks location
        if tok != "." and len(tok) > len(suffix) and tok.endswith(suffix):
            stem = tok[: -len(suffix)]
            key = suffix if collapse else (stem, suffix)
            keys[key].add(stem)
            counts[key] += 1
            matches.add(tok)
    accepted = {k for k in keys
                if counts[k] >= min_count and len(keys[k]) >= min_diversity}
    if not accepted:
        return set()
    if collapse:
        return matches
    return {stem + suffix for (stem, _sfx) in accepted}  # never reached: diversity==1


def precision_recall(predicted: set[str], truth: set[str]) -> tuple[float, float]:
    if not predicted:
        return 0.0, 0.0
    tp = len(predicted & truth)
    return tp / len(predicted), tp / len(truth)
