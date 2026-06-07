from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExecutionMode(str, Enum):
    DETERMINISTIC_CORE = "DETERMINISTIC_CORE"
    AIR_GAPPED_CONTAINER = "AIR_GAPPED_CONTAINER"
    TEMPLATE_RENDER = "TEMPLATE_RENDER"
    GROQ_BOUNDED_INTERFACE = "GROQ_BOUNDED_INTERFACE"


class Modality(str, Enum):
    TEXT = "text"
    CODE = "code"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DATA = "data"


class IntentDomain(str, Enum):
    WORKSPACE_OPERATION = "WORKSPACE_OPERATION"
    GENERAL_KNOWLEDGE = "GENERAL_KNOWLEDGE"
    EMOTIONAL_SOCIAL = "EMOTIONAL_SOCIAL"
    META_SYSTEM = "META_SYSTEM"
    UNKNOWN = "UNKNOWN"


class ProvenanceClass(str, Enum):
    SYMBOLIC_SOLVER = "SYMBOLIC_SOLVER"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    PLAUSIBLE_LEARNED = "PLAUSIBLE_LEARNED"
    UNVERIFIED_STALE = "UNVERIFIED_STALE"
    GAP_UNRESOLVED = "GAP_UNRESOLVED"
    UNKNOWN = "UNKNOWN"


class TraceEvent(BaseModel):
    stage: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class LayerResult(BaseModel):
    layer: str
    activated: bool
    deterministic: bool = True
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class Hypothesis(BaseModel):
    target_ir: str
    score: float
    role: Literal["primary", "overlay", "secondary", "candidate"] = "candidate"
    reason: str = ""


class SemanticIR(BaseModel):
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    target_ir: str
    system_action: str
    confidence: float
    scope_constraints: dict[str, Any] = Field(default_factory=dict)
    execution_mode: ExecutionMode = ExecutionMode.DETERMINISTIC_CORE
    domain_namespace: str = "TECHNICAL"
    intent_domain: IntentDomain = IntentDomain.WORKSPACE_OPERATION
    tokens: list[str] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    context_inherited: bool = False
    context_boosted: bool = False
    transformer_interface_used: bool = False


class Entity(BaseModel):
    id: str
    name: str
    type: str = "concept"


class Relation(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: float = 0.8


class CausalLink(BaseModel):
    cause: str
    effect: str
    confidence: float = 0.8


class TemporalInfo(BaseModel):
    tense: str = "present"
    timestamp: datetime = Field(default_factory=utc_now)


class SignatureIntent(BaseModel):
    type: str
    certainty: str = "confirmed"


class StructuredSignature(BaseModel):
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    causal_chain: list[CausalLink] = Field(default_factory=list)
    temporal: TemporalInfo = Field(default_factory=TemporalInfo)
    intent: SignatureIntent = Field(default_factory=lambda: SignatureIntent(type="unknown"))


class Confidence(BaseModel):
    score: float = 0.0
    source: str = "unknown"


class Importance(BaseModel):
    retrieval_count: int = 0
    current_score: float = 0.5


class MemorySignature(BaseModel):
    id: str
    provenance: str
    structured: StructuredSignature
    latent_embedding: list[float]
    abstraction_tags: list[str] = Field(default_factory=list)
    confidence: Confidence = Field(default_factory=Confidence)
    importance: Importance = Field(default_factory=Importance)
    modality: Modality = Modality.TEXT
    linked_signatures: list[str] = Field(default_factory=list)
    raw_excerpt: str = ""
    workspace_id: str | None = None
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class RetrievalResult(BaseModel):
    signature: MemorySignature
    score: float
    reasons: list[str] = Field(default_factory=list)


class ActivationDecision(BaseModel):
    route: Literal["retrieval", "canvas", "invention", "sandbox"]
    run_canvas: bool = False
    run_invention: bool = False
    run_retrieval: bool = True
    run_abstraction: bool = True
    run_world_model: bool = True
    reason: str = ""
    confidence: float = 0.0


class CapabilityKind(str, Enum):
    MEMORY_CHAT = "memory_chat"
    WORLD_KNOWLEDGE = "world_knowledge"
    CODING = "coding"
    MATH_SCIENCE = "math_science"
    CREATIVE_TEXT = "creative_text"
    IMAGE_GENERATION = "image_generation"
    AUDIO_GENERATION = "audio_generation"
    VIDEO_GENERATION = "video_generation"
    AGENTIC_TASK = "agentic_task"


class CapabilityPlan(BaseModel):
    kind: CapabilityKind = CapabilityKind.MEMORY_CHAT
    route: str = "memory_first"
    confidence: float = 0.0
    reason: str = ""
    secondary_intents: list[CapabilityKind] = Field(default_factory=list)
    routing_signals: dict[str, Any] = Field(default_factory=dict)
    requires_external_adapter: bool = False
    allowed_adapters: list[str] = Field(default_factory=list)
    verification_requirements: list[str] = Field(default_factory=list)
    energy_profile: Literal["low", "medium", "high"] = "low"
    context_strategy: Literal["persistent_memory", "bounded_retrieval", "tool_augmented", "generation_provider"] = "persistent_memory"
    human_approval_required: bool = False


class CapabilityExecutionResult(BaseModel):
    kind: CapabilityKind
    adapter: str
    status: Literal["not_required", "available", "unavailable", "blocked", "queued"]
    confidence: float = 0.0
    summary: str = ""
    provenance: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class CanvasResult(BaseModel):
    activated: bool
    session_id: str | None = None
    signatures_created: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    used_groq: bool = False


class InventionResult(BaseModel):
    activated: bool
    goal: str
    candidate_steps: list[str] = Field(default_factory=list)
    simulation_notes: list[str] = Field(default_factory=list)
    used_groq: bool = False
    mcts_traces: list[dict[str, Any]] = Field(default_factory=list)
    node_scores: dict[str, float] = Field(default_factory=dict)
    simulation_metrics: dict[str, Any] = Field(default_factory=dict)


class AbstractionResult(BaseModel):
    concepts: list[str] = Field(default_factory=list)
    analogies: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class WorldModelActivation(BaseModel):
    rule: str
    confidence: float
    source: str


class FeedbackRequest(BaseModel):
    user_id: str
    trace_id: str
    rating: Literal["positive", "negative", "correction"]
    notes: str = ""
    workspace_id: str | None = None
    thread_id: str | None = None
    source_signature_ids: list[str] = Field(default_factory=list)


class FeedbackResponse(BaseModel):
    accepted: bool
    trace_id: str
    stored_events: int


class VerifiedResultSignature(BaseModel):
    id: str
    kind: Literal["query", "sandbox", "math", "canvas", "invention", "review", "training"]
    status: Literal["verified", "failed", "queued", "blocked"]
    cache_key: str | None = None
    confidence: float = 0.0
    summary: str = ""
    provenance: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class CanvasRunRequest(BaseModel):
    user_id: str
    dataset_ref: str
    scope: str = "session_uploads"
    budget: float | None = None


class CanvasRunResponse(BaseModel):
    canvas_session_id: str
    status: Literal["queued", "running", "completed", "failed"]
    estimated_duration: str
    signatures_created: int = 0
    dataset_ref: str
    scope: str


class InventionRunRequest(BaseModel):
    user_id: str
    goal: str
    domain: str = "general"
    modules: list[str] = Field(default_factory=list)
    budget: float | None = None


class InventionRunResponse(BaseModel):
    invention_session_id: str
    status: Literal["queued", "running", "completed", "failed"]
    estimated_duration: str
    modules_activated: list[str] = Field(default_factory=list)
    goal: str
    domain: str


class ReviewActionRequest(BaseModel):
    user_id: str
    provenance: str
    rule: str
    action: Literal["accept", "correct", "reject", "promote", "rollback"]
    corrected_rule: str | None = None
    notes: str = ""


class ReviewActionResponse(BaseModel):
    accepted: bool
    action: str
    rule: str
    result_signature: VerifiedResultSignature


class SandboxRunRequest(BaseModel):
    user_id: str
    code: str
    language: Literal["python"] = "python"
    tests: str = ""
    timeout_ms: int = Field(default=1500, ge=100, le=5000)
    workspace_id: str | None = None


class SandboxRunResponse(BaseModel):
    status: Literal["passed", "failed", "timeout", "blocked", "cached"]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    cache_key: str
    result_signature: VerifiedResultSignature


class MathSolveRequest(BaseModel):
    user_id: str
    expression: str
    solve_for: str | None = None
    timeout_ms: int = Field(default=500, ge=50, le=3000)
    workspace_id: str | None = None


class MathSolveResponse(BaseModel):
    status: Literal["solved", "failed", "timeout", "cached"]
    result: str
    method: str
    cache_key: str
    result_signature: VerifiedResultSignature


class SimulationScope(BaseModel):
    entities: list[str] = Field(default_factory=list)
    depth: int = 3
    time_budget_ms: int = 200
    strategy: Literal["NEAREST_CAUSE", "CRITICAL_PATH", "FULL"] = "NEAREST_CAUSE"


class SimulationResult(BaseModel):
    scenario: str
    passed: bool
    confidence: float
    outcomes: list[str] = Field(default_factory=list)
    scope: SimulationScope = Field(default_factory=SimulationScope)


class ConstraintCheck(BaseModel):
    name: str
    passed: bool
    confidence: float
    detail: str


class PlanStep(BaseModel):
    order: int
    action: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected_output: str = ""


class ExecutionPlan(BaseModel):
    goal: str
    steps: list[PlanStep]
    deterministic: bool = True


class ReasoningStep(BaseModel):
    claim: str
    confidence: float
    sources: list[str] = Field(default_factory=list)
    relation: str = "ASSERT"
    source_signature_ids: list[str] = Field(default_factory=list)
    provenance_class: ProvenanceClass = ProvenanceClass.UNKNOWN


class VerifiedCognitiveObject(BaseModel):
    trace_id: str
    intent: str
    verified_plan: ExecutionPlan
    simulation_results: list[SimulationResult] = Field(default_factory=list)
    constraint_checks: list[ConstraintCheck] = Field(default_factory=list)
    semantic_graph: dict[str, Any] = Field(default_factory=dict)
    reasoning_chain: list[ReasoningStep] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    confidence_tier: int = 5
    style_signature: dict[str, Any] = Field(default_factory=lambda: {"tone": "technical", "format": "answer"})
    generation_mode: Literal["FACT", "CREATIVE", "HYBRID", "TEMPLATE"] = "FACT"
    activation: ActivationDecision | None = None
    canvas_result: CanvasResult | None = None
    invention_result: InventionResult | None = None
    abstraction_result: AbstractionResult | None = None
    world_model_activations: list[WorldModelActivation] = Field(default_factory=list)
    capability_plan: CapabilityPlan | None = None
    capability_results: list[CapabilityExecutionResult] = Field(default_factory=list)
    layer_results: list[LayerResult] = Field(default_factory=list)


class PipelineRequest(BaseModel):
    user_id: str
    query: str
    modality: Modality = Modality.TEXT
    workspace_id: str | None = None
    thread_id: str | None = None
    canvas_hint: bool = False
    invention_hint: bool = False
    return_trace: bool = True


class PipelineResponse(BaseModel):
    response: str
    ir: SemanticIR
    reasoning_chain: list[ReasoningStep]
    confidence: float
    gaps: list[str]
    sources: list[str]
    simulation_results: list[SimulationResult]
    trace: list[TraceEvent]
    layer_results: list[LayerResult] = Field(default_factory=list)
    activation: ActivationDecision | None = None
    canvas_result: CanvasResult | None = None
    invention_result: InventionResult | None = None
    abstraction_result: AbstractionResult | None = None
    world_model_activations: list[WorldModelActivation] = Field(default_factory=list)
    capability_plan: CapabilityPlan | None = None
    capability_results: list[CapabilityExecutionResult] = Field(default_factory=list)
    used_groq: bool = False
    suggestions: list[str] = Field(default_factory=list)


class TrainingIngestRequest(BaseModel):
    user_id: str
    content: str
    modality: Modality = Modality.TEXT
    source_trust: float = Field(default=0.8, ge=0.0, le=1.0)
    domain_hint: str | None = None
    workspace_id: str | None = None


class MemoryUpdateRequest(BaseModel):
    user_id: str
    signature_id: str
    corrected_content: str | None = None
    source_trust: float = Field(default=0.9, ge=0.0, le=1.0)
    domain_hint: str | None = None
    workspace_id: str | None = None
    notes: str = ""


class MemoryDeleteRequest(BaseModel):
    user_id: str
    signature_id: str
    workspace_id: str | None = None
    reason: str = ""


class MemoryRollbackRequest(BaseModel):
    user_id: str
    time_window_hours: int = 24
    workspace_id: str | None = None
    batch_id: str | None = None


class MemoryRollbackResponse(BaseModel):
    accepted: bool
    deleted_count: int
    time_window_hours: int
    workspace_id: str | None = None
    batch_id: str | None = None
    detail: str = ""


class MemoryMutationResponse(BaseModel):
    accepted: bool
    action: Literal["update", "delete"]
    signature_id: str
    replacement_signature: MemorySignature | None = None
    memory_stats: dict[str, int]
    detail: str = ""


class WorldModelCandidate(BaseModel):
    rule: str
    confidence: float
    provenance: str
    review_required: bool


class SPPETrainingPair(BaseModel):
    # Set 1 (Ingestion, Tests, Training UI Bridge)
    id: str | None = None
    semantic_ir: str | None = None
    query: str | None = None
    response: str | None = None
    quality_score: float | None = None
    source: str | None = None
    created_at: datetime | None = None

    # Set 2 (Pipeline)
    signature_id: str | None = None
    semantic_intention_graph: dict[str, Any] | None = None
    original_text: str | None = None
    confidence: float | None = None
    accepted: bool | None = None

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        # Populate Set 1 from Set 2 if missing
        if self.signature_id and not self.id:
            self.id = f"sppe-{self.signature_id}"
        if self.original_text and not self.query:
            self.query = self.original_text
        if self.original_text and not self.response:
            self.response = self.original_text
        if self.confidence is not None and self.quality_score is None:
            self.quality_score = self.confidence
        if not self.source:
            self.source = "pipeline"
        if not self.created_at:
            self.created_at = utc_now()
        if self.accepted is None:
            if self.confidence is not None:
                self.accepted = self.confidence >= 0.75
            elif self.quality_score is not None:
                self.accepted = self.quality_score >= 0.75
            else:
                self.accepted = False

        # Populate Set 2 from Set 1 if missing
        if self.id and not self.signature_id:
            self.signature_id = self.id
        if self.query and not self.original_text:
            self.original_text = self.query
        if self.quality_score is not None and self.confidence is None:
            self.confidence = self.quality_score
        if self.accepted is None and self.quality_score is not None:
            self.accepted = self.quality_score >= 0.75


class AutoTrainingDecision(BaseModel):
    enabled: bool = False
    should_schedule: bool = False
    task_type: Literal["encoder_finetune", "reranker_finetune", "world_model_extractor", "sppe_refiner", "sppe_renderer_finetune"] = "encoder_finetune"
    reason: str = ""
    counters: dict[str, int | float | bool] = Field(default_factory=dict)
    requires_human_approval: bool = True


class TrainingIngestResponse(BaseModel):
    signature: MemorySignature
    world_model_candidates: list[WorldModelCandidate]
    sppe_training_pair: SPPETrainingPair
    memory_stats: dict[str, int]
    trace: list[TraceEvent]
    auto_training_decision: AutoTrainingDecision | None = None


class TrainingDashboardResponse(BaseModel):
    memory_stats: dict[str, int]
    human_review_queue: list[WorldModelCandidate] = Field(default_factory=list)
    ambiguity_queue: list[dict[str, Any]] = Field(default_factory=list)
    recent_signatures: list[MemorySignature] = Field(default_factory=list)
    world_models: list[WorldModelCandidate] = Field(default_factory=list)
    pipeline_monitor: dict[str, Any] = Field(default_factory=dict)
    canvas_sessions: list[CanvasRunResponse] = Field(default_factory=list)
    invention_sessions: list[InventionRunResponse] = Field(default_factory=list)
    feedback_events: int = 0
    production_readiness: dict[str, Any] = Field(default_factory=dict)
    auto_training_decision: AutoTrainingDecision | None = None


class TrainingPanelItem(BaseModel):
    id: str
    panel: str
    kind: str
    title: str
    subtitle: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class TrainingPanelPage(BaseModel):
    panel: str
    items: list[TrainingPanelItem] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
    total: int = 0


class ModalTrainingRequest(BaseModel):
    user_id: str
    workspace_id: str | None = None
    task_type: Literal["encoder_finetune", "reranker_finetune", "world_model_extractor", "sppe_refiner", "sppe_renderer_finetune"] = "encoder_finetune"
    title: str = "JIMS-AI encoder fine-tune"
    notes: str = ""
    gpu: bool = True


# Backward-compat alias
KaggleTrainingRequest = ModalTrainingRequest


class ModalTrainingResponse(BaseModel):
    run_id: str
    status: Literal["prepared", "submitted", "running", "completed", "failed"]
    task_type: str
    kernel_ref: str | None = None
    local_path: str | None = None
    detail: str = ""
    submitted_at: datetime = Field(default_factory=utc_now)


# Backward-compat alias
KaggleTrainingResponse = ModalTrainingResponse


class ProviderStatus(BaseModel):
    name: str
    configured: bool
    available: bool
    detail: str
