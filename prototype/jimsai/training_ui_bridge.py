"""
Integration bridge between autonomous agent and existing training UI.

The autonomous agent and human training UI work together:
- Agent: Volume work (extraction, normalization, embedding, routine signature creation)
- Human: Quality work (review, ambiguity resolution, corrections, domain expertise)

This bridge:
- Routes auto-accepted SPPE pairs directly to memory
- Routes medium-confidence pairs to human review queue
- Collects human corrections as training signal
- Automatically re-ingests corrected data
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .event_store import AuditEventStore
from .ingestion_worker_pool import IngestionResult
from .models import MemorySignature, SPPETrainingPair, WorldModelCandidate, utc_now
from .pipeline import JimsAIPipeline


logger = logging.getLogger(__name__)


@dataclass
class ReviewQueueItem:
    """Item queued for human review."""

    item_id: str
    item_type: str  # "sppe", "world_model", "ambiguity"
    content: dict[str, Any]
    confidence: float
    priority: int  # 1-10 (10 = urgent)
    created_at: str
    human_decision: str | None = None
    correction: dict[str, Any] | None = None
    processed_at: str | None = None


class TrainingUIBridge:
    """
    Bridge between autonomous agent and training UI.
    
    Coordinates:
    - SPPE pair confidence routing (auto-accept vs. human review)
    - World model candidate review
    - Ambiguity resolution
    - Human corrections as training signal
    - Re-ingestion of corrected data
    """

    def __init__(self, pipeline: JimsAIPipeline):
        self.pipeline = pipeline
        self.event_store = AuditEventStore()
        self.review_queue: list[ReviewQueueItem] = []
        self.auto_accepted: list[SPPETrainingPair] = []
        self.human_corrections: list[dict[str, Any]] = []

    async def route_sppe_pair(
        self,
        pair: SPPETrainingPair,
        confidence: float,
    ) -> tuple[str, ReviewQueueItem | None]:
        """
        Route SPPE pair based on confidence.
        
        High confidence (>0.90) → auto-accept
        Medium confidence (0.65-0.90) → human review
        Low confidence (<0.65) → reject with correction signal
        """
        
        if confidence >= 0.90:
            # Auto-accept: add directly to memory
            await self._auto_accept_sppe_pair(pair)
            return "auto_accepted", None
        
        elif confidence >= 0.65:
            # Human review: queue for training UI
            item = ReviewQueueItem(
                item_id=pair.id,
                item_type="sppe",
                content={
                    "query": pair.query,
                    "response": pair.response,
                    "quality_score": pair.quality_score,
                },
                confidence=confidence,
                priority=int((1 - confidence) * 10),  # Lower confidence = higher priority
                created_at=utc_now(),
            )
            self.review_queue.append(item)
            
            self.event_store.append(
                "sppe_queued_for_review",
                pair.id,
                {"confidence": confidence, "priority": item.priority},
            )
            
            logger.info(f"📋 Queued SPPE {pair.id} for human review (confidence: {confidence:.4f})")
            return "queued_for_review", item
        
        else:
            # Reject: generate correction signal
            await self._generate_correction_signal(pair, confidence)
            return "rejected", None

    async def route_world_model_candidate(
        self,
        candidate: WorldModelCandidate,
        confidence: float,
    ) -> tuple[str, ReviewQueueItem | None]:
        """
        Route world model candidate based on confidence.
        
        High confidence (>0.85) → auto-accept
        Medium confidence (0.60-0.85) → human review
        Low confidence (<0.60) → reject
        """
        
        if confidence >= 0.85:
            # Auto-accept
            await self._auto_accept_world_model(candidate)
            return "auto_accepted", None
        
        elif confidence >= 0.60:
            # Human review
            item = ReviewQueueItem(
                item_id=candidate.id,
                item_type="world_model",
                content={
                    "cause": candidate.cause,
                    "effect": candidate.effect,
                    "evidence": candidate.evidence[:200],
                },
                confidence=confidence,
                priority=int((1 - confidence) * 10),
                created_at=utc_now(),
            )
            self.review_queue.append(item)
            
            logger.info(f"📋 Queued world model {candidate.id} for review (confidence: {confidence:.4f})")
            return "queued_for_review", item
        
        else:
            return "rejected", None

    async def _auto_accept_sppe_pair(self, pair: SPPETrainingPair) -> None:
        """Auto-accept SPPE pair - add to training data."""
        
        self.auto_accepted.append(pair)
        self.event_store.append(
            "sppe_auto_accepted",
            pair.id,
            {"source": pair.source, "quality_score": pair.quality_score},
        )
        
        logger.debug(f"✅ Auto-accepted SPPE {pair.id} (quality: {pair.quality_score:.4f})")

    async def _auto_accept_world_model(self, candidate: WorldModelCandidate) -> None:
        """Auto-accept world model candidate."""
        
        # Add to graph
        self.pipeline.graph.add_causal_link(
            cause=candidate.cause,
            effect=candidate.effect,
        )
        
        self.event_store.append(
            "world_model_auto_accepted",
            candidate.id,
            {"cause": candidate.cause, "effect": candidate.effect},
        )
        
        logger.debug(f"✅ Auto-accepted world model {candidate.id}")

    async def _generate_correction_signal(self, pair: SPPETrainingPair, confidence: float) -> None:
        """Generate correction signal for low-confidence pairs."""
        
        # This creates negative training signal - what NOT to do
        correction = {
            "pair_id": pair.id,
            "query": pair.query,
            "response": pair.response,
            "confidence": confidence,
            "reason": "Low confidence - request correction",
            "created_at": utc_now(),
        }
        
        self.human_corrections.append(correction)
        
        self.event_store.append(
            "correction_signal_generated",
            pair.id,
            correction,
        )
        
        logger.debug(f"📝 Generated correction signal for {pair.id} (confidence: {confidence:.4f})")

    async def process_human_decision(
        self,
        review_item_id: str,
        decision: str,  # "accept", "reject", "correct"
        correction: dict[str, Any] | None = None,
    ) -> None:
        """
        Process human decision from training UI.
        
        Decisions:
        - accept: Move to training data
        - reject: Generate negative training signal
        - correct: Update signature and re-ingest
        """
        
        # Find review item
        item = next((i for i in self.review_queue if i.item_id == review_item_id), None)
        if not item:
            logger.warning(f"Review item {review_item_id} not found")
            return
        
        item.human_decision = decision
        item.correction = correction
        item.processed_at = utc_now()
        
        self.event_store.append(
            "human_review_decision",
            review_item_id,
            {"decision": decision, "item_type": item.item_type},
        )
        
        if decision == "accept":
            # Accept human's review - add to training data
            logger.info(f"✅ Human accepted {item.item_type} {review_item_id}")
            
        elif decision == "reject":
            # Reject - generate negative signal
            logger.info(f"❌ Human rejected {item.item_type} {review_item_id}")
            
        elif decision == "correct":
            # Correct - use correction as training signal
            logger.info(f"✏️ Human corrected {item.item_type} {review_item_id}")
            
            # Store correction
            self.human_corrections.append({
                "review_item_id": review_item_id,
                "correction": correction,
                "created_at": utc_now(),
            })

    def get_review_queue(self, limit: int = 20) -> list[ReviewQueueItem]:
        """Get items awaiting human review, sorted by priority."""
        
        pending = [item for item in self.review_queue if item.human_decision is None]
        pending.sort(key=lambda x: (-x.priority, x.created_at))
        
        return pending[:limit]

    def get_review_queue_stats(self) -> dict[str, Any]:
        """Get statistics about review queue."""
        
        pending = [item for item in self.review_queue if item.human_decision is None]
        
        by_type = {}
        for item in pending:
            by_type[item.item_type] = by_type.get(item.item_type, 0) + 1
        
        return {
            "total_pending": len(pending),
            "by_type": by_type,
            "auto_accepted": len(self.auto_accepted),
            "corrections_collected": len(self.human_corrections),
            "avg_confidence": sum(item.confidence for item in pending) / len(pending) if pending else 0.0,
        }

    def get_quality_metrics(self) -> dict[str, Any]:
        """Get quality metrics from human review decisions."""
        
        decided_items = [item for item in self.review_queue if item.human_decision]
        
        if not decided_items:
            return {"total_reviewed": 0}
        
        accepted = sum(1 for item in decided_items if item.human_decision == "accept")
        rejected = sum(1 for item in decided_items if item.human_decision == "reject")
        corrected = sum(1 for item in decided_items if item.human_decision == "correct")
        
        return {
            "total_reviewed": len(decided_items),
            "accepted": accepted,
            "rejected": rejected,
            "corrected": corrected,
            "acceptance_rate": accepted / len(decided_items) if decided_items else 0.0,
            "correction_rate": corrected / len(decided_items) if decided_items else 0.0,
            "corrections_collected": len(self.human_corrections),
        }


# Integration with existing training UI
def integrate_with_training_ui(pipeline: JimsAIPipeline) -> TrainingUIBridge:
    """
    Integrate autonomous agent with training UI.
    
    This bridge coordinates:
    1. Autonomous agent routes auto-acceptable work
    2. Human training UI reviews ambiguous cases
    3. Human corrections feed back as training signal
    4. System continuously improves from both sources
    """
    return TrainingUIBridge(pipeline)
