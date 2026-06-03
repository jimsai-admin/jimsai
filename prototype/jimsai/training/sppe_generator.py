"""
SPPE (Structured Preference Pair Example) Pipeline

Generates training pairs from user queries, semantic IR, and outputs.
Scores pairs by quality and feeds to training orchestrator.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
import json
import hashlib

# Events are defined in the eventing module, not here.

logger = logging.getLogger(__name__)


@dataclass
class ExecutionTrace:
    """Complete trace of query execution"""
    query_id: UUID
    query: str
    semantic_confidence: float = 0.0
    semantic_ir: Dict[str, Any] = field(default_factory=dict)
    verification_status: str = "unverified"
    sources: List[str] = field(default_factory=list)
    hallucination_gaps: List[str] = field(default_factory=list)
    route_type: str = ""
    used_t1: bool = True
    used_t2: bool = True
    memory_confidence: float = 0.0
    output_confidence: float = 0.0
    execution_time_ms: float = 0.0
    provider: str = ""
    cost: float = 0.0


@dataclass
class SPPEPair:
    """A training example with semantic IR, preference signal, and output"""
    pair_id: UUID = field(default_factory=uuid4)
    semantic_ir: Dict[str, Any] = field(default_factory=dict)
    semantic_ir_hash: str = ""
    preference: float = 0.0  # Quality signal
    output: str = ""
    output_hash: str = ""
    quality_score: float = 0.0  # 0-1 composite score
    signal_efficiency: float = 0.0  # How informative this pair is
    provenance: Dict[str, Any] = field(default_factory=dict)
    batch_id: Optional[UUID] = None
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict"""
        return {
            "pair_id": str(self.pair_id),
            "semantic_ir_hash": self.semantic_ir_hash,
            "preference": self.preference,
            "output_hash": self.output_hash,
            "quality_score": self.quality_score,
            "signal_efficiency": self.signal_efficiency,
            "provenance": self.provenance,
            "batch_id": str(self.batch_id) if self.batch_id else None,
            "created_at": self.created_at.isoformat(),
        }


class SPPEPairGenerator:
    """Generate Structured Preference Pair Examples from query execution"""
    
    def __init__(self, event_store=None):
        self.event_store = event_store
    
    async def generate_pair(
        self,
        query: str,
        semantic_ir: Dict[str, Any],
        output: str,
        trace: ExecutionTrace
    ) -> SPPEPair:
        """
        Create SPPE pair from query execution
        
        Args:
            query: Original user query
            semantic_ir: L1 structured representation
            output: Final verified output
            trace: Complete execution trace
            
        Returns:
            SPPE pair ready for training
        """
        
        # Compute hashes
        semantic_ir_hash = self._hash_dict(semantic_ir)
        output_hash = self._hash_string(output)
        
        # Extract preference signal
        preference = self._extract_preference_signal(trace)
        
        # Score pair quality
        quality_score = self._score_pair(trace)
        
        # Calculate signal efficiency
        signal_efficiency = self._calculate_signal_efficiency(trace, quality_score)
        
        # Build provenance
        provenance = {
            "query": query,
            "query_id": str(trace.query_id),
            "route_type": trace.route_type,
            "provider": trace.provider,
            "verification_status": trace.verification_status,
            "execution_time_ms": trace.execution_time_ms,
            "cost": trace.cost,
            "timestamp": datetime.now().isoformat(),
            "model_version": "v9_phase5",
        }
        
        pair = SPPEPair(
            semantic_ir=semantic_ir,
            semantic_ir_hash=semantic_ir_hash,
            preference=preference,
            output=output,
            output_hash=output_hash,
            quality_score=quality_score,
            signal_efficiency=signal_efficiency,
            provenance=provenance,
        )
        
        logger.info(f"Generated SPPE pair (quality={quality_score:.3f}, "
                   f"efficiency={signal_efficiency:.3f})")
        
        return pair
    
    def _extract_preference_signal(self, trace: ExecutionTrace) -> float:
        """
        Extract how "correct" this output is
        
        Returns:
            0.0 (wrong) to 1.0 (perfect)
        """
        
        signal = 0.5  # Start neutral
        
        # Increase for verified outputs
        if trace.verification_status == "verified":
            signal += 0.3
        elif trace.verification_status == "cached":
            signal += 0.2
        
        # Increase for sourced claims
        if trace.sources:
            signal += min(len(trace.sources) * 0.05, 0.15)
        
        # Decrease for gaps
        if trace.hallucination_gaps:
            signal -= min(len(trace.hallucination_gaps) * 0.05, 0.15)
        
        # Clamp to [0, 1]
        return max(0.0, min(1.0, signal))
    
    def _score_pair(self, trace: ExecutionTrace) -> float:
        """
        Score overall pair quality for training
        
        Factors:
        - Semantic clarity (how well understood the query)
        - Output verification (how confident we are in correctness)
        - Source grounding (factual claims have sources)
        - Hallucination risk (explicit gaps marked)
        - Efficiency (useful for training)
        
        Returns:
            0.0 to 1.0 quality score
        """
        
        weights = {
            "semantic_clarity": 0.25,
            "output_verification": 0.30,
            "source_grounding": 0.20,
            "gap_clarity": 0.15,
            "efficiency": 0.10,
        }
        
        scores = {
            "semantic_clarity": trace.semantic_confidence,
            "output_verification": 1.0 if trace.verification_status == "verified" else 0.5,
            "source_grounding": min(len(trace.sources) / 3, 1.0),
            "gap_clarity": 1.0 - min(len(trace.hallucination_gaps) * 0.1, 1.0),
            "efficiency": self._estimate_efficiency(trace),
        }
        
        quality = sum(scores[k] * weights[k] for k in weights.keys())
        
        logger.debug(f"Pair quality breakdown: {scores}")
        
        return quality
    
    def _calculate_signal_efficiency(
        self, 
        trace: ExecutionTrace, 
        quality_score: float
    ) -> float:
        """
        How informative is this pair for training?
        
        High-quality + diverse examples = high efficiency
        Low-quality or similar to past examples = low efficiency
        
        Returns:
            0.0 to 1.0 efficiency score
        """
        
        # Start with quality as base
        efficiency = quality_score
        
        # High execution cost = more informative (rare event)
        if trace.execution_time_ms > 1000:
            efficiency += 0.1
        elif trace.execution_time_ms > 5000:
            efficiency += 0.2
        
        # Complex queries = more informative
        semantic_ir_complexity = len(trace.semantic_ir.get("entities", [])) + \
                                 len(trace.semantic_ir.get("relations", []))
        if semantic_ir_complexity > 5:
            efficiency += 0.05
        
        # Novel providers = informative
        if trace.provider == "docker":
            efficiency += 0.05
        elif trace.provider == "z3":
            efficiency += 0.05
        
        # Clamp to [0, 1]
        return max(0.0, min(1.0, efficiency))
    
    def _estimate_efficiency(self, trace: ExecutionTrace) -> float:
        """Estimate how useful this example is for training"""
        # Verified outputs are useful for training
        if trace.verification_status == "verified":
            return 0.9
        elif trace.verification_status == "cached":
            return 0.6
        else:
            return 0.3
    
    @staticmethod
    def _hash_dict(d: Dict[str, Any]) -> str:
        """Hash dictionary for uniqueness"""
        json_str = json.dumps(d, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()[:16]
    
    @staticmethod
    def _hash_string(s: str) -> str:
        """Hash string for uniqueness"""
        return hashlib.sha256(s.encode()).hexdigest()[:16]


class SPPEBatchStore:
    """Store and manage SPPE pair batches"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    async def add_pair(
        self,
        pair: SPPEPair,
        workspace_id: UUID
    ) -> UUID:
        """Add pair to current batch"""
        
        # Get or create current batch for workspace
        batch_id = await self._get_or_create_batch(workspace_id)
        
        # Store pair
        await self.db.execute(
            """
            INSERT INTO sppe_pairs (
                pair_id, batch_id, workspace_id,
                semantic_ir_hash, output_hash,
                quality_score, signal_efficiency,
                provenance, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
            """,
            str(pair.pair_id),
            str(batch_id),
            str(workspace_id),
            pair.semantic_ir_hash,
            pair.output_hash,
            pair.quality_score,
            pair.signal_efficiency,
            json.dumps(pair.provenance),
        )
        
        await self.db.commit()
        
        return batch_id
    
    async def get_batch(self, batch_id: UUID) -> Dict[str, Any]:
        """Get batch with statistics"""
        
        result = await self.db.execute(
            """
            SELECT 
                batch_id,
                COUNT(*) as pair_count,
                AVG(quality_score) as quality_avg,
                AVG(signal_efficiency) as efficiency_avg,
                MIN(created_at) as created_at,
                EXTRACT(EPOCH FROM (NOW() - MIN(created_at))) as age_seconds,
                SUM(CASE WHEN quality_score > 0.8 THEN 1 ELSE 0 END) as high_quality_count
            FROM sppe_pairs
            WHERE batch_id = %s
            GROUP BY batch_id
            """,
            str(batch_id)
        )
        
        row = result.fetchone()
        
        if not row:
            return None
        
        return {
            "batch_id": str(row[0]),
            "pair_count": row[1],
            "quality_avg": float(row[2]),
            "efficiency_avg": float(row[3]),
            "created_at": row[4],
            "age_seconds": float(row[5]),
            "high_quality_count": row[6],
            "high_quality_ratio": row[6] / row[1] if row[1] > 0 else 0,
        }
    
    async def _get_or_create_batch(self, workspace_id: UUID) -> UUID:
        """Get current batch or create new one"""
        
        # Check for existing open batch
        result = await self.db.execute(
            """
            SELECT batch_id FROM sppe_batches
            WHERE workspace_id = %s AND status = 'open'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            str(workspace_id)
        )
        
        row = result.fetchone()
        if row:
            return UUID(row[0])
        
        # Create new batch
        batch_id = uuid4()
        await self.db.execute(
            """
            INSERT INTO sppe_batches (
                batch_id, workspace_id, status, created_at
            ) VALUES (%s, %s, 'open', NOW())
            """,
            str(batch_id),
            str(workspace_id)
        )
        
        await self.db.commit()
        
        return batch_id
    
    async def get_batches_for_workspace(
        self,
        workspace_id: UUID,
        status: str = "open"
    ) -> List[Dict[str, Any]]:
        """Get all batches for a workspace"""
        
        result = await self.db.execute(
            """
            SELECT batch_id, status, created_at, pair_count
            FROM sppe_batches
            WHERE workspace_id = %s AND status = %s
            ORDER BY created_at DESC
            """,
            str(workspace_id),
            status
        )
        
        batches = []
        for row in result.fetchall():
            batches.append({
                "batch_id": str(row[0]),
                "status": row[1],
                "created_at": row[2],
                "pair_count": row[3],
            })
        
        return batches
