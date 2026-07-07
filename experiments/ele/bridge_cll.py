"""ELE -> CLL bridge (spec §3.2 / build-order step 3, small closed domain).

The interface contract under test (grounding review §2): ELE emits AMBIGUITY
SETS — multiple candidate frames with confidence — and CLL's ConceptGraph is
what resolves/records them. The bridge:

  - maps each candidate frame to typed relation edges with the frame's
    confidence and a per-candidate source id (auditable);
  - preserves ConceptGraph's refusal semantics (non-composable predicates do
    not chain — the honest gap, exactly where an LLM would guess);
  - treats correction as a graph edit (remove returns the edges as audit).

Reuses experiments/concept_model/concept_model.py — no duplicate graph code.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "concept_model"))
from concept_model import ConceptGraph  # noqa: E402


@dataclass
class CandidateFrame:
    roles: dict[str, str]          # agent / verb(predicate) / object ...
    confidence: float
    source: str                    # ELE evidence id (auditable)


@dataclass
class AmbiguitySet:
    candidates: list[CandidateFrame] = field(default_factory=list)


def frames_to_graph(graph: ConceptGraph, ambiguity: AmbiguitySet) -> list[tuple]:
    """Record EVERY candidate (recall-first, like CLL's top-3 concept
    candidates); downstream evidence — retrieval intersection, corrections —
    resolves which survives. Returns (subject, predicate, object, confidence)
    tuples actually added."""
    added = []
    for cand in sorted(ambiguity.candidates, key=lambda c: -c.confidence):
        subject = cand.roles["agent"]
        predicate = cand.roles["verb"]
        obj = cand.roles["object"]
        graph.add(subject, predicate, obj, cand.confidence, cand.source)
        added.append((subject, predicate, obj, cand.confidence))
    return added


def resolve_candidate(graph: ConceptGraph, losing: CandidateFrame) -> list:
    """Correction as graph edit: remove the losing candidate's edge; the
    returned edges ARE the audit trail (ConceptGraph.remove semantics)."""
    return graph.remove(losing.roles["agent"], losing.roles["verb"], losing.roles["object"])
