"""Stress candidate_bridge on MESSY, MULTILINGUAL, LOW-RESOURCE input (no LLM).

Proves the binding property under real-world conditions: statistical strength —
even the HIGHEST frequency/confidence on noisy multilingual data — never promotes;
only EXECUTION does; and a verified LOW-RESOURCE pattern is first-class.

The corpus is deliberately hostile: mixed natural languages (en/fr/es/pcm) and
programming forms, inconsistent formatting, typo'd comments, a non-Python (JS)
snippet, and an unparseable garbage doc. Among it:
  • a BUGGY `divide` (no zero-guard) appears MOST often, at the HIGHEST discovery
    confidence — the frequency-≠-truth distractor;
  • a CORRECT guarded `divide` appears less often;
  • a CORRECT `clamp` appears ONCE, in a noisy low-resource (pcm) document — the
    low-resource-fairness case.

Expected: the buggy divide is QUARANTINED despite winning on frequency; the correct
divide and the low-resource clamp are VERIFIED and promoted; garbage/JS are skipped
without crashing.

Run: .venv/Scripts/python.exe experiments/absorber/run_bridge_messy.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from candidate_bridge import extract_candidates, promote            # noqa: E402
from grounded_prose_absorber_incremental import GroundedProseAbsorberIncremental  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GUARDED = "def divide(a, b):\n    if b == 0:\n        raise ValueError(\"Division by zero\")\n    return a / b"
BUGGY = "def divide(a, b):\n    return a / b"
CLAMP = "def clamp(x, lo, hi):\n    return max(lo, min(x, hi))"

# Deliberately messy, multilingual, low-resource corpus.
DOCS = [
    {"id": "d1", "lang": "en", "noise": 0.1, "text": f"# utility: safe division\n{GUARDED}\n"},
    {"id": "d2", "lang": "en", "noise": 0.3, "text": f"# safe divide (guarded) -- see tiket #42  spacng weird\n{GUARDED}\nend of snippet"},
    {"id": "d3", "lang": "fr", "noise": 0.2, "text": f"# division simple, attention division par zéro\n{BUGGY}\nfin"},
    {"id": "d4", "lang": "en", "noise": 0.2, "text": f"quick helper below\n{BUGGY}\n"},
    {"id": "d5", "lang": "es", "noise": 0.3, "text": f"// revisar codigo mezclado\n{BUGGY}\nxxx"},
    {"id": "d6", "lang": "en", "noise": 0.1, "text": f"{BUGGY}\n"},
    {"id": "d7", "lang": "pcm", "noise": 0.7, "text": f"# clamp value - abeg make e no pass boundary o\n{CLAMP}\n"},
    {"id": "d8", "lang": "?", "noise": 0.9, "text": "def broken(::: ¡garbage! мусор ;;;minified"},
    {"id": "d9", "lang": "js", "noise": 0.5, "text": "function divide(a,b){ return a/b; } // not python"},
]


def main() -> int:
    absorber = GroundedProseAbsorberIncremental()
    for d in DOCS:
        absorber.ingest_document(d["text"])          # streaming, messy-safe
    sig = absorber.get_current_signatures()

    print("=" * 82)
    print("candidate_bridge on MESSY / MULTILINGUAL / LOW-RESOURCE input (no LLM)")
    print("-" * 82)
    print(f"absorbed {sig['docs']} docs ({', '.join(sorted({d['lang'] for d in DOCS}))}), "
          f"{sig['tokens']} tokens, vocab {sig['vocab']}")
    print(f"discovered pivots (language-universal): {[t for t, _ in sig['pivot_markers'][:6]]}")

    candidates = extract_candidates(DOCS, absorber)
    result = promote(candidates)

    print("\ncandidates mined (statistical proposal — NOT yet trusted):")
    for c in sorted(candidates, key=lambda c: -c.confidence):
        print(f"   {c.name:8} conf={c.confidence:.2f} support={c.support} noise={c.noise} "
              f"langs={c.lang:8} prov={c.provenance}")

    print("\nAFTER THE VERIFICATION GATE:")
    print("  VERIFIED → ledger-eligible:")
    for c in result["ledger"]:
        print(f"     ✓ {c.name} (conf {c.confidence:.2f}, support {c.support}) — {c.detail}")
    print("  QUARANTINED (failed execution, NOT promoted despite statistics):")
    for c in result["quarantined"]:
        print(f"     ✗ {c.name} (conf {c.confidence:.2f}, support {c.support}) — {c.detail}")
    if result["unproven"]:
        print("  UNPROVEN (no spec — honestly not promoted, not called wrong):")
        for c in result["unproven"]:
            print(f"     ? {c.name} — {c.detail}")

    # ── property checks ──────────────────────────────────────────────────
    by = {}
    for c in candidates:
        by.setdefault(c.name, []).append(c)
    divides = by.get("divide", [])
    buggy = next((c for c in divides if "if b" not in c.source), None)
    guarded = next((c for c in divides if "if b" in c.source), None)
    clamp = next((c for c in by.get("clamp", [])), None)
    ledger_names = {c.name for c in result["ledger"]}

    freq_not_truth = (buggy and guarded and buggy.confidence >= guarded.confidence
                      and buggy.status == "quarantined" and guarded.status == "verified")
    low_resource_fair = (clamp is not None and clamp.status == "verified" and clamp.confidence < 0.3)
    only_verified = all(c.status == "verified" for c in result["ledger"])

    print("\n" + "-" * 82)
    print(f"  frequency ≠ truth: buggy divide had HIGHER confidence ({buggy.confidence:.2f} ≥ "
          f"{guarded.confidence:.2f}) yet was QUARANTINED = {freq_not_truth}")
    print(f"  low-resource fair: noisy pcm 'clamp' (conf {clamp.confidence:.2f}) VERIFIED and "
          f"promoted = {low_resource_fair}")
    print(f"  gate integrity: only execution-verified units in ledger = {only_verified}")
    print(f"  messy-safe: garbage/JS docs skipped without crashing = True (ran to here)")
    ok = freq_not_truth and low_resource_fair and only_verified
    print("VERDICT:", "PASS — under messy/multilingual/low-resource input, statistics only PROPOSE; "
          "execution DISPOSES; verified low-resource patterns are first-class; no LLM."
          if ok else "FAIL — see rows")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
