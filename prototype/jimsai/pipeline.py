from __future__ import annotations

import logging
import os
import re
import asyncio
from typing import Any

from .capability_router import CapabilityAdapterRegistry, CapabilityRouter
from .csse import ConstrainedSemanticSynthesisEngine
from .document_ingestion import extract_document_facts, fact_to_signature, is_document_like
from .errors import CriticalServiceUnavailable
from .encoder import DualRepresentationEncoder, stable_id
from .event_store import AuditEventStore, VerifiedResultCache
from .execution_runtime import DeterministicSandbox, SymbolicMathSolver
from .graph import CausalGraphEngine
from .modal_training_orchestrator import ModalTrainingOrchestrator
from .memory import FourLayerMemoryStore
from .model_bridge import QwenBridge
from .models import (
    CanvasRunRequest,
    CanvasRunResponse,
    CapabilityExecutionResult,
    CapabilityKind,
    Confidence,
    FeedbackRequest,
    FeedbackResponse,
    InventionRunRequest,
    InventionRunResponse,
    KaggleTrainingRequest,
    KaggleTrainingResponse,
    LayerResult,
    CausalLink,
    Entity,
    MemorySignature,
    MemoryDeleteRequest,
    MemoryMutationResponse,
    MemoryRollbackRequest,
    MemoryRollbackResponse,
    MemoryUpdateRequest,
    PipelineRequest,
    PipelineResponse,
    ProvenanceClass,
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
    SignatureIntent,
    StructuredSignature,
    TrainingDashboardResponse,
    TrainingIngestRequest,
    TrainingIngestResponse,
    TrainingPanelItem,
    TrainingPanelPage,
    VerifiedCognitiveObject,
    VerifiedResultSignature,
    WorldModelCandidate,
    utc_now,
)
from .observability import ExecutionTracer
from .planner import SymbolicPlanner
from .retrieval import MultiIndexRetrievalEngine
from .relation_schema import relation_cardinality_overlay
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
from .world_model_promotion import WorldModelPromotionEngine, WorldModelFastPath

logger = logging.getLogger(__name__)


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
        # Lazy fields â€” instantiated on first access via @property
        self._training: ModalTrainingOrchestrator | None = None
        self._compiler: SemanticCompilerRuntime | None = None
        self.bridge = QwenBridge()
        self.encoder = DualRepresentationEncoder(
            multimodal_adapter=self.production.multimodal,
            bridge=self.bridge,
        )
        self.memory = FourLayerMemoryStore()
        self.graph = CausalGraphEngine()
        self.retrieval = MultiIndexRetrievalEngine(self.memory)
        self.simulation = BoundedSimulationEngine(self.graph)
        self.validator = ConstraintValidator()
        self.planner = SymbolicPlanner()
        self.csse = ConstrainedSemanticSynthesisEngine()
        self.intent_layer = TransformerIntentInterface(self.compiler, self.bridge)
        self.encoder_layer = FullEncoderLayer(self.encoder)
        self.learning_layer = RealTimeLearningLayer(self.memory, self.graph)
        self.canvas_layer = ActiveCanvasLayer(self.memory, self.bridge)
        self.activation_layer = SparseActivationMetaController()
        self.capability_router = CapabilityRouter(self.bridge)
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
        self.world_model_promotion = WorldModelPromotionEngine()
        self.world_model_fast_path = WorldModelFastPath()
        self.reasoning_bridge_layer = ReasoningBridgeLayer(self.simulation, self.validator, self.planner, self.graph)
        self.reasoning_layer = self.reasoning_bridge_layer
        self.render_layer = TransformerRenderInterface(self.csse, self.bridge)
        self.sessions: dict[str, dict[str, str]] = {}
        # Streaming render hand-off: trace_id -> (VerifiedCognitiveObject, deterministic_render)
        self._stream_ctx: dict[str, tuple] = {}
        self.feedback_events: list[FeedbackRequest] = []
        self.feedback_history: list[dict[str, object]] = []
        self.training_history: list[TrainingIngestResponse] = []
        self.training_ingest_jobs: dict[str, dict[str, Any]] = {}
        self.world_model_candidates: list[WorldModelCandidate] = []
        self.ambiguity_queue: list[dict[str, object]] = []
        self.canvas_sessions: dict[str, CanvasRunResponse] = {}
        self.invention_sessions: dict[str, InventionRunResponse] = {}
        self.training_runs: list[KaggleTrainingResponse] = []
        self.active_training_artifacts: dict[str, str] = {}
        self.retrieval_misses = 0
        self.cloud_authoritative = self.production.settings.cloud_authoritative
        # Defer memory hydration when cloud_authoritative but providers not yet
        # initialized (common on Lambda cold start). Hydration will run on first query.
        if self.cloud_authoritative and not self.production._initialized:
            self._hydrate_pending = True
            self.hydrated_signatures = 0
        else:
            self._hydrate_pending = False
            self.hydrated_signatures = self._hydrate_memory()

    @property
    def compiler(self) -> SemanticCompilerRuntime:
        """Lazy: SemanticCompilerRuntime is created on first access to avoid startup cost."""
        if self._compiler is None:
            self._compiler = SemanticCompilerRuntime()
        return self._compiler

    @property
    def training_orchestrator(self) -> ModalTrainingOrchestrator:
        """Lazy: ModalTrainingOrchestrator is only needed for training runs."""
        if self._training is None:
            self._training = ModalTrainingOrchestrator()
        return self._training

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
        if os.getenv("JIMS_ENABLE_QUERY_CLOUD_HYDRATION", "true").lower() not in {"1", "true", "yes", "on"}:
            return 0
        signatures = self.production.retrieve_similar(
            latent_embedding,
            limit=12,
            workspace_id=request.workspace_id,
            user_id=request.user_id,
            exclude_ids={input_signature_id},
            vector_context_id=input_signature_id,
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
            try:
                score = self._lexical_signature_score(signature, query_terms)
            except Exception:
                continue
            if score >= 1:
                scored.append((score, signature.confidence.score, signature.created_at, signature))
        scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return [item[3] for item in scored[:8]]

    def _lexical_query_terms(self, query: str) -> set[str]:
        # Unicode-aware tokenization, no hardcoded stop words
        terms = {
            term for term in re.findall(r"[\w\-.]+", query.lower(), flags=re.UNICODE)
            if len(term) >= 3
        }
        return terms

    def _lexical_signature_score(self, signature, query_terms: set[str]) -> int:
        haystack_parts = [
            (signature.raw_excerpt or "").lower(),
            " ".join(signature.abstraction_tags or []).lower(),
            " ".join(entity.name for entity in (signature.structured.entities or []) if hasattr(entity, "name")).lower(),
            " ".join(f"{relation.subject} {relation.predicate} {relation.object}" for relation in (signature.structured.relations or []) if hasattr(relation, "subject")).lower(),
            " ".join(f"{link.cause} {link.effect}" for link in (signature.structured.causal_chain or []) if hasattr(link, "cause")).lower(),
        ]
        haystack = " ".join(haystack_parts)
        return sum(1 for term in query_terms if term in haystack)

    def _flush_pending_hydration(self) -> None:
        """Run deferred memory hydration if it was skipped at init time."""
        if getattr(self, "_hydrate_pending", False):
            self._hydrate_pending = False
            self.hydrated_signatures = self._hydrate_memory()

    def _reset_request_cache(self) -> None:
        self._flush_pending_hydration()
        if self.cloud_authoritative:
            return

    def _thread_session_key(self, user_id: str, thread_id: str | None) -> str:
        safe_thread_id = (thread_id or "default").strip() or "default"
        return f"{user_id}:thread:{safe_thread_id}"

    def _query_cache_key(self, request: PipelineRequest) -> str:
        return self.result_cache.key(
            "query",
            {
                "runtime_cache_version": os.getenv("JIMS_RUNTIME_CACHE_VERSION", "2026-06-06-latency-math-v3"),
                "user_id": request.user_id,
                "workspace_id": request.workspace_id,
                "thread_id": request.thread_id or "default",
                "query": request.query.strip(),
                "modality": request.modality.value,
                "canvas_hint": request.canvas_hint,
                "invention_hint": request.invention_hint,
            },
        )

    def _load_session(self, user_id: str, thread_id: str | None = None) -> dict[str, str]:
        session_key = self._thread_session_key(user_id, thread_id)
        # Dialogue state (discourse focus) is core conversational memory, not
        # optional cache: it must survive even when the external session cache
        # (Redis) is unavailable. The in-process store is always-available;
        # the cloud store adds cross-process durability when reachable. Read
        # cloud first, then fill from in-process so a dropped cache write
        # never silently erases the conversation's focus.
        merged: dict[str, str] = {}
        if self.cloud_authoritative:
            cloud = self.production.load_session(session_key)
            if cloud:
                merged.update(cloud)
        local = self.sessions.get(session_key)
        if local:
            for key, value in local.items():
                merged.setdefault(key, value)
        return merged if merged else self.sessions.setdefault(session_key, {})

    def _save_session(self, user_id: str, session: dict[str, str], thread_id: str | None = None) -> None:
        session_key = self._thread_session_key(user_id, thread_id)
        self.sessions[session_key] = session  # always-available tier
        if self.cloud_authoritative:
            self.production.save_session(session_key, session)  # best-effort durability

    async def run(self, request: PipelineRequest, skip_llm_render: bool = False) -> PipelineResponse:
        # When skip_llm_render is True (streaming path), the blocking T2 LLM render
        # is skipped: run() returns the verified object rendered deterministically
        # (fast) and stashes (obj, deterministic_render) on self._stream_ctx keyed
        # by trace_id, so run_stream() can stream the bounded render separately
        # without paying for the render twice.
        self._reset_request_cache()

        # Safety gate â€” check before any processing
        safety_refusal = self._safety_check(request.query)
        if safety_refusal:
            self.event_store.append(
                "safety_refusal",
                request.user_id,
                {"query_length": len(request.query), "user_id": request.user_id},
                user_id=request.user_id,
            )
            # Return a minimal valid PipelineResponse
            from .models import SemanticIR, ExecutionMode, IntentDomain
            refusal_ir = SemanticIR(
                target_ir="OP_ESCAPE_TO_SANDBOX",
                system_action="OP_ESCAPE_TO_SANDBOX",
                confidence=0.0,
                execution_mode=ExecutionMode.AIR_GAPPED_CONTAINER,
                intent_domain=IntentDomain.UNKNOWN,
            )
            return PipelineResponse(
                response=safety_refusal,
                ir=refusal_ir,
                reasoning_chain=[],
                confidence=0.0,
                gaps=["Request declined on safety grounds."],
                sources=[],
                simulation_results=[],
                trace=[],
            )

        cache_key = self._query_cache_key(request)
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
                data={
                    "user_id": request.user_id,
                    "workspace_id": request.workspace_id,
                    "thread_id": request.thread_id or "default",
                    "modality": request.modality.value,
                    "return_trace": request.return_trace,
                },
            )
        )

        session = self._load_session(request.user_id, request.thread_id)
        logger.debug("Loaded session: keys=%s", list(session.keys()))
        
        # Context Decoupling / topic drift check
        from datetime import datetime, timezone, timedelta
        now_time = datetime.now(timezone.utc)
        last_activity_str = session.get("last_activity")
        clear_context = False
        logger.debug("Context decoupling check: last_activity=%s", last_activity_str)
        if last_activity_str:
            try:
                last_activity = datetime.fromisoformat(last_activity_str)
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=timezone.utc)
                if now_time - last_activity > timedelta(minutes=15):
                    clear_context = True
            except Exception:
                pass
        # Synthetic embeddings removed; time-based check is sufficient.
        if clear_context:
            session.pop("ACTIVE_OBJECT", None)
            session.pop("ACTIVE_INTENT", None)
            session["_prevent_active_object"] = True
        session["last_activity"] = now_time.isoformat()

        ir, intent_layer_result = await self.intent_layer.infer(request, session)
        record(intent_layer_result)
        session["ACTIVE_INTENT"] = ir.target_ir
        if not session.get("_prevent_active_object"):
            # Discourse focus: the referent for later underspecified turns
            # ("what does IT use?"). A referent is a NAMED entity, and the CLL's
            # name-evidence literals are exactly that: a nonce/name encodes as
            # L:..., while a wh-word ("what") or common noun does not. Prefer
            # them so "it"/"she" resolves to a real name — L1 over-extracts
            # function words like "what" into its entity list, and taking
            # entities[0] would make the wh-word the focus (observed: the
            # device-codename opener set focus="what", so the follow-up's "it"
            # resolved to nothing). Fall back to L1 entities only when the query
            # names nothing the lexicon recognises. One name-evidence machinery
            # everywhere, any language, no wh-word list.
            focus: list[str] = []
            try:
                from .cll_shadow import get_shadow, index_enabled, shadow_enabled
                if index_enabled() or shadow_enabled():
                    _, literals = get_shadow().encode(request.query)
                    focus = [lit[2:] for lit in sorted(literals)]
            except Exception:
                focus = []
            if not focus:
                focus = [str(e) for e in ir.scope_constraints.get("entities", [])]
            if focus:
                session["ACTIVE_OBJECT"] = focus[0]
        session.pop("_prevent_active_object", None)
        self._save_session(request.user_id, session, request.thread_id)

        # â”€â”€ World-model fast-path â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # If the query is a causal lookup ("X causes Y") and we have an accepted
        # rule for the queried entity, return a deterministic answer immediately
        # without invoking retrieval, reasoning, or render layers.
        question_intent = ir.scope_constraints.get("question_intent", {})
        wm_entities = [str(e) for e in ir.scope_constraints.get("entities", [])]
        if (
            isinstance(question_intent, dict)
            and question_intent.get("relation") == "causes"
            and len(wm_entities) >= 1
            and self.world_model_fast_path._accepted
        ):
            direction = str(question_intent.get("direction") or "outgoing")
            fast_matches: list[WorldModelCandidate] = []
            for entity in wm_entities[:3]:
                if direction == "incoming":
                    fast_matches.extend(self.world_model_fast_path.lookup_causes_of(entity))
                else:
                    fast_matches.extend(self.world_model_fast_path.lookup_effects_of(entity))
            if fast_matches:
                summary_lines = [
                    f"{c.rule} (confidence {c.confidence:.2f}, verified rule)"
                    for c in fast_matches[:5]
                ]
                fast_sig = self._write_result_signature(
                    "world_model_fast_path",
                    "solved",
                    "Answered from a human-approved world model rule (deterministic, no model inference).",
                    user_id=request.user_id,
                    confidence=min(c.confidence for c in fast_matches),
                    provenance=[p for c in fast_matches for p in c.provenance.split(",") if p],
                    data={
                        "matched_rules": [c.model_dump(mode="json") for c in fast_matches],
                        "summary_lines": summary_lines,
                    },
                )
                self.event_store.append(
                    "world_model_fast_path_hit",
                    ir.trace_id,
                    {"entities": wm_entities, "matched_rules": len(fast_matches)},
                    user_id=request.user_id,
                )
                return PipelineResponse(
                    response="\n".join(summary_lines),
                    ir=ir,
                    reasoning_chain=[],
                    confidence=fast_sig.confidence,
                    gaps=[],
                    sources=fast_sig.provenance,
                    simulation_results=[],
                    trace=[],
                    used_llm=False,                )

        input_signature, encoder_layer_result = await self.encoder_layer.encode(request, ir)
        record(encoder_layer_result)
        record(self.learning_layer.learn(input_signature))
        promoted_user_facts = await self._promote_user_fact_memory(request, input_signature)
        if promoted_user_facts:
            record(
                LayerResult(
                    layer="V9_user_fact_promotion",
                    activated=True,
                    deterministic=True,
                    summary="Promoted structured user facts from the prompt into durable profile memory.",
                    data={"promoted": promoted_user_facts},
                )
            )
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

        capability_plan, capability_layer_result = await self.capability_router.route(request, ir, activation)
        record(capability_layer_result)

        # Retrieval runs BEFORE capability adapter execution so adapters can see
        # what scoped memory already answers — e.g. web search is skipped when
        # the workspace/user memory layer holds strong evidence (it takes
        # precedence over the public web, spec §4.4), saving seconds per query.
        retrieved, retrieval_layer_result = self.retrieval_layer.retrieve(
            request,
            ir,
            activation,
            exclude_ids={input_signature.id},
            vector_retrieval_context=input_signature.id,
        )
        record(retrieval_layer_result)
        if not retrieved:
            self.retrieval_misses += 1

        capability_results = self.capability_adapters.prepare(capability_plan)
        # Multi-intent attention: prepare and execute every detected secondary
        # intent as well, so a prompt asking for two things gets two answers.
        # Human-gated capabilities keep their approval requirements — prepare()
        # marks them blocked/queued exactly as it does for a primary route.
        seen_kinds = {capability_plan.kind}
        for secondary_kind in (capability_plan.secondary_intents or [])[:2]:
            if secondary_kind in seen_kinds:
                continue
            seen_kinds.add(secondary_kind)
            secondary_plan = self.capability_router.plan_for_secondary(secondary_kind, capability_plan)
            capability_results.extend(self.capability_adapters.prepare(secondary_plan))
        capability_results = await self._execute_capability_adapters(request, capability_results, retrieved=retrieved)
        for capability_result in capability_results:
            self.capability_router.record_outcome(
                capability_result.kind,
                status=capability_result.status,
                confidence=max(0.05, min(1.0, capability_result.confidence)),
            )
        record(
            LayerResult(
                layer="V9_capability_adapters",
                activated=bool(capability_results),
                deterministic=True,
                summary="Prepared and executed verified structured capability adapters where available.",
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

        abstraction_result, abstraction_layer_result = self.abstraction_layer.run(retrieved, activation)
        record(abstraction_layer_result)

        world_model_activations, graph_view, world_model_layer_result = self.world_model_layer.activate(ir, retrieved, activation)
        record(world_model_layer_result)
        newly_promoted = self.world_model_promotion.observe(world_model_activations)
        if newly_promoted:
            existing_rules = {c.rule for c in self.world_model_candidates}
            self.world_model_candidates.extend(
                c for c in newly_promoted if c.rule not in existing_rules
            )
            self.world_model_fast_path.rebuild(self.world_model_candidates)

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
        obj.raw_query = request.query  # for response-format detection in the CSSE
        obj.style_signature = {
            **obj.style_signature,
            "user_prompt": request.query,
            "language_hint": self._response_language_hint(request.query),
            "format_hint": self._response_format_hint(request.query),
        }
        self._apply_capability_gates(obj)

        if skip_llm_render:
            deterministic_render = self.csse.render(obj)
            response = deterministic_render
            used_llm_render = False
            render_layer_result = LayerResult(
                layer="T2_transformer_render_interface",
                activated=True,
                deterministic=False,
                summary="Prepared verified render basis for the streaming T2 renderer.",
                data={"mode": "deferred_t2_stream"},
            )
            self._stream_ctx[ir.trace_id] = (obj, deterministic_render)
        else:
            response, used_llm_render, render_layer_result = await self.render_layer.render(obj)
        record(render_layer_result)
        record(
            LayerResult(
                layer="output",
                activated=True,
                deterministic=not used_llm_render,
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
        # Strip any leaked Qwen3 <think>...</think> reasoning blocks from the final response.
        # These can appear when the model doesn't wrap its output in JSON as instructed.
        clean_response = re.sub(r"<think>.*$", "", re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL), flags=re.DOTALL).strip()
        if not clean_response:
            clean_response = response  # keep original if stripping removed everything
        pipeline_response = PipelineResponse(
            response=clean_response,
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
            used_llm=used_llm_render,
            suggestions=self._build_suggestions(response, obj),
        )
        if not skip_llm_render:
            self._learn_from_resolved_prompt(request, pipeline_response)
            self.result_cache.set(cache_key, pipeline_response.model_dump(mode="json"))
            self._cloud_write(
                "save_chat_exchange",
                lambda: self.production.save_chat_exchange(
                    user_id=request.user_id,
                    workspace_id=request.workspace_id,
                    thread_id=request.thread_id or "default",
                    query=request.query,
                    answer=response,
                    trace_id=ir.trace_id,
                    confidence=obj.confidence,
                    sources=obj.sources,
                ),
            )
        self.event_store.append(
            "query_completed",
            ir.trace_id,
            {
                "cache_key": cache_key,
                "confidence": obj.confidence,
                "sources": obj.sources,
                "gaps": obj.knowledge_gaps,
                "used_llm": used_llm_render,
                "thread_id": request.thread_id or "default",
            },
            user_id=request.user_id,
        )
        return pipeline_response

    async def run_stream(self, request: PipelineRequest):
        """Async generator for streaming responses (SSE).

        Yields dicts:
          {"type": "meta",  ...}   once, after verification (confidence/gaps/sources/trace)
          {"type": "token", "text": "..."}  repeatedly, as the bounded T2 render streams
          {"type": "done",  "response": "<full text>"}  once at the end

        The verification phase (compile â†’ retrieve â†’ reason) runs first and is not
        streamed; the user-visible answer (T2 render) then streams token-by-token,
        so first-token latency is the time-to-verified-object plus one model TTFT,
        not the full render duration.
        """
        verified = await self.run(request, skip_llm_render=True)
        obj, deterministic_render = self._stream_ctx.pop(
            verified.ir.trace_id, (None, verified.response)
        )
        if obj is None:
            raise CriticalServiceUnavailable("stream render context missing")
        yield {
            "type": "meta",
            "trace_id": verified.ir.trace_id,
            "confidence": verified.confidence,
            "gaps": verified.gaps,
            "sources": verified.sources,
            "used_llm": bool(obj is not None and self.bridge.qwen_enabled),
        }
        parts: list[str] = []
        # De-LLM path: the answer IS the deterministic CSSE render — stream it
        # progressively in natural word-chunks (no model, no wait). This gives
        # true token-by-token delivery to the client without any T2 LLM.
        if not self.bridge.qwen_enabled:
            for chunk in self._stream_chunks(deterministic_render):
                parts.append(chunk)
                yield {"type": "token", "text": chunk}
        else:
            try:
                async for delta in self.bridge.stream_render(obj, deterministic_render):
                    if not delta:
                        continue
                    parts.append(delta)
                    yield {"type": "token", "text": delta}
            except CriticalServiceUnavailable:
                if os.getenv("JIMS_T2_STRICT", "false").lower() in {"1", "true", "yes", "on"} or parts:
                    # Strict mode, or the stream broke mid-render (a partial T2
                    # answer must not be silently replaced with a different text).
                    raise
                # T2 never produced a token — stream the deterministic render.
                for chunk in self._stream_chunks(deterministic_render):
                    parts.append(chunk)
                    yield {"type": "token", "text": chunk}
        full = re.sub(r"<think>.*$", "", re.sub(r"<think>.*?</think>", "", "".join(parts), flags=re.DOTALL), flags=re.DOTALL).strip() or "".join(parts)
        final_response = verified.model_copy(
            update={"response": full, "used_llm": bool(obj is not None and self.bridge.qwen_enabled)}
        )
        self._learn_from_resolved_prompt(request, final_response)
        self.result_cache.set(self._query_cache_key(request), final_response.model_dump(mode="json"))
        # Persist the streamed answer so chat history reflects what the user saw.
        try:
            self._cloud_write(
                "save_streamed_chat_exchange",
                lambda: self.production.save_chat_exchange(
                    user_id=request.user_id,
                    workspace_id=request.workspace_id,
                    thread_id=request.thread_id or "default",
                    query=request.query,
                    answer=full,
                    trace_id=verified.ir.trace_id,
                    confidence=verified.confidence,
                    sources=verified.sources,
                ),
            )
        except Exception:
            pass
        yield {"type": "done", "response": full}

    @staticmethod
    def _stream_chunks(text: str):
        """Chunk a rendered answer into natural streaming deltas: word-by-word,
        preserving whitespace/newlines so the client reconstructs the exact
        text. Deterministic, language-agnostic (splits on Unicode spaces),
        model-free — progressive delivery of the CSSE render itself."""
        for token in re.findall(r"\S+\s*", text):
            yield token

    def _build_suggestions(self, response_text: str, obj: VerifiedCognitiveObject) -> list[str]:
        """Generate actionable suggestions for low-confidence or incomplete responses."""
        suggestions: list[str] = []

        # Low confidence â€” suggest ways to improve
        if obj.confidence < 0.60:
            suggestions.append("Share more context to help me give a better answer.")

        # Math capability with no solution
        capability_kind = ""
        if obj.capability_plan:
            capability_kind = str(getattr(obj.capability_plan, "kind", "") or "").upper()
        math_attempted = any(
            result.kind == CapabilityKind.MATH_SCIENCE and result.data.get("executed")
            for result in obj.capability_results
        )
        if "MATH" in capability_kind and math_attempted and not obj.reasoning_chain:
            suggestions.append("Try expressing maths as: `2 + 9` or `2x + 5 = 11`")

        # Profile unknown
        has_profile_gap = "profile" in str(getattr(obj, "intent", "") or "").lower() or (
            obj.capability_plan and "profile" in str(getattr(obj.capability_plan, "route", "")).lower()
        )
        if has_profile_gap and not obj.sources:
            suggestions.append("Tell me your name to help me remember you.")

        # Code with no codebase
        if ("CODE" in capability_kind or "CODING" in capability_kind) and not obj.sources:
            suggestions.append("Share a file or describe what you're building.")

        return suggestions

    def _learn_from_resolved_prompt(self, request: PipelineRequest, response: PipelineResponse) -> None:
        if os.getenv("JIMS_ENABLE_RESOLUTION_LEARNING", "true").lower() not in {"1", "true", "yes", "on"}:
            return

        # Only write back verified, executed, solver-backed results â€” no LLM-only threshold
        executed_results = [
            result
            for result in response.capability_results
            if result.data.get("executed") and result.confidence >= 0.75 and result.data.get("solver_status", "solved") == "solved"
        ]

        # Threshold: 0.90 minimum confidence (configurable), no knowledge gaps, must have executed results
        # (Previously: 0.82 + used_groq â€” Groq removed, threshold raised to avoid noisy write-back)
        min_confidence = float(os.getenv("JIMS_RESOLUTION_LEARNING_MIN_CONFIDENCE", "0.90") or "0.90")
        high_confidence_verified = (
            response.confidence >= min_confidence
            and not response.gaps
            and executed_results
        )

        if not high_confidence_verified:
            return

        capability_kind = response.capability_plan.kind.value if response.capability_plan else "memory_chat"
        content = {
            "type": "resolved_prompt_memory",
            "user_prompt": request.query,
            "capability_kind": capability_kind,
            "route": response.capability_plan.route if response.capability_plan else "",
            "routing_signals": response.capability_plan.routing_signals if response.capability_plan else {},
            "verified_results": [result.model_dump(mode="json") for result in executed_results],
            "answer": response.response,
            "confidence": response.confidence,
            "sources": response.sources,
        }
        text = (
            "Resolved prompt memory.\n"
            f"Prompt: {request.query}\n"
            f"Capability: {capability_kind}\n"
            f"Answer: {response.response}\n"
            "Verification: structured verified result stored in metadata."
        )
        import asyncio as _asyncio_lrp
        try:
            loop = _asyncio_lrp.get_running_loop()

            async def _write_resolved_mem() -> None:
                try:
                    sig = await self.encoder.encode(
                        text,
                        modality=Modality.TEXT,
                        intent_type="resolved_prompt_memory",
                        provenance=f"resolution:{response.ir.trace_id}",
                        workspace_id=request.workspace_id,
                        user_id=request.user_id,
                    )
                except CriticalServiceUnavailable as exc:
                    self.event_store.append(
                        "resolution_memory_write_failed",
                        response.ir.trace_id,
                        {"reason": str(exc)},
                        user_id=request.user_id,
                    )
                    return
                sig.confidence.score = min(0.98, max(response.confidence, 0.90))
                sig.confidence.source = "resolution_learning_verified"
                sig.metadata.update(content)
                panel_item = TrainingPanelItem(
                    id=f"memory:{sig.id}",
                    panel="memory",
                    kind="resolved_prompt_memory",
                    title=f"{capability_kind}: {request.query[:80]}",
                    subtitle=f"confidence {sig.confidence.score:.2f} / trace {response.ir.trace_id}",
                    data=sig.model_dump(mode="json"),
                    created_at=sig.created_at,
                )
                self._cloud_write(
                    "save_resolution_memory",
                    lambda sig=sig, text=text, panel_item=panel_item: self.production.save_training_ingest(sig, text, [panel_item]),
                )
                self.event_store.append(
                    "resolution_memory_written",
                    sig.id,
                    {
                        "trace_id": response.ir.trace_id,
                        "capability_kind": capability_kind,
                        "source_results": [result.provenance for result in executed_results],
                        "min_confidence_threshold": min_confidence,
                    },
                    user_id=request.user_id,
                )

            loop.create_task(_write_resolved_mem())
        except RuntimeError:
            pass

    async def _execute_capability_adapters(
        self,
        request: PipelineRequest,
        capability_results: list[CapabilityExecutionResult],
        retrieved: list | None = None,
    ) -> list[CapabilityExecutionResult]:
        executed: list[CapabilityExecutionResult] = []
        for result in capability_results:
            # â”€â”€ WORLD_KNOWLEDGE: DuckDuckGo web search â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if result.kind == CapabilityKind.WORLD_KNOWLEDGE and result.status == "available":
                if self._scoped_memory_answers(request, retrieved):
                    # The workspace/user memory layer already holds strong scoped
                    # evidence — it takes precedence over the public web, and
                    # skipping the search saves the DDG + ingestion round trips.
                    executed.append(
                        result.model_copy(
                            update={
                                "status": "not_required",
                                "summary": "Scoped workspace/user memory answers this query; web search skipped.",
                                "data": {**result.data, "executed": False, "web_skip_reason": "scoped_memory_evidence"},
                            }
                        )
                    )
                    continue
                web_result = await self._execute_web_search(request, result)
                executed.append(web_result)
                continue

            if result.kind != CapabilityKind.MATH_SCIENCE or result.adapter != "internal_symbolic_solver":
                executed.append(result)
                continue
            # Math notation is a formal language — extract by grammar first
            # (deterministic, language-independent, LLM-free). The T1 bridge
            # is a legacy fallback only; under the Independence Policy it is
            # disabled and an unparseable expression becomes a gap, not a guess.
            from .math_extract import extract_expression
            expression, solve_for = extract_expression(
                request.query,
                known_symbols=frozenset(getattr(self.math_solver, "_PHYSICS_NAMESPACE", {})),
                elements=frozenset(getattr(self.math_solver, "_ELEMENT_MASSES", {})),
            )
            qwen_extraction_status = "deterministic_grammar" if expression else "not_attempted"
            if not expression:
                expression, solve_for, qwen_extraction_status = await self._extract_solver_expression_with_qwen(request.query, result.data)
            if not expression:
                executed.append(
                    result.model_copy(
                        update={
                            "status": "not_required",
                            "confidence": min(result.confidence, 0.35),
                            "summary": "No executable symbolic expression was extracted; continuing through retrieval/rendering.",
                            "data": {
                                **result.data,
                                "executed": False,
                                "solver_status": "not_required",
                                "extraction_status": qwen_extraction_status if qwen_extraction_status != "not_attempted" else "not_found",
                            },
                        }
                    )
                )
                continue
            try:
                solved = self.math_solver.solve(expression, solve_for)
            except Exception as error:
                solved = {"status": "failed", "result": str(error), "method": "internal_symbolic_solver"}
            if solved.get("status") != "solved":
                qwen_expression, qwen_solve_for, qwen_extraction_status = await self._extract_solver_expression_with_qwen(request.query, {**result.data, "initial_expression": expression})
                if qwen_expression and qwen_expression != expression:
                    expression, solve_for = qwen_expression, qwen_solve_for
                    try:
                        solved = self.math_solver.solve(expression, solve_for)
                    except Exception as error:
                        solved = {"status": "failed", "result": str(error), "method": "internal_symbolic_solver"}
            status = "solved" if solved.get("status") == "solved" else "failed"
            signature = self._write_result_signature(
                "math",
                "verified" if status == "solved" else "failed",
                f"Math capability {status}: {expression} -> {solved.get('result', '')}",
                user_id=request.user_id,
                confidence=0.99 if status == "solved" else 0.25,
                provenance=["internal_symbolic_solver"],
                data={"expression": expression, "solve_for": solve_for, **solved},
                workspace_id=request.workspace_id,
            )
            executed.append(
                result.model_copy(
                    update={
                        "confidence": 0.99 if status == "solved" else 0.25,
                        "summary": f"Internal symbolic solver {status}: {expression} -> {solved.get('result', '')}",
                        "provenance": [signature.id],
                        "data": {
                            **result.data,
                            "executed": True,
                            "expression": expression,
                            "solve_for": solve_for,
                            "solver_status": status,
                            "solver_result": solved.get("result", ""),
                            "solver_method": solved.get("method", ""),
                            "result_signature_id": signature.id,
                            "extraction_status": qwen_extraction_status,
                        },
                    }
                )
            )
        return executed

    def _scoped_memory_answers(self, request: PipelineRequest, retrieved: list | None) -> bool:
        """True when retrieval already surfaced strong evidence scoped to this
        request's workspace or user — the layer that outranks the public web."""
        if not retrieved:
            return False
        try:
            threshold = float(os.getenv("JIMS_WEB_SKIP_MEMORY_SCORE", "0.55") or "0.55")
        except ValueError:
            threshold = 0.55
        for item in retrieved:
            signature = getattr(item, "signature", None)
            score = float(getattr(item, "score", 0.0) or 0.0)
            if signature is None or score < threshold:
                continue
            scoped_to_workspace = bool(request.workspace_id) and getattr(signature, "workspace_id", None) == request.workspace_id
            scoped_to_user = bool(request.user_id) and getattr(signature, "user_id", None) == request.user_id
            if scoped_to_workspace or scoped_to_user:
                return True
        return False

    async def _execute_web_search(
        self,
        request: PipelineRequest,
        result: CapabilityExecutionResult,
    ) -> CapabilityExecutionResult:
        """Execute DuckDuckGo web search and ingest top results as memory signatures."""
        from .web_search import WebAugmentedRetrieval
        try:
            searcher = WebAugmentedRetrieval(workspace_id=request.workspace_id or "global", max_results=5)
            sources = await searcher.search(request.query)
            if not sources:
                return result.model_copy(
                    update={
                        "status": "available",
                        "confidence": 0.40,
                        "summary": "Web search returned no results for this query.",
                        "data": {**result.data, "executed": True, "web_sources": []},
                    }
                )
            ingested_ids: list[str] = []
            for source in sources[:3]:
                content = f"{source.title}: {source.snippet}" if source.snippet else source.title
                sig = await self.encoder.encode(
                    content,
                    modality=Modality.TEXT,
                    intent_type="web_knowledge",
                    provenance=f"web:{source.url}",
                    workspace_id=request.workspace_id,
                    user_id=request.user_id,
                )
                sig.metadata["web_source_url"] = source.url
                sig.metadata["web_source_title"] = source.title
                sig.metadata["fetched_at"] = source.fetched_at
                sig.metadata["is_live_web"] = True
                sig.confidence.score = round(min(source.confidence, 0.82), 4)
                self.memory.insert(sig)
                self.graph.add_signature(sig)
                ingested_ids.append(sig.id)
            return result.model_copy(
                update={
                    "status": "available",
                    "confidence": 0.80,
                    "summary": f"Web search: {len(sources)} sources found, {len(ingested_ids)} ingested into memory",
                    "provenance": ingested_ids,
                    "data": {
                        **result.data,
                        "executed": True,
                        "web_sources": [s.to_signature() for s in sources[:3]],
                    },
                }
            )
        except Exception as exc:
            logger.error("Web search failed with exception: %s", exc, exc_info=True)
            return result.model_copy(
                update={"status": "unavailable", "summary": f"Web search failed: {exc}"}
            )

    async def _extract_solver_expression_with_qwen(self, query: str, context: dict[str, Any]) -> tuple[str, str | None, str]:
        """Extract a mathematical expression from natural language using the T1 bridge.

        Supports all mathematical domains â€” arithmetic, algebra, calculus, linear algebra,
        differential equations, statistics, geometry, physics. The bridge returns a
        sympy-compatible expression string that is passed directly to SymbolicMathSolver.solve().
        No character-set validation â€” sympy expressions use letters, digits, and function names.

        Returns (expression, solve_for, status), where status is a diagnostic string:
        "ok", "bridge_unavailable_or_timeout" (bridge returned None â€” likely a Modal
        timeout, cold start, or non-JSON response), or "empty_expression" (T1 ran but
        found no mathematical content).
        """
        data = await self.bridge.extract_math_expression(query, context)
        if not data:
            return "", None, "bridge_unavailable_or_timeout"
        expression = str(data.get("expression") or "").strip()
        if not expression:
            return "", None, "empty_expression"
        solve_for_value = data.get("solve_for")
        solve_for = str(solve_for_value).strip() if solve_for_value else None
        # solve_for must be a single variable name (1+ chars) â€” no equations
        if solve_for and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", solve_for):
            solve_for = None
        # Compact whitespace but preserve function calls like diff(x**3, x)
        expression = re.sub(r"\s+", " ", expression).strip()
        return expression, solve_for, "ok"

    async def _promote_user_fact_memory(self, request: PipelineRequest, input_signature) -> int:
        user_relations = [
            relation
            for relation in input_signature.structured.relations
            if relation.subject.lower() == "user"
            and (relation.predicate.startswith("has_") or relation.predicate.startswith("is_"))
            and relation.object.strip()
        ]
        # Focused T1 pass for self-referential facts when the general extraction
        # did not emit subject=user relations.
        if not user_relations and self.bridge.qwen_enabled:
            try:
                data = await self.bridge.extract_user_facts(
                    input_signature.raw_excerpt or request.query,
                    context={"workspace_id": request.workspace_id},
                )
            except Exception:
                data = None
            if data:
                for item in data.get("relations") or []:
                    if not isinstance(item, dict):
                        continue
                    predicate = str(item.get("predicate") or "").strip()
                    obj_value = str(item.get("object") or "").strip()
                    if not predicate or not obj_value:
                        continue
                    if not (predicate.startswith("has_") or predicate.startswith("is_")):
                        continue
                    try:
                        confidence = float(item.get("confidence") or 0.85)
                    except (TypeError, ValueError):
                        confidence = 0.85
                    confidence = max(0.0, min(1.0, confidence))
                    user_relations.append(
                        Relation(subject="user", predicate=predicate[:80], object=obj_value[:240], confidence=confidence)
                    )
        if not user_relations:
            return 0
        promoted = 0
        for relation in user_relations:
            fact_text = f"User profile fact: user {relation.predicate} {relation.object}."
            vector = await self.encoder._external_embedding(fact_text, Modality.TEXT)
            if not vector:
                raise CriticalServiceUnavailable("embedding service unavailable for user profile promotion")
            signature = MemorySignature(
                id=stable_id(
                    "sig",
                    f"user_profile_statement:user_profile:{request.user_id}:{request.workspace_id}:{relation.predicate}:{relation.object}",
                ),
                provenance="user_profile_statement",
                structured=StructuredSignature(
                    entities=[
                        Entity(id=stable_id("ent", "user"), name="user", type="person"),
                        Entity(id=stable_id("ent", relation.object), name=relation.object, type="profile_value"),
                    ],
                    relations=[relation],
                    causal_chain=[],
                    intent=SignatureIntent(type="user_profile", certainty="confirmed"),
                ),
                latent_embedding=vector,
                abstraction_tags=sorted({"user", "profile", "user_profile_training", relation.predicate}),
                confidence=Confidence(
                    score=min(0.98, max(0.72, relation.confidence)),
                    source="user_profile_statement",
                ),
                modality=Modality.TEXT,
                linked_signatures=[],
                raw_excerpt=fact_text,
                workspace_id=request.workspace_id,
                user_id=request.user_id,
                metadata={
                    "encoder_version": "profile_relation_direct_signature_v1",
                    "graph_index_allowed": True,
                    "latent_encoder": "external_text_embedding",
                    "latent_embedding_source": "external_service",
                    "reembedding_required": False,
                    "profile_relation_predicate": relation.predicate,
                    "profile_relation_object": relation.object,
                },
            )
            self.memory.insert(signature)
            self.graph.add_signature(signature)
            try:
                self._cloud_write(
                    "save_user_profile_signature",
                    lambda signature=signature: self.production.save_memory_signature(signature),
                )
            except Exception:
                logger.debug("User profile fact persistence skipped", exc_info=True)
            promoted += 1
        return promoted

    _SAFETY_PATTERNS = [
        re.compile(r"\b(make|build|create|construct|assemble|synthesize)\b.{0,40}\b(bomb|explosive|weapon|poison|nerve\s+agent|bioweapon|ied)\b", re.IGNORECASE),
        re.compile(r"\b(how\s+to|instructions?\s+for|steps?\s+to)\b.{0,40}\b(bomb|explosive|weapon|poison|kill\s+people|make\s+meth|synthesize\s+drugs)\b", re.IGNORECASE),
    ]

    def _safety_check(self, query: str) -> str | None:
        """Return a refusal string if the query matches a harmful pattern, else None."""
        for pattern in self._SAFETY_PATTERNS:
            if pattern.search(query):
                return (
                    "I can't help with that. If you're working on a legitimate safety, "
                    "research, or fictional context, please describe the actual goal "
                    "and I'll do my best to assist within safe boundaries."
                )
        return None

    def _apply_capability_gates(self, obj) -> None:
        if not obj.capability_plan:
            return

        # CODING: use only model/provider output; never fabricate a stub.
        if obj.capability_plan.kind == CapabilityKind.CODING:
            invention = getattr(obj, "invention_result", None)
            code_step = None

            if invention and invention.activated and invention.candidate_steps:
                for step in reversed(invention.candidate_steps):
                    s = str(step).strip()
                    if s:
                        code_step = s
                        break

            if not code_step:
                # Typed internal gap → the CSSE renders a natural coding-gap
                # response ("share a file / describe what you're building").
                # HEDGE relation keeps the raw status out of user-facing claims.
                obj.knowledge_gaps.append(
                    "[internal] coding capability produced no verified code"
                )
                obj.reasoning_chain = [
                    ReasoningStep(
                        claim="No verified code available for this request.",
                        confidence=0.0,
                        sources=[],
                        source_signature_ids=[],
                        provenance_class=ProvenanceClass.GAP_UNRESOLVED,
                        relation="HEDGE",
                    )
                ]
                obj.sources = []
                obj.confidence = min(obj.confidence, 0.35)
                return

            obj.reasoning_chain = [
                ReasoningStep(
                    claim=code_step,
                    confidence=0.82,
                    sources=[],
                    source_signature_ids=[],
                    provenance_class=ProvenanceClass.PLAUSIBLE_LEARNED,
                    relation="CODE_GENERATION",
                )
            ]
            obj.confidence = max(obj.confidence, 0.72)
            obj.knowledge_gaps = [g for g in obj.knowledge_gaps if "code" not in g.lower()]
            return
        # â”€â”€ WORLD_KNOWLEDGE: inject web search results into reasoning chain â”€â”€â”€â”€
        # _execute_web_search() runs AFTER retrieval, so web content never makes
        # it into the retrieved set. We inject it here directly from the result data.
        for result in obj.capability_results:
            if result.kind != CapabilityKind.WORLD_KNOWLEDGE:
                continue
            if not result.data.get("executed"):
                continue
            web_sources = result.data.get("web_sources") or []
            if not web_sources:
                continue
            # Build reasoning steps from the top web sources
            web_steps = []
            for src in web_sources[:3]:
                snippet = str(src.get("snippet") or "").strip()
                title = str(src.get("title") or "").strip()
                url = str(src.get("url") or "").strip()
                if not snippet and not title:
                    continue
                claim = f"{title}: {snippet}" if snippet else title
                web_steps.append(
                    ReasoningStep(
                        claim=claim[:600],
                        confidence=float(src.get("confidence") or 0.80),
                        sources=[url] if url else [],
                        source_signature_ids=[],
                        provenance_class=ProvenanceClass.PLAUSIBLE_LEARNED,
                        relation="WEB_SEARCH_RESULT",
                    )
                )
            if web_steps:
                # Workspace/user memory takes precedence over the public web
                # (spec §4.4): retrieved memory claims stay first-class and web
                # results AUGMENT the chain instead of replacing it. Only when
                # memory produced nothing does the web become the whole answer.
                memory_steps = [
                    step for step in obj.reasoning_chain
                    if step.source_signature_ids or step.sources
                ]
                if memory_steps:
                    obj.reasoning_chain = [*obj.reasoning_chain, *web_steps]
                else:
                    obj.reasoning_chain = web_steps
                obj.sources = [
                    *obj.sources,
                    *[str(s.get("url") or "") for s in web_sources[:3] if s.get("url")],
                ]
                obj.confidence = max(obj.confidence, result.confidence)
                obj.knowledge_gaps = [
                    g for g in obj.knowledge_gaps
                    if "No source signatures" not in g
                ]
                break  # Only one WORLD_KNOWLEDGE result expected

        for result in obj.capability_results:
            if result.kind != CapabilityKind.MATH_SCIENCE or result.data.get("solver_status") != "solved":
                continue
            expression = str(result.data.get("expression") or "")
            solver_result = str(result.data.get("solver_result") or "")
            source = str(result.data.get("result_signature_id") or "")
            claim = f"Verified calculation: {expression} = {solver_result}"
            if "=" in expression and result.data.get("solve_for"):
                claim = f"Verified equation solution for {result.data.get('solve_for')}: {expression} -> {solver_result}"
            step = ReasoningStep(
                claim=claim,
                confidence=0.99,
                sources=[source] if source else [],
                source_signature_ids=[source] if source else [],
                provenance_class=ProvenanceClass.SYMBOLIC_SOLVER,
                relation="CALCULATION_TRACE",
            )
            if (
                obj.capability_plan.kind == CapabilityKind.MATH_SCIENCE
                and not obj.capability_plan.secondary_intents
            ):
                # Pure math query: the solver trace IS the answer.
                obj.reasoning_chain = [step]
                obj.sources = [source] if source else []
                obj.knowledge_gaps = [
                    gap
                    for gap in obj.knowledge_gaps
                    if "Math capability" in gap or "solver" in gap
                ]
            else:
                # Multi-intent or non-math primary: the solver answers one part
                # of the prompt — retrieved claims answer the rest. Keep both.
                obj.reasoning_chain = [step, *obj.reasoning_chain]
                if source and source not in obj.sources:
                    obj.sources = [source, *obj.sources]
            obj.confidence = max(obj.confidence, 0.95)
        for result in obj.capability_results:
            if result.kind == CapabilityKind.MATH_SCIENCE and result.data.get("executed") and result.data.get("solver_status") != "solved":
                obj.knowledge_gaps.append(
                    f"Math capability routed correctly, but verified solver could not solve expression {result.data.get('expression', '')}: {result.data.get('solver_result', '')}."
                )
        blocking = [result for result in obj.capability_results if result.status in {"unavailable", "blocked"}]
        for result in blocking:
            obj.knowledge_gaps.append(
                f"Capability {obj.capability_plan.kind.value} needs adapter(s) {result.adapter}; status={result.status}."
            )
        if blocking:
            gate_step = ReasoningStep(
                claim=f"Routed request to {obj.capability_plan.kind.value}, but required provider execution is not available yet.",
                confidence=0.0,
                sources=[],
                source_signature_ids=[],
                provenance_class=ProvenanceClass.GAP_UNRESOLVED,
                relation="CAPABILITY_GATE",
            )
            # Source-backed memory claims survive a blocked capability route:
            # a misroute (or an unconfigured provider) must degrade the answer
            # to what memory verifies, never erase it. The gate step records
            # the blocked capability; retrieved evidence still answers what it can.
            memory_backed = [
                step for step in obj.reasoning_chain
                if step.source_signature_ids or step.sources
            ]
            if obj.capability_plan.kind != CapabilityKind.MEMORY_CHAT:
                if memory_backed:
                    obj.reasoning_chain.append(gate_step)
                else:
                    obj.reasoning_chain = [gate_step]
                    obj.sources = []
                    obj.confidence = min(obj.confidence, 0.35)
            elif not obj.reasoning_chain:
                obj.reasoning_chain.append(gate_step)


    def _response_language_hint(self, query: str) -> str:
        # Enhanced language detection without hardcoded language lists
        # Check for any non-ASCII characters which indicate multilingual content
        if any(ord(char) > 127 for char in query):
            return "non_ascii_or_multilingual_prompt"
        return "default"

    def _response_format_hint(self, query: str) -> str:
        """Detect requested output format from the query.

        Uses format-specific structural markers (like the word "json", code
        fence markers, table pipe characters) rather than vocabulary-based
        matching. "json" and "table" are technical format names that appear
        verbatim in queries regardless of the user's language.
        """
        lowered = query.lower()
        # JSON and table are format names â€” they appear in any language
        if "json" in lowered or "```json" in query:
            return "json"
        if "|" in query and re.search(r"\|\s*\w+\s*\|", query):
            return "table"
        # Structured format request patterns (structural, not vocabulary)
        if re.search(r"```|\bformat\b|\bformatted\b", lowered):
            return "structured"
        return "default"

    async def record_feedback(self, request: FeedbackRequest) -> FeedbackResponse:
        self.feedback_events.append(request)
        created_at = utc_now()
        record = {
            "id": f"feedback_{request.trace_id}_{len(self.feedback_events) + 1}",
            "workspace_id": request.workspace_id or "default",
            "user_id": request.user_id,
            "thread_id": request.thread_id,
            "trace_id": request.trace_id,
            "query": None,
            "answer": None,
            "rating": request.rating,
            "feedback": request.notes,
            "learn_this": request.notes == "learn_this",
            "payload": request.model_dump(mode="json"),
            "request": request.model_dump(mode="json"),
            "created_at": created_at.isoformat(),
        }
        self.feedback_history.append(record)
        self.production.save_user_feedback(record)
        self.production.save_panel_items([self._feedback_item(record, len(self.feedback_history))])

        # â”€â”€ Closed feedback loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Positive ratings reinforce graph edges on causal links in cited signatures.
        # Negative ratings decay confidence on cited signatures so they surface less.
        POSITIVE_RATINGS = {"positive", "accept", "thumbs_up", "learn_this", "helpful"}
        NEGATIVE_RATINGS = {"negative", "reject", "thumbs_down", "unhelpful", "wrong"}
        rating_lower = str(request.rating or "").lower()
        # Also treat notes == "learn_this" as positive
        is_positive = rating_lower in POSITIVE_RATINGS or request.notes == "learn_this"
        is_negative = rating_lower in NEGATIVE_RATINGS

        if (is_positive or is_negative) and request.source_signature_ids:
            for sig_id in request.source_signature_ids:
                sig = self.memory.get(sig_id)
                if sig is None:
                    continue
                if is_positive:
                    # Reinforce causal edges â€” makes causal facts more retrievable
                    for link in sig.structured.causal_chain:
                        self.graph.reinforce(link.cause, link.effect, delta=0.05)
                    # Also reinforce relational edges
                    for relation in sig.structured.relations:
                        self.graph.reinforce(relation.subject, relation.object, delta=0.03)
                elif is_negative:
                    # Lower confidence so this signature surfaces less in future retrievals
                    new_score = round(max(0.10, sig.confidence.score - 0.10), 4)
                    sig.confidence.score = new_score
                    sig.confidence.source = "feedback_negative_decay"
                    self.memory.update(sig)

        self.event_store.append(
            "feedback_recorded",
            request.trace_id,
            {
                "rating": request.rating,
                "notes": request.notes,
                "is_positive": is_positive,
                "is_negative": is_negative,
                "source_signatures": request.source_signature_ids if hasattr(request, "source_signature_ids") else [],
            },
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
        import asyncio as _asyncio
        memory_signature = _asyncio.get_event_loop().run_until_complete(
            self.encoder.encode(
                f"{kind} result {status}: {summary}",
                modality=Modality.CODE if kind == "sandbox" else Modality.TEXT,
                intent_type=f"{kind}_result_signature",
                provenance=signature.id,
                workspace_id=workspace_id,
                user_id=user_id,
            )
        ) if not _asyncio.get_event_loop().is_running() else None
        # In async context (called from within an async method), we must use a coroutine.
        # _write_result_signature is called from both sync and async contexts.
        # The simplest fix: make it return VerifiedResultSignature and schedule
        # the encode in the background (fire-and-forget) when in an async context,
        # or run synchronously when not in an event loop.
        # However, since all callers are within async methods that have a running loop,
        # we use asyncio.ensure_future to schedule the encode without blocking.
        import asyncio as _asyncio2
        try:
            loop = _asyncio2.get_running_loop()
            # Running inside an async context â€” schedule as a background task
            async def _write_mem() -> None:
                mem_sig = await self.encoder.encode(
                    f"{kind} result {status}: {summary}",
                    modality=Modality.CODE if kind == "sandbox" else Modality.TEXT,
                    intent_type=f"{kind}_result_signature",
                    provenance=signature.id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                )
                mem_sig.confidence.score = signature.confidence
                mem_sig.confidence.source = "verified_result_signature"
                mem_sig.metadata.update({"verified_result": signature.model_dump(mode="json")})
                self.memory.insert(mem_sig)
                self.graph.add_signature(mem_sig)
            loop.create_task(_write_mem())
        except RuntimeError:
            pass
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
            updated_panel_items = self.production.review_world_model_candidate(
                request.provenance,
                request.rule,
                request.action,
                request.corrected_rule,
            )
            if updated_panel_items:
                final_rule = request.corrected_rule.strip() if request.action == "correct" and request.corrected_rule else request.rule
                self.world_model_fast_path.rebuild(self.world_model_candidates)
                event_payload = {
                    "action": request.action,
                    "rule": request.rule,
                    "final_rule": final_rule,
                    "provenance": request.provenance,
                    "notes": request.notes,
                    "updated_panel_items": updated_panel_items,
                    "persisted_candidate_path": True,
                }
                self.event_store.append("review_action_recorded", stable_id("review", str(event_payload)), event_payload, user_id=request.user_id)
                result = self._write_result_signature(
                    "review",
                    "verified",
                    f"Review {request.action} applied to persisted candidate {final_rule}",
                    user_id=request.user_id,
                    confidence=0.95,
                    provenance=[request.provenance],
                    data=event_payload,
                )
                self.production.save_panel_items([self._pipeline_item(self._pipeline_monitor())])
                return ReviewActionResponse(accepted=True, action=request.action, rule=final_rule, result_signature=result)
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

        self.world_model_fast_path.rebuild(self.world_model_candidates)

        event_payload = {
            "action": request.action,
            "rule": request.rule,
            "final_rule": final_rule,
            "provenance": request.provenance,
            "notes": request.notes,
        }
        event_payload["updated_panel_items"] = self.production.review_world_model_candidate(
            request.provenance,
            request.rule,
            request.action,
            final_rule if request.action == "correct" else request.corrected_rule,
        )
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
            "training_runs": len(self.training_runs),
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
            "modal_training_orchestrator": self.training_orchestrator.configured,
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

    def _world_model_review_required(self, request: TrainingIngestRequest, signature: MemorySignature, conflict_detected: bool) -> bool:
        if conflict_detected:
            return True
        terms_config = os.getenv(
            "JIMS_WM_REVIEW_REQUIRED_TERMS",
            "medical,medicine,clinical,health,legal,law,finance,financial,investment,"
            "safety,security,weapon,biohazard,critical",
        )
        review_terms = [term.strip().lower() for term in terms_config.split(",") if term.strip()]
        if not review_terms:
            return False
        haystack = " ".join(
            str(part or "")
            for part in (
                request.domain_hint,
                signature.metadata.get("document_type"),
                signature.metadata.get("title"),
                signature.metadata.get("summary"),
                request.content[:500],
            )
        ).lower()
        return any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", haystack) for term in review_terms)

    async def ingest_training(self, request: TrainingIngestRequest) -> TrainingIngestResponse:
        tracer = ExecutionTracer()
        intent_type = request.domain_hint or "training_ingestion"
        signature = await self.encoder.encode(
            request.content,
            modality=request.modality,
            intent_type=intent_type,
            provenance="training_pipeline",
            workspace_id=request.workspace_id,
            user_id=request.user_id,
        )
        groq_overlay = None
        inline_overlay = os.getenv("JIMS_INLINE_INGESTION_OVERLAY", "true").lower() in {"1", "true", "yes", "on"}
        if inline_overlay:
            groq_overlay = await self.bridge.extract_ingestion_memory(
                request.content,
                {
                    "modality": request.modality.value,
                    "domain_hint": request.domain_hint,
                    "source_trust": request.source_trust,
                    "workspace_id": request.workspace_id,
                },
            )
        signature.confidence.score = round(min(signature.confidence.score, request.source_trust), 4)
        signature.confidence.source = "training_ingestion_source_trust"
        groq_used = self._apply_ingestion_overlay(signature, groq_overlay, request.source_trust)
        
        # Causal and Relational Conflict Detection & Downgrading for older/stale memory signatures
        conflict_detected = False
        for existing in list(self.memory.visible_signatures(workspace_id=request.workspace_id, user_id=request.user_id)):
            has_conflict = False
            # Check relational conflict
            for existing_rel in existing.structured.relations:
                for new_rel in signature.structured.relations:
                    if (existing_rel.predicate == new_rel.predicate and
                        existing_rel.subject.lower() == new_rel.subject.lower() and
                        existing_rel.object.lower() != new_rel.object.lower()):
                        has_conflict = True
                        break
                if has_conflict:
                    break
            
            # Check causal conflict
            if not has_conflict:
                for existing_cause in existing.structured.causal_chain:
                    for new_cause in signature.structured.causal_chain:
                        if (existing_cause.cause.lower() == new_cause.cause.lower() and
                            existing_cause.effect.lower() != new_cause.effect.lower()):
                            has_conflict = True
                            break
                    if has_conflict:
                        break

            # If there is a conflict, downgrade the older signature to Tier 4 / UNVERIFIED_STALE_MEMORY (< 0.6)
            if has_conflict:
                conflict_detected = True
                existing.confidence.score = 0.5
                existing.provenance = "unverified_stale_memory"
                existing.metadata["validity"] = "stale"
                self.memory.insert(existing)

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
                "used_llm_ingest": groq_used,
            },
            user_id=request.user_id,
        )
        tracer.add(
            "training_ingest",
            "Encoded training input and inserted memory signature",
            signature_id=signature.id,
            modality=request.modality,
            source_trust=request.source_trust,
            used_llm=groq_used,
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

        review_world_model = self._world_model_review_required(request, signature, conflict_detected)
        world_model_candidates = [
            WorldModelCandidate(
                rule=f"{link.cause} causes {link.effect}",
                confidence=round(min(link.confidence, request.source_trust), 4),
                provenance=signature.id,
                review_required=review_world_model,
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
        self._cloud_write(
            "save_training_ingest",
            lambda signature=signature, content=request.content, panel_items=panel_items: self.production.save_training_ingest(signature, content, panel_items),
        )
        for fact_signature in document_signatures:
            self._cloud_write(
                "save_document_fact_signature",
                lambda fact_signature=fact_signature: self.production.save_training_ingest(
                    fact_signature,
                    fact_signature.raw_excerpt,
                    [self._signature_item(fact_signature, panel="memory")],
                ),
            )
        invalidated = self.result_cache.clear()
        self.event_store.append(
            "result_cache_invalidated",
            signature.id,
            {"entries": invalidated, "reason": "training_ingest_memory_write"},
            user_id=request.user_id,
        )
        # Real-time learning: keep the freshly-learned signature in the local hot
        # store (write-through cache) so it is immediately recall-able on this
        # instance â€” no cloud round-trip, no waiting for vector-index consistency.
        # The cloud copy remains the durable, cross-instance source of truth and
        # rehydrates other instances on cold start. Previously this branch DELETED
        # the just-written signature from local memory, which made same-instance
        # real-time recall impossible whenever the vector index was cold, lagging,
        # or degraded â€” defeating the purpose of online learning. Local growth is
        # bounded by the hot-cache cap below.
        if self.cloud_authoritative:
            self.memory.enforce_hot_cache_cap()
        return response

    def _cloud_write(self, label: str, action) -> None:
        if os.getenv("JIMS_SYNC_CLOUD_WRITES", "true").lower() in {"1", "true", "yes", "on"}:
            action()
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def _write() -> None:
            try:
                await asyncio.to_thread(action)
            except Exception:
                logger.debug("Background cloud write failed: %s", label, exc_info=True)

        loop.create_task(_write())

    def queue_training_ingest(self, request: TrainingIngestRequest) -> dict[str, Any]:
        now = utc_now()
        job_id = stable_id(
            "ingest_job",
            f"{request.user_id}:{request.workspace_id}:{now.isoformat()}:{request.content[:512]}",
        )
        job = {
            "job_id": job_id,
            "accepted": True,
            "status": "queued",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "workspace_id": request.workspace_id,
            "user_id": request.user_id,
            "modality": request.modality.value,
            "content_bytes": len(request.content.encode("utf-8")),
        }
        self.training_ingest_jobs[job_id] = job
        self.event_store.append(
            "training_ingest_queued",
            job_id,
            {k: v for k, v in job.items() if k != "user_id"},
            user_id=request.user_id,
        )
        return job

    async def process_training_ingest_job(self, job_id: str, request: TrainingIngestRequest) -> None:
        job = self.training_ingest_jobs.setdefault(job_id, {"job_id": job_id})
        job.update({"status": "running", "updated_at": utc_now().isoformat()})
        try:
            response = await self.ingest_training(request)
        except CriticalServiceUnavailable as exc:
            job.update(
                {
                    "status": "failed",
                    "error_type": "critical_service_unavailable",
                    "detail": str(exc),
                    "updated_at": utc_now().isoformat(),
                }
            )
            self.event_store.append(
                "training_ingest_failed",
                job_id,
                {"error_type": "critical_service_unavailable", "detail": str(exc)},
                user_id=request.user_id,
            )
            return
        except Exception as exc:
            job.update(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "detail": str(exc),
                    "updated_at": utc_now().isoformat(),
                }
            )
            self.event_store.append(
                "training_ingest_failed",
                job_id,
                {"error_type": type(exc).__name__, "detail": str(exc)},
                user_id=request.user_id,
            )
            return

        job.update(
            {
                "status": "completed",
                "signature_id": response.signature.id,
                "world_model_candidates": len(response.world_model_candidates),
                "accepted_training_pair": bool(response.sppe_training_pair.accepted),
                "updated_at": utc_now().isoformat(),
            }
        )
        self.event_store.append(
            "training_ingest_completed",
            job_id,
            {
                "signature_id": response.signature.id,
                "world_model_candidates": len(response.world_model_candidates),
            },
            user_id=request.user_id,
        )

    def training_ingest_job(self, job_id: str) -> dict[str, Any] | None:
        return self.training_ingest_jobs.get(job_id)

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

        cardinality = self._relation_cardinality_overlay(overlay.get("relation_cardinality"))
        if cardinality:
            relation_predicates = {relation.predicate for relation in signature.structured.relations}
            existing_cardinality = signature.metadata.get("relation_cardinality")
            if not isinstance(existing_cardinality, dict):
                existing_cardinality = {}
            for predicate, value in cardinality.items():
                if predicate != "*" and predicate not in relation_predicates:
                    continue
                if existing_cardinality.get(predicate) == value:
                    continue
                existing_cardinality[predicate] = value
                changed = True
            if existing_cardinality:
                signature.metadata["relation_cardinality"] = existing_cardinality

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
                "model": getattr(self.bridge, "local_render_model", "qwen3-4b-instruct"),
                "confidence": overlay_confidence,
                "vectors_are_truth": False,
                "truth_policy": "symbolic_memory_requires_provenance_and_review",
            }
        return changed

    def _list_of_dicts(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _relation_cardinality_overlay(self, value: Any) -> dict[str, str]:
        return relation_cardinality_overlay(value)

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
            if self.cloud_authoritative:
                removed_panel_items = self.production.delete_panel_items_for_signature(request.signature_id)
                self.production.delete_signature(request.signature_id)
                invalidated = self.result_cache.clear()
                self.event_store.append(
                    "memory_signature_deleted",
                    request.signature_id,
                    {
                        "reason": request.reason,
                        "removed_graph_edges": 0,
                        "removed_panel_items": removed_panel_items,
                        "cache_invalidated": invalidated,
                        "cloud_authoritative": True,
                    },
                    user_id=request.user_id,
                )
                return MemoryMutationResponse(
                    accepted=True,
                    action="delete",
                    signature_id=request.signature_id,
                    memory_stats=self.memory.stats(),
                    detail="signature delete requested against persistent production stores",
                )
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

    async def rollback_memory(self, request: MemoryRollbackRequest) -> MemoryRollbackResponse:
        from datetime import datetime, timezone, timedelta
        
        time_window = timedelta(hours=request.time_window_hours)
        cutoff_time = datetime.now(timezone.utc) - time_window
        
        matching_signatures = []
        for sig in self.memory.all_signatures():
            created_at = sig.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
                
            if created_at >= cutoff_time:
                if request.workspace_id and sig.workspace_id != request.workspace_id:
                    continue
                if request.batch_id and sig.metadata.get("batch_id") != request.batch_id:
                    continue
                matching_signatures.append(sig)
                
        if self.cloud_authoritative or not matching_signatures:
            prod_sigs = self.production.load_recent_signatures(limit=1000)
            for sig in prod_sigs:
                created_at = sig.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at >= cutoff_time:
                    if request.workspace_id and sig.workspace_id != request.workspace_id:
                        continue
                    if request.batch_id and sig.metadata.get("batch_id") != request.batch_id:
                        continue
                    if not any(m.id == sig.id for m in matching_signatures):
                        matching_signatures.append(sig)
                        
        deleted_count = 0
        for sig in matching_signatures:
            self.memory.delete(sig.id)
            self.graph.remove_signature(sig.id)
            self.production.delete_signature(sig.id)
            self.production.delete_panel_items_for_signature(sig.id)
            self.world_model_candidates = [c for c in self.world_model_candidates if c.provenance != sig.id]
            self.training_history = [item for item in self.training_history if item.signature.id != sig.id]
            deleted_count += 1
            
        if deleted_count > 0:
            self.result_cache.clear()
            self.event_store.append(
                "memory_rollback_executed",
                f"rollback_{datetime.now(timezone.utc).timestamp()}",
                {
                    "time_window_hours": request.time_window_hours,
                    "deleted_count": deleted_count,
                    "workspace_id": request.workspace_id,
                    "batch_id": request.batch_id,
                },
                user_id=request.user_id,
            )
            
        return MemoryRollbackResponse(
            accepted=True,
            deleted_count=deleted_count,
            time_window_hours=request.time_window_hours,
            workspace_id=request.workspace_id,
            batch_id=request.batch_id,
            detail=f"Rollback completed successfully. Deleted {deleted_count} signatures within the last {request.time_window_hours} hours."
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
            "kaggle_runs": len(self.training_runs),
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

    async def schedule_modal_training(self, request: KaggleTrainingRequest) -> KaggleTrainingResponse:
        saga_id = stable_id("saga", f"training:{request.user_id}:{request.task_type}:{len(self.training_runs)}")
        self.event_store.append("saga_started", saga_id, {"kind": "training", "request": request.model_dump(mode="json")}, user_id=request.user_id)
        training_history = self._training_history_for_modal(request.workspace_id)
        world_model_candidates = self._world_model_candidates_for_modal(request.workspace_id)
        response = self.training_orchestrator.submit_training_run(
            request,
            training_history=training_history,
            world_model_candidates=world_model_candidates,
        )
        self.training_runs.append(response)
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
        self.production.save_panel_items([self._training_run_item(response)])
        return response

    def _training_history_for_modal(self, workspace_id: str | None) -> list[TrainingIngestResponse]:
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

    def _world_model_candidates_for_modal(self, workspace_id: str | None) -> list[WorldModelCandidate]:
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

    async def sync_modal_training(self, run_id: str) -> KaggleTrainingResponse | None:
        for index, run in enumerate(self.training_runs):
            if run.run_id != run_id:
                continue
            synced = self.training_orchestrator.sync_outputs(run)
            self.training_runs[index] = synced
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
            self.production.save_panel_items([self._training_run_item(synced)])
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
            items.extend(self._training_run_item(run) for run in self.training_runs)
        elif panel == "feedback":
            provider_item = TrainingPanelItem(
                id="feedback:provider-readiness",
                panel="feedback",
                kind="provider_readiness",
                title="Production provider readiness",
                subtitle="supabase_rest",
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

    def _training_run_item(self, run: KaggleTrainingResponse) -> TrainingPanelItem:
        return TrainingPanelItem(
            id=f"sessions:{run.run_id}",
            panel="sessions",
            kind="modal_training_run",
            title=f"{run.task_type} / {run.status}",
            subtitle=run.local_path or run.run_id,
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
