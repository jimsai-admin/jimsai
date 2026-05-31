"""
CQRS Projections - Read-optimized views built from events

These maintain materialized views that answer common queries
without replaying the entire event stream.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List
from uuid import UUID

from .events import (
    SemanticSignatureCreated,
    MemoryIngested,
    SignatureInvalidated,
    SPPEPairGenerated,
    HumanReviewCompleted,
    ProvenanceRecorded,
    ExecutionCached,
)

logger = logging.getLogger(__name__)


class MemorySignatureProjection:
    """Materialized view of memory signatures"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    async def project(self, event):
        """Process event into projection"""
        
        if isinstance(event, SemanticSignatureCreated):
            await self._handle_signature_created(event)
        elif isinstance(event, SignatureInvalidated):
            await self._handle_signature_invalidated(event)
        elif isinstance(event, MemoryIngested):
            await self._handle_memory_ingested(event)
    
    async def _handle_signature_created(self, event):
        """Create signature record in read model"""
        
        await self.db.execute(
            """
            INSERT INTO memory_signature_projection (
                signature_id, workspace_id, structured_content,
                entities, relations, causal_links,
                confidence, source_query, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
            ON CONFLICT (signature_id) DO UPDATE SET
                structured_content = EXCLUDED.structured_content,
                confidence = EXCLUDED.confidence,
                updated_at = NOW()
            """,
            str(event.signature_id),
            str(event.workspace_id),
            str(event.structured_ir),
            str(event.entities),
            str(event.relations),
            str(event.causal_links),
            event.confidence,
            event.source_query,
        )
        
        await self.db.commit()
        logger.debug(f"Projected signature created: {event.signature_id}")
    
    async def _handle_memory_ingested(self, event):
        """Update signature with cloud storage references"""
        
        await self.db.execute(
            """
            UPDATE memory_signature_projection
            SET supabase_id = %s,
                vectorize_id = %s,
                r2_key = %s,
                freshness_epoch = %s,
                persisted_at = NOW()
            WHERE signature_id = %s
            """,
            event.supabase_id,
            event.vectorize_id,
            event.r2_key,
            event.freshness_epoch,
            str(event.signature_id),
        )
        
        await self.db.commit()
        logger.debug(f"Projected memory ingestion: {event.signature_id}")
    
    async def _handle_signature_invalidated(self, event):
        """Mark signature as invalid"""
        
        await self.db.execute(
            """
            UPDATE memory_signature_projection
            SET valid = FALSE,
                invalidation_reason = %s,
                invalidated_at = NOW()
            WHERE signature_id = %s
            """,
            event.reason,
            str(event.signature_id),
        )
        
        await self.db.commit()
        logger.debug(f"Projected signature invalidation: {event.signature_id}")


class SPPEPairProjection:
    """Materialized view of training pair quality"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    async def project(self, event):
        """Process event into projection"""
        
        if isinstance(event, SPPEPairGenerated):
            await self._handle_pair_generated(event)
    
    async def _handle_pair_generated(self, event):
        """Track pair for training batch"""
        
        await self.db.execute(
            """
            INSERT INTO sppe_pair_projection (
                pair_id, workspace_id, batch_id,
                quality_score, signal_efficiency,
                created_at
            ) VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            str(event.pair_id),
            str(event.workspace_id),
            str(event.batch_id) if event.batch_id else None,
            event.quality_score,
            event.signal_efficiency,
        )
        
        # Update batch statistics
        if event.batch_id:
            await self.db.execute(
                """
                INSERT INTO batch_statistics (
                    batch_id, pair_count, avg_quality, avg_efficiency,
                    high_quality_count, updated_at
                ) VALUES (
                    %s, 1, %s, %s,
                    CASE WHEN %s > 0.8 THEN 1 ELSE 0 END,
                    NOW()
                )
                ON CONFLICT (batch_id) DO UPDATE SET
                    pair_count = batch_statistics.pair_count + 1,
                    avg_quality = (
                        (batch_statistics.avg_quality * (batch_statistics.pair_count - 1) +
                         EXCLUDED.avg_quality) / batch_statistics.pair_count
                    ),
                    high_quality_count = batch_statistics.high_quality_count +
                        CASE WHEN %s > 0.8 THEN 1 ELSE 0 END,
                    updated_at = NOW()
                """,
                str(event.batch_id),
                event.quality_score,
                event.signal_efficiency,
                event.quality_score,
                event.quality_score,
            )
        
        await self.db.commit()
        logger.debug(f"Projected SPPE pair: {event.pair_id}")


class ReviewQueueProjection:
    """Materialized view of review queue"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    async def project(self, event):
        """Process event into projection"""
        
        if isinstance(event, HumanReviewCompleted):
            await self._handle_review_completed(event)
    
    async def _handle_review_completed(self, event):
        """Mark review as completed"""
        
        await self.db.execute(
            """
            UPDATE review_queue_projection
            SET status = 'completed',
                reviewer_id = %s,
                decision = %s,
                feedback = %s,
                completed_at = NOW()
            WHERE review_id = %s
            """,
            str(event.reviewer_id),
            event.decision,
            event.feedback,
            str(event.review_id),
        )
        
        await self.db.commit()
        logger.debug(f"Projected review completion: {event.review_id}")


class ProvenanceProjection:
    """Materialized view of execution provenance"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    async def project(self, event):
        """Process event into projection"""
        
        if isinstance(event, ProvenanceRecorded):
            await self._handle_provenance_recorded(event)
        elif isinstance(event, ExecutionCached):
            await self._handle_cache_hit(event)
    
    async def _handle_provenance_recorded(self, event):
        """Record execution provenance"""
        
        await self.db.execute(
            """
            INSERT INTO provenance_projection (
                query_id, capability_type, provider,
                input_hash, output_hash,
                verification_status,
                execution_time_ms, cost,
                created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
            """,
            str(event.query_id),
            event.capability_type,
            event.provider,
            event.input_hash,
            event.output_hash,
            event.verification_status,
            event.execution_time_ms,
            event.cost,
        )
        
        await self.db.commit()
        logger.debug(f"Projected provenance: {event.query_id}")
    
    async def _handle_cache_hit(self, event):
        """Track cache effectiveness"""
        
        await self.db.execute(
            """
            INSERT INTO cache_statistics (
                cache_key, hit_count, age_seconds,
                updated_at
            ) VALUES (
                %s, 1, %s, NOW()
            )
            ON CONFLICT (cache_key) DO UPDATE SET
                hit_count = cache_statistics.hit_count + 1,
                age_seconds = EXCLUDED.age_seconds,
                updated_at = NOW()
            """,
            event.cache_key,
            event.cache_age_seconds,
        )
        
        await self.db.commit()
        logger.debug(f"Projected cache hit: {event.cache_key}")


class QueryMetricsProjection:
    """Materialized view of query metrics for dashboard"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    async def get_workspace_metrics(self, workspace_id: UUID) -> Dict[str, Any]:
        """Get metrics for workspace dashboard"""
        
        result = await self.db.execute(
            """
            SELECT
                COUNT(*) as total_queries,
                COUNT(CASE WHEN used_t1 THEN 1 END) as t1_used,
                COUNT(CASE WHEN NOT used_t1 THEN 1 END) as t1_skipped,
                COUNT(CASE WHEN used_t2 THEN 1 END) as t2_used,
                COUNT(CASE WHEN NOT used_t2 THEN 1 END) as t2_skipped,
                AVG(memory_confidence) as avg_memory_confidence,
                AVG(output_confidence) as avg_output_confidence
            FROM query_metrics_projection
            WHERE workspace_id = %s
            """,
            str(workspace_id)
        )
        
        row = result.fetchone()
        
        if not row:
            return {
                "total_queries": 0,
                "t1_skip_rate": "0%",
                "t2_skip_rate": "0%",
                "transformer_thinning": "inactive",
            }
        
        total = row[0]
        t1_skipped = row[2]
        t2_skipped = row[4]
        
        return {
            "total_queries": total,
            "t1_used": row[1],
            "t1_skipped": t1_skipped,
            "t1_skip_rate": f"{100 * t1_skipped / total:.1f}%" if total > 0 else "0%",
            "t2_used": row[3],
            "t2_skipped": t2_skipped,
            "t2_skip_rate": f"{100 * t2_skipped / total:.1f}%" if total > 0 else "0%",
            "avg_memory_confidence": float(row[5]) if row[5] else 0.0,
            "avg_output_confidence": float(row[6]) if row[6] else 0.0,
            "transformer_thinning": "active" if t1_skipped > 0.5 * total else "emerging",
        }
    
    async def get_cache_metrics(self, workspace_id: UUID) -> Dict[str, Any]:
        """Get cache effectiveness metrics"""
        
        result = await self.db.execute(
            """
            SELECT
                COUNT(*) as total_cache_entries,
                SUM(hit_count) as total_hits,
                AVG(hit_count) as avg_hits_per_entry
            FROM cache_statistics_projection
            WHERE workspace_id = %s
            """,
            str(workspace_id)
        )
        
        row = result.fetchone()
        
        if not row or row[0] == 0:
            return {
                "total_cache_entries": 0,
                "cache_hit_rate": "0%",
                "total_hits": 0,
            }
        
        return {
            "total_cache_entries": row[0],
            "total_hits": row[1],
            "avg_hits_per_entry": float(row[2]) if row[2] else 0.0,
            "cache_hit_rate": f"{100 * row[1] / (row[1] + row[0]):.1f}%",
        }
