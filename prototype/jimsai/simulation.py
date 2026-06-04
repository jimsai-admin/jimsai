from __future__ import annotations

from .graph import CausalGraphEngine
from .models import SemanticIR, SimulationResult, SimulationScope


class BoundedSimulationEngine:
    def __init__(self, graph: CausalGraphEngine) -> None:
        self.graph = graph

    def verify_ast(self, code: str) -> tuple[bool, str]:
        import ast
        try:
            ast.parse(code)
            return True, "AST syntax check passed successfully."
        except SyntaxError as e:
            return False, f"AST syntax check failed: {e.msg} at line {e.lineno}"
        except Exception as e:
            return False, f"AST verification error: {str(e)}"

    def verify_path_connectivity(self, source: str, target: str) -> bool:
        traversal = self.graph.traverse(source, depth=4)
        for node in traversal:
            if node.lower() == target.lower():
                return True
            for edge in traversal[node]:
                if edge["target"].lower() == target.lower():
                    return True
        return False

    def run(self, ir: SemanticIR) -> list[SimulationResult]:
        entities = [str(e) for e in ir.scope_constraints.get("entities", [])]
        scope = SimulationScope(entities=entities, depth=3, time_budget_ms=200)
        
        ast_outcomes = []
        code_input = ir.scope_constraints.get("code") or ir.scope_constraints.get("raw_input") or ""
        if ir.intent_domain.value == "coding" or ir.target_ir == "CODE_GENERATE":
            if code_input and "def " in str(code_input):
                passed, detail = self.verify_ast(str(code_input))
                ast_outcomes.append(f"AST check: {detail}")

        if not entities:
            return [
                SimulationResult(
                    scenario="bounded_local_simulation",
                    passed=True,
                    confidence=0.55,
                    outcomes=["No explicit entity scope was provided; simulation limited to IR-level checks."] + ast_outcomes,
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
                
        if len(entities) >= 2:
            connected = self.verify_path_connectivity(entities[0], entities[1])
            outcomes.append(f"Connectivity check between {entities[0]} and {entities[1]}: {'connected' if connected else 'not directly connected'}")

        return [
            SimulationResult(
                scenario="bounded_local_simulation",
                passed=True,
                confidence=0.74 if any("paths" in o or "connected" in o for o in outcomes) else 0.6,
                outcomes=outcomes + ast_outcomes,
                scope=scope,
            )
        ]
