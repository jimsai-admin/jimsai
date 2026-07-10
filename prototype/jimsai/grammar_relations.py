"""Grammar-based relation extraction (no LLM) — populate the reasoning graph.

In de-LLM mode nothing extracts (subject, predicate, object) triples, so the
causal/relational graph stays empty and traversal reasoning has nothing to walk.
This fills that gap the same way `math_extract` fills the math gap: with grammar,
not a model and not a per-language verb list.

Principle: a binary relation is two ENTITIES with connecting text between them.
The entities are the CLL name-evidence literals (language-independent — a nonce
is a nonce in any language); the PREDICATE is exactly the text between them,
lower-cased and space-collapsed. Nothing is hardcoded — the predicate is DATA
(the words the source actually used: "causes", "requires", "leads to", "dépend
de", …), so it works across languages and domains without a verb list.

Scope (honest): the clean, unambiguous case — a sentence whose entity set is
exactly two, in order, with a short connective between them. Sentences with more
entities or none are left to richer extraction (ELE constructions); this never
guesses a relation it cannot ground in two real entities and their connective.
"""

from __future__ import annotations

import re

_STOP_EDGES = {"the", "a", "an", "is", "are", "was", "were", "of", "to", "and"}


def _entities_in_order(text: str, shadow) -> list[tuple[str, int]]:
    """CLL name-evidence literals with their position, earliest first."""
    if shadow is None or not getattr(shadow, "loaded", False):
        return []
    try:
        _concepts, literals = shadow.encode(text, mode="document")
    except Exception:
        return []
    low = text.lower()
    out: list[tuple[str, int]] = []
    for lit in literals:
        name = lit[2:]
        pos = low.find(name)
        if pos >= 0:
            out.append((name, pos))
    out.sort(key=lambda t: t[1])
    return out


def extract_relations(text: str, shadow) -> list[tuple[str, str, str]]:
    """Return [(subject, predicate, object), …] for sentences that contain
    exactly two entities with a connective between them. Predicate is the raw
    between-text (data, any language); empty when nothing clean is found."""
    relations: list[tuple[str, str, str]] = []
    for sentence in re.split(r"(?<=[.!?。？！])\s+", text.strip()):
        ents = _entities_in_order(sentence, shadow)
        if len(ents) != 2:
            continue
        (e1, p1), (e2, p2) = ents
        between = sentence.lower()[p1 + len(e1):p2].strip(" ,;:-")
        # Trim leading articles/copulas so "the" or "is" don't bloat the label,
        # but keep the meaningful verb the source used. Reject an empty or
        # implausibly long connective (not a clean binary relation).
        raw_toks = [t for t in re.split(r"\s+", between) if t]
        # HIGH-PRECISION abstention (language-universal): a passive ("is …
        # by") or a negation ("does not …") adds MULTIPLE function words to the
        # connective, whereas a clean active relation is a content verb plus at
        # most one preposition ("causes", "leads to"). Count COMMON words (the
        # sourced common-vocabulary set — data, not a hardcoded English list); if
        # 2+ appear, the construction reverses or negates the relation, so ABSTAIN
        # rather than assert a wrong-direction or fabricated causal edge. Precision
        # is what the traversal reasoner needs; recall it can afford to gap.
        common = getattr(shadow, "_common_words", set())
        try:
            from .cll_shadow import surface_key
            n_common = sum(1 for t in raw_toks if surface_key(t) in common)
        except Exception:
            n_common = 0
        toks = list(raw_toks)
        while toks and toks[0] in _STOP_EDGES:
            toks.pop(0)
        while toks and toks[-1] in _STOP_EDGES:
            toks.pop()
        predicate = " ".join(toks)
        if predicate and 1 <= len(toks) <= 4 and e1 != e2 and n_common < 2:
            relations.append((e1, predicate, e2))
    return relations
