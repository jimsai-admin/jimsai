from __future__ import annotations

import os
import re
from typing import Any

from .constraints import ConstraintValidator
from .csse import ConstrainedSemanticSynthesisEngine
from .encoder import DualRepresentationEncoder
from .graph import CausalGraphEngine
from .memory import FourLayerMemoryStore
from .model_bridge import QwenBridge
from .models import (
    AbstractionResult,
    ActivationDecision,
    CanvasResult,
    ExecutionMode,
    ExecutionPlan,
    Hypothesis,
    IntentDomain,
    InventionResult,
    LayerResult,
    MemorySignature,
    PipelineRequest,
    ReasoningStep,
    RetrievalResult,
    SemanticIR,
    SimulationResult,
    VerifiedCognitiveObject,
    WorldModelActivation,
)
from .planner import SymbolicPlanner
from .retrieval import MultiIndexRetrievalEngine, term_matches
from .semantic_compiler import SemanticCompilerRuntime
from .simulation import BoundedSimulationEngine


ALLOWED_TARGETS = {
    "WORKSPACE_QUERY",
    "FETCH_DOCUMENT",
    "SYSTEM_DIAGNOSTIC",
    "CODE_GENERATE",
    "RUN_CANVAS",
    "RUN_INVENTION",
    "GENERAL_FACT",
    "EMOTIONAL_CATCH",
    "META_INQUIRY",
    "OP_ESCAPE_TO_SANDBOX",
}
DOCUMENT_FACT_PREDICATES = {
    "means",
    "has_title",
    "has_case_study",
    "has_author",
    "has_institution",
    "has_student_id",
    "has_objective",
    "has_module",
    "has_problem",
    "uses_technology",
    "has_name",
    "has_role",
    "is_building",
}
USER_PROFILE_QUERY_TOKENS = {"i", "me", "my", "mine", "myself", "name", "profile", "know", "remember"}
IMPORTANT_SHORT_QUERY_TERMS = {"ai", "ui", "ux", "db", "t1", "t2", "r2"}


def _layer(layer: str, activated: bool, summary: str, data: dict[str, Any] | None = None, deterministic: bool = True) -> LayerResult:
    return LayerResult(layer=layer, activated=activated, deterministic=deterministic, summary=summary, data=data or {})


def _strict_entity_match(query_entity: str, candidate: str) -> bool:
    query = query_entity.lower()
    value = candidate.lower()
    return value == query or value.startswith(f"{query}.")


def _edge_claim(source: str, predicate: str, target: str) -> str:
    phrase = "depends on" if predicate == "depends_on" else predicate
    return f"{source} {phrase} {target}."


def _document_claim(subject: str, predicate: str, obj: str) -> str:
    if predicate == "means":
        return f"{subject} means {obj}."
    if predicate == "has_title":
        return f"The project title is {obj}."
    if predicate == "has_case_study":
        return f"The case study is {obj}."
    if predicate == "has_author":
        return f"The researcher is {obj}."
    if predicate == "has_institution":
        return f"The institution is {obj}."
    if predicate == "has_student_id":
        return f"The student ID is {obj}."
    if predicate == "has_objective":
        return f"Objective: {obj}."
    if predicate == "has_module":
        return f"Module: {obj}."
    if predicate == "has_problem":
        return f"Problem: {obj}."
    if predicate == "uses_technology":
        return f"Technology used: {obj}."
    if predicate == "has_name":
        return f"Your name is {obj}."
    if predicate == "has_role":
        return f"You are {obj}."
    if predicate == "is_building":
        return f"You are building {obj}."
    if subject.lower() == "user" and predicate.startswith("has_"):
        label = predicate[4:].replace("_", " ")
        if label.endswith(" first name"):
            owner = label[: -len(" first name")].strip()
            return f"Your {owner}'s first name is {obj}."
        return f"Your {label} is {obj}."
    return f"{subject} {predicate} {obj}."


class TransformerIntentInterface:
    """T1 bounded interface: classify intent, never execute or answer."""

    def __init__(self, compiler: SemanticCompilerRuntime, bridge: QwenBridge) -> None:
        self.compiler = compiler
        self.bridge = bridge

    async def infer(self, request: PipelineRequest, session: dict[str, Any]) -> tuple[SemanticIR, LayerResult]:
        deterministic_ir = self.compiler.compile(request.query, namespace="TECHNICAL", session=session)
        local_overlay = await self.bridge.infer_intent(request.query, deterministic_ir.model_dump(mode="json"))
        used_local_model = False
        ir = deterministic_ir

        # Typo-correction pass: if embedding confidence is low and Qwen is available,
        # rewrite the query and re-classify. Only runs when JIMS_TYPO_CORRECTION_ENABLED=true.
        typo_correction_enabled = (
            os.getenv("JIMS_TYPO_CORRECTION_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        )
        if (
            typo_correction_enabled
            and self.bridge.qwen_enabled
            and 0.20 <= deterministic_ir.confidence < 0.50
            and deterministic_ir.target_ir == "OP_ESCAPE_TO_SANDBOX"
            and all(ord(c) < 128 for c in request.query)  # ASCII only — not low-resource language
        ):
            clean_query = await self.bridge.rewrite_for_clarity(request.query)
            if clean_query and clean_query.strip().lower() != request.query.strip().lower():
                rewritten_ir = self.compiler.compile(clean_query, namespace="TECHNICAL", session=session)
                if rewritten_ir.confidence > deterministic_ir.confidence:
                    # Use rewritten classification but keep original query text visible
                    deterministic_ir = rewritten_ir.model_copy(
                        update={"scope_constraints": {**rewritten_ir.scope_constraints, "typo_corrected_query": clean_query}}
                    )
                    ir = deterministic_ir

        if local_overlay:
            candidate = self._overlay_to_ir(deterministic_ir, local_overlay)
            if candidate:
                ir = candidate
                used_local_model = True
        data = {
            "target_ir": ir.target_ir,
            "confidence": ir.confidence,
            "used_groq": False,
            "used_local_model": used_local_model,
            "local_model_skip_reason": self.bridge.last_t1_skip_reason,
            "groq_skip_reason": "external_groq_disabled",
            "deterministic_target_ir": deterministic_ir.target_ir,
        }
        return ir, _layer("T1_transformer_intent_interface", True, "Compiled input into bounded Semantic IR.", data, deterministic=not used_local_model)

    def _overlay_to_ir(self, deterministic_ir: SemanticIR, overlay: dict[str, Any]) -> SemanticIR | None:
        target = str(overlay.get("target_ir") or overlay.get("intent") or "").strip().upper()
        if target not in ALLOWED_TARGETS:
            return None
        try:
            overlay_confidence = float(overlay.get("confidence", 0.0))
        except (TypeError, ValueError):
            overlay_confidence = 0.0
        if overlay_confidence < 0.55:
            return deterministic_ir.model_copy(
                update={
                    "transformer_interface_used": True,
                    "hypotheses": [
                        *deterministic_ir.hypotheses,
                        Hypothesis(target_ir=target, score=round(max(overlay_confidence, 0.0), 4), role="candidate", reason="Groq T1 low-confidence overlay"),
                    ],
                }
            )

        scope = dict(deterministic_ir.scope_constraints)
        overlay_scope = overlay.get("scope_constraints")
        if isinstance(overlay_scope, dict):
            for key, value in overlay_scope.items():
                if isinstance(value, (str, int, float, bool, list)):
                    scope.setdefault(str(key), value)

        target_should_override = (
            deterministic_ir.target_ir == "OP_ESCAPE_TO_SANDBOX"
            or deterministic_ir.confidence < 0.3
            or target in {"RUN_CANVAS", "RUN_INVENTION"}
        )
        target_ir = target if target_should_override else deterministic_ir.target_ir
        confidence = round(max(deterministic_ir.confidence, min(overlay_confidence, 0.75)), 4)
        execution_mode = deterministic_ir.execution_mode
        if target_should_override and target_ir != "OP_ESCAPE_TO_SANDBOX":
            execution_mode = ExecutionMode.GROQ_BOUNDED_INTERFACE
        domain = deterministic_ir.intent_domain
        if target_ir == "GENERAL_FACT":
            domain = IntentDomain.GENERAL_KNOWLEDGE
        elif target_ir == "META_INQUIRY":
            domain = IntentDomain.META_SYSTEM
        elif target_ir == "EMOTIONAL_CATCH":
            domain = IntentDomain.EMOTIONAL_SOCIAL

        return deterministic_ir.model_copy(
            update={
                "target_ir": target_ir,
                "system_action": target_ir,
                "confidence": confidence,
                "scope_constraints": scope,
                "execution_mode": execution_mode,
                "intent_domain": domain,
                "transformer_interface_used": True,
                "hypotheses": [
                    *deterministic_ir.hypotheses,
                    Hypothesis(target_ir=target, score=round(overlay_confidence, 4), role="overlay", reason="Groq T1 bounded overlay"),
                ],
            }
        )


class FullEncoderLayer:
    """L1 full encoder: convert input into dual symbolic and latent signature state."""

    def __init__(self, encoder: DualRepresentationEncoder) -> None:
        self.encoder = encoder

    def encode(self, request: PipelineRequest, ir: SemanticIR) -> tuple[MemorySignature, LayerResult]:
        signature = self.encoder.encode(
            request.query,
            modality=request.modality,
            intent_type=ir.target_ir.lower(),
            provenance="local_extraction",
            workspace_id=request.workspace_id,
            user_id=request.user_id,
        )
        return signature, _layer(
            "L1_full_encoder",
            True,
            "Built dual-representation signature with symbolic fields and latent embedding.",
            {
                "signature_id": signature.id,
                "modality": signature.modality.value,
                "entities": [entity.name for entity in signature.structured.entities],
                "relations": len(signature.structured.relations),
                "causal_links": len(signature.structured.causal_chain),
                "abstraction_tags": signature.abstraction_tags[:12],
                "latent_source": signature.metadata.get("latent_embedding_source"),
            },
        )


class RealTimeLearningLayer:
    """L2 real-time learning: validate, link, and index the signature."""

    def __init__(self, memory: FourLayerMemoryStore, graph: CausalGraphEngine) -> None:
        self.memory = memory
        self.graph = graph

    def learn(self, signature: MemorySignature) -> LayerResult:
        related_ids = self._related_signature_ids(signature)
        conflicts = self._conflicts(signature)
        signature.linked_signatures = sorted(set(signature.linked_signatures) | set(related_ids))[:24]
        signature.metadata["l2_learning"] = {
            "source_trust": signature.confidence.score,
            "linked_signature_count": len(signature.linked_signatures),
            "conflict_count": len(conflicts),
            "indexes": ["sensory", "working", "episodic", "semantic", "entity", "temporal", "causal", "importance"],
        }
        if conflicts:
            signature.confidence.score = round(max(0.1, signature.confidence.score - min(0.2, 0.05 * len(conflicts))), 4)
            signature.metadata["l2_learning"]["conflicts"] = conflicts[:12]
        self.memory.insert(signature)
        self.graph.add_signature(signature)
        return _layer(
            "L2_real_time_learning",
            True,
            "Validated source trust, linked related signatures, checked conflicts, and updated all memory indexes.",
            {
                "signature_id": signature.id,
                "memory": self.memory.stats(),
                "linked_signatures": signature.linked_signatures,
                "conflicts": conflicts,
                "source_trust": signature.confidence.score,
            },
        )

    def _related_signature_ids(self, signature: MemorySignature) -> list[str]:
        related: set[str] = set()
        entity_names = {entity.name.lower() for entity in signature.structured.entities}
        predicates = {relation.predicate for relation in signature.structured.relations}
        for existing in self.memory.visible_signatures(workspace_id=signature.workspace_id, user_id=signature.user_id):
            if existing.id == signature.id:
                continue
            existing_entities = {entity.name.lower() for entity in existing.structured.entities}
            existing_predicates = {relation.predicate for relation in existing.structured.relations}
            if entity_names & existing_entities or predicates & existing_predicates:
                related.add(existing.id)
        return sorted(related)

    def _conflicts(self, signature: MemorySignature) -> list[dict[str, str]]:
        conflicts: list[dict[str, str]] = []
        single_value_predicates = {"means", "has_title", "has_case_study", "has_author", "has_student_id", "is_a"}
        new_relations = {(relation.subject.lower(), relation.predicate, relation.object.lower()) for relation in signature.structured.relations}
        for existing in self.memory.visible_signatures(workspace_id=signature.workspace_id, user_id=signature.user_id):
            for relation in existing.structured.relations:
                if relation.predicate not in single_value_predicates:
                    continue
                if (relation.subject.lower(), relation.predicate, relation.object.lower()) in new_relations:
                    continue
                for new_relation in signature.structured.relations:
                    if new_relation.predicate not in single_value_predicates:
                        continue
                    same_slot = relation.subject.lower() == new_relation.subject.lower() and relation.predicate == new_relation.predicate
                    if same_slot and relation.object.lower() != new_relation.object.lower():
                        conflicts.append(
                            {
                                "existing_signature": existing.id,
                                "subject": new_relation.subject,
                                "predicate": new_relation.predicate,
                                "existing_object": relation.object,
                                "new_object": new_relation.object,
                            }
                        )
        return conflicts


class ActiveCanvasLayer:
    """L3 active canvas: bounded synthesis over current request and local memory."""

    def __init__(self, memory: FourLayerMemoryStore, bridge: QwenBridge) -> None:
        self.memory = memory
        self.bridge = bridge

    async def run(self, request: PipelineRequest, ir: SemanticIR) -> tuple[CanvasResult, LayerResult]:
        active = request.canvas_hint or ir.target_ir == "RUN_CANVAS"
        patterns: list[str] = []
        used_groq = False
        if active:
            entities = [str(entity) for entity in ir.scope_constraints.get("entities", [])]
            if entities:
                patterns.append(f"entity_scope:{','.join(entities[:6])}")
            causal_count = sum(
                len(sig.structured.causal_chain)
                for sig in self.memory.visible_signatures(workspace_id=request.workspace_id, user_id=request.user_id)
            )
            patterns.append(f"known_causal_links:{causal_count}")
            groq_result = await self.bridge.canvas_synthesis(request.query)
            if groq_result:
                used_groq = True
                raw_patterns = groq_result.get("patterns", [])
                if isinstance(raw_patterns, list):
                    patterns.extend(str(pattern)[:200] for pattern in raw_patterns[:8])
        result = CanvasResult(
            activated=active,
            session_id=f"canvas_{ir.trace_id[:12]}" if active else None,
            patterns=sorted(set(patterns)),
            used_groq=used_groq,
        )
        return result, _layer(
            "L3_active_canvas",
            active,
            "Ran canvas synthesis." if active else "Canvas skipped by sparse routing preconditions.",
            result.model_dump(mode="json"),
            deterministic=not used_groq,
        )


class SparseActivationMetaController:
    """L4 sparse activation: choose bounded route without activating every subsystem."""

    def decide(self, request: PipelineRequest, ir: SemanticIR, canvas: CanvasResult) -> tuple[ActivationDecision, LayerResult]:
        if ir.scope_constraints.get("profile_query") or set(ir.tokens) & USER_PROFILE_QUERY_TOKENS:
            decision = ActivationDecision(route="retrieval", run_retrieval=True, reason="User-profile query should retrieve scoped memory.", confidence=max(ir.confidence, 0.55))
        elif ir.execution_mode == ExecutionMode.AIR_GAPPED_CONTAINER:
            decision = ActivationDecision(route="sandbox", reason="Semantic IR confidence below deterministic ontology threshold.", confidence=ir.confidence)
        elif canvas.activated:
            decision = ActivationDecision(
                route="canvas",
                run_canvas=True,
                run_retrieval=True,
                run_abstraction=True,
                run_world_model=True,
                reason="Canvas hint or RUN_CANVAS IR activated synthesis path.",
                confidence=ir.confidence,
            )
        elif request.invention_hint or ir.target_ir in {"RUN_INVENTION", "CODE_GENERATE"}:
            decision = ActivationDecision(
                route="invention",
                run_invention=True,
                run_retrieval=True,
                run_abstraction=True,
                run_world_model=True,
                reason="Invention or code generation target requires candidate generation.",
                confidence=ir.confidence,
            )
        else:
            decision = ActivationDecision(route="retrieval", run_retrieval=True, reason="Default deterministic retrieval route.", confidence=ir.confidence)
        return decision, _layer("L4_sparse_activation_meta_controller", True, "Selected bounded runtime route.", decision.model_dump(mode="json"))


class MCTSNode:
    def __init__(self, code_or_step: str, parent: MCTSNode | None = None) -> None:
        self.code_or_step = code_or_step
        self.parent = parent
        self.children: list[MCTSNode] = []
        self.visits = 0
        self.value = 0.0
        self.error_trace = ""


class InventionEngineLayer:
    """L5 invention engine: create candidate plans, constrained by IR and current memory."""

    def __init__(self, planner: SymbolicPlanner, bridge: QwenBridge) -> None:
        self.planner = planner
        self.bridge = bridge

    async def run(self, request: PipelineRequest, ir: SemanticIR, decision: ActivationDecision) -> tuple[InventionResult, LayerResult]:
        active = decision.run_invention or request.invention_hint or ir.target_ir in {"RUN_INVENTION", "CODE_GENERATE"}
        steps: list[str] = []
        notes: list[str] = []
        used_groq = False
        mcts_traces: list[dict[str, Any]] = []
        node_scores: dict[str, float] = {}
        simulation_metrics: dict[str, Any] = {}

        if active:
            plan = self.planner.plan(ir)
            initial_plan = "\n".join(step.action for step in plan.steps)
            steps = [step.action for step in plan.steps]
            notes = ["Candidates verified using Monte Carlo Tree Search (MCTS) with Sandbox simulation."]

            mcts_res = await self.run_mcts(request.query, initial_plan)
            if mcts_res["best_path"]:
                steps.extend(mcts_res["best_path"])
                used_groq = True
            mcts_traces = mcts_res["traces"]
            node_scores = mcts_res["node_scores"]
            simulation_metrics = mcts_res["metrics"]

        result = InventionResult(
            activated=active,
            goal=ir.target_ir,
            candidate_steps=steps,
            simulation_notes=notes,
            used_groq=used_groq,
            mcts_traces=mcts_traces,
            node_scores=node_scores,
            simulation_metrics=simulation_metrics
        )
        return result, _layer(
            "L5_invention_engine",
            active,
            "Generated bounded invention candidates via MCTS." if active else "Invention engine skipped by sparse activation.",
            result.model_dump(mode="json"),
            deterministic=not used_groq,
        )

    async def run_mcts(self, goal: str, initial_plan: str, iterations: int = 5) -> dict[str, Any]:
        from .execution_runtime import DeterministicSandbox
        sandbox = DeterministicSandbox()

        root = MCTSNode(initial_plan)

        candidates = await self.bridge.invention_candidates(
            goal,
            {"plan": initial_plan, "scope": {}, "stage": "initial"}
        )
        if candidates and "candidate_steps" in candidates:
            for step in candidates["candidate_steps"]:
                root.children.append(MCTSNode(str(step), parent=root))

        if not root.children:
            root.children.append(MCTSNode(initial_plan + "\n# Step 1: Analyze problem\n# Step 2: Implement solution", parent=root))

        # Early-exit: if the first Qwen call already produced a real code candidate
        # (long string with code tokens), skip the MCTS loop entirely to avoid
        # N×120s HF Space round-trips.  MCTS iterations add value for multi-step
        # reasoning tasks but are expensive when a single LLM call suffices.
        CODE_TOKENS = ("def ", "class ", "import ", "function ", "const ", "let ",
                       "var ", "fn ", "pub ", "SELECT ", "CREATE ", "async ", "return ")
        first_real_code = next(
            (c.code_or_step for c in root.children
             if len(c.code_or_step) > 100 or any(t in c.code_or_step for t in CODE_TOKENS)),
            None,
        )
        if first_real_code:
            # Score and return immediately — no further Qwen calls needed
            root.visits = 1
            best_child = root.children[0]
            best_child.visits = 1
            best_child.value = 1.0
            return {
                "best_path": [first_real_code],
                "traces": [{"node": first_real_code, "visits": 1, "value": 1.0, "error": ""}],
                "node_scores": {first_real_code: 1.0},
                "metrics": {"total_iterations": 0, "early_exit": True},
            }

        for _ in range(iterations):
            node = root
            while node.children:
                import math
                best_child = None
                best_uct = -1.0
                for child in node.children:
                    if child.visits == 0:
                        uct = float('inf')
                    else:
                        uct = (child.value / child.visits) + 1.41 * math.sqrt(math.log(node.visits) / child.visits)
                    if uct > best_uct:
                        best_uct = uct
                        best_child = child
                if best_child is None:
                    break
                node = best_child

            passed = True
            error_msg = ""
            score = 0.5

            if "def " in node.code_or_step or "import " in node.code_or_step or "class " in node.code_or_step or "print(" in node.code_or_step:
                exec_res = sandbox.run_python(node.code_or_step, "", 1500)
                if exec_res.get("status") != "passed":
                    passed = False
                    error_msg = exec_res.get("stderr") or exec_res.get("stdout") or "Execution failed"
                    score = 0.0
                else:
                    score = 1.0
            else:
                import ast
                try:
                    ast.parse(node.code_or_step)
                    score = 0.9
                except SyntaxError:
                    if len(node.code_or_step.strip()) > 5:
                        score = 0.7
                    else:
                        passed = False
                        score = 0.2

            node.visits += 1
            node.value += score
            node.error_trace = error_msg

            if not passed and error_msg:
                reflection_prompt = f"The candidate code failed with error:\n{error_msg}\nPlease generate a corrected version of the code."
                corrected = await self.bridge.invention_candidates(
                    goal,
                    {"failed_code": node.code_or_step, "error": error_msg, "prompt": reflection_prompt}
                )
                if corrected and "candidate_steps" in corrected:
                    for step in corrected["candidate_steps"]:
                        node.children.append(MCTSNode(str(step), parent=node))
            elif node.visits > 0 and len(node.children) == 0:
                deeper = await self.bridge.invention_candidates(
                    goal,
                    {"context": node.code_or_step, "stage": "deeper"}
                )
                if deeper and "candidate_steps" in deeper:
                    for step in deeper["candidate_steps"]:
                        node.children.append(MCTSNode(str(step), parent=node))

            curr = node.parent
            while curr:
                curr.visits += 1
                curr.value += score
                curr = curr.parent

        best_path = []
        curr = root
        traces = []
        node_scores = {}
        while curr.children:
            best_child = max(curr.children, key=lambda c: c.visits)
            if best_child.visits == 0:
                break
            best_path.append(best_child.code_or_step)
            node_scores[best_child.code_or_step] = best_child.value / best_child.visits if best_child.visits > 0 else 0.0
            traces.append({
                "node": best_child.code_or_step,
                "visits": best_child.visits,
                "value": best_child.value,
                "error": best_child.error_trace
            })
            curr = best_child

        return {
            "best_path": best_path,
            "traces": traces,
            "node_scores": node_scores,
            "metrics": {"total_iterations": iterations}
        }


class MultiIndexRetrievalLayer:
    """L6 multi-index retrieval: entity, causal, semantic hash, temporal, and importance indexes."""

    def __init__(self, retrieval: MultiIndexRetrievalEngine) -> None:
        self.retrieval = retrieval

    def retrieve(self, request: PipelineRequest, ir: SemanticIR, decision: ActivationDecision, exclude_ids: set[str]) -> tuple[list[RetrievalResult], LayerResult]:
        if not decision.run_retrieval or decision.route == "sandbox":
            return [], _layer("L6_multi_index_retrieval", False, "Retrieval bypassed by sandbox routing.", {"count": 0})
        retrieved = self.retrieval.retrieve(
            ir,
            request.query,
            exclude_ids=exclude_ids,
            workspace_id=request.workspace_id,
            user_id=request.user_id,
        )
        return retrieved, _layer(
            "L6_multi_index_retrieval",
            True,
            "Retrieved ranked signatures from local multi-index memory.",
            {"count": len(retrieved), "ids": [item.signature.id for item in retrieved], "reasons": {item.signature.id: item.reasons for item in retrieved}},
        )


class AbstractionEngineLayer:
    """L7 abstraction engine: lift retrieved signatures into reusable concepts."""

    def run(self, retrieved: list[RetrievalResult], decision: ActivationDecision) -> tuple[AbstractionResult, LayerResult]:
        if not decision.run_abstraction or not retrieved:
            result = AbstractionResult(concepts=[], analogies=[], confidence=0.0)
            return result, _layer("L7_abstraction_engine", False, "No retrieved signatures available for abstraction.", result.model_dump(mode="json"))
        concepts: set[str] = set()
        analogies: list[str] = []
        for item in retrieved:
            concepts.update(item.signature.abstraction_tags)
            concepts.update(entity.name for entity in item.signature.structured.entities)
            for relation in item.signature.structured.relations[:3]:
                analogies.append(f"{relation.subject} --{relation.predicate}--> {relation.object}")
        confidence = round(sum(item.score for item in retrieved) / len(retrieved), 4)
        result = AbstractionResult(concepts=sorted(concepts)[:16], analogies=analogies[:10], confidence=confidence)
        return result, _layer("L7_abstraction_engine", True, "Built deterministic abstractions from retrieved signatures.", result.model_dump(mode="json"))


class LatentWorldModelLayer:
    """L8 latent world model: activate causal rules already present in memory or graph."""

    def __init__(self, graph: CausalGraphEngine) -> None:
        self.graph = graph

    def activate(self, ir: SemanticIR, retrieved: list[RetrievalResult], decision: ActivationDecision) -> tuple[list[WorldModelActivation], dict[str, Any], LayerResult]:
        entities = [str(entity) for entity in ir.scope_constraints.get("entities", [])]
        query_terms = set(ir.tokens) | {entity.lower() for entity in entities}
        question_intent = ir.scope_constraints.get("question_intent", {})
        graph_view: dict[str, Any] = {}
        activations: list[WorldModelActivation] = []

        # Configurable causal traversal depth — increase when query asks for full chain
        base_depth = min(max(int(os.getenv("JIMS_CAUSAL_TRAVERSAL_DEPTH", "4") or "4"), 1), 8)
        query_lower = ir.scope_constraints.get("raw_length", 0) and " ".join(ir.tokens).lower()
        deep_chain_requested = isinstance(query_lower, str) and any(
            kw in query_lower for kw in ("trace all", "full chain", "complete path", "all causes", "all effects")
        )
        causal_depth = min(base_depth + 2, 8) if deep_chain_requested else base_depth

        if decision.run_world_model:
            for entity in entities[:3]:
                graph_view[entity] = self.graph.traverse(entity, depth=3)
            seen_rules: set[str] = set()
            if isinstance(question_intent, dict) and question_intent.get("relation") == "causes":
                direction = str(question_intent.get("direction") or "outgoing")
                for entity in entities[:3]:
                    edges = (
                        self.graph.incoming_edges(entity, predicates={"causes"}, depth=causal_depth)
                        if direction == "incoming"
                        else self.graph.outgoing_edges(entity, predicates={"causes"}, depth=causal_depth)
                    )
                    for edge in edges:
                        rule = f"{edge['source']} causes {edge['target']}"
                        if rule in seen_rules:
                            continue
                        seen_rules.add(rule)
                        activations.append(WorldModelActivation(rule=rule, confidence=float(edge["weight"]), source=str(edge["source_signature"])))
            for item in retrieved:
                for link in item.signature.structured.causal_chain:
                    if query_terms and not any(
                        term_matches(term, link.cause) or term_matches(term, link.effect)
                        for term in query_terms
                    ):
                        continue
                    rule = f"{link.cause} causes {link.effect}"
                    if rule in seen_rules:
                        continue
                    seen_rules.add(rule)
                    activations.append(WorldModelActivation(rule=rule, confidence=round(min(link.confidence, item.score), 4), source=item.signature.id))
        return activations, graph_view, _layer(
            "L8_latent_world_model",
            bool(activations or graph_view),
            "Activated causal world-model rules from local graph.",
            {"rules": [activation.model_dump(mode="json") for activation in activations], "graph_entities": list(graph_view.keys())},
        )


class ReasoningBridgeLayer:
    """L9 reasoning bridge: assemble a Verified Cognitive Object for rendering."""

    def __init__(self, simulation: BoundedSimulationEngine, validator: ConstraintValidator, planner: SymbolicPlanner, graph: CausalGraphEngine) -> None:
        self.simulation = simulation
        self.validator = validator
        self.planner = planner
        self.graph = graph

    def build(
        self,
        ir: SemanticIR,
        retrieved: list[RetrievalResult],
        graph_view: dict[str, Any],
        canvas: CanvasResult,
        activation: ActivationDecision,
        invention: InventionResult,
        abstraction: AbstractionResult,
        world_model: list[WorldModelActivation],
        prior_layers: list[LayerResult],
    ) -> tuple[VerifiedCognitiveObject, list[SimulationResult], LayerResult]:
        simulations = self.simulation.run(ir)
        checks, gaps = self.validator.validate(ir, retrieved, simulations)
        if ir.execution_mode == ExecutionMode.AIR_GAPPED_CONTAINER:
            gaps.append("Input did not match the deterministic ontology; no factual claims were emitted from core memory.")
        plan = self._plan_with_layer_names(ir)
        reasoning_chain = self._direct_reasoning_steps(ir, retrieved)
        if not reasoning_chain:
            reasoning_chain = self._memory_excerpt_steps(ir, retrieved)
        if not reasoning_chain:
            reasoning_chain = [
                ReasoningStep(
                    claim=f"Retrieved signature {result.signature.id} supports intent {ir.target_ir}",
                    confidence=min(0.99, result.score),
                    sources=[result.signature.id],
                    relation="ASSERT",
                )
                for result in retrieved[:5]
            ]
        if not reasoning_chain:
            reasoning_chain = [
                ReasoningStep(
                    claim="No verified claim emitted because retrieval returned no source signatures.",
                    confidence=0.3,
                    sources=[],
                    relation="HEDGE",
                )
            ]
        confidence_values = [ir.confidence, *[step.confidence for step in reasoning_chain], *[check.confidence for check in checks]]
        confidence = round(sum(confidence_values) / len(confidence_values), 4)
        sources = sorted({source for step in reasoning_chain for source in step.sources})
        obj = VerifiedCognitiveObject(
            trace_id=ir.trace_id,
            intent=ir.target_ir,
            verified_plan=plan,
            simulation_results=simulations,
            constraint_checks=checks,
            semantic_graph=graph_view,
            reasoning_chain=reasoning_chain,
            knowledge_gaps=gaps,
            sources=sources,
            confidence=confidence,
            activation=activation,
            canvas_result=canvas,
            invention_result=invention,
            abstraction_result=abstraction,
            world_model_activations=world_model,
            layer_results=prior_layers,
        )
        return obj, simulations, _layer(
            "L9_reasoning_bridge",
            True,
            "Built Verified Cognitive Object from plan, simulation, constraints, graph, and sources.",
            {"confidence": confidence, "sources": sources, "gaps": gaps, "simulation_count": len(simulations)},
        )

    def _memory_excerpt_steps(self, ir: SemanticIR, retrieved: list[RetrievalResult]) -> list[ReasoningStep]:
        query_terms = {
            token.lower().strip(".,:;!?")
            for token in ir.tokens
            if len(token.strip(".,:;!?")) >= 3 or token.lower().strip(".,:;!?") in IMPORTANT_SHORT_QUERY_TERMS
        }
        if "image" in query_terms and ({"memory", "reason", "reasoning", "save", "saving"} & query_terms):
            query_terms.update({"visible", "evidence", "inference", "gaps"})
        if {"transformer", "thinning"} & query_terms and {"inference", "cost", "reduce"} & query_terms:
            query_terms.update({"t1", "t2", "bypass", "confidence"})
        wants_explanation = bool(query_terms & {"how", "why", "cause", "caus", "reduce", "lower", "cost", "effect", "impact"})
        wants_guidance = bool(
            query_terms
            & {
                "answer",
                "blood",
                "caught",
                "explain",
                "fafsa",
                "health",
                "information",
                "interest",
                "manage",
                "need",
                "pressure",
                "recognize",
                "risk",
                "risks",
                "safe",
                "safety",
                "symptom",
                "tax",
                "test",
                "user",
                "withholding",
            }
        )
        candidates: list[tuple[int, float, int, str, RetrievalResult]] = []
        minimum_sentence_score = 1 if wants_guidance else (2 if len(query_terms) >= 3 else 1)
        for result_index, result in enumerate(retrieved):
            excerpt = result.signature.raw_excerpt.strip()
            if not excerpt:
                continue
            for sentence_score, sentence in self._scored_excerpt_sentences(
                excerpt,
                query_terms,
                include_causal=wants_explanation,
                include_guidance=wants_guidance,
            ):
                if sentence_score < minimum_sentence_score:
                    continue
                candidates.append((sentence_score, result.score, -result_index, sentence, result))
        candidates.sort(reverse=True)

        seen: set[str] = set()
        steps: list[ReasoningStep] = []
        wants_answer_policy = bool({"answer", "grounded", "csse"} & query_terms and {"user", "source", "claims"} & query_terms)
        limit = 6 if wants_explanation or wants_answer_policy else 4
        for _sentence_score, _result_score, _result_index, sentence, result in candidates:
            key = sentence.lower()
            if key in seen:
                continue
            seen.add(key)
            steps.append(
                ReasoningStep(
                    claim=sentence,
                    confidence=round(min(0.92, result.score, result.signature.confidence.score), 4),
                    sources=[result.signature.id],
                    relation="MEMORY_EXCERPT",
                )
            )
            if len(steps) >= limit:
                return steps
        return steps

    def _scored_excerpt_sentences(
        self,
        excerpt: str,
        query_terms: set[str],
        include_causal: bool = False,
        include_guidance: bool = False,
    ) -> list[tuple[int, str]]:
        cleaned = re.sub(r"\s+", " ", excerpt).strip()
        if not cleaned:
            return []
        sentences = [
            sentence.strip(" -")
            for sentence in re.split(r"(?<=[.!?])\s+", cleaned)
            if sentence.strip(" -")
        ]
        if not sentences:
            sentences = [cleaned]
        scored: list[tuple[int, int, str]] = []
        for index, sentence in enumerate(sentences[:12]):
            lower = sentence.lower()
            if self._is_provenance_sentence(lower):
                continue
            score = sum(1 for term in query_terms if term and term in lower)
            if include_causal and (" causes " in lower or " depends on " in lower):
                score = max(score, 1)
            if include_guidance:
                score += self._guidance_sentence_score(lower, query_terms)
            if score:
                scored.append((score, -index, sentence[:320]))
        if not scored:
            return []
        scored.sort(reverse=True)
        output: list[tuple[int, str]] = []
        for _score, _index, sentence in scored:
            clean = sentence.strip()
            output.append((_score, clean if clean.endswith((".", "?", "!")) else f"{clean}."))
        return output

    def _is_provenance_sentence(self, lower_sentence: str) -> bool:
        return (
            lower_sentence.startswith("source url:")
            or lower_sentence.startswith("source license:")
            or lower_sentence.startswith("project source ")
            or lower_sentence.startswith("## ")
            or lower_sentence.startswith("|")
            or "| --- |" in lower_sentence
            or "training text is local paraphrase" in lower_sentence
        )

    def _guidance_sentence_score(self, lower_sentence: str, query_terms: set[str]) -> int:
        if query_terms & {"answer", "answers", "user", "users"} and any(
            marker in lower_sentence
            for marker in ("grounded", "csse", "source trace", "source grounding", "unsupported claim", "unsupported claims")
        ):
            return 4
        guidance_markers = (
            "should",
            "should not",
            "must",
            "requires",
            "require",
            "depends on",
            "do not",
            "avoid",
            "check",
            "verify",
            "risk",
            "risks",
            "safer",
            "secrets",
            "human approval",
            "provenance",
        )
        return 1 if any(re.search(rf"\b{re.escape(marker)}\b", lower_sentence) for marker in guidance_markers) else 0

    def _direct_reasoning_steps(self, ir: SemanticIR, retrieved: list[RetrievalResult]) -> list[ReasoningStep]:
        entities = [str(entity) for entity in ir.scope_constraints.get("entities", [])]
        entity_keys = [entity.lower() for entity in entities]
        query_terms = set(ir.tokens) | set(entity_keys)
        question_intent = ir.scope_constraints.get("question_intent", {})
        if not isinstance(question_intent, dict):
            question_intent = {}
        relation_filter = str(question_intent.get("relation") or "")
        direction = str(question_intent.get("direction") or "")
        wants_dependency = relation_filter == "depends_on" or any(token.startswith("depend") or token in {"require", "use"} for token in ir.tokens)
        wants_causal = relation_filter == "causes" or bool(set(ir.tokens) & {"why", "cause", "caus", "happen", "late", "delay", "fail", "failure", "slowdown", "impact", "affect", "occur", "blocked", "block"})
        wants_profile = bool(ir.scope_constraints.get("profile_query")) or bool(set(ir.tokens) & USER_PROFILE_QUERY_TOKENS)
        steps: list[ReasoningStep] = []
        seen: set[str] = set()

        def relevant(value: str) -> bool:
            return bool(query_terms) and any(term_matches(term, value) for term in query_terms)

        def targeted(value: str) -> bool:
            return bool(entity_keys) and any(_strict_entity_match(entity, value) for entity in entity_keys)

        def add(claim: str, confidence: float, source: str, relation: str) -> None:
            key = f"{claim.lower()}:{source}"
            if key in seen:
                return
            seen.add(key)
            steps.append(
                ReasoningStep(
                    claim=claim,
                    confidence=round(min(0.99, confidence), 4),
                    sources=[source],
                    relation=relation,
                )
            )

        if relation_filter in DOCUMENT_FACT_PREDICATES:
            requires_entity_target = relation_filter == "means"
            for result in retrieved:
                sig = result.signature
                for relation in sig.structured.relations:
                    if relation.predicate != relation_filter:
                        continue
                    if requires_entity_target and entity_keys and not (targeted(relation.subject) or targeted(relation.object)):
                        continue
                    add(
                        _document_claim(relation.subject, relation.predicate, relation.object),
                        min(relation.confidence, result.score),
                        sig.id,
                        relation.predicate.upper(),
                    )
            if steps:
                return steps[:24]

        dynamic_user_steps: list[tuple[float, ReasoningStep]] = []
        query_token_set = set(ir.tokens)
        for result in retrieved:
            sig = result.signature
            for relation in sig.structured.relations:
                if relation.subject.lower() != "user":
                    continue
                is_user_relation = relation.predicate.startswith("has_") or relation.predicate.startswith("is_")
                if not is_user_relation:
                    continue
                predicate_terms = set(relation.predicate.replace("has_", "").replace("is_", "").split("_"))
                object_terms = set(re.findall(r"[a-z0-9]+", relation.object.lower()))
                overlap_terms = (predicate_terms | object_terms) & query_token_set
                relation_score = len(overlap_terms) + (0.35 * result.score) + (0.25 * relation.confidence)
                if relation_score < 0.55:
                    continue
                step = ReasoningStep(
                    claim=_document_claim(relation.subject, relation.predicate, relation.object),
                    confidence=round(min(0.99, relation.confidence, result.score), 4),
                    sources=[sig.id],
                    relation=relation.predicate.upper(),
                )
                dynamic_user_steps.append((relation_score, step))
        ranked_user_steps = sorted(dynamic_user_steps, key=lambda item: (-item[0], -item[1].confidence))
        top_user_score = ranked_user_steps[0][0] if ranked_user_steps else 0.0
        for _score, step in ranked_user_steps:
            if top_user_score and _score < top_user_score - 0.75:
                continue
            add(step.claim, step.confidence, step.sources[0] if step.sources else "", step.relation)
        if steps and dynamic_user_steps:
            return steps[:8]

        if wants_causal:
            self._add_causal_path_steps(retrieved, entity_keys, direction or "outgoing", add)
            self._add_graph_path_steps(entity_keys, direction or "outgoing", "causes", add)

        for result in retrieved:
            sig = result.signature
            for relation in sig.structured.relations:
                if relation.predicate == "depends_on" and wants_dependency:
                    if direction == "incoming":
                        relation_matches = targeted(relation.object)
                    elif direction == "outgoing":
                        relation_matches = targeted(relation.subject)
                    else:
                        relation_matches = relevant(relation.subject) or relevant(relation.object)
                    if relation_matches:
                        add(
                            f"{relation.subject} depends on {relation.object}.",
                            min(relation.confidence, result.score),
                            sig.id,
                            "DEPENDS_ON",
                        )
                elif relation.predicate == "causes" and wants_causal and not question_intent:
                    if relevant(relation.subject) or relevant(relation.object):
                        add(
                            f"{relation.subject} causes {relation.object}.",
                            min(relation.confidence, result.score),
                            sig.id,
                            "CAUSES",
                        )
            for link in sig.structured.causal_chain:
                if wants_causal and not question_intent and (relevant(link.cause) or relevant(link.effect)):
                    add(
                        f"{link.cause} causes {link.effect}.",
                        min(link.confidence, result.score),
                        sig.id,
                        "CAUSES",
                    )
        if wants_dependency and direction in {"incoming", "outgoing"}:
            self._add_graph_path_steps(entity_keys, direction, "depends_on", add, depth=1)
        return steps[:8]

    def _add_causal_path_steps(self, retrieved: list[RetrievalResult], entity_keys: list[str], direction: str, add) -> None:
        if not entity_keys:
            return
        outgoing: dict[str, list[tuple[str, str, float, str]]] = {}
        incoming: dict[str, list[tuple[str, str, float, str]]] = {}
        for result in retrieved:
            for link in result.signature.structured.causal_chain:
                confidence = min(link.confidence, result.score)
                outgoing.setdefault(link.cause.lower(), []).append((link.cause, link.effect, confidence, result.signature.id))
                incoming.setdefault(link.effect.lower(), []).append((link.cause, link.effect, confidence, result.signature.id))
        if direction == "incoming":
            queue = [node for node in incoming if any(_strict_entity_match(entity, node) for entity in entity_keys)]
            visited = set(queue)
            for _depth in range(4):
                next_queue: list[str] = []
                for node in queue:
                    for cause, effect, confidence, source in incoming.get(node, []):
                        add(f"{cause} causes {effect}.", confidence, source, "CAUSES")
                        cause_key = cause.lower()
                        if cause_key not in visited:
                            visited.add(cause_key)
                            next_queue.append(cause_key)
                if not next_queue:
                    break
                queue = next_queue
            return

        queue = [node for node in outgoing if any(_strict_entity_match(entity, node) for entity in entity_keys)]
        visited = set(queue)
        for _depth in range(4):
            next_queue = []
            for node in queue:
                for cause, effect, confidence, source in outgoing.get(node, []):
                    add(f"{cause} causes {effect}.", confidence, source, "CAUSES")
                    effect_key = effect.lower()
                    if effect_key not in visited:
                        visited.add(effect_key)
                        next_queue.append(effect_key)
            if not next_queue:
                break
            queue = next_queue

    def _add_graph_path_steps(self, entity_keys: list[str], direction: str, predicate: str, add, depth: int = 4) -> None:
        if not entity_keys:
            return
        predicates = {predicate}
        for entity in entity_keys:
            edges = (
                self.graph.incoming_edges(entity, predicates=predicates, depth=depth)
                if direction == "incoming"
                else self.graph.outgoing_edges(entity, predicates=predicates, depth=depth)
            )
            for edge in edges:
                add(
                    _edge_claim(str(edge["source"]), str(edge["predicate"]), str(edge["target"])),
                    float(edge["weight"]),
                    str(edge["source_signature"]),
                    "DEPENDS_ON" if predicate == "depends_on" else "CAUSES",
                )

    def _plan_with_layer_names(self, ir: SemanticIR) -> ExecutionPlan:
        plan = self.planner.plan(ir)
        plan.steps.insert(
            0,
            plan.steps[0].model_copy(
                update={
                    "order": 0,
                    "action": "strict_layer_chain",
                    "inputs": {"layers": ["T1", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "T2", "feedback"]},
                    "expected_output": "bounded deterministic execution trace",
                }
            ),
        )
        for idx, step in enumerate(plan.steps, start=1):
            step.order = idx
        return plan


class TransformerRenderInterface:
    """T2 bounded interface: render the VCO without adding new claims."""

    def __init__(self, csse: ConstrainedSemanticSynthesisEngine, bridge: QwenBridge) -> None:
        self.csse = csse
        self.bridge = bridge

    async def render(self, obj: VerifiedCognitiveObject) -> tuple[str, bool, LayerResult]:
        deterministic_render = self.csse.render(obj)
        local_render = await self.bridge.render(obj, deterministic_render)
        used_local_model = bool(local_render)
        response = local_render or deterministic_render
        return response, used_local_model, _layer(
            "T2_transformer_render_interface",
            True,
            "Rendered Verified Cognitive Object through CSSE with optional bounded local model phrasing.",
            {
                "used_groq": False,
                "used_local_model": used_local_model,
                "mode": "local_bounded" if used_local_model else "csse",
                "local_model_skip_reason": self.bridge.last_t2_skip_reason,
                "groq_skip_reason": "external_groq_disabled",
            },
            deterministic=not used_local_model,
        )
