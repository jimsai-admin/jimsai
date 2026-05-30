from __future__ import annotations

from .graph import CausalGraphEngine
from .models import SemanticIR, SimulationResult, SimulationScope


class BoundedSimulationEngine:
    def __init__(self, graph: CausalGraphEngine) -> None:
        self.graph = graph

    def run(self, ir: SemanticIR) -> list[SimulationResult]:
        entities = [str(e) for e in ir.scope_constraints.get("entities", [])]
        scope = SimulationScope(entities=entities, depth=3, time_budget_ms=200)
        if not entities:
            return [
                SimulationResult(
                    scenario="bounded_local_simulation",
                    passed=True,
                    confidence=0.55,
                    outcomes=["No explicit entity scope was provided; simulation limited to IR-level checks."],
                    scope=scope,
                )
            ]
        outcomes: list[str] = []
        for entity in entities[:3]:
            traversal = self.graph.traverse(entity, depth=scope.depth)
            if traversal:
                outcomes.append(f"{entity} has causal/dependency paths: {sorted(traversal.keys())}")
            elif incoming := self.graph.incoming(entity):
                explanations = [f"{edge['source']} {edge['predicate']} {edge['target']}" for edge in incoming[:4]]
                outcomes.append(f"{entity} is explained by incoming causal/dependency paths: {explanations}")
            else:
                outcomes.append(f"{entity} has no known causal expansion in local graph.")
        return [
            SimulationResult(
                scenario="bounded_local_simulation",
                passed=True,
                confidence=0.74 if any("paths" in o for o in outcomes) else 0.6,
                outcomes=outcomes,
                scope=scope,
            )
        ]
