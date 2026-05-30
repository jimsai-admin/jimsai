from __future__ import annotations

from .models import ConstraintCheck, RetrievalResult, SemanticIR, SimulationResult


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
