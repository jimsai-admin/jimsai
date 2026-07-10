"""Discourse Composer — order verified claims by entity continuity (no LLM).

Sequences a set of independently-verified claims so related facts sit together
(M9, `experiments/discourse/run_m9.py`): each claim should CONTINUE the current
focus — share an entity with the one before it — the computable proxy for
discourse coherence. A reordered set reads as a passage instead of a random
list, and the operation is meaning-preserving (whole claims are reordered, never
rewritten).

EVERY LANGUAGE, no hardcoding. Ordering keys on ENTITY IDENTITY only — the CLL
name-evidence literals in each claim, which are script- and language-agnostic
(a nonce entity is the same token whether the sentence around it is English,
French, or Nigerian Pidgin). There is NO function word, article, pronoun, or
connective anywhere in this module, so nothing here privileges one language or
needs a per-language table a developer must maintain.

Deliberately NOT here: surface reduction of repetition — eliding a repeated
subject or substituting a pronoun (M10). That is inherently language-specific
(it needs the language's coordinator, articles, and agreement system), so doing
it without hardcoding requires those closed classes to be DISCOVERED per
language (ELE, per M3's distributional function-word finding) or composed at the
structured level and realized once by the Surface Realizer. Until that data
exists it is not done — an English-only elision shipped to every language would
be exactly the hardcoding this project rejects. The M10 mechanism stays proven
offline; its production home is structure-level composition, not this surface.
"""

from __future__ import annotations


def _entities(claim: str, shadow) -> frozenset[str]:
    """Language-agnostic entity set of a claim: its CLL name-evidence literals
    (document mode captures name-like tokens in any position, incl. the
    sentence-initial subject). Empty when the concept index is unavailable."""
    if shadow is None or not getattr(shadow, "loaded", False):
        return frozenset()
    try:
        _, literals = shadow.encode(claim, mode="document")
        return frozenset(l[2:] for l in literals)
    except Exception:
        return frozenset()


def compose(claims: list[str], shadow=None) -> list[str]:
    """Return the claims reordered by greedy entity-continuity. Each next claim
    is the remaining one sharing the most entities with the current focus; ties
    and no-overlap keep original order (stable). Never drops or rewrites a
    claim. Language-universal — no function words, no per-language data."""
    claims = [c.strip() for c in claims if c and c.strip()]
    if len(claims) < 3:
        return claims  # nothing to gain reordering 0–2 claims

    ent = [_entities(c, shadow) for c in claims]
    if not any(ent):
        return claims  # no entity signal (e.g. index off) — leave as-is

    remaining = list(range(len(claims)))
    order = [remaining.pop(0)]
    while remaining:
        focus = ent[order[-1]]
        # pick the remaining claim with the most shared entities; on a tie or
        # zero overlap, the earliest remaining index wins (stable).
        best_k, best_overlap = 0, -1
        for k, idx in enumerate(remaining):
            overlap = len(focus & ent[idx])
            if overlap > best_overlap:
                best_k, best_overlap = k, overlap
        order.append(remaining.pop(best_k))
    return [claims[i] for i in order]
