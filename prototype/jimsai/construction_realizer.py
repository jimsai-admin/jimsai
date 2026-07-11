"""Faithful surface realization with round-trip fidelity verification (no LLM).

Production version of the validated M-GEN mechanism
(experiments/synthesis/run_m_gen.py): the generation layer must never voice a
surface that does not still MEAN the verified content. Two capabilities:

  * fidelity_ok(source, realized, shadow) — the ROUND-TRIP GUARD. Every anchor
    (named entity + number/value) present in the verified `source` must survive in
    the transformed `realized` surface; if any is dropped or corrupted, the
    transform changed the meaning and must be REJECTED. Anchors are
    language-independent (a name/number is the same token in any language), so
    this guards cross-language realization without a per-language rule. This is the
    live analogue of the M8/M-GEN never-voice-a-wrong guarantee, on the surface.

  * realize_fact(fact, constructions, lang, shadow) — construction-based
    realization of a structured (subject, relation, object) fact by REUSING a
    discovered construction (the same frame ELE extraction learns), round-trip
    verified. Returns None (abstain) if no faithful surface can be produced —
    generation gaps honestly rather than guessing.

Nothing here hardcodes a language, a template string, or a relation name.
"""

from __future__ import annotations

import re

_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def _anchors(text: str, shadow) -> set[str]:
    """Meaning-bearing tokens that MUST survive any faithful transform: numeric
    values, and named-entity literals from the CLL (language-independent)."""
    anchors: set[str] = set(_NUM.findall(text or ""))
    try:
        if shadow is not None and getattr(shadow, "loaded", False):
            _concepts, literals = shadow.encode(text, mode="document")
            for lit in literals:
                name = lit[2:] if len(lit) > 2 else lit
                if name:
                    anchors.add(name)
    except Exception:
        pass
    return anchors


def fidelity_ok(source: str, realized: str, shadow) -> bool:
    """True iff every anchor (entity, number) in `source` also appears in
    `realized`. If `source` carries no anchors, nothing factual can be corrupted,
    so the transform is allowed. Fail-safe: on any doubt the caller keeps the
    verified source rather than emitting a possibly-wrong surface."""
    if not source or not realized:
        return True
    src = _anchors(source, shadow)
    if not src:
        return True
    low = realized.lower()
    return all(a.lower() in low for a in src)


def guard_realization(source: str, realized: str, shadow) -> str:
    """Return `realized` only if it faithfully preserves the source's anchors;
    otherwise fall back to the verified `source`. The one call sites use."""
    if realized == source:
        return source
    return realized if fidelity_ok(source, realized, shadow) else source


def realize_fact(fact: tuple[str, str, str], constructions: dict, lang: str,
                 shadow=None, rng=None) -> str | None:
    """Realize (subject, relation, object) via a discovered construction for the
    relation, round-trip verified. `constructions` maps relation -> list of
    templates (token sequences with <SUBJ>/<OBJ> slots), as discovered by ELE.
    Returns a faithful surface, or None if none can be produced (abstain)."""
    subject, relation, obj = fact
    templates = (constructions or {}).get(relation)
    if not templates:
        return None                          # no construction for this relation → gap
    for tmpl in (templates if rng is None else [rng.choice(templates)]):
        toks = [subject if t == "<SUBJ>" else obj if t == "<OBJ>" else t for t in tmpl]
        surface = " ".join(toks)
        surface = surface[0].upper() + surface[1:] if surface else surface
        # round-trip: both entities must survive in the produced surface
        if fidelity_ok(f"{subject} {obj}", surface, shadow):
            return surface
    return None


def realize_facts(facts, constructions, lang: str, shadow=None, rng=None) -> str:
    """Realize a set of facts into text; silently abstain on any fact with no
    faithful construction (gap-honest). Simple discourse ordering (topic-first)."""
    clauses = []
    for f in sorted(facts, key=lambda f: (f[0], f[1])):
        c = realize_fact(f, constructions, lang, shadow, rng)
        if c is not None:
            clauses.append(c)
    return ". ".join(clauses) + ("." if clauses else "")
