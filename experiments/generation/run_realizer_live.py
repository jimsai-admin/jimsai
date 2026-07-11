"""Live test — faithful realization + round-trip fidelity guard, ACTIVE in CSSE.

Proves the M-GEN guarantee is wired into the real answer path (prototype/jimsai):
  1. fidelity_ok / guard_realization — entities and numeric values must survive any
     surface transform; a drop/corruption is rejected (fall back to the verified
     source). Language-independent.
  2. realize_fact — construction-based realization round-trips or abstains.
  3. INTEGRATION — csse._realize_language keeps the faithful source when the
     language realizer would corrupt an entity, and passes a faithful one through.

Run: JIMS_CONCEPT_INDEX=on JIMS_OOV_NAMES=on \
     .venv/Scripts/python.exe experiments/generation/run_realizer_live.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "prototype"))
os.environ.setdefault("JIMS_CONCEPT_INDEX", "on")
os.environ.setdefault("JIMS_OOV_NAMES", "on")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from jimsai.cll_shadow import get_shadow  # noqa: E402
from jimsai.construction_realizer import (  # noqa: E402
    fidelity_ok, guard_realization, realize_fact, realize_facts,
)

checks: list[tuple[str, bool]] = []


def check(name: str, cond: bool) -> None:
    checks.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


def main() -> int:
    shadow = get_shadow()
    print("=" * 74)
    print("LIVE realizer + fidelity guard (active in CSSE) — no LLM")
    print("-" * 74)

    # 1. fidelity guard — the round-trip invariant
    check("entities survive a faithful cross-language realization",
          fidelity_ok("Zorvenqia lives in Trelvax", "Zorvenqia habite à Trelvax", shadow))
    check("a CHANGED number is rejected (96 → 69)",
          not fidelity_ok("the answer is 96", "the answer is 69", shadow))
    check("a DROPPED entity is rejected (PoziDB removed)",
          not fidelity_ok("Kwendal uses PoziDB", "Kwendal uses it", shadow))
    check("chrome with no anchors is allowed to translate freely",
          fidelity_ok("here is what I found", "voici ce que j'ai trouvé", shadow))
    check("guard_realization keeps the faithful source on corruption",
          guard_realization("value is 42", "value is 24", shadow) == "value is 42")
    check("guard_realization passes a faithful transform through",
          guard_realization("Ara wins", "Ara gagne", shadow) == "Ara gagne")

    # 2. construction realization — round-trip or abstain
    cons = {"capital_of": [("<SUBJ>", "is", "the", "capital", "of", "<OBJ>")],
            "founded_by": [("<SUBJ>", "was", "founded", "by", "<OBJ>")]}
    s = realize_fact(("Ara", "capital_of", "Bel"), cons, "en", shadow)
    check("realize_fact produces faithful surface with both entities",
          s == "Ara is the capital of Bel" and "Ara" in s and "Bel" in s)
    check("realize_fact ABSTAINS on a relation with no construction (gap-honest)",
          realize_fact(("Ara", "no_such_relation", "Bel"), cons, "en", shadow) is None)
    text = realize_facts({("Ara", "capital_of", "Bel"), ("Cyr", "founded_by", "Dun")}, cons, "en", shadow)
    check("realize_facts composes multiple facts faithfully",
          "Ara is the capital of Bel" in text and "Cyr was founded by Dun" in text)

    # 3. INTEGRATION — the guard is live inside csse._realize_language
    import jimsai.surface_realizer as SR
    from jimsai.csse import ConstrainedSemanticSynthesisEngine

    class Step:                                   # minimal stand-in for a VCO step
        def __init__(self, claim): self.claim = claim
        def model_copy(self, update): return Step(update.get("claim", self.claim))

    csse = ConstrainedSemanticSynthesisEngine()
    original = SR.realize_in_language
    try:
        # simulate a realizer that CORRUPTS an entity (drops "Trelvax")
        SR.realize_in_language = lambda claim, lang, sh: claim.replace("Trelvax", "Zzz")
        out = csse._realize_language(None, [Step("Zorvenqia moved to Trelvax")], "fr")
        check("CSSE guard rejects a corrupting realization → keeps verified source",
              out[0].claim == "Zorvenqia moved to Trelvax")
        # simulate a faithful realizer (entities preserved)
        SR.realize_in_language = lambda claim, lang, sh: claim.replace("moved to", "a déménagé à")
        out2 = csse._realize_language(None, [Step("Zorvenqia moved to Trelvax")], "fr")
        check("CSSE passes a faithful realization through (entities intact)",
              "Trelvax" in out2[0].claim and "Zorvenqia" in out2[0].claim and "déménagé" in out2[0].claim)
    finally:
        SR.realize_in_language = original

    # English is always a no-op (fail-safe)
    out_en = csse._realize_language(None, [Step("value is 7")], "en")
    check("English render is an untouched no-op", out_en[0].claim == "value is 7")

    print("-" * 74)
    passed = sum(ok for _n, ok in checks)
    print(f"{passed}/{len(checks)} checks passed")
    ok = passed == len(checks)
    print("VERDICT:", "PASS — faithful, fidelity-guarded realization is live in the answer path; "
          "generation cannot voice a surface that corrupts a verified entity/value; no LLM"
          if ok else "FAIL — see checks")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
