from __future__ import annotations

import os
import re
from typing import Any

from .capability_router import CapabilityAdapterRegistry, CapabilityRouter
from .csse import ConstrainedSemanticSynthesisEngine
from .document_ingestion import extract_document_facts, fact_to_signature, is_document_like
from .encoder import DualRepresentationEncoder, stable_id
from .event_store import AuditEventStore, VerifiedResultCache
from .execution_runtime import DeterministicSandbox, SymbolicMathSolver
from .graph import CausalGraphEngine
from .kaggle_orchestrator import KaggleGPUOrchestrator
from .memory import FourLayerMemoryStore
from .model_bridge import GroqBridge
from .models import (
    CanvasRunRequest,
    CanvasRunResponse,
    FeedbackRequest,
    FeedbackResponse,
    InventionRunRequest,
    InventionRunResponse,
    KaggleTrainingRequest,
    KaggleTrainingResponse,
    LayerResult,
    CausalLink,
    Entity,
    MemoryDeleteRequest,
    MemoryMutationResponse,
    MemoryUpdateRequest,
    PipelineRequest,
    PipelineResponse,
    ReasoningStep,
    Relation,
    ReviewActionRequest,
    ReviewActionResponse,
    SandboxRunRequest,
    SandboxRunResponse,
    MathSolveRequest,
    MathSolveResponse,
    Modality,
    SPPETrainingPair,
    TrainingDashboardResponse,
    TrainingIngestRequest,
    TrainingIngestResponse,
    TrainingPanelItem,
    TrainingPanelPage,
    VerifiedResultSignature,
    WorldModelCandidate,
    utc_now,
)
from .observability import ExecutionTracer
from .planner import SymbolicPlanner
from .retrieval import MultiIndexRetrievalEngine
from .runtime_layers import (
    AbstractionEngineLayer,
    ActiveCanvasLayer,
    FullEncoderLayer,
    InventionEngineLayer,
    LatentWorldModelLayer,
    MultiIndexRetrievalLayer,
    ReasoningBridgeLayer,
    RealTimeLearningLayer,
    SparseActivationMetaController,
    TransformerIntentInterface,
    TransformerRenderInterface,
)
from .semantic_compiler import SemanticCompilerRuntime
from .simulation import BoundedSimulationEngine
from .constraints import ConstraintValidator
from .provider_adapters import ProductionRuntime
from .training_policy import AutoTrainingPolicy


TRAINING_PANEL_IDS = {
    "ingestion",
    "review",
    "ambiguity",
    "memory",
    "world-model",
    "pipeline",
    "sessions",
    "feedback",
    "autonomous",
    "artifacts",
    "evaluation",
}


class JimsAIPipeline:
    def __init__(self) -> None:
        self.production = ProductionRuntime()
        self.kaggle = KaggleGPUOrchestrator()
        self.compiler = SemanticCompilerRuntime()
        self.encoder = DualRepresentationEncoder(multimodal_adapter=self.production.multimodal)
        self.memory = FourLayerMemoryStore()
        self.graph = CausalGraphEngine()
        self.retrieval = MultiIndexRetrievalEngine(self.memory)
        self.simulation = BoundedSimulationEngine(self.graph)
        self.validator = ConstraintValidator()
        self.planner = SymbolicPlanner()
        self.csse = ConstrainedSemanticSynthesisEngine()
        self.bridge = GroqBridge()
        self.intent_layer = TransformerIntentInterface(self.compiler, self.bridge)
        self.encoder_layer = FullEncoderLayer(self.encoder)
        self.learning_layer = RealTimeLearningLayer(self.memory, self.graph)
        self.canvas_layer = ActiveCanvasLayer(self.memory, self.bridge)
        self.activation_layer = SparseActivationMetaController()
        self.capability_router = CapabilityRouter()
        self.capability_adapters = CapabilityAdapterRegistry()
        self.training_policy = AutoTrainingPolicy()
        self.event_store = AuditEventStore()
        self.result_cache = VerifiedResultCache()
        self.sandbox = DeterministicSandbox()
        self.math_solver = SymbolicMathSolver()
        self.invention_layer = InventionEngineLayer(self.planner, self.bridge)
        self.retrieval_layer = MultiIndexRetrievalLayer(self.retrieval)
        self.abstraction_layer = AbstractionEngineLayer()
        self.world_model_layer = LatentWorldModelLayer(self.graph)
        self.reasoning_bridge_layer = ReasoningBridgeLayer(self.simulation, self.validator, self.planner, self.graph)
        self.render_layer = TransformerRenderInterface(self.csse, self.bridge)
        self.sessions: dict[str, dict[str, str]] = {}
        self.feedback_events: list[FeedbackRequest] = []
        self.feedback_history: list[dict[str, object]] = []
        self.training_history: list[TrainingIngestResponse] = []
        self.world_model_candidates: list[WorldModelCandidate] = []
        self.ambiguity_queue: list[dict[str, object]] = []
        self.canvas_sessions: dict[str, CanvasRunResponse] = {}
        self.invention_sessions: dict[str, InventionRunResponse] = {}
        self.kaggle_runs: list[KaggleTrainingResponse] = []
        self.active_training_artifacts: dict[str, str] = {}
        self.retrieval_misses = 0
        self.cloud_authoritative = self.production.settings.cloud_authoritative
        self.hydrated_signatures = self._hydrate_memory()

    def _hydrate_memory(self) -> int:
        if self.cloud_authoritative:
            return 0
        count = 0
        for signature in self.production.load_recent_signatures(limit=750):
            self.memory.insert(signature)
            self.graph.add_signature(signature)
            count += 1
        return count

    def _hydrate_persistent_retrieval(self, request: PipelineRequest, input_signature_id: str, latent_embedding: list[float]) -> int:
        signatures = self.production.retrieve_similar(
            latent_embedding,
            limit=12,
            workspace_id=request.workspace_id,
            user_id=request.user_id,
            exclude_ids={input_signature_id},
        )
        signatures.extend(self._lexical_persistent_hydration(request, exclude_ids={input_signature_id, *[signature.id for signature in signatures]}))
        count = 0
        for signature in signatures:
            if self.memory.get(signature.id):
                continue
            self.memory.insert(signature)
            self.graph.add_signature(signature)
            count += 1
        self.hydrated_signatures += count
        return count

    def _lexical_persistent_hydration(self, request: PipelineRequest, exclude_ids: set[str], limit: int = 150) -> list:
        recent = self.production.load_recent_signatures(limit=limit)
        if not recent:
            return []
        query_terms = self._lexical_query_terms(request.query)
        if not query_terms:
            return []
        scored = []
        for signature in recent:
            if signature.id in exclude_ids:
                continue
            if not self.production._visible_to_scope(signature, workspace_id=request.workspace_id, user_id=request.user_id):
                continue
            score = self._lexical_signature_score(signature, query_terms)
            if score >= 2:
                scored.append((score, signature.confidence.score, signature.created_at, signature))
        scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return [item[3] for item in scored[:8]]

    def _lexical_query_terms(self, query: str) -> set[str]:
        stop_terms = {"what", "how", "why", "the", "and", "for", "with", "about", "should"}
        terms = {
            term
            for term in re.findall(r"[a-z0-9_\-.]+", query.lower())
            if len(term) >= 3 and term not in stop_terms
        }
        expanded = set(terms)
        for term in terms:
            if len(term) > 4 and term.endswith("s"):
                expanded.add(term[:-1])
        return expanded

    def _lexical_signature_score(self, signature, query_terms: set[str]) -> int:
        haystack_parts = [
            signature.raw_excerpt.lower(),
            " ".join(signature.abstraction_tags).lower(),
            " ".join(entity.name for entity in signature.structured.entities).lower(),
            " ".join(f"{relation.subject} {relation.predicate} {relation.object}" for relation in signature.structured.relations).lower(),
            " ".join(f"{link.cause} {link.effect}" for link in signature.structured.causal_chain).lower(),
        ]
        haystack = " ".join(haystack_parts)
        return sum(1 for term in query_terms if term in haystack)

    def _reset_request_cache(self) -> None:
        if self.cloud_authoritative:
            return

    def _load_session(self, user_id: str) -> dict[str, str]:
        if self.cloud_authoritative:
            return self.production.load_session(user_id)
        return self.sessions.setdefault(user_id, {})

    def _save_session(self, user_id: str, session: dict[str, str]) -> None:
        if self.cloud_authoritative:
            self.production.save_session(user_id, session)
        else:
            self.sessions[user_id] = session

    async def run(self, request: PipelineRequest) -> PipelineResponse:
        self._reset_request_cache()
        cache_key = self.result_cache.key(
            "query",
            {
                "user_id": request.user_id,
                "workspace_id": request.workspace_id,
                "query": request.query.strip(),
                "modality": request.modality.value,
                "canvas_hint": request.canvas_hint,
                "invention_hint": request.invention_hint,
            },
        )
        cached = self.result_cache.get(cache_key)
        if cached:
            self.event_store.append(
                "query_cache_hit",
                cache_key,
                {"cache_key": cache_key, "query": request.query, "workspace_id": request.workspace_id},
                user_id=request.user_id,
            )
            return PipelineResponse.model_validate(cached["value"])

        self.event_store.append(
            "query_received",
            cache_key,
            {"query": request.query, "workspace_id": request.workspace_id, "modality": request.modality.value},
            user_id=request.user_id,
        )
        tracer = ExecutionTracer()
        layer_results: list[LayerResult] = []

        def record(layer: LayerResult) -> None:
            layer_results.append(layer)
            tracer.add(layer.layer, layer.summary, **layer.data)

        record(
            LayerResult(
                layer="input",
                activated=True,
                deterministic=True,
                summary="Accepted request into the JIMS-AI strict prototype pipeline.",
                data={"user_id": request.user_id, "modality": request.modality.value, "return_trace": request.return_trace},
            )
        )

        session = self._load_session(request.user_id)
        ir, intent_layer_result = await self.intent_layer.infer(request, session)
        record(intent_layer_result)
        session["ACTIVE_INTENT"] = ir.target_ir
        if ir.scope_constraints.get("entities"):
            session["ACTIVE_OBJECT"] = str(ir.scope_constraints["entities"][0])
        self._save_session(request.user_id, session)

        input_signature, encoder_layer_result = self.encoder_layer.encode(request, ir)
        record(encoder_layer_result)
        record(self.learning_layer.learn(input_signature))
        hydrated_now = self._hydrate_persistent_retrieval(request, input_signature.id, input_signature.latent_embedding)
        record(
            LayerResult(
                layer="V9_persistent_retrieval_hydration",
                activated=hydrated_now > 0,
                deterministic=True,
                summary="Hydrated local runtime memory with Vectorize/Supabase matches before retrieval.",
                data={
                    "hydrated": hydrated_now,
                    "vectorize_available": self.production.statuses.get("vectorize").available if "vectorize" in self.production.statuses else False,
                    "supabase_available": self.production.statuses.get("supabase_postgres").available if "supabase_postgres" in self.production.statuses else False,
                },
            )
        )

        canvas_result, canvas_layer_result = await self.canvas_layer.run(request, ir)
        record(canvas_layer_result)
        if canvas_result.activated and canvas_result.session_id and canvas_result.session_id not in self.canvas_sessions:
            self.canvas_sessions[canvas_result.session_id] = CanvasRunResponse(
                canvas_session_id=canvas_result.session_id,
                status="completed",
                estimated_duration="completed inline for prototype request",
                signatures_created=len(canvas_result.signatures_created),
                dataset_ref=request.workspace_id or "prompt_context",
                scope="query_canvas",
            )

        activation, activation_layer_result = self.activation_layer.decide(request, ir, canvas_result)
        record(activation_layer_result)

        capability_plan, capability_layer_result = self.capability_router.route(request, ir, activation)
        record(capability_layer_result)
        capability_results = self.capability_adapters.prepare(capability_plan)
        record(
            LayerResult(
                layer="V9_capability_adapters",
                activated=bool(capability_results),
                deterministic=True,
                summary="Prepared structured capability adapters without executing unverified tools.",
                data={"results": [result.model_dump(mode="json") for result in capability_results]},
            )
        )

        invention_result, invention_layer_result = await self.invention_layer.run(request, ir, activation)
        record(invention_layer_result)
        if invention_result.activated:
            invention_session_id = f"invention_{ir.trace_id[:12]}"
            self.invention_sessions.setdefault(
                invention_session_id,
                InventionRunResponse(
                    invention_session_id=invention_session_id,
                    status="completed",
                    estimated_duration="completed inline for prototype request",
                    modules_activated=["recursive_planner", "bounded_simulation"],
                    goal=request.query,
                    domain=ir.domain_namespace.lower(),
                ),
            )

        retrieved, retrieval_layer_result = self.retrieval_layer.retrieve(request, ir, activation, exclude_ids={input_signature.id})
        record(retrieval_layer_result)
        if not retrieved:
            self.retrieval_misses += 1

        abstraction_result, abstraction_layer_result = self.abstraction_layer.run(retrieved, activation)
        record(abstraction_layer_result)

        world_model_activations, graph_view, world_model_layer_result = self.world_model_layer.activate(ir, retrieved, activation)
        record(world_model_layer_result)

        obj, simulations, reasoning_layer_result = self.reasoning_bridge_layer.build(
            ir=ir,
            retrieved=retrieved,
            graph_view=graph_view,
            canvas=canvas_result,
            activation=activation,
            invention=invention_result,
            abstraction=abstraction_result,
            world_model=world_model_activations,
            prior_layers=layer_results,
        )
        record(reasoning_layer_result)
        obj.capability_plan = capability_plan
        obj.capability_results = capability_results
        self._apply_capability_gates(obj)

        response, used_groq_render, render_layer_result = await self.render_layer.render(obj)
        record(render_layer_result)
        record(
            LayerResult(
                layer="output",
                activated=True,
                deterministic=not used_groq_render,
                summary="Returned bounded response and persisted trace for feedback.",
                data={"trace_id": ir.trace_id, "sources": obj.sources, "confidence": obj.confidence},
            )
        )
        record(
            LayerResult(
                layer="feedback",
                activated=False,
                deterministic=True,
                summary="Feedback endpoint is ready for user correction, acceptance, or rejection.",
                data={"trace_id": ir.trace_id, "endpoint": "/v1/feedback"},
            )
        )
        obj.layer_results = layer_results
        used_groq = ir.transformer_interface_used or canvas_result.used_groq or invention_result.used_groq or used_groq_render
        pipeline_response = PipelineResponse(
            response=response,
            ir=ir,
            reasoning_chain=obj.reasoning_chain,
            confidence=obj.confidence,
            gaps=obj.knowledge_gaps,
            sources=obj.sources,
            simulation_results=simulations,
            trace=tracer.events if request.return_trace else [],
            layer_results=layer_results,
            activation=activation,
            canvas_result=canvas_result,
            invention_result=invention_result,
            abstraction_result=abstraction_result,
            world_model_activations=world_model_activations,
            capability_plan=capability_plan,
            capability_results=capability_results,
            used_groq=used_groq,
        )
        self.result_cache.set(cache_key, pipeline_response.model_dump(mode="json"))
        self.event_store.append(
            "query_completed",
            ir.trace_id,
            {
                "cache_key": cache_key,
                "confidence": obj.confidence,
                "sources": obj.sources,
                "gaps": obj.knowledge_gaps,
                "used_groq": used_groq,
            },
            user_id=request.user_id,
        )
        return pipeline_response

    def _apply_capability_gates(self, obj) -> None:
        if not obj.capability_plan:
            return
        blocking = [result for result in obj.capability_results if result.status in {"unavailable", "blocked"}]
        for result in blocking:
            obj.knowledge_gaps.append(
                f"Capability {obj.capability_plan.kind.value} needs adapter(s) {result.adapter}; status={result.status}."
            )
        if blocking and not obj.reasoning_chain:
            obj.reasoning_chain.append(
                ReasoningStep(
                    claim=f"Routed request to {obj.capability_plan.kind.value}, but required provider execution is not available yet.",
                    confidence=0.0,
                    sources=[],
                    relation="CAPABILITY_GATE",
                )
            )

    async def record_feedback(self, request: FeedbackRequest) -> FeedbackResponse:
        self.feedback_events.append(request)
        created_at = utc_now()
        record = {
            "request": request.model_dump(mode="json"),
            "created_at": created_at.isoformat(),
        }
        self.feedback_history.append(record)
        self.production.save_panel_items([self._feedback_item(record, len(self.feedback_history))])
        self.event_store.append(
            "feedback_recorded",
            request.trace_id,
            {"rating": request.rating, "notes": request.notes},
            user_id=request.user_id,
        )
        return FeedbackResponse(accepted=True, trace_id=request.trace_id, stored_events=len(self.feedback_events))

    def _write_result_signature(
        self,
        kind: str,
        status: str,
        summary: str,
        user_id: str,
        cache_key: str | None = None,
        confidence: float = 0.0,
        provenance: list[str] | None = None,
        data: dict[str, object] | None = None,
        workspace_id: str | None = None,
    ) -> VerifiedResultSignature:
        payload = data or {}
        signature = VerifiedResultSignature(
            id=stable_id("result", f"{kind}:{status}:{summary}:{cache_key}:{payload}"),
            kind=kind,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            cache_key=cache_key,
            confidence=round(confidence, 4),
            summary=summary,
            provenance=provenance or [],
            data=payload,
        )
        memory_signature = self.encoder.encode(
            f"{kind} result {status}: {summary}",
            modality=Modality.CODE if kind == "sandbox" else Modality.TEXT,
            intent_type=f"{kind}_result_signature",
            provenance=signature.id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        memory_signature.confidence.score = signature.confidence
        memory_signature.confidence.source = "verified_result_signature"
        memory_signature.metadata.update({"verified_result": signature.model_dump(mode="json")})
        self.memory.insert(memory_signature)
        self.graph.add_signature(memory_signature)
        self.event_store.append(
            "result_signature_written",
            signature.id,
            signature.model_dump(mode="json"),
            user_id=user_id,
        )
        return signature

    async def review_action(self, request: ReviewActionRequest) -> ReviewActionResponse:
        target_index = next(
            (
                index
                for index, candidate in enumerate(self.world_model_candidates)
                if candidate.provenance == request.provenance and candidate.rule == request.rule
            ),
            -1,
        )
        if target_index < 0:
            result = self._write_result_signature(
                "review",
                "failed",
                f"Review target not found: {request.rule}",
                user_id=request.user_id,
                confidence=0.0,
                provenance=[request.provenance],
                data=request.model_dump(mode="json"),
            )
            return ReviewActionResponse(accepted=False, action=request.action, rule=request.rule, result_signature=result)

        candidate = self.world_model_candidates[target_index]
        final_rule = request.corrected_rule.strip() if request.action == "correct" and request.corrected_rule else candidate.rule
        if request.action in {"accept", "promote"}:
            candidate.review_required = False
            self.world_model_candidates[target_index] = candidate
        elif request.action == "correct":
            self.world_model_candidates[target_index] = WorldModelCandidate(
                rule=final_rule,
                confidence=max(candidate.confidence, 0.9),
                provenance=candidate.provenance,
                review_required=False,
            )
        elif request.action == "reject":
            self.world_model_candidates.pop(target_index)
        elif request.action == "rollback":
            candidate.review_required = True
            self.world_model_candidates[target_index] = candidate

        event_payload = {
            "action": request.action,
            "rule": request.rule,
            "final_rule": final_rule,
            "provenance": request.provenance,
            "notes": request.notes,
        }
        self.event_store.append("review_action_recorded", stable_id("review", str(event_payload)), event_payload, user_id=request.user_id)
        result = self._write_result_signature(
            "review",
            "verified",
            f"Review {request.action} applied to {final_rule}",
            user_id=request.user_id,
            confidence=0.95,
            provenance=[request.provenance],
            data=event_payload,
        )
        self.production.save_panel_items([self._pipeline_item(self._pipeline_monitor())])
        return ReviewActionResponse(accepted=True, action=request.action, rule=final_rule, result_signature=result)

    async def run_sandbox(self, request: SandboxRunRequest) -> SandboxRunResponse:
        cache_key = self.result_cache.key(
            "sandbox",
            {
                "workspace_id": request.workspace_id,
                "language": request.language,
                "code": request.code,
                "tests": request.tests,
                "timeout_ms": request.timeout_ms,
            },
        )
        cached = self.result_cache.get(cache_key)
        if cached:
            data = dict(cached["value"])
            result_signature = VerifiedResultSignature.model_validate(data.pop("result_signature"))
            self.event_store.append("sandbox_cache_hit", cache_key, {"cache_key": cache_key}, user_id=request.user_id)
            data["status"] = "cached"
            return SandboxRunResponse(**data, result_signature=result_signature)

        saga_id = stable_id("saga", f"sandbox:{cache_key}")
        self.event_store.append("saga_started", saga_id, {"kind": "sandbox", "cache_key": cache_key}, user_id=request.user_id)
        execution = self.sandbox.run_python(request.code, request.tests, request.timeout_ms)
        status = str(execution["status"])
        result_signature = self._write_result_signature(
            "sandbox",
            "verified" if status == "passed" else "failed",
            f"Sandbox execution {status}",
            user_id=request.user_id,
            cache_key=cache_key,
            confidence=0.98 if status == "passed" else 0.5,
            data={"execution": execution, "language": request.language},
            workspace_id=request.workspace_id,
        )
        response = SandboxRunResponse(
            status=status,  # type: ignore[arg-type]
            stdout=str(execution.get("stdout", "")),
            stderr=str(execution.get("stderr", "")),
            exit_code=execution.get("exit_code") if isinstance(execution.get("exit_code"), int) else None,
            cache_key=cache_key,
            result_signature=result_signature,
        )
        self.result_cache.set(cache_key, response.model_dump(mode="json"))
        self.event_store.append("sandbox_execution_completed", cache_key, response.model_dump(mode="json"), user_id=request.user_id)
        self.event_store.append("saga_completed", saga_id, {"kind": "sandbox", "status": status}, user_id=request.user_id)
        return response

    async def solve_math(self, request: MathSolveRequest) -> MathSolveResponse:
        cache_key = self.result_cache.key(
            "math",
            {
                "workspace_id": request.workspace_id,
                "expression": request.expression,
                "solve_for": request.solve_for,
                "timeout_ms": request.timeout_ms,
            },
        )
        cached = self.result_cache.get(cache_key)
        if cached:
            data = dict(cached["value"])
            result_signature = VerifiedResultSignature.model_validate(data.pop("result_signature"))
            self.event_store.append("math_cache_hit", cache_key, {"cache_key": cache_key}, user_id=request.user_id)
            data["status"] = "cached"
            return MathSolveResponse(**data, result_signature=result_signature)

        saga_id = stable_id("saga", f"math:{cache_key}")
        self.event_store.append("saga_started", saga_id, {"kind": "math", "cache_key": cache_key}, user_id=request.user_id)
        try:
            solved = self.math_solver.solve(request.expression, request.solve_for)
        except Exception as error:
            solved = {"status": "failed", "result": str(error), "method": "sympy"}
        status = "solved" if solved["status"] == "solved" else "failed"
        result_signature = self._write_result_signature(
            "math",
            "verified" if status == "solved" else "failed",
            f"Math solve {status}: {solved['result']}",
            user_id=request.user_id,
            cache_key=cache_key,
            confidence=0.99 if status == "solved" else 0.2,
            data={"expression": request.expression, "solve_for": request.solve_for, **solved},
            workspace_id=request.workspace_id,
        )
        response = MathSolveResponse(
            status=status,  # type: ignore[arg-type]
            result=solved["result"],
            method=solved["method"],
            cache_key=cache_key,
            result_signature=result_signature,
        )
        self.result_cache.set(cache_key, response.model_dump(mode="json"))
        self.event_store.append("math_solve_completed", cache_key, response.model_dump(mode="json"), user_id=request.user_id)
        self.event_store.append("saga_completed", saga_id, {"kind": "math", "status": status}, user_id=request.user_id)
        return response

    async def schedule_canvas(self, request: CanvasRunRequest) -> CanvasRunResponse:
        session_id = f"canvas_{len(self.canvas_sessions) + 1:06d}"
        saga_id = stable_id("saga", f"canvas:{session_id}:{request.dataset_ref}")
        self.event_store.append("saga_started", saga_id, {"kind": "canvas", "request": request.model_dump(mode="json")}, user_id=request.user_id)
        task_id = self.production.enqueue("jimsai.training.process_canvas", request.model_dump(mode="json"))
        response = CanvasRunResponse(
            canvas_session_id=session_id,
            status="queued",
            estimated_duration=f"celery task {task_id}" if task_id else "prototype queue: manual worker required for large corpus",
            dataset_ref=request.dataset_ref,
            scope=request.scope,
        )
        self.canvas_sessions[session_id] = response
        self._write_result_signature(
            "canvas",
            "queued",
            f"Canvas run queued for {request.dataset_ref}",
            user_id=request.user_id,
            confidence=0.8,
            provenance=[request.dataset_ref],
            data={"session": response.model_dump(mode="json"), "saga_id": saga_id},
        )
        self.event_store.append("saga_step_completed", saga_id, {"step": "canvas_queued", "session": response.model_dump(mode="json")}, user_id=request.user_id)
        self.production.save_panel_items([self._session_item(response)])
        return response

    async def canvas_status(self, session_id: str) -> CanvasRunResponse | None:
        return self.canvas_sessions.get(session_id)

    async def schedule_invention(self, request: InventionRunRequest) -> InventionRunResponse:
        session_id = f"invention_{len(self.invention_sessions) + 1:06d}"
        modules = request.modules or ["recursive_planner", "bounded_simulation"]
        saga_id = stable_id("saga", f"invention:{session_id}:{request.goal}")
        self.event_store.append("saga_started", saga_id, {"kind": "invention", "request": request.model_dump(mode="json")}, user_id=request.user_id)
        task_id = self.production.enqueue("jimsai.training.process_invention", request.model_dump(mode="json"))
        response = InventionRunResponse(
            invention_session_id=session_id,
            status="queued",
            estimated_duration=f"celery task {task_id}" if task_id else "prototype queue: manual worker required for long-running invention",
            modules_activated=modules,
            goal=request.goal,
            domain=request.domain,
        )
        self.invention_sessions[session_id] = response
        self._write_result_signature(
            "invention",
            "queued",
            f"Invention run queued for {request.goal}",
            user_id=request.user_id,
            confidence=0.8,
            provenance=[request.goal],
            data={"session": response.model_dump(mode="json"), "saga_id": saga_id},
        )
        self.event_store.append("saga_step_completed", saga_id, {"step": "invention_queued", "session": response.model_dump(mode="json")}, user_id=request.user_id)
        self.production.save_panel_items([self._session_item(response)])
        return response

    async def invention_status(self, session_id: str) -> InventionRunResponse | None:
        return self.invention_sessions.get(session_id)

    async def training_dashboard(self) -> TrainingDashboardResponse:
        signatures = sorted(self.memory.all_signatures(), key=lambda sig: sig.created_at, reverse=True)
        reviewed = [candidate for candidate in self.world_model_candidates if not candidate.review_required]
        pending = [candidate for candidate in self.world_model_candidates if candidate.review_required]
        pipeline_monitor = {
            "signatures_total": len(signatures),
            "world_model_candidates_total": len(self.world_model_candidates),
            "sppe_pairs_total": len(self.training_history),
            "human_review_pending": len(pending),
            "ambiguity_pending": len(self.ambiguity_queue),
            "feedback_events": len(self.feedback_events),
            "canvas_sessions": len(self.canvas_sessions),
            "invention_sessions": len(self.invention_sessions),
            "kaggle_runs": len(self.kaggle_runs),
            "active_training_artifacts": len(self.active_training_artifacts),
            "hydrated_signatures": self.hydrated_signatures,
            "retrieval_misses": self.retrieval_misses,
        }
        health = self._system_health_score(pending_count=len(pending))
        pipeline_monitor.update(
            {
                "system_health_score": health["score"],
                "system_health_limiting_factor": health["limiting_factor"],
                "system_health_next_step": health["next_step"],
            }
        )
        production_readiness = {
            "strict_layer_chain": True,
            "bounded_transformer_interfaces": True,
            "local_phase1_runtime": True,
            "external_provider_adapters": self.production.enabled,
            "v9_capability_router": True,
            "human_review_ui": True,
            "edge_case_tests": True,
            "kaggle_gpu_orchestrator": self.kaggle.configured,
            "auto_training_detection": True,
            "adaptive_transformer_thinning": self.bridge.adaptive_thinning,
        }
        production_readiness.update(self.production.readiness())
        production_readiness.update(self.capability_adapters.readiness())
        auto_training_decision = self._current_auto_training_decision()
        return TrainingDashboardResponse(
            memory_stats=self.memory.stats(),
            human_review_queue=pending[:25],
            ambiguity_queue=self.ambiguity_queue[:25],
            recent_signatures=signatures[:12],
            world_models=(reviewed + pending)[:25],
            pipeline_monitor=pipeline_monitor,
            canvas_sessions=list(self.canvas_sessions.values())[-20:],
            invention_sessions=list(self.invention_sessions.values())[-20:],
            feedback_events=len(self.feedback_events),
            production_readiness=production_readiness,
            auto_training_decision=auto_training_decision,
        )

    async def ingest_training(self, request: TrainingIngestRequest) -> TrainingIngestResponse:
        tracer = ExecutionTracer()
        intent_type = request.domain_hint or "training_ingestion"
        signature = self.encoder.encode(
            request.content,
            modality=request.modality,
            intent_type=intent_type,
            provenance="training_pipeline",
            workspace_id=request.workspace_id,
            user_id=request.user_id,
        )
        signature.confidence.score = round(min(signature.confidence.score, request.source_trust), 4)
        signature.confidence.source = "training_ingestion_source_trust"
        groq_overlay = await self.bridge.extract_ingestion_memory(
            request.content,
            {
                "modality": request.modality.value,
                "domain_hint": request.domain_hint,
                "source_trust": request.source_trust,
                "workspace_id": request.workspace_id,
            },
        )
        groq_used = self._apply_ingestion_overlay(signature, groq_overlay, request.source_trust)
        self.memory.insert(signature)
        self.graph.add_signature(signature)
        self.event_store.append(
            "memory_signature_inserted",
            signature.id,
            {
                "provenance": signature.provenance,
                "confidence": signature.confidence.score,
                "modality": signature.modality.value,
                "workspace_id": request.workspace_id,
                "used_groq_ingest": groq_used,
            },
            user_id=request.user_id,
        )
        tracer.add(
            "training_ingest",
            "Encoded training input and inserted memory signature",
            signature_id=signature.id,
            modality=request.modality,
            source_trust=request.source_trust,
            used_groq=groq_used,
        )
        if groq_overlay:
            tracer.add(
                "groq_structured_ingestion",
                "Merged bounded Groq extraction into memory signature before indexing",
                used=groq_used,
                document_type=signature.metadata.get("document_type"),
                title=signature.metadata.get("title"),
                relation_count=len(signature.structured.relations),
                causal_count=len(signature.structured.causal_chain),
            )

        document_signatures = []
        if is_document_like(request.content):
            for fact in extract_document_facts(request.content):
                fact_signature = fact_to_signature(fact, signature.id)
                fact_signature.confidence.score = round(min(fact_signature.confidence.score, request.source_trust), 4)
                fact_signature.confidence.source = "document_structured_extractor_source_trust"
                self.memory.insert(fact_signature)
                self.graph.add_signature(fact_signature)
                self.event_store.append(
                    "memory_signature_inserted",
                    fact_signature.id,
                    {
                        "provenance": fact_signature.provenance,
                        "confidence": fact_signature.confidence.score,
                        "modality": fact_signature.modality.value,
                        "workspace_id": request.workspace_id,
                        "parent_signature": signature.id,
                    },
                    user_id=request.user_id,
                )
                document_signatures.append(fact_signature)
            tracer.add(
                "document_structured_extraction",
                "Extracted document facts into typed memory signatures",
                count=len(document_signatures),
                signature_ids=[item.id for item in document_signatures],
            )

        world_model_candidates = [
            WorldModelCandidate(
                rule=f"{link.cause} causes {link.effect}",
                confidence=round(min(link.confidence, request.source_trust), 4),
                provenance=signature.id,
                review_required=min(link.confidence, request.source_trust) < 0.9,
            )
            for link in signature.structured.causal_chain
        ]
        self.world_model_candidates.extend(world_model_candidates)
        if not signature.structured.entities and request.content.strip():
            self.ambiguity_queue.append(
                {
                    "case_id": f"amb_{signature.id}",
                    "signature_id": signature.id,
                    "reason": "No explicit entity extracted from non-empty training content.",
                    "impact_score": round(1.0 - signature.confidence.score, 4),
                    "created_at": utc_now().isoformat(),
                }
            )
        tracer.add(
            "world_model_candidates",
            "Extracted causal world model candidates from signature",
            count=len(world_model_candidates),
        )

        semantic_intention_graph = {
            "entities": [entity.model_dump() for entity in signature.structured.entities],
            "relations": [relation.model_dump() for relation in signature.structured.relations],
            "causal_chain": [link.model_dump() for link in signature.structured.causal_chain],
            "intent": signature.structured.intent.model_dump(),
        }
        sppe_pair = SPPETrainingPair(
            signature_id=signature.id,
            semantic_intention_graph=semantic_intention_graph,
            original_text=request.content,
            confidence=signature.confidence.score,
            accepted=signature.confidence.score >= 0.75,
        )
        tracer.add(
            "sppe_pair",
            "Generated confidence-scored SPPE training pair",
            accepted=sppe_pair.accepted,
            confidence=sppe_pair.confidence,
        )
        response = TrainingIngestResponse(
            signature=signature,
            world_model_candidates=world_model_candidates,
            sppe_training_pair=sppe_pair,
            memory_stats=self.memory.stats(),
            trace=tracer.events,
        )
        self.training_history.append(response)
        response.auto_training_decision = self._current_auto_training_decision()
        panel_items = self._items_for_ingest_response(response)
        panel_items.extend(self._signature_item(fact_signature, panel="memory") for fact_signature in document_signatures)
        panel_items.append(self._pipeline_item(self._pipeline_monitor()))
        self.production.save_training_ingest(signature, request.content, panel_items)
        for fact_signature in document_signatures:
            self.production.save_training_ingest(
                fact_signature,
                fact_signature.raw_excerpt,
                [self._signature_item(fact_signature, panel="memory")],
            )
        invalidated = self.result_cache.clear()
        self.event_store.append(
            "result_cache_invalidated",
            signature.id,
            {"entries": invalidated, "reason": "training_ingest_memory_write"},
            user_id=request.user_id,
        )
        if self.cloud_authoritative:
            for item in [signature, *document_signatures]:
                self.memory.delete(item.id)
                self.graph.remove_signature(item.id)
        return response

    def _apply_ingestion_overlay(self, signature, overlay: dict[str, Any] | None, source_trust: float) -> bool:
        if not overlay:
            return False

        changed = False
        existing_entities = {entity.name.lower(): entity for entity in signature.structured.entities}
        for item in self._list_of_dicts(overlay.get("entities")):
            name = str(item.get("name") or "").strip()
            if not name or name.lower() in existing_entities:
                continue
            entity_type = str(item.get("type") or "concept").strip() or "concept"
            entity = Entity(id=stable_id("ent", name), name=name[:160], type=entity_type[:64])
            signature.structured.entities.append(entity)
            existing_entities[name.lower()] = entity
            changed = True

        existing_relations = {
            (relation.subject.lower(), relation.predicate, relation.object.lower())
            for relation in signature.structured.relations
        }
        relation_items = [*self._list_of_dicts(overlay.get("relations")), *self._list_of_dicts(overlay.get("facts"))]
        for item in relation_items:
            subject = str(item.get("subject") or "").strip()
            predicate = str(item.get("predicate") or "").strip()
            obj = str(item.get("object") or "").strip()
            if not subject or not predicate or not obj:
                continue
            key = (subject.lower(), predicate, obj.lower())
            if key in existing_relations:
                continue
            confidence = self._bounded_confidence(item.get("confidence"), source_trust)
            signature.structured.relations.append(Relation(subject=subject[:160], predicate=predicate[:80], object=obj[:240], confidence=confidence))
            for name in (subject, obj):
                if name.lower() not in existing_entities:
                    entity = Entity(id=stable_id("ent", name), name=name[:160], type="concept")
                    signature.structured.entities.append(entity)
                    existing_entities[name.lower()] = entity
            existing_relations.add(key)
            changed = True

        existing_causal = {(link.cause.lower(), link.effect.lower()) for link in signature.structured.causal_chain}
        for item in self._list_of_dicts(overlay.get("causal_links")):
            cause = str(item.get("cause") or "").strip()
            effect = str(item.get("effect") or "").strip()
            if not cause or not effect or (cause.lower(), effect.lower()) in existing_causal:
                continue
            confidence = self._bounded_confidence(item.get("confidence"), source_trust)
            signature.structured.causal_chain.append(CausalLink(cause=cause[:180], effect=effect[:180], confidence=confidence))
            existing_causal.add((cause.lower(), effect.lower()))
            changed = True

        metadata_keys = ("document_type", "title", "summary")
        for key in metadata_keys:
            value = overlay.get(key)
            if isinstance(value, str) and value.strip():
                signature.metadata[key] = value.strip()[:500]
                changed = True

        tags = [str(tag).strip().lower() for tag in overlay.get("tags", []) if str(tag).strip()] if isinstance(overlay.get("tags"), list) else []
        if tags:
            signature.abstraction_tags = sorted(set(signature.abstraction_tags) | set(tags))[:64]
            changed = True

        if changed:
            overlay_confidence = self._bounded_confidence(overlay.get("confidence"), source_trust)
            signature.confidence.score = round(max(signature.confidence.score, min(source_trust, overlay_confidence)), 4)
            signature.confidence.source = "groq_structured_ingestion_source_trust"
            signature.metadata["groq_ingestion"] = {
                "used": True,
                "model": self.bridge.ingest_model,
                "confidence": overlay_confidence,
                "vectors_are_truth": False,
                "truth_policy": "symbolic_memory_requires_provenance_and_review",
            }
        return changed

    def _list_of_dicts(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _bounded_confidence(self, value: Any, source_trust: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = 0.72
        return round(max(0.0, min(confidence, source_trust, 0.96)), 4)

    async def update_memory(self, request: MemoryUpdateRequest) -> MemoryMutationResponse:
        existing = self.memory.get(request.signature_id)
        if not existing or not self.memory._visible_to_scope(existing, workspace_id=request.workspace_id, user_id=request.user_id):
            return MemoryMutationResponse(
                accepted=False,
                action="update",
                signature_id=request.signature_id,
                memory_stats=self.memory.stats(),
                detail="signature not found or not visible in this scope",
            )
        content = request.corrected_content.strip() if request.corrected_content else existing.raw_excerpt
        ingest = await self.ingest_training(
            TrainingIngestRequest(
                user_id=request.user_id,
                workspace_id=request.workspace_id,
                content=content,
                modality=existing.modality,
                source_trust=request.source_trust,
                domain_hint=request.domain_hint or existing.structured.intent.type,
            )
        )
        existing.metadata["validity"] = "superseded"
        existing.metadata["superseded_by"] = ingest.signature.id
        self.memory.update(existing)
        self.graph.remove_signature(existing.id)
        removed_panel_items = self.production.delete_panel_items_for_signature(existing.id)
        self.production.delete_signature(existing.id)
        invalidated = self.result_cache.clear()
        self.event_store.append(
            "memory_signature_updated",
            request.signature_id,
            {
                "replacement_signature": ingest.signature.id,
                "notes": request.notes,
                "cache_invalidated": invalidated,
                "removed_panel_items": removed_panel_items,
            },
            user_id=request.user_id,
        )
        return MemoryMutationResponse(
            accepted=True,
            action="update",
            signature_id=request.signature_id,
            replacement_signature=ingest.signature,
            memory_stats=self.memory.stats(),
            detail="signature superseded by corrected memory",
        )

    async def delete_memory(self, request: MemoryDeleteRequest) -> MemoryMutationResponse:
        existing = self.memory.get(request.signature_id)
        if not existing or not self.memory._visible_to_scope(existing, workspace_id=request.workspace_id, user_id=request.user_id):
            return MemoryMutationResponse(
                accepted=False,
                action="delete",
                signature_id=request.signature_id,
                memory_stats=self.memory.stats(),
                detail="signature not found or not visible in this scope",
            )
        self.memory.delete(request.signature_id)
        removed_edges = self.graph.remove_signature(request.signature_id)
        removed_panel_items = self.production.delete_panel_items_for_signature(request.signature_id)
        self.production.delete_signature(request.signature_id)
        self.world_model_candidates = [candidate for candidate in self.world_model_candidates if candidate.provenance != request.signature_id]
        self.training_history = [item for item in self.training_history if item.signature.id != request.signature_id]
        invalidated = self.result_cache.clear()
        self.event_store.append(
            "memory_signature_deleted",
            request.signature_id,
            {
                "reason": request.reason,
                "removed_graph_edges": removed_edges,
                "removed_panel_items": removed_panel_items,
                "cache_invalidated": invalidated,
            },
            user_id=request.user_id,
        )
        return MemoryMutationResponse(
            accepted=True,
            action="delete",
            signature_id=request.signature_id,
            memory_stats=self.memory.stats(),
            detail="signature removed from local memory, graph, candidates, and caches",
        )

    async def training_panel_page(self, panel: str, cursor: str | None = None, limit: int = 25) -> TrainingPanelPage:
        if panel not in TRAINING_PANEL_IDS:
            return TrainingPanelPage(panel=panel, items=[], total=0)
        external_page = self.production.list_panel_items(panel, cursor, limit)
        if external_page is not None:
            return external_page
        items = self._panel_items(panel)
        offset = max(int(cursor or "0"), 0)
        page_size = min(max(limit, 1), 100)
        visible = items[offset : offset + page_size]
        next_offset = offset + page_size
        has_more = next_offset < len(items)
        return TrainingPanelPage(
            panel=panel,
            items=visible,
            next_cursor=str(next_offset) if has_more else None,
            has_more=has_more,
            total=len(items),
        )

    def _filter_external_panel_page(self, page: TrainingPanelPage) -> TrainingPanelPage:
        items = [item for item in page.items if self._panel_item_is_live(item)]
        removed = len(page.items) - len(items)
        return page.model_copy(
            update={
                "items": items,
                "total": max(0, page.total - removed),
                "has_more": page.has_more,
            }
        )

    def _panel_item_is_live(self, item: TrainingPanelItem) -> bool:
        signature_id = self._signature_id_from_panel_item(item)
        if not signature_id:
            return True
        if self.memory.get(signature_id):
            return True
        if item.kind in {"training_ingest", "signature", "world_model_candidate", "ambiguity_case"}:
            return False
        return True

    def _signature_id_from_panel_item(self, item: TrainingPanelItem) -> str:
        data = item.data or {}
        signature = data.get("signature")
        if isinstance(signature, dict) and isinstance(signature.get("id"), str):
            return signature["id"]
        for key in ("id", "provenance", "signature_id"):
            value = data.get(key)
            if isinstance(value, str) and value.startswith("sig_"):
                return value
        if ":" in item.id:
            candidate = item.id.rsplit(":", 1)[-1]
            if candidate.startswith("sig_"):
                return candidate
        return ""

    def _pipeline_monitor(self) -> dict[str, object]:
        pending = [candidate for candidate in self.world_model_candidates if candidate.review_required]
        health = self._system_health_score(pending_count=len(pending))
        return {
            "system_health_score": health["score"],
            "system_health_limiting_factor": health["limiting_factor"],
            "system_health_next_step": health["next_step"],
            "signatures_total": len(self.memory.all_signatures()),
            "world_model_candidates_total": len(self.world_model_candidates),
            "sppe_pairs_total": len(self.training_history),
            "human_review_pending": len(pending),
            "ambiguity_pending": len(self.ambiguity_queue),
            "feedback_events": len(self.feedback_events),
            "canvas_sessions": len(self.canvas_sessions),
            "invention_sessions": len(self.invention_sessions),
            "kaggle_runs": len(self.kaggle_runs),
            "active_training_artifacts": len(self.active_training_artifacts),
            "hydrated_signatures": self.hydrated_signatures,
            "retrieval_misses": self.retrieval_misses,
            **self.result_cache.stats(),
            **self.event_store.stats(),
            "auto_training": self._current_auto_training_decision().model_dump(mode="json"),
        }

    async def audit_events(self, limit: int = 100) -> list[dict[str, object]]:
        return self.event_store.tail(limit=limit)

    def _system_health_score(self, pending_count: int | None = None) -> dict[str, object]:
        signatures = self.memory.all_signatures()
        total = len(signatures)
        if pending_count is None:
            pending_count = len([candidate for candidate in self.world_model_candidates if candidate.review_required])
        average_confidence = sum(signature.confidence.score for signature in signatures) / total if total else 0.0
        retrieval_precision_proxy = 1.0 - min(1.0, self.retrieval_misses / max(total + self.retrieval_misses, 1))
        review_health = 1.0 - min(1.0, pending_count / max(len(self.world_model_candidates), 1))
        t1_bypass_proxy = 1.0 if self.bridge.adaptive_thinning else 0.5
        sppe_quality = len([item for item in self.training_history if item.sppe_training_pair.accepted]) / max(len(self.training_history), 1)
        score = round(
            100
            * (
                0.28 * average_confidence
                + 0.24 * retrieval_precision_proxy
                + 0.18 * review_health
                + 0.16 * t1_bypass_proxy
                + 0.14 * sppe_quality
            )
        )
        factors = {
            "encoder confidence": average_confidence,
            "retrieval precision": retrieval_precision_proxy,
            "review backlog": review_health,
            "T1 bypass readiness": t1_bypass_proxy,
            "SPPE quality": sppe_quality,
        }
        limiting_factor = min(factors, key=factors.get)
        next_steps = {
            "encoder confidence": "Ingest higher-trust reviewed documents and tune the encoder on accepted signatures.",
            "retrieval precision": "Add source signatures for missed queries and materialize the hot-path importance index.",
            "review backlog": "Clear human-review candidates before promoting more world-model rules.",
            "T1 bypass readiness": "Raise deterministic compiler coverage before increasing transformer thinning.",
            "SPPE quality": "Review rejected SPPE pairs and bootstrap with synthetic query/signature/output triples.",
        }
        return {
            "score": max(0, min(100, score)),
            "limiting_factor": limiting_factor,
            "next_step": next_steps[limiting_factor],
            "components": {key: round(value, 4) for key, value in factors.items()},
        }

    def _current_auto_training_decision(self):
        return self.training_policy.evaluate(
            self.training_history,
            self.world_model_candidates,
            self.ambiguity_queue,
            retrieval_misses=self.retrieval_misses,
        )

    async def schedule_kaggle_training(self, request: KaggleTrainingRequest) -> KaggleTrainingResponse:
        saga_id = stable_id("saga", f"training:{request.user_id}:{request.task_type}:{len(self.kaggle_runs)}")
        self.event_store.append("saga_started", saga_id, {"kind": "training", "request": request.model_dump(mode="json")}, user_id=request.user_id)
        training_history = self._training_history_for_kaggle(request.workspace_id)
        world_model_candidates = self._world_model_candidates_for_kaggle(request.workspace_id)
        response = self.kaggle.submit_training_run(
            request,
            training_history=training_history,
            world_model_candidates=world_model_candidates,
        )
        self.kaggle_runs.append(response)
        self._write_result_signature(
            "training",
            "queued" if response.status in {"prepared", "submitted", "running"} else "failed",
            f"Training run {response.status}: {response.task_type}",
            user_id=request.user_id,
            confidence=0.8 if response.status != "failed" else 0.2,
            provenance=[response.run_id],
            data={"run": response.model_dump(mode="json"), "saga_id": saga_id},
            workspace_id=request.workspace_id,
        )
        self.event_store.append("saga_step_completed", saga_id, {"step": "training_submitted", "run": response.model_dump(mode="json")}, user_id=request.user_id)
        self.production.save_panel_items([self._kaggle_run_item(response)])
        return response

    def _training_history_for_kaggle(self, workspace_id: str | None) -> list[TrainingIngestResponse]:
        history = [
            item
            for item in self.training_history
            if workspace_id is None or item.signature.workspace_id in {None, workspace_id}
        ]
        by_signature_id = {item.signature.id: item for item in history}
        max_items = int(os.getenv("JIMS_KAGGLE_MAX_PANEL_ITEMS", "500") or "500")
        for panel_item in self._persistent_panel_items("ingestion", max_items):
            if panel_item.kind != "training_ingest":
                continue
            try:
                item = TrainingIngestResponse.model_validate(panel_item.data)
            except Exception:
                continue
            if workspace_id is not None and item.signature.workspace_id not in {None, workspace_id}:
                continue
            by_signature_id.setdefault(item.signature.id, item)
        return sorted(by_signature_id.values(), key=lambda item: item.signature.created_at, reverse=True)

    def _world_model_candidates_for_kaggle(self, workspace_id: str | None) -> list[WorldModelCandidate]:
        candidates = list(self.world_model_candidates)
        by_key = {(item.provenance, item.rule): item for item in candidates}
        max_items = int(os.getenv("JIMS_KAGGLE_MAX_PANEL_ITEMS", "500") or "500")
        for panel_name in ("world-model", "review"):
            for panel_item in self._persistent_panel_items(panel_name, max_items):
                if panel_item.kind != "world_model_candidate":
                    continue
                if workspace_id is not None:
                    signature_id = str(panel_item.data.get("provenance") or "")
                    signature = self.memory.get(signature_id)
                    if signature and signature.workspace_id not in {None, workspace_id}:
                        continue
                try:
                    item = WorldModelCandidate.model_validate(panel_item.data)
                except Exception:
                    continue
                by_key.setdefault((item.provenance, item.rule), item)
        return list(by_key.values())

    def _persistent_panel_items(self, panel: str, max_items: int) -> list[TrainingPanelItem]:
        if max_items <= 0:
            return []
        items: list[TrainingPanelItem] = []
        cursor: str | None = None
        page_size = min(max_items, 100)
        while len(items) < max_items:
            page = self.production.list_panel_items(panel, cursor=cursor, limit=min(page_size, max_items - len(items)))
            if page is None:
                break
            items.extend(page.items)
            if not page.has_more or not page.next_cursor:
                break
            cursor = page.next_cursor
        return items[:max_items]

    async def sync_kaggle_training(self, run_id: str) -> KaggleTrainingResponse | None:
        for index, run in enumerate(self.kaggle_runs):
            if run.run_id != run_id:
                continue
            synced = self.kaggle.sync_outputs(run)
            self.kaggle_runs[index] = synced
            if synced.status == "completed" and synced.local_path:
                self.active_training_artifacts[synced.task_type] = synced.local_path
            event_type = "saga_completed" if synced.status == "completed" else "saga_step_completed"
            self.event_store.append(
                event_type,
                stable_id("saga", f"training:{run_id}"),
                {"step": "training_sync", "run": synced.model_dump(mode="json")},
                user_id="system",
            )
            self._write_result_signature(
                "training",
                "verified" if synced.status == "completed" else "queued",
                f"Training run synced: {synced.status}",
                user_id="system",
                confidence=0.95 if synced.status == "completed" else 0.75,
                provenance=[run_id],
                data={"run": synced.model_dump(mode="json")},
            )
            self.production.save_panel_items([self._kaggle_run_item(synced)])
            return synced
        return None

    def _items_for_ingest_response(self, response: TrainingIngestResponse) -> list[TrainingPanelItem]:
        items = [
            self._ingestion_item(response),
            self._signature_item(response.signature, panel="memory"),
        ]
        items.extend(self._candidate_item(candidate, "world-model") for candidate in response.world_model_candidates)
        items.extend(self._candidate_item(candidate, "review") for candidate in response.world_model_candidates if candidate.review_required)
        items.extend(self._ambiguity_item(item) for item in self.ambiguity_queue if item.get("signature_id") == response.signature.id)
        return items

    def _panel_items(self, panel: str) -> list[TrainingPanelItem]:
        if panel == "ingestion":
            items = [self._ingestion_item(response) for response in self.training_history]
        elif panel == "review":
            items = [
                self._candidate_item(candidate, panel)
                for candidate in self.world_model_candidates
                if candidate.review_required
            ]
        elif panel == "ambiguity":
            items = [self._ambiguity_item(item) for item in self.ambiguity_queue]
        elif panel == "memory":
            items = [self._signature_item(signature, panel) for signature in self.memory.all_signatures()]
        elif panel == "world-model":
            items = [self._candidate_item(candidate, panel) for candidate in self.world_model_candidates]
        elif panel == "pipeline":
            items = [self._pipeline_item(self._pipeline_monitor())]
        elif panel == "sessions":
            items = [self._session_item(session) for session in self.canvas_sessions.values()]
            items.extend(self._session_item(session) for session in self.invention_sessions.values())
            items.extend(self._kaggle_run_item(run) for run in self.kaggle_runs)
        elif panel == "feedback":
            provider_item = TrainingPanelItem(
                id="feedback:provider-readiness",
                panel="feedback",
                kind="provider_readiness",
                title="Production provider readiness",
                subtitle=self.production.settings.storage_backend,
                data=self.production.readiness(),
                created_at=utc_now(),
            )
            items = [provider_item]
            items.extend(self._feedback_item(record, index + 1) for index, record in enumerate(self.feedback_history))
        else:
            items = []
        return sorted(items, key=lambda item: (item.created_at, item.id), reverse=True)

    def _ingestion_item(self, response: TrainingIngestResponse) -> TrainingPanelItem:
        accepted = "accepted" if response.sppe_training_pair.accepted else "queued"
        return TrainingPanelItem(
            id=f"ingestion:{response.signature.id}",
            panel="ingestion",
            kind="training_ingest",
            title=response.signature.id,
            subtitle=f"{response.signature.modality.value} / SPPE {accepted} / confidence {response.signature.confidence.score:.2f}",
            data=response.model_dump(mode="json"),
            created_at=response.signature.created_at,
        )

    def _signature_item(self, signature, panel: str) -> TrainingPanelItem:
        return TrainingPanelItem(
            id=f"{panel}:{signature.id}",
            panel=panel,
            kind="signature",
            title=signature.id,
            subtitle=f"{signature.provenance} / {signature.modality.value} / confidence {signature.confidence.score:.2f}",
            data=signature.model_dump(mode="json"),
            created_at=signature.created_at,
        )

    def _candidate_item(self, candidate: WorldModelCandidate, panel: str) -> TrainingPanelItem:
        created_at = self._created_at_for_signature(candidate.provenance)
        state = "review required" if candidate.review_required else "accepted"
        return TrainingPanelItem(
            id=f"{panel}:{stable_id('wm', f'{candidate.provenance}:{candidate.rule}')}",
            panel=panel,
            kind="world_model_candidate",
            title=candidate.rule,
            subtitle=f"{state} / confidence {candidate.confidence:.2f} / {candidate.provenance}",
            data=candidate.model_dump(mode="json"),
            created_at=created_at,
        )

    def _ambiguity_item(self, item: dict[str, object]) -> TrainingPanelItem:
        created_at_value = item.get("created_at")
        created_at = utc_now()
        if isinstance(created_at_value, str):
            try:
                from datetime import datetime

                created_at = datetime.fromisoformat(created_at_value)
            except ValueError:
                created_at = utc_now()
        return TrainingPanelItem(
            id=f"ambiguity:{item.get('case_id', stable_id('amb', str(item)))}",
            panel="ambiguity",
            kind="ambiguity_case",
            title=str(item.get("case_id", "ambiguity")),
            subtitle=f"{item.get('reason', 'needs operator review')} / impact {float(item.get('impact_score', 0.0)):.2f}",
            data=dict(item),
            created_at=created_at,
        )

    def _pipeline_item(self, monitor: dict[str, object]) -> TrainingPanelItem:
        return TrainingPanelItem(
            id="pipeline:current",
            panel="pipeline",
            kind="pipeline_monitor",
            title="Training pipeline monitor",
            subtitle=f"{monitor['signatures_total']} signatures / {monitor['human_review_pending']} reviews pending",
            data=monitor,
            created_at=utc_now(),
        )

    def _session_item(self, session: CanvasRunResponse | InventionRunResponse) -> TrainingPanelItem:
        if isinstance(session, CanvasRunResponse):
            session_id = session.canvas_session_id
            title = session.dataset_ref
            subtitle = f"{session.status} / {session.scope}"
            data = session.model_dump(mode="json")
            kind = "canvas_session"
        else:
            session_id = session.invention_session_id
            title = session.goal
            subtitle = f"{session.status} / {session.domain}"
            data = session.model_dump(mode="json")
            kind = "invention_session"
        return TrainingPanelItem(
            id=f"sessions:{session_id}",
            panel="sessions",
            kind=kind,
            title=title,
            subtitle=subtitle,
            data=data,
            created_at=utc_now(),
        )

    def _kaggle_run_item(self, run: KaggleTrainingResponse) -> TrainingPanelItem:
        return TrainingPanelItem(
            id=f"sessions:{run.run_id}",
            panel="sessions",
            kind="kaggle_training_run",
            title=f"{run.task_type} / {run.status}",
            subtitle=run.kernel_ref or run.local_path or "kaggle package",
            data=run.model_dump(mode="json"),
            created_at=run.submitted_at,
        )

    def _feedback_item(self, record: dict[str, object], index: int) -> TrainingPanelItem:
        request = record.get("request", {})
        created_at = utc_now()
        created_at_value = record.get("created_at")
        if isinstance(created_at_value, str):
            try:
                from datetime import datetime

                created_at = datetime.fromisoformat(created_at_value)
            except ValueError:
                created_at = utc_now()
        trace_id = request.get("trace_id", "unknown") if isinstance(request, dict) else "unknown"
        rating = request.get("rating", "feedback") if isinstance(request, dict) else "feedback"
        return TrainingPanelItem(
            id=f"feedback:{index}:{trace_id}",
            panel="feedback",
            kind="feedback_event",
            title=str(rating),
            subtitle=str(trace_id),
            data=record,
            created_at=created_at,
        )

    def _created_at_for_signature(self, signature_id: str):
        signature = self.memory.get(signature_id)
        return signature.created_at if signature else utc_now()
