"""World Model Rule Promotion Engine.

Frequency-based promotion of repeated causal patterns (observed via
LatentWorldModelLayer activations across queries) into
WorldModelCandidate rules for human review.

Design constraints (deliberately scoped — see roadmap-doc-12.md):
  - No analogical generalization. A rule is promoted only when the
    EXACT (cause, effect) pair has been observed independently
    enough times.
  - No automatic acceptance. Every promoted candidate starts with
    review_required=True and only becomes usable for the fast-path
    after a human calls review_action(action="accept"/"promote").
  - Stateless w.r.t. the LLM — this module never calls T1/T2/Tier3.
    It only reads WorldModelActivation objects already produced by
    LatentWorldModelLayer.activate(), which runs on every query
    regardless of this module's existence.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .models import WorldModelActivation, WorldModelCandidate


_RELATION_ALIASES = {
    "depends on": "depends_on",
    "is a": "is_a",
    "caused by": "caused_by",
}


def _parse_rule(rule: str) -> tuple[str, str, str] | None:
    cleaned = re.sub(r"\s+", " ", rule.strip().rstrip("."))
    if not cleaned:
        return None
    for phrase, predicate in sorted(_RELATION_ALIASES.items(), key=lambda item: -len(item[0])):
        match = re.match(rf"^(.+?)\s+{re.escape(phrase)}\s+(.+)$", cleaned, flags=re.IGNORECASE)
        if match:
            subject = match.group(1).strip()
            obj = match.group(2).strip()
            return (subject, predicate, obj) if subject and obj else None
    match = re.match(r"^(.+?)\s+([A-Za-z][A-Za-z0-9_]{1,80})\s+(.+)$", cleaned, flags=re.UNICODE)
    if not match:
        return None
    subject = match.group(1).strip()
    predicate = match.group(2).strip().lower()
    obj = match.group(3).strip()
    return (subject, predicate, obj) if subject and predicate and obj else None


def _canonical_rule(parsed: tuple[str, str, str]) -> str:
    subject, predicate, obj = parsed
    return f"{subject} {predicate} {obj}"


def _normalize_rule(rule: str) -> str:
    """Normalize 'X causes Y' strings for stable dedup keys.

    Case-insensitive, collapses whitespace. Does NOT translate or
    stem entity names — exact-match by design (see module docstring).
    """
    parsed = _parse_rule(rule)
    if parsed is not None:
        return re.sub(r"\s+", " ", _canonical_rule(parsed).strip().lower())
    return re.sub(r"\s+", " ", rule.strip().lower())


@dataclass
class _RuleObservation:
    rule: str                          # original-cased rule string, first-seen form
    predicate: str = ""
    count: int = 0
    confidence_sum: float = 0.0
    provenances: set[str] = field(default_factory=set)

    @property
    def avg_confidence(self) -> float:
        return self.confidence_sum / self.count if self.count else 0.0


class WorldModelPromotionEngine:
    """Accumulates causal-rule observations across queries and
    promotes repeated, sufficiently-confident ones to
    WorldModelCandidate for review.

    Thresholds are read from env vars so they can be tuned per
    deployment without code changes:
      JIMS_WM_PROMOTION_MIN_COUNT   (default 3)
      JIMS_WM_PROMOTION_MIN_CONF    (default 0.6)
    """

    def __init__(self) -> None:
        self._observations: dict[str, _RuleObservation] = {}
        self._promoted_keys: set[str] = set()

    def _min_count(self) -> int:
        try:
            return max(1, int(os.getenv("JIMS_WM_PROMOTION_MIN_COUNT", "3")))
        except ValueError:
            return 3

    def _min_confidence(self) -> float:
        try:
            return min(1.0, max(0.0, float(os.getenv("JIMS_WM_PROMOTION_MIN_CONF", "0.6"))))
        except ValueError:
            return 0.6

    def observe(self, activations: list[WorldModelActivation]) -> list[WorldModelCandidate]:
        """Record activations from a single query's LatentWorldModelLayer
        output. Returns any NEWLY promoted candidates (empty list if none).

        Only activations whose rule contains " causes " (the only
        rule shape LatentWorldModelLayer currently produces) are
        considered. This keeps the promotion engine in lockstep with
        what the graph layer actually emits — no speculative rule
        shapes are invented here.
        """
        newly_promoted: list[WorldModelCandidate] = []

        for activation in activations:
            parsed = _parse_rule(activation.rule)
            if parsed is None:
                continue

            key = _normalize_rule(activation.rule)
            obs = self._observations.get(key)
            if obs is None:
                obs = _RuleObservation(rule=_canonical_rule(parsed), predicate=parsed[1])
                self._observations[key] = obs

            obs.count += 1
            obs.confidence_sum += float(activation.confidence)
            if activation.source:
                obs.provenances.add(str(activation.source))

            if (
                key not in self._promoted_keys
                and obs.count >= self._min_count()
                and obs.avg_confidence >= self._min_confidence()
            ):
                self._promoted_keys.add(key)
                newly_promoted.append(
                    WorldModelCandidate(
                        rule=obs.rule,
                        confidence=round(obs.avg_confidence, 4),
                        provenance=",".join(sorted(obs.provenances)) or "unknown",
                        review_required=True,
                    )
                )

        return newly_promoted

    def stats(self) -> dict[str, int | float]:
        """Summary for diagnostics / world_model_confidence_avg.

        Returns {"observed_rules": int, "promoted_rules": int, "avg_confidence": float}.
        avg_confidence is the mean of per-rule average confidences across all
        observed rules (not just promoted ones).
        """
        if not self._observations:
            return {"observed_rules": 0, "promoted_rules": 0, "avg_confidence": 0.0, "relation_types": 0}

        confidences = [obs.avg_confidence for obs in self._observations.values()]
        predicates = {obs.predicate for obs in self._observations.values() if obs.predicate}
        return {
            "observed_rules": len(self._observations),
            "promoted_rules": len(self._promoted_keys),
            "avg_confidence": round(sum(confidences) / len(confidences), 4),
            "relation_types": len(predicates),
        }


class WorldModelFastPath:
    """Lookup table of ACCEPTED (review_required=False) causal rules,
    rebuilt from pipeline.world_model_candidates on demand.

    Used for the deterministic fast-path: if a query's extracted
    entities exactly match an accepted rule's cause/effect pair,
    answer directly without invoking T1/T2.
    """

    _CAUSES_PATTERN = re.compile(r"^(.+?)\s+causes\s+(.+)$", re.IGNORECASE)

    def __init__(self) -> None:
        self._accepted: dict[tuple[str, str], WorldModelCandidate] = {}

    def rebuild(self, candidates: list[WorldModelCandidate]) -> None:
        """Rebuild the lookup table from the current candidate list.

        Only candidates with review_required=False AND whose rule
        matches "X causes Y" are indexed. Previous state is fully
        replaced — not merged.
        """
        self._accepted.clear()

        for candidate in candidates:
            if candidate.review_required:
                continue
            match = self._CAUSES_PATTERN.match(candidate.rule.strip())
            if not match:
                continue
            cause = match.group(1).strip().lower()
            effect = match.group(2).strip().lower()
            self._accepted[(cause, effect)] = candidate

    def lookup(self, cause: str, effect: str) -> WorldModelCandidate | None:
        """Exact normalized-string lookup for a specific (cause, effect) pair.

        Returns the matching WorldModelCandidate or None if not found.
        """
        return self._accepted.get((cause.strip().lower(), effect.strip().lower()))

    def lookup_effects_of(self, cause: str) -> list[WorldModelCandidate]:
        """All accepted rules where the cause matches (after normalization)."""
        cause_norm = cause.strip().lower()
        return [c for (cz, _), c in self._accepted.items() if cz == cause_norm]

    def lookup_causes_of(self, effect: str) -> list[WorldModelCandidate]:
        """All accepted rules where the effect matches (after normalization)."""
        effect_norm = effect.strip().lower()
        return [c for (_, ez), c in self._accepted.items() if ez == effect_norm]
