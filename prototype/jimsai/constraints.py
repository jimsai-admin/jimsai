from __future__ import annotations

import os

from .models import ConstraintCheck, RetrievalResult, SemanticIR, SimulationResult
from .relation_schema import relation_is_functional


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


class ConstraintValidator:
    def validate(
        self,
        ir: SemanticIR,
        retrieval_results: list[RetrievalResult],
        simulations: list[SimulationResult],
    ) -> tuple[list[ConstraintCheck], list[str]]:
        checks: list[ConstraintCheck] = []
        gaps: list[str] = []
        checks.append(
            ConstraintCheck(
                name="ir_confidence_threshold",
                passed=ir.confidence >= 0.18,
                confidence=ir.confidence,
                detail="IR confidence is above deterministic execution threshold." if ir.confidence >= 0.18 else "IR routed to sandbox due to low confidence.",
            )
        )
        source_count = len(retrieval_results)
        checks.append(
            ConstraintCheck(
                name="source_grounding",
                passed=source_count > 0,
                confidence=min(1.0, source_count / 3),
                detail=f"{source_count} source signatures retrieved.",
            )
        )
        if source_count == 0:
            gaps.append("No source signatures matched the query; factual claims are withheld.")
        else:
            min_source_quality = max(0.0, min(1.0, _env_float("JIMS_VALIDATION_MIN_SOURCE_QUALITY", 0.45)))
            source_quality = self._source_quality(retrieval_results)
            checks.append(
                ConstraintCheck(
                    name="source_quality",
                    passed=source_quality >= min_source_quality,
                    confidence=source_quality,
                    detail=f"Average source quality is {source_quality:.2f}; minimum required is {min_source_quality:.2f}.",
                )
            )
            if source_quality < min_source_quality:
                gaps.append("Retrieved sources are below the validation confidence threshold.")

            conflicts = self._functional_relation_conflicts(retrieval_results)
            checks.append(
                ConstraintCheck(
                    name="retrieval_contradiction_check",
                    passed=not conflicts,
                    confidence=1.0 if not conflicts else 0.25,
                    detail=f"{len(conflicts)} conflicting functional relation slot(s) found.",
                )
            )
            if conflicts:
                gaps.append("Retrieved memory contains conflicting source claims; answer should preserve uncertainty.")
        if not all(sim.passed for sim in simulations):
            gaps.append("At least one bounded simulation failed.")
        checks.append(
            ConstraintCheck(
                name="simulation_bounds",
                passed=all(sim.scope.time_budget_ms <= 200 for sim in simulations),
                confidence=1.0,
                detail="Simulation is bounded to local causal neighbourhood by default.",
            )
        )
        return checks, gaps

    def _source_quality(self, retrieval_results: list[RetrievalResult]) -> float:
        if not retrieval_results:
            return 0.0
        values = [
            max(0.0, min(1.0, (float(result.score) + float(result.signature.confidence.score)) / 2.0))
            for result in retrieval_results
        ]
        return round(sum(values) / len(values), 4)

    def _functional_relation_conflicts(self, retrieval_results: list[RetrievalResult]) -> list[dict[str, object]]:
        slots: dict[tuple[str, str], dict[str, set[str]]] = {}
        for result in retrieval_results:
            for relation in result.signature.structured.relations:
                predicate = relation.predicate.strip()
                if not self._relation_is_functional(result, predicate):
                    continue
                key = (relation.subject.strip().lower(), predicate)
                slot = slots.setdefault(key, {"objects": set(), "sources": set()})
                slot["objects"].add(relation.object.strip().lower())
                slot["sources"].add(result.signature.id)

        conflicts: list[dict[str, object]] = []
        for (subject, predicate), slot in slots.items():
            if len(slot["objects"]) <= 1:
                continue
            conflicts.append(
                {
                    "subject": subject,
                    "predicate": predicate,
                    "objects": sorted(slot["objects"]),
                    "sources": sorted(slot["sources"]),
                }
            )
        return conflicts

    def _relation_is_functional(self, result: RetrievalResult, predicate: str) -> bool:
        return relation_is_functional(result.signature, predicate)
