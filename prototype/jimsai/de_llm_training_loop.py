"""De-LLM training loop (production) — measure → ingest(source) → re-measure →
keep/rollback → promote.

The REAL, no-fabrication core the autonomous training agent uses in place of the
old placeholder metrics (the hardcoded 0.88 / +0.02 deltas). Ported from the
validated experiment ``experiments/training/run_train_loop.py`` (VERDICT PASS)
into reusable code. Design guarantees, all load-bearing:

  * Every metric is a REAL measured quantity — the CLL's offline messy-extraction
    precision/recall on nonce, un-memorisable probes. No hardcoded scores, no LLM
    anywhere in the path.
  * A coverage ingestion is KEPT only if it improves precision AND does not
    regress recall (the gap-honesty guard); otherwise it is ROLLED BACK. So the
    loop can only ever help or no-op — never silently trade recall for precision.
  * When a language has NO sourced coverage (low-resource: pcm/yo/sw are not in
    the frequency corpus), the loop measures the gap, tries, finds nothing to
    ingest, rolls back, and reports "still gated — needs learned coverage". That
    honest no-op is the point: it never fabricates an improvement it cannot make.

Not concurrency-safe: it snapshots and restores the shared CLL common-vocabulary
set, so callers must run one training pass at a time (the agent's cycles are
sequential).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .cll_shadow import get_shadow, surface_key


# Messy, colloquial probes per language with their TRUE (nonce) entities. NONCE
# entities cannot be memorised, so extraction accuracy on them measures the
# GENERAL mechanism, not recall of seen strings. These are a held-out measurement
# set (a benchmark), not hardcoded answers wired into the pipeline.
DEFAULT_PROBES: dict[str, list[tuple[str, set[str]]]] = {
    "en": [
        ("kwendal? oh we ended up going with pozidb for that one", {"kwendal", "pozidb"}),
        ("so um zorvenqia actually moved out to trelvax last year", {"zorvenqia", "trelvax"}),
        ("yeah muvrenko basically took over from the old bexil stuff", {"muvrenko", "bexil"}),
    ],
    "fr": [
        ("bon euh zorvenqia est partie vivre à trelvax il y a un an", {"zorvenqia", "trelvax"}),
        ("kwendal on a finalement choisi pozidb pour ce projet", {"kwendal", "pozidb"}),
        ("franchement muvrenko a remplacé le vieux truc bexil", {"muvrenko", "bexil"}),
    ],
    # Low-resource creole — deliberately included. It has NO frequency-corpus
    # source, so the loop will honestly roll back and report it as still gated.
    "pcm": [
        ("kwendal? na pozidb we take use for am", {"kwendal", "pozidb"}),
        ("zorvenqia comot go trelvax since last year", {"zorvenqia", "trelvax"}),
        ("muvrenko na im replace that old bexil own", {"muvrenko", "bexil"}),
    ],
}

_COMMON_WORDS_PATH = (
    Path(__file__).resolve().parents[2]
    / "experiments" / "concept_model" / "data" / "common_words.jsonl"
)


@dataclass
class TrainResult:
    """Outcome of one language's measure→ingest→re-measure→gate pass."""

    lang: str
    action: str                       # "none" | "ingest_common_vocab" | "no_source"
    before: dict                      # {precision, recall, tp, fp, fn}
    after: dict
    kept: bool                        # was the ingestion retained (vs rolled back)?
    promotable: bool                  # does the language now clear the promote bar?
    ingested_terms: int = 0
    log: list[str] = field(default_factory=list)

    @property
    def precision_delta(self) -> float:
        return round(self.after["precision"] - self.before["precision"], 3)

    @property
    def recall_delta(self) -> float:
        return round(self.after["recall"] - self.before["recall"], 3)


def measure_language(lang: str, probes: list[tuple[str, set[str]]] | None = None) -> dict:
    """REAL offline extraction quality on a language's messy probes.

    precision = extracted literals that are true entities;
    recall    = true entities that were found.
    No fabrication: the numbers come straight from the CLL encoder.
    """
    sh = get_shadow()
    rows = probes if probes is not None else DEFAULT_PROBES.get(lang, [])
    tp = fp = fn = 0
    for text, gold in rows:
        _concepts, lits = sh.encode(text, mode="document")
        got = {x[2:] for x in lits}
        tp += len(got & gold)
        fp += len(got - gold)
        fn += len(gold - got)
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    return {"precision": round(prec, 3), "recall": round(rec, 3), "tp": tp, "fp": fp, "fn": fn}


def common_keys_for(lang: str) -> set[str]:
    """Sourced common-vocabulary surface keys for a language (provenance: the
    frequency-list ingestion). Empty for low-resource languages absent from the
    corpus — which is exactly what makes the honest roll-back happen."""
    keys: set[str] = set()
    if _COMMON_WORDS_PATH.exists():
        for line in _COMMON_WORDS_PATH.open(encoding="utf-8"):
            row = json.loads(line)
            if row.get("lang") == lang:
                k = surface_key(row["surface"])
                if k:
                    keys.add(k)
    return keys


def measurable_languages() -> list[str]:
    """Languages we can actually MEASURE (have probes for) — the agent reports
    real scores only for these, never a fabricated number for the rest."""
    return sorted(DEFAULT_PROBES)


def train_language(
    lang: str,
    target_precision: float = 0.8,
    target_recall: float = 0.8,
    probes: list[tuple[str, set[str]]] | None = None,
) -> TrainResult:
    """One de-LLM training pass for a language. Measures the gap from the base
    artifact's gap-state, ingests sourced coverage, re-measures, and KEEPS only
    if precision improved without recall regressing — else rolls back."""
    sh = get_shadow()
    rows = probes if probes is not None else DEFAULT_PROBES.get(lang, [])

    # Snapshot so we can ROLL BACK to exactly the prior base artifact.
    snapshot = set(sh._common_words)
    lang_common = common_keys_for(lang)          # read source ONCE
    lang_keys = snapshot & lang_common
    # Start from the GAP state: this language's common words NOT yet ingested.
    sh._common_words = snapshot - lang_keys
    before = measure_language(lang, rows)
    log = [f"[{lang}] MEASURE (gap state): precision={before['precision']:.0%} recall={before['recall']:.0%}"]

    if before["precision"] >= target_precision and before["recall"] >= target_recall:
        sh._common_words = snapshot
        return TrainResult(lang, "none", before, before, kept=True, promotable=True,
                           log=log + ["  no gap — skip"])

    if not lang_common:
        # Low-resource: nothing sourced to ingest. Honest no-op — never fake it.
        sh._common_words = snapshot
        log.append(f"  GAP but NO sourced coverage for '{lang}' → cannot ingest "
                   f"(low-resource); still gated — needs learned coverage")
        return TrainResult(lang, "no_source", before, before, kept=False,
                           promotable=False, log=log)

    log.append(f"  GAP (precision < {target_precision:.0%}) → TARGET: ingest common vocabulary ({lang})")
    # INGEST from source (reload the language's common words into the base set).
    sh._common_words = (snapshot - lang_keys) | lang_common
    after = measure_language(lang, rows)
    log.append(f"  INGEST {len(lang_common)} common words → RE-MEASURE: "
               f"precision={after['precision']:.0%} recall={after['recall']:.0%}")

    improved = after["precision"] > before["precision"] + 1e-9
    no_regress = after["recall"] >= before["recall"] - 1e-9
    kept = improved and no_regress
    if kept:
        log.append(f"  KEEP ✓ (precision {before['precision']:.0%}→{after['precision']:.0%}, recall held)")
        sh._common_words = (snapshot - lang_keys) | lang_common
    else:
        log.append(f"  ROLL BACK ✗ (improved={improved}, recall_ok={no_regress})")
        sh._common_words = snapshot
        after = before

    promotable = after["precision"] >= target_precision and after["recall"] >= target_recall
    log.append(f"  PROMOTE-GATE: precision {after['precision']:.0%} ≥ {target_precision:.0%} "
               f"and recall ≥ {target_recall:.0%} → {'PROMOTABLE' if promotable else 'still gated'}")
    return TrainResult(lang, "ingest_common_vocab", before, after, kept=kept,
                       promotable=promotable, ingested_terms=len(lang_common), log=log)


def train_all(target_precision: float = 0.8) -> list[TrainResult]:
    """Run one training pass over every measurable language."""
    return [train_language(lang, target_precision) for lang in measurable_languages()]
