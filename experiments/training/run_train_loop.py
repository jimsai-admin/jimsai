"""De-LLM training loop — measure → ingest → re-measure → keep/rollback → promote.

Makes the autonomous training agent's core concrete and DE-LLM (no Groq, no
synthetic generation). It enriches BASE-model coverage from SOURCED data and
guards every step with a measured metric, rolling back anything that does not
help or that regresses gap-honesty — the discipline the common-vocabulary work
proved by hand.

The metric here is the OFFLINE messy-extraction quality (milliseconds, no
backend): for messy facts in a language, does the CLL extract the RIGHT entities
(precision = extracted literals that are true entities; recall = true entities
found)? This is the exact quantity the noun-only-lexicon gap broke and common
vocabulary fixed, so a coverage ingestion moves it directly.

The loop:
  1. MEASURE  a language's extraction quality.
  2. If precision < target ⇒ a coverage GAP.
  3. TARGET   the gap with a SOURCED ingestion action (common-vocabulary here;
              broaden_lexicon / ELE-construction discovery for other gap types).
  4. INGEST   from source (provenance-stamped), reload the base artifact.
  5. RE-MEASURE; KEEP iff precision improved AND recall did not drop (gap-honesty
              guard); else ROLL BACK.
  6. PROMOTE-GATE: report whether the gated mechanism now clears its bar.

Run: .venv/Scripts/python.exe experiments/training/run_train_loop.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "prototype"))
import os  # noqa: E402

os.environ.setdefault("JIMS_CONCEPT_INDEX", "on")
from jimsai.cll_shadow import get_shadow, surface_key  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Messy facts per language with their TRUE entities (the ground truth to hit).
GOLD = {
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
}


def measure(lang: str) -> dict:
    """Offline extraction quality on this language's messy facts."""
    sh = get_shadow()
    tp = fp = fn = 0
    for text, gold in GOLD[lang]:
        _c, lits = sh.encode(text, mode="document")
        got = {x[2:] for x in lits}
        tp += len(got & gold)
        fp += len(got - gold)
        fn += len(gold - got)
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    return {"precision": round(prec, 3), "recall": round(rec, 3), "tp": tp, "fp": fp, "fn": fn}


def _common_keys_for(lang: str) -> set[str]:
    """The common-vocabulary surface keys for a language from the sourced file
    (this stands in for the ingest+reload of the base artifact)."""
    path = Path(__file__).resolve().parents[1] / "concept_model" / "data" / "common_words.jsonl"
    keys: set[str] = set()
    if path.exists():
        for line in path.open(encoding="utf-8"):
            row = json.loads(line)
            if row.get("lang") == lang:
                k = surface_key(row["surface"])
                if k:
                    keys.add(k)
    return keys


def train_language(lang: str, target_precision: float = 0.8) -> dict:
    sh = get_shadow()
    # Snapshot the base artifact so we can ROLL BACK.
    snapshot = set(sh._common_words)
    lang_common = _common_keys_for(lang)          # read the source ONCE
    lang_keys = snapshot & lang_common
    # Start from the GAP state: this language's common words NOT yet ingested.
    sh._common_words = snapshot - lang_keys
    sh._bg_df.clear()
    before = measure(lang)

    log = [f"[{lang}] MEASURE (gap state): precision={before['precision']:.0%} recall={before['recall']:.0%}"]
    if before["precision"] >= target_precision:
        sh._common_words = snapshot
        return {"lang": lang, "action": "none", "before": before, "after": before,
                "kept": True, "promotable": True, "log": log + ["  no gap — skip"]}

    log.append(f"  GAP (precision < {target_precision:.0%}) → TARGET: ingest common vocabulary ({lang})")
    # INGEST from source (reload the language's common words into the base set).
    ingested = lang_common
    sh._common_words = (snapshot - lang_keys) | ingested
    after = measure(lang)
    log.append(f"  INGEST {len(ingested)} common words → RE-MEASURE: "
               f"precision={after['precision']:.0%} recall={after['recall']:.0%}")

    # KEEP iff precision improved AND recall did not regress (gap-honesty guard).
    improved = after["precision"] > before["precision"] + 1e-9
    no_regress = after["recall"] >= before["recall"] - 1e-9
    kept = improved and no_regress
    if kept:
        log.append(f"  KEEP ✓ (precision {before['precision']:.0%}→{after['precision']:.0%}, recall held)")
        final_state = (snapshot - lang_keys) | ingested
    else:
        log.append(f"  ROLL BACK ✗ (improved={improved}, recall_ok={no_regress})")
        final_state = snapshot
        after = before
    sh._common_words = final_state
    promotable = after["precision"] >= target_precision and after["recall"] >= 0.8
    log.append(f"  PROMOTE-GATE: precision {after['precision']:.0%} ≥ {target_precision:.0%} "
               f"and recall ≥ 80% → {'PROMOTABLE' if promotable else 'still gated'}")
    return {"lang": lang, "action": "ingest_common_vocab", "before": before, "after": after,
            "kept": kept, "promotable": promotable, "log": log}


def main() -> int:
    print("=" * 72)
    print("De-LLM training loop — measure → ingest(source) → re-measure → keep/rollback → promote")
    print("=" * 72)
    results = []
    for lang in ("en", "fr"):
        r = train_language(lang)
        for line in r["log"]:
            print(line)
        print("-" * 72)
        results.append(r)
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "train_loop.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    gains = [r for r in results if r["kept"] and r["action"] != "none"]
    print(f"kept {len(gains)}/{len(results)} ingestions; "
          f"{sum(r['promotable'] for r in results)}/{len(results)} languages now promotable")
    print("VERDICT:", "PASS — de-LLM loop measures a real gap, closes it from source, guards gap-honesty, gates promotion"
          if gains and all(r["after"]["recall"] >= r["before"]["recall"] for r in results)
          else "MIXED — see log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
