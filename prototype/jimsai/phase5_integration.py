"""
Phase 5 EventStore Integration - Wires event sourcing into the pipeline

Provides initialization and integration patterns for connecting the event store,
SPPE generator, creative writing adapter, and other Phase 5 components to the
existing JimsAI pipeline.
"""

from __future__ import annotations

import logging
from typing import Optional, Callable, Any
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# Import Phase 5 components
try:
    from prototype.jimsai.eventing import (
        EventStore, 
        DomainEvent,
        UserQueryReceived,
        QueryRooted,
        ProvenanceRecorded,
        SPPEPairGenerated,
        CreativeWritingGenerated,
        T1SkipDecided,
        T2SkipDecided,
        ModelActivated,
        HumanReviewRequested,
        HumanReviewCompleted,
    )
    from prototype.jimsai.eventing.projections import (
        MemorySignatureProjection,
        SPPEPairProjection,
        ReviewQueueProjection,
        ProvenanceProjection,
    )
    from prototype.jimsai.training.sppe_generator import (
        SPPEPairGenerator,
        ExecutionTrace,
        SPPEBatchStore,
    )
except ImportError as e:
    logger.error(f"Failed to import Phase 5 components: {e}")
    raise


class EventStorePipeline:
    """
    Integrates event sourcing into the JimsAI pipeline.
    
    This wrapper enables:
    - Event emission for every query/decision
    - CQRS projections for metrics
    - SPPE pair generation from execution traces
    - Audit trail for compliance
    """
    
    def __init__(self, event_store: EventStore, workspace_id: str):
        self.event_store = event_store
        self.workspace_id = workspace_id
        self.sppe_generator = SPPEPairGenerator()
        # For MVP testing, create a mock batch store if needed
        try:
            self.batch_store = SPPEBatchStore(None)  # None works for MVP testing
        except TypeError:
            # If SPPEBatchStore requires db_session, create a minimal mock
            self.batch_store = type('MockBatchStore', (), {
                'add_pair': lambda self, pair, ws: None,
                'get_batch': lambda self, bid: None,
            })()
        
        # Register CQRS projections for fast queries
        self._register_projections()
        
        logger.info(f"EventStorePipeline initialized for workspace: {workspace_id}")
    
    def _register_projections(self) -> None:
        """Register CQRS projections to event store."""
        self.event_store.register_projection(MemorySignatureProjection())
        self.event_store.register_projection(SPPEPairProjection())
        self.event_store.register_projection(ReviewQueueProjection())
        self.event_store.register_projection(ProvenanceProjection())
        logger.info("✓ Registered 4 CQRS projections")
    
    async def emit_query_received(
        self,
        query_id: str,
        query: str,
        user_id: str,
        metadata: Optional[dict] = None
    ) -> None:
        """Emit UserQueryReceived event."""
        event = UserQueryReceived(
            aggregate_id=query_id,
            query=query,
            user_id=user_id,
            timestamp=datetime.utcnow(),
            workspace_id=self.workspace_id,
            metadata=metadata or {}
        )
        await self.event_store.append(event)
        logger.debug(f"Emitted UserQueryReceived for query: {query_id}")
    
    async def emit_query_rooted(
        self,
        query_id: str,
        route: str,
        confidence: float,
        reasoning: str
    ) -> None:
        """Emit QueryRooted event when route is determined."""
        event = QueryRooted(
            aggregate_id=query_id,
            route=route,
            confidence=confidence,
            reasoning=reasoning,
            timestamp=datetime.utcnow(),
            workspace_id=self.workspace_id,
        )
        await self.event_store.append(event)
        logger.debug(f"Emitted QueryRooted for query: {query_id} -> {route}")
    
    async def record_execution(
        self,
        query_id: str,
        provider: str,
        input_data: str,
        output_data: str,
        execution_time_ms: float,
        verification_status: str,
        sources: Optional[list] = None,
        gaps: Optional[list] = None,
        cache_hit: bool = False
    ) -> None:
        """Record execution results as ProvenanceRecorded event."""
        import hashlib
        
        input_hash = hashlib.sha256(input_data.encode()).hexdigest()[:8]
        output_hash = hashlib.sha256(output_data.encode()).hexdigest()[:8]
        
        event = ProvenanceRecorded(
            aggregate_id=query_id,
            provider=provider,
            input_hash=input_hash,
            output_hash=output_hash,
            verification_status=verification_status,
            execution_time_ms=execution_time_ms,
            sources=sources or [],
            gaps=gaps or [],
            cache_hit=cache_hit,
            timestamp=datetime.utcnow(),
            workspace_id=self.workspace_id,
        )
        await self.event_store.append(event)
        logger.debug(f"Recorded execution: {query_id} via {provider}")
    
    async def emit_t1_skip_decision(
        self,
        query_id: str,
        memory_confidence: float,
        reason: str
    ) -> None:
        """Emit T1SkipDecided when intent parser is skipped."""
        event = T1SkipDecided(
            aggregate_id=query_id,
            memory_confidence=memory_confidence,
            reason=reason,
            timestamp=datetime.utcnow(),
            workspace_id=self.workspace_id,
        )
        await self.event_store.append(event)
        logger.debug(f"Emitted T1SkipDecided for query: {query_id}")
    
    async def emit_t2_skip_decision(
        self,
        query_id: str,
        csse_confidence: float,
        reason: str
    ) -> None:
        """Emit T2SkipDecided when fluency renderer is skipped."""
        event = T2SkipDecided(
            aggregate_id=query_id,
            csse_confidence=csse_confidence,
            reason=reason,
            timestamp=datetime.utcnow(),
            workspace_id=self.workspace_id,
        )
        await self.event_store.append(event)
        logger.debug(f"Emitted T2SkipDecided for query: {query_id}")
    
    async def generate_sppe_pair(
        self,
        query_id: str,
        query: str,
        semantic_ir: dict,
        output: str,
        trace: ExecutionTrace
    ) -> None:
        """Generate SPPE training pair and emit event."""
        pair = self.sppe_generator.generate_pair(
            query=query,
            semantic_ir=semantic_ir,
            output=output,
            trace=trace
        )
        
        if pair:
            # Store pair in batch
            await self.batch_store.add_pair(pair, self.workspace_id)
            
            # Emit event
            event = SPPEPairGenerated(
                aggregate_id=query_id,
                pair_id=pair.pair_id,
                quality_score=pair.quality_score,
                signal_efficiency=pair.signal_efficiency,
                batch_id=pair.batch_id,
                timestamp=datetime.utcnow(),
                workspace_id=self.workspace_id,
            )
            await self.event_store.append(event)
            logger.info(f"Generated SPPE pair (quality={pair.quality_score:.2f}) for query: {query_id}")
    
    async def emit_creative_writing_generated(
        self,
        query_id: str,
        prompt: str,
        style: str,
        content: str,
        model_used: str,
        verification_status: str,
        execution_time_ms: float
    ) -> None:
        """Emit CreativeWritingGenerated event."""
        event = CreativeWritingGenerated(
            aggregate_id=query_id,
            prompt=prompt,
            style=style,
            content=content,
            model_used=model_used,
            verification_status=verification_status,
            execution_time_ms=execution_time_ms,
            timestamp=datetime.utcnow(),
            workspace_id=self.workspace_id,
        )
        await self.event_store.append(event)
        logger.debug(f"Emitted CreativeWritingGenerated for query: {query_id}")
    
    async def request_human_review(
        self,
        item_id: str,
        item_type: str,
        description: str,
        priority: int = 1
    ) -> str:
        """Request human review and return review_id."""
        import uuid
        review_id = str(uuid.uuid4())
        
        event = HumanReviewRequested(
            aggregate_id=review_id,
            item_id=item_id,
            item_type=item_type,
            description=description,
            priority=priority,
            timestamp=datetime.utcnow(),
            workspace_id=self.workspace_id,
        )
        await self.event_store.append(event)
        logger.info(f"Requested human review: {review_id} for {item_type}/{item_id}")
        
        return review_id
    
    async def complete_human_review(
        self,
        review_id: str,
        decision: str,
        feedback: str,
        reviewer_id: Optional[str] = None
    ) -> None:
        """Complete a human review."""
        event = HumanReviewCompleted(
            aggregate_id=review_id,
            decision=decision,
            feedback=feedback,
            reviewer_id=reviewer_id or "system",
            timestamp=datetime.utcnow(),
            workspace_id=self.workspace_id,
        )
        await self.event_store.append(event)
        logger.info(f"Completed review: {review_id} -> {decision}")
    
    async def get_metrics(self) -> dict:
        """Get current system metrics from projections."""
        stats = await self.event_store.get_event_statistics()
        return {
            "total_events": stats.get("total_events", 0),
            "events_by_type": stats.get("events_by_type", {}),
            "t1_skip_rate": stats.get("t1_skip_rate", 0.0),
            "t2_skip_rate": stats.get("t2_skip_rate", 0.0),
            "avg_query_latency_ms": stats.get("avg_query_latency_ms", 0.0),
            "total_cost": stats.get("total_cost", 0.0),
            "timestamp": datetime.utcnow().isoformat(),
        }


# Global event store pipeline instance
_event_store_pipeline: Optional[EventStorePipeline] = None


async def initialize_phase5(
    event_store: EventStore,
    workspace_id: str = "default"
) -> EventStorePipeline:
    """Initialize Phase 5 event sourcing in the pipeline."""
    global _event_store_pipeline
    _event_store_pipeline = EventStorePipeline(event_store, workspace_id)
    return _event_store_pipeline


def get_event_store_pipeline() -> EventStorePipeline:
    """Get the current event store pipeline instance."""
    if _event_store_pipeline is None:
        raise RuntimeError("EventStorePipeline not initialized. Call initialize_phase5() first.")
    return _event_store_pipeline


async def create_execution_trace(
    query_id: str,
    query: str,
    semantic_confidence: float,
    semantic_ir: dict,
    verification_status: str,
    sources: list,
    hallucination_gaps: list,
    route_type: str,
    used_t1: bool,
    used_t2: bool,
    memory_confidence: float,
    output_confidence: float,
    execution_time_ms: float,
    provider: str,
    cost: float
) -> ExecutionTrace:
    """Create an ExecutionTrace for SPPE pair generation."""
    return ExecutionTrace(
        query_id=query_id,
        query=query,
        semantic_confidence=semantic_confidence,
        semantic_ir=semantic_ir,
        verification_status=verification_status,
        sources=sources,
        hallucination_gaps=hallucination_gaps,
        route_type=route_type,
        used_t1=used_t1,
        used_t2=used_t2,
        memory_confidence=memory_confidence,
        output_confidence=output_confidence,
        execution_time_ms=execution_time_ms,
        provider=provider,
        cost=cost,
    )
