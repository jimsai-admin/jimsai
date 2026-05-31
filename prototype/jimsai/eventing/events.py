"""
Domain Event Definitions for JimsAI

These represent facts about what happened in the system.
Immutable, append-only, typed for audit trail.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4
import json


@dataclass
class DomainEvent:
    """Base class for all domain events"""
    
    aggregate_id: Union[str, UUID]
    aggregate_type: str
    version: int = 1
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict:
        """Serialize to JSON-compatible dict"""
        data = asdict(self)
        # Convert datetime and UUID to strings
        for key, val in data.items():
            if isinstance(val, (datetime, UUID)):
                data[key] = str(val)
        return data
    
    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(self.to_dict(), default=str)


# ============================================================================
# Query Lifecycle Events
# ============================================================================

@dataclass
class UserQueryReceived(DomainEvent):
    """User submitted a query"""
    workspace_id: Union[str, UUID] = None
    user_id: Union[str, UUID] = None
    query: str = None
    conversation_id: Optional[Union[str, UUID]] = None
    
    def __post_init__(self):
        self.aggregate_type = "query"
        super().__post_init__()


@dataclass
class QueryRooted(DomainEvent):
    """Query processed into Semantic IR"""
    query_id: Union[str, UUID] = None
    workspace_id: Union[str, UUID] = None
    semantic_ir: Dict[str, Any] = None
    entities: List[str] = None
    relations: List[Dict] = None
    intent_confidence: float = 0.0
    
    def __post_init__(self):
        self.aggregate_type = "query"
        super().__post_init__()


# ============================================================================
# Memory & Signature Events
# ============================================================================

@dataclass
class SemanticSignatureCreated(DomainEvent):
    """L1 encoder produced structured + latent signature"""
    signature_id: Union[str, UUID] = None
    workspace_id: Union[str, UUID] = None
    structured_ir: Dict[str, Any] = None
    vector: Optional[List[float]] = None
    entities: List[str] = None
    relations: List[Dict] = None
    causal_links: List[Dict] = None
    confidence: float = 0.0
    source_query: str = None
    
    def __post_init__(self):
        self.aggregate_type = "memory_signature"
        super().__post_init__()


@dataclass
class MemoryIngested(DomainEvent):
    """Memory signature persisted to cloud storage"""
    signature_id: Union[str, UUID] = None
    workspace_id: Union[str, UUID] = None
    supabase_id: Optional[Union[str, UUID]] = None
    vectorize_id: Optional[str] = None
    neo4j_nodes: Optional[List[str]] = None
    r2_key: Optional[str] = None
    freshness_epoch: int = 0
    
    def __post_init__(self):
        self.aggregate_type = "memory_signature"
        super().__post_init__()


@dataclass
class SignatureVectorized(DomainEvent):
    """Embedding generated for signature"""
    signature_id: Union[str, UUID] = None
    workspace_id: Union[str, UUID] = None
    vector_id: str = None
    vector_dim: int = 0
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    def __post_init__(self):
        self.aggregate_type = "memory_signature"
        super().__post_init__()


@dataclass
class SignatureInvalidated(DomainEvent):
    """Signature cached/invalidated after correction"""
    signature_id: Union[str, UUID] = None
    workspace_id: Union[str, UUID] = None
    reason: str = None
    cascaded_invalidations: List[Union[str, UUID]] = None
    
    def __post_init__(self):
        self.aggregate_type = "memory_signature"
        super().__post_init__()


# ============================================================================
# Provenance & Verification Events
# ============================================================================

@dataclass
class ProvenanceRecorded(DomainEvent):
    """Execution result with provenance"""
    query_id: Union[str, UUID] = None
    capability_type: str = None  # "web_search", "code_execution", "math_solve"
    input_hash: str = None
    provider: str = None  # "duckduckgo", "docker", "z3"
    output_hash: str = None
    verification_status: str = None  # "verified", "cached", "unverified"
    execution_time_ms: float = 0.0
    cost: float = 0.0
    
    def __post_init__(self):
        self.aggregate_type = "provenance"
        super().__post_init__()


@dataclass
class ExecutionCached(DomainEvent):
    """Result retrieved from cache"""
    query_hash: str = None
    cache_key: str = None
    cache_age_seconds: int = 0
    hit_rate: float = 0.0
    
    def __post_init__(self):
        self.aggregate_type = "cache"
        super().__post_init__()


@dataclass
class CacheInvalidated(DomainEvent):
    """Cache entries invalidated"""
    workspace_id: Union[str, UUID] = None
    cache_keys: List[str] = None
    scope: str = None  # "memory_signature", "query_result", "global"
    reason: str = None  # "correction", "model_update", "time_expiry"
    affected_queries: int = 0
    
    def __post_init__(self):
        self.aggregate_type = "cache"
        super().__post_init__()


# ============================================================================
# Human Review Events
# ============================================================================

@dataclass
class HumanReviewRequested(DomainEvent):
    """Item queued for human review"""
    review_id: Union[str, UUID] = None
    workspace_id: Union[str, UUID] = None
    item_type: str = None  # "memory", "correction", "training", "approval"
    item_id: Union[str, UUID] = None
    item_content: Dict[str, Any] = None
    priority: int = 0  # 1-10
    reason: str = None
    auto_assigned_to: Optional[Union[str, UUID]] = None
    
    def __post_init__(self):
        self.aggregate_type = "review_item"
        super().__post_init__()


@dataclass
class HumanReviewCompleted(DomainEvent):
    """Human review decision submitted"""
    review_id: Union[str, UUID] = None
    workspace_id: Union[str, UUID] = None
    reviewer_id: Union[str, UUID] = None
    decision: str = None  # "approve", "reject", "correct"
    correction: Optional[Dict[str, Any]] = None
    feedback: str = None
    confidence: float = 0.0
    
    def __post_init__(self):
        self.aggregate_type = "review_item"
        super().__post_init__()


# ============================================================================
# Training Pipeline Events
# ============================================================================

@dataclass
class SPPEPairGenerated(DomainEvent):
    """Structured Preference Pair Example created"""
    pair_id: Union[str, UUID] = None
    workspace_id: Union[str, UUID] = None
    semantic_ir_hash: str = None
    output_hash: str = None
    quality_score: float = 0.0  # 0-1
    signal_efficiency: float = 0.0
    provenance: Dict[str, Any] = None
    batch_id: Optional[Union[str, UUID]] = None
    
    def __post_init__(self):
        self.aggregate_type = "training_pair"
        super().__post_init__()


@dataclass
class TrainingTriggered(DomainEvent):
    """Training job initiated"""
    job_id: Union[str, UUID] = None
    workspace_id: Union[str, UUID] = None
    batch_id: Union[str, UUID] = None
    pair_count: int = 0
    quality_avg: float = 0.0
    trigger_reason: List[str] = None  # ["pair_count_reached", "quality_threshold_met"]
    artifacts_to_train: List[str] = None  # ["encoder", "reranker", "world_model"]
    validation_holdout_ratio: float = 0.2
    status: str = "awaiting_approval"
    
    def __post_init__(self):
        self.aggregate_type = "training_job"
        super().__post_init__()


@dataclass
class TrainingApproved(DomainEvent):
    """Training job approved by human"""
    job_id: Union[str, UUID] = None
    reviewer_id: Union[str, UUID] = None
    kaggle_run_id: Optional[str] = None
    status: str = "kaggle_queued"
    
    def __post_init__(self):
        self.aggregate_type = "training_job"
        super().__post_init__()


@dataclass
class TrainingCompleted(DomainEvent):
    """Kaggle training run finished"""
    job_id: Union[str, UUID] = None
    kaggle_run_id: str = None
    artifacts: Dict[str, str] = None  # artifact_type -> artifact_version
    training_duration_seconds: float = 0.0
    metrics: Dict[str, float] = None
    
    def __post_init__(self):
        self.aggregate_type = "training_job"
        super().__post_init__()


@dataclass
class ArtifactValidated(DomainEvent):
    """Artifact validation against held-out test set"""
    artifact_id: Union[str, UUID] = None
    artifact_type: str = None  # "encoder", "reranker", "world_model"
    validation_score: float = 0.0
    validation_passed: bool = False
    validation_metrics: Dict[str, float] = None
    
    def __post_init__(self):
        self.aggregate_type = "artifact"
        super().__post_init__()


@dataclass
class ArtifactActivationRequested(DomainEvent):
    """Artifact activation pending human approval"""
    artifact_id: Union[str, UUID] = None
    artifact_type: str = None
    validation_score: float = 0.0
    status: str = "awaiting_approval"
    
    def __post_init__(self):
        self.aggregate_type = "artifact"
        super().__post_init__()


@dataclass
class ModelActivated(DomainEvent):
    """Artifact hot-swapped into production"""
    artifact_id: Union[str, UUID] = None
    artifact_type: str = None
    validation_score: float = 0.0
    prev_artifact_id: Optional[Union[str, UUID]] = None
    rollback_metadata: Dict[str, Any] = None
    activated_at: datetime = None
    
    def __post_init__(self):
        if self.activated_at is None:
            self.activated_at = datetime.now()
        self.aggregate_type = "artifact"
        super().__post_init__()


@dataclass
class TrainingFailed(DomainEvent):
    """Training job failed"""
    job_id: Union[str, UUID] = None
    reason: str = None
    error_details: Dict[str, Any] = None
    status: str = "failed"
    
    def __post_init__(self):
        self.aggregate_type = "training_job"
        super().__post_init__()


# ============================================================================
# Generative Capability Events
# ============================================================================

@dataclass
class ImageGenerationRequested(DomainEvent):
    """Image generation initiated"""
    generation_id: Union[str, UUID] = None
    workspace_id: Union[str, UUID] = None
    prompt: str = None
    requires_approval: bool = False
    status: str = None
    
    def __post_init__(self):
        self.aggregate_type = "image_generation"
        super().__post_init__()


@dataclass
class ImageGenerated(DomainEvent):
    """Image successfully generated"""
    generation_id: Union[str, UUID] = None
    workspace_id: Union[str, UUID] = None
    image_url: str = None
    prompt: str = None
    model: str = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        self.aggregate_type = "image_generation"
        super().__post_init__()


@dataclass
class VideoGenerationRequested(DomainEvent):
    """Video generation requested (always requires approval)"""
    generation_id: Union[str, UUID] = None
    workspace_id: Union[str, UUID] = None
    prompt: str = None
    status: str = "awaiting_approval"
    
    def __post_init__(self):
        self.aggregate_type = "video_generation"
        super().__post_init__()


@dataclass
class VideoGenerationApproved(DomainEvent):
    """Video generation approved by human"""
    generation_id: Union[str, UUID] = None
    reviewer_id: Union[str, UUID] = None
    status: str = "processing"
    
    def __post_init__(self):
        self.aggregate_type = "video_generation"
        super().__post_init__()


@dataclass
class VideoGenerated(DomainEvent):
    """Video successfully generated"""
    generation_id: Union[str, UUID] = None
    video_url: str = None
    prompt: str = None
    approved_by: Union[str, UUID] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        self.aggregate_type = "video_generation"
        super().__post_init__()


# ============================================================================
# Creative Writing Events
# ============================================================================

@dataclass
class CreativeWritingRequested(DomainEvent):
    """Creative writing generation requested"""
    writing_id: Union[str, UUID] = None
    workspace_id: Union[str, UUID] = None
    prompt: str = None
    style: str = None  # "poetic", "technical", "conversational", "academic"
    used_deterministic: bool = False
    used_t2: bool = False
    
    def __post_init__(self):
        self.aggregate_type = "creative_writing"
        super().__post_init__()


@dataclass
class CreativeWritingGenerated(DomainEvent):
    """Creative writing output produced"""
    writing_id: Union[str, UUID] = None
    output: str = None
    style: str = None
    confidence: float = 0.0
    verification_status: str = None
    model_used: str = None
    
    def __post_init__(self):
        self.aggregate_type = "creative_writing"
        super().__post_init__()


# ============================================================================
# Governance & Quota Events
# ============================================================================

@dataclass
class ProviderUsageRecorded(DomainEvent):
    """Provider usage tracked for quota enforcement"""
    workspace_id: Union[str, UUID] = None
    provider: str = None  # "duckduckgo", "docker", "z3"
    action: str = None  # "search", "execute", "solve"
    cost: float = 0.0
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        self.aggregate_type = "provider_usage"
        super().__post_init__()


@dataclass
class QuotaExceeded(DomainEvent):
    """Provider quota exceeded"""
    workspace_id: Union[str, UUID] = None
    provider: str = None
    action: str = None
    usage: int = 0
    limit: int = 0
    
    def __post_init__(self):
        self.aggregate_type = "quota"
        super().__post_init__()


# ============================================================================
# Transformer Thinning Events
# ============================================================================

@dataclass
class T1SkipDecided(DomainEvent):
    """T1 (intent parser) skipped"""
    query_id: Union[str, UUID] = None
    reason: str = None  # "high_memory_confidence", "deterministic_query"
    memory_confidence: float = 0.0
    
    def __post_init__(self):
        self.aggregate_type = "optimization"
        super().__post_init__()


@dataclass
class T2SkipDecided(DomainEvent):
    """T2 (fluency renderer) skipped"""
    query_id: Union[str, UUID] = None
    reason: str = None  # "high_csse_confidence", "verified_output"
    output_confidence: float = 0.0
    
    def __post_init__(self):
        self.aggregate_type = "optimization"
        super().__post_init__()


# Event registry for deserialization
EVENT_REGISTRY = {
    "UserQueryReceived": UserQueryReceived,
    "QueryRooted": QueryRooted,
    "SemanticSignatureCreated": SemanticSignatureCreated,
    "MemoryIngested": MemoryIngested,
    "SignatureVectorized": SignatureVectorized,
    "SignatureInvalidated": SignatureInvalidated,
    "ProvenanceRecorded": ProvenanceRecorded,
    "ExecutionCached": ExecutionCached,
    "CacheInvalidated": CacheInvalidated,
    "HumanReviewRequested": HumanReviewRequested,
    "HumanReviewCompleted": HumanReviewCompleted,
    "SPPEPairGenerated": SPPEPairGenerated,
    "TrainingTriggered": TrainingTriggered,
    "TrainingApproved": TrainingApproved,
    "TrainingCompleted": TrainingCompleted,
    "ArtifactValidated": ArtifactValidated,
    "ArtifactActivationRequested": ArtifactActivationRequested,
    "ModelActivated": ModelActivated,
    "TrainingFailed": TrainingFailed,
    "ImageGenerationRequested": ImageGenerationRequested,
    "ImageGenerated": ImageGenerated,
    "VideoGenerationRequested": VideoGenerationRequested,
    "VideoGenerationApproved": VideoGenerationApproved,
    "VideoGenerated": VideoGenerated,
    "CreativeWritingRequested": CreativeWritingRequested,
    "CreativeWritingGenerated": CreativeWritingGenerated,
    "ProviderUsageRecorded": ProviderUsageRecorded,
    "QuotaExceeded": QuotaExceeded,
    "T1SkipDecided": T1SkipDecided,
    "T2SkipDecided": T2SkipDecided,
}
