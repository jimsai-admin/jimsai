from __future__ import annotations

from .models import ExecutionPlan, PlanStep, SemanticIR


class SymbolicPlanner:
    def plan(self, ir: SemanticIR) -> ExecutionPlan:
        steps: list[PlanStep] = [
            PlanStep(order=1, action="compile_ir", inputs={"target_ir": ir.target_ir}, expected_output="typed Semantic IR"),
            PlanStep(order=2, action="retrieve_signatures", inputs={"tokens": ir.tokens}, expected_output="ranked source signatures"),
        ]
        if ir.target_ir in {"RUN_CANVAS"}:
            steps.append(PlanStep(order=3, action="schedule_canvas", inputs=ir.scope_constraints, expected_output="canvas job or existing signatures"))
        elif ir.target_ir in {"RUN_INVENTION", "CODE_GENERATE"}:
            steps.append(PlanStep(order=3, action="decompose_problem", inputs=ir.scope_constraints, expected_output="sub-problems & dependencies"))
            steps.append(PlanStep(order=4, action="generate_sub_functions", inputs=ir.scope_constraints, expected_output="independent code modules"))
            steps.append(PlanStep(order=5, action="assemble_code", inputs=ir.scope_constraints, expected_output="fully assembled solution"))
            steps.append(PlanStep(order=6, action="run_recursive_planner", inputs=ir.scope_constraints, expected_output="candidate plan"))
            steps.append(PlanStep(order=7, action="simulate_candidates", inputs=ir.scope_constraints, expected_output="bounded simulation result"))
        else:
            steps.append(PlanStep(order=3, action="compose_reasoning_chain", inputs=ir.scope_constraints, expected_output="verified chain"))
        steps.append(PlanStep(order=len(steps) + 1, action="render_csse", inputs={"mode": "FACT"}, expected_output="grounded response"))
        return ExecutionPlan(goal=ir.target_ir, steps=steps)
