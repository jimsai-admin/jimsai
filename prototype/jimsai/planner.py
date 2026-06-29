from __future__ import annotations

from typing import Any

from .models import ExecutionMode, ExecutionPlan, PlanStep, SemanticIR


class SymbolicPlanner:
    def plan(self, ir: SemanticIR) -> ExecutionPlan:
        signals = self._signals(ir)
        steps: list[PlanStep] = []

        def add(action: str, inputs: dict[str, Any] | None = None, expected_output: str = "") -> None:
            steps.append(
                PlanStep(
                    order=len(steps) + 1,
                    action=action,
                    inputs=inputs or {},
                    expected_output=expected_output,
                )
            )

        add(
            "compile_ir",
            {
                "target_ir": ir.target_ir,
                "confidence": ir.confidence,
                "intent_domain": ir.intent_domain.value,
                "hypotheses": [h.model_dump(mode="json") for h in ir.hypotheses],
            },
            "typed Semantic IR with confidence and competing hypotheses",
        )

        if signals["requires_decomposition"]:
            add(
                "decompose_objectives",
                {
                    "complexity": signals,
                    "scope": self._scope_summary(ir),
                },
                "ordered objectives, constraints, dependencies, and blockers",
            )

        add(
            "resolve_context_scope",
            {
                "entities": list(ir.scope_constraints.get("entities", [])),
                "question_intent": ir.scope_constraints.get("question_intent"),
                "context_inherited": ir.context_inherited,
                "profile_query": bool(ir.scope_constraints.get("profile_query")),
            },
            "bounded user/workspace/thread scope for downstream layers",
        )

        if ir.execution_mode == ExecutionMode.AIR_GAPPED_CONTAINER or ir.target_ir == "OP_ESCAPE_TO_SANDBOX":
            add(
                "build_sandbox_handoff",
                {
                    "confidence": ir.confidence,
                    "hypotheses": [h.model_dump(mode="json") for h in ir.hypotheses],
                },
                "uncertainty-preserving sandbox handoff with no factual claims",
            )
            add(
                "validate_constraints_and_sources",
                {"source_required": False, "reason": "sandbox route cannot emit factual claims"},
                "explicit gaps for unsupported or unclassified input",
            )
            add("render_csse", {"mode": "GAP"}, "bounded gap response")
            return ExecutionPlan(goal=ir.target_ir, steps=steps)

        add(
            "retrieve_signatures",
            {
                "tokens": ir.tokens,
                "entities": list(ir.scope_constraints.get("entities", [])),
                "relation": self._relation_filter(ir),
                "profile_query": bool(ir.scope_constraints.get("profile_query")),
            },
            "ranked source signatures scoped to user/workspace",
        )

        if signals["needs_dependency_graph"]:
            add(
                "construct_dependency_graph",
                {
                    "entities": list(ir.scope_constraints.get("entities", [])),
                    "relation": self._relation_filter(ir),
                    "max_depth": signals["graph_depth"],
                },
                "dependency or causal paths grounded in retrieved signatures",
            )

        if ir.target_ir == "RUN_CANVAS":
            add("schedule_canvas", ir.scope_constraints, "canvas job or existing signatures")
        elif ir.target_ir in {"RUN_INVENTION", "CODE_GENERATE"}:
            add("decompose_problem", ir.scope_constraints, "sub-problems and dependency order")
            add("generate_sub_functions", ir.scope_constraints, "candidate implementation modules")
            add("assemble_code", ir.scope_constraints, "assembled candidate solution")
            add("run_recursive_planner", ir.scope_constraints, "candidate plan with alternatives")
            add("simulate_candidates", ir.scope_constraints, "bounded simulation result")
        elif signals["requires_decomposition"]:
            add(
                "resolve_subgoal_dependencies",
                {"scope": self._scope_summary(ir), "graph_required": signals["needs_dependency_graph"]},
                "subgoal outputs ordered by dependency and evidence availability",
            )

        add(
            "compose_reasoning_chain",
            {
                "grounding_required": True,
                "multi_intent": signals["multi_intent"],
                "verification_before_render": True,
            },
            "verified chain with sources, confidence, and gaps",
        )
        add(
            "validate_constraints_and_sources",
            {
                "source_required": True,
                "confidence": ir.confidence,
                "expected_sources": "retrieved signatures or verified tool results",
            },
            "claim-level checks and explicit knowledge gaps",
        )
        add("render_csse", {"mode": "FACT"}, "grounded response")
        return ExecutionPlan(goal=ir.target_ir, steps=steps)

    def _signals(self, ir: SemanticIR) -> dict[str, Any]:
        scope = ir.scope_constraints if isinstance(ir.scope_constraints, dict) else {}
        entities = scope.get("entities") if isinstance(scope.get("entities"), list) else []
        numbers = scope.get("numbers") if isinstance(scope.get("numbers"), list) else []
        question_intent = scope.get("question_intent") if isinstance(scope.get("question_intent"), dict) else {}
        hypotheses = [h for h in ir.hypotheses if h.target_ir != ir.target_ir]
        secondary_intents = scope.get("secondary_intents") if isinstance(scope.get("secondary_intents"), list) else []

        multi_intent = bool(secondary_intents or hypotheses)
        structurally_complex = (
            len(ir.tokens) >= 18
            or len(entities) >= 2
            or len(numbers) >= 2
            or bool(question_intent)
            or multi_intent
        )
        requires_decomposition = structurally_complex or ir.target_ir in {"RUN_INVENTION", "CODE_GENERATE"}
        needs_dependency_graph = (
            len(entities) >= 2
            or bool(question_intent)
            or ir.target_ir in {"RUN_INVENTION", "CODE_GENERATE", "RUN_CANVAS"}
        )
        graph_depth = 4
        if len(entities) >= 4 or len(ir.tokens) >= 32 or multi_intent:
            graph_depth = 6

        return {
            "token_count": len(ir.tokens),
            "entity_count": len(entities),
            "number_count": len(numbers),
            "has_question_intent": bool(question_intent),
            "multi_intent": multi_intent,
            "requires_decomposition": requires_decomposition,
            "needs_dependency_graph": needs_dependency_graph,
            "graph_depth": graph_depth,
        }

    def _relation_filter(self, ir: SemanticIR) -> str | None:
        question_intent = ir.scope_constraints.get("question_intent")
        if isinstance(question_intent, dict):
            relation = question_intent.get("relation")
            return str(relation) if relation else None
        return None

    def _scope_summary(self, ir: SemanticIR) -> dict[str, Any]:
        scope = ir.scope_constraints if isinstance(ir.scope_constraints, dict) else {}
        return {
            "entities": list(scope.get("entities", [])) if isinstance(scope.get("entities"), list) else [],
            "numbers": list(scope.get("numbers", [])) if isinstance(scope.get("numbers"), list) else [],
            "question_intent": scope.get("question_intent") if isinstance(scope.get("question_intent"), dict) else None,
            "profile_query": bool(scope.get("profile_query")),
            "token_count": len(ir.tokens),
        }
