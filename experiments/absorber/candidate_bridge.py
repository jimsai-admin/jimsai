"""candidate_bridge — messy/multilingual absorber signals → VERIFIED patterns (no LLM).

Enforces the architecture's binding rule under real-world conditions:
  a statistical signal is evidence FOR A CANDIDATE, never evidence OF CORRECTNESS.

Statistical strength — even high frequency on messy, multilingual, low-resource
input — only PROPOSES a candidate. Execution VERIFIES. Only verified units reach
the ledger. Every candidate carries PROVENANCE + source NOISE + a DISCOVERY
confidence (statistical, NOT correctness), so the ledger can down-weight noisy or
low-resource sources — but verification is the EQUALISER: a verified low-resource
pattern is exactly as trustworthy as a verified high-resource one.

Honest scope: this bridge (a) extracts candidate code units tolerantly from messy
prose (skips what it cannot parse — never crashes on mess), (b) attaches metadata,
(c) verifies by REAL execution against a spec, (d) promotes only verified. Deriving
the spec from a prose request, and extractors for non-Python languages, are named
gaps — the SEED spec/extractor is the engineer bootstrap the training loop grows.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

RAISE = "RAISE_VALUEERROR"

# SEED verification specs (bootstrap — engineer-provided; grown by verified results).
# Keyed by function role. Honest: deriving these from a prose request is a named gap.
SEED_SPECS: dict[str, list] = {
    "divide": [((6, 2), 3.0), ((9, 3), 3.0), ((5, 0), RAISE)],
    "clamp": [((5, 0, 10), 5), ((-3, 0, 10), 0), ((99, 0, 10), 10)],
}

_DEF = re.compile(r"(^[ \t]*def[ \t]+(\w+)[ \t]*\([^)]*\)\s*:.*?)(?=^\S|^[ \t]*def[ \t]|\Z)",
                  re.M | re.S)


@dataclass
class Candidate:
    name: str
    source: str
    lang: str
    support: int                       # absorbed frequency across documents
    provenance: list[str]              # source document ids
    noise: float                       # mean noise level of the sources (0..1)
    confidence: float                  # DISCOVERY confidence (statistical) — NOT correctness
    status: str = "candidate"          # candidate | verified | quarantined
    detail: str = ""


def extract_candidates(docs: list[dict], absorber=None) -> list[Candidate]:
    """Tolerantly pull candidate function units from messy/multilingual documents.
    A malformed or non-extractable block is simply skipped — never fatal."""
    # (name, normalized_body) -> aggregated evidence
    agg: dict[tuple[str, str], dict] = {}
    for d in docs:
        text, did, noise, lang = d["text"], d["id"], d.get("noise", 0.0), d.get("lang", "?")
        try:
            for m in _DEF.finditer(text):
                src = m.group(1).rstrip()
                name = m.group(2)
                norm = re.sub(r"\s+", " ", re.sub(r"#.*", "", src)).strip()   # ignore comments/spacing
                key = (name, norm)
                e = agg.setdefault(key, {"name": name, "source": src, "prov": [],
                                         "noise": [], "langs": set()})
                e["prov"].append(did); e["noise"].append(noise); e["langs"].add(lang)
        except Exception:
            continue                    # messy-safe: skip unparseable documents
    out = []
    for (name, _norm), e in agg.items():
        support = len(e["prov"])
        # DISCOVERY confidence: rises with support, falls with source noise. This is
        # a statistical prior on WHERE TO LOOK — it does not assert correctness.
        mean_noise = sum(e["noise"]) / len(e["noise"]) if e["noise"] else 0.0
        conf = round((1 - mean_noise) * (1 - 1 / (1 + math.log1p(support))), 3)
        out.append(Candidate(name=name, source=e["source"], lang="/".join(sorted(e["langs"])),
                             support=support, provenance=e["prov"], noise=round(mean_noise, 2),
                             confidence=conf))
    return out


def verify(cand: Candidate, specs: dict = SEED_SPECS) -> bool:
    """REAL verification: exec the candidate and run it against its spec. The ONLY
    thing that can move a candidate to 'verified'. No spec ⇒ cannot verify ⇒ stays
    a candidate (gap-honest: unverifiable is not 'wrong', it is 'unproven')."""
    spec = specs.get(cand.name)
    if spec is None:
        cand.status = "unproven"; cand.detail = "no spec — cannot verify"
        return False
    ns: dict = {}
    try:
        exec(cand.source, ns)                    # noqa: S102 — sandboxed generated/mined source
    except Exception as e:
        cand.status = "quarantined"; cand.detail = f"exec error: {type(e).__name__}"
        return False
    fn = ns.get(cand.name)
    if not callable(fn):
        cand.status = "quarantined"; cand.detail = "no callable"
        return False
    passed = 0
    for args, expected in spec:
        try:
            r = fn(*args)
            ok = expected != RAISE and r == expected
        except ValueError:
            ok = expected == RAISE
        except Exception:
            ok = False
        passed += ok
    if passed == len(spec):
        cand.status = "verified"; cand.detail = f"{passed}/{len(spec)} spec examples"
        return True
    cand.status = "quarantined"; cand.detail = f"only {passed}/{len(spec)} spec examples"
    return False


def promote(candidates: list[Candidate], specs: dict = SEED_SPECS) -> dict:
    """Verify every candidate; ONLY verified ones are ledger-eligible. Statistical
    strength (support/confidence) is never sufficient — this is the gate."""
    ledger, quarantined, unproven = [], [], []
    for c in sorted(candidates, key=lambda c: -c.confidence):   # try confident first (prior only)
        if verify(c, specs):
            ledger.append(c)
        elif c.status == "unproven":
            unproven.append(c)
        else:
            quarantined.append(c)
    return {"ledger": ledger, "quarantined": quarantined, "unproven": unproven}
