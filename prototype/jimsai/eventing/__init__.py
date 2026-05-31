"""
Event Sourcing & CQRS Infrastructure for JimsAI

Provides append-only event log, domain event definitions,
saga orchestration, and read model projections.
"""

from .events import (
    DomainEvent,
    UserQueryReceived,
    QueryRooted,
    SemanticSignatureCreated,
    MemoryIngested,
    SignatureVectorized,
    SignatureInvalidated,
    ProvenanceRecorded,
    ExecutionCached,
    CacheInvalidated,
    HumanReviewRequested,
    HumanReviewCompleted,
    SPPEPairGenerated,
    TrainingTriggered,
    TrainingApproved,
    TrainingCompleted,
    ModelActivated,
    T1SkipDecided,
    T2SkipDecided,
    CreativeWritingGenerated,
    ImageGenerated,
    VideoGenerated,
)

from .event_store import EventStore

from .projections import (
    MemorySignatureProjection,
    SPPEPairProjection,
    ReviewQueueProjection,
)

__all__ = [
    "DomainEvent",
    "UserQueryReceived",
    "QueryRooted",
    "SemanticSignatureCreated",
    "MemoryIngested",
    "SignatureVectorized",
    "SignatureInvalidated",
    "ProvenanceRecorded",
    "ExecutionCached",
    "CacheInvalidated",
    "HumanReviewRequested",
    "HumanReviewCompleted",
    "SPPEPairGenerated",
    "TrainingTriggered",
    "TrainingApproved",
    "TrainingCompleted",
    "ModelActivated",
    "T1SkipDecided",
    "T2SkipDecided",
    "CreativeWritingGenerated",
    "ImageGenerated",
    "VideoGenerated",
    "EventStore",
    "MemorySignatureProjection",
    "SPPEPairProjection",
    "ReviewQueueProjection",
]
