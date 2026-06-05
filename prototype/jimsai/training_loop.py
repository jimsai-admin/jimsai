"""
Training Loop Integration: End-to-end SPPE generation, validation, and batch orchestration.

Provides:
- SPPE pair generation from queries + execution results
- Quality filtering (confidence thresholds, conflict detection)
- Training batch preparation for Kaggle
- Hot-swap mechanism with canary testing
- Retrieval quality measurement

This enables JimsAI's continuous learning advantage over frozen frontier models.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class PairQuality(Enum):
    """Quality assessment of SPPE pair."""
    EXCELLENT = 0.95  # High confidence, well-verified
    GOOD = 0.85       # Confident, system performed well
    ACCEPTABLE = 0.70 # Reasonable, minor issues
    MARGINAL = 0.50   # Low confidence, ambiguous
    REJECTED = 0.0    # Should not be used for training


@dataclass
class SPPEPair:
    """
    Structured Problem-Plan-Execution pair for training.
    
    S = Structured problem (intent, entities, context)
    P = Plan (routing decision, reasoning steps)
    E = Execution (actual output, verification result)
    """
    problem: dict  # {"query": str, "intent": str, "entities": list}
    plan: dict     # {"target_ir": str, "reasoning": list, "confidence": float}
    execution: dict # {"success": bool, "output": str, "verification": float}
    quality_score: float
    human_reviewed: bool = False
    workspace_id: Optional[str] = None
    created_at: str = None
    
    def __post_init__(self):
        """Initialize timestamps."""
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
    
    def compute_hash(self) -> str:
        """Compute pair hash for deduplication."""
        content = json.dumps(
            {
                "problem": self.problem,
                "plan": self.plan,
            },
            sort_keys=True
        )
        return hashlib.sha256(content.encode()).hexdigest()
    
    def to_training_format(self) -> dict:
        """Convert to training batch format."""
        return {
            "input": self.problem["query"],
            "intent": self.problem["intent"],
            "entities": self.problem.get("entities", []),
            "target_ir": self.plan["target_ir"],
            "output": self.execution["output"],
            "verification": self.execution["verification"],
            "quality": self.quality_score,
            "human_reviewed": self.human_reviewed,
        }


class SPPEGenerator:
    """Generate SPPE training pairs from query execution."""
    
    def __init__(self, workspace_id: str):
        """Initialize SPPE generator."""
        self.workspace_id = workspace_id
        self._pair_cache: dict[str, SPPEPair] = {}
    
    def generate(
        self,
        query: str,
        intent: str,
        entities: list,
        target_ir: str,
        plan_steps: list,
        plan_confidence: float,
        execution_output: str,
        execution_success: bool,
        verification_score: float,
    ) -> SPPEPair:
        """
        Generate SPPE pair from query execution.
        
        Args:
            query: Original user query
            intent: Classified intent
            entities: Extracted entities
            target_ir: Selected IR target
            plan_steps: Reasoning steps
            plan_confidence: Confidence in routing decision
            execution_output: Output from execution
            execution_success: Whether execution succeeded
            verification_score: How well output matches expectations
        
        Returns:
            SPPEPair ready for training
        """
        # Assess pair quality
        quality_score = self._assess_quality(
            plan_confidence,
            execution_success,
            verification_score,
        )
        
        pair = SPPEPair(
            problem={
                "query": query,
                "intent": intent,
                "entities": entities,
            },
            plan={
                "target_ir": target_ir,
                "reasoning": plan_steps,
                "confidence": plan_confidence,
            },
            execution={
                "success": execution_success,
                "output": execution_output,
                "verification": verification_score,
            },
            quality_score=quality_score,
            workspace_id=self.workspace_id,
        )
        
        # Cache for deduplication
        pair_hash = pair.compute_hash()
        if pair_hash in self._pair_cache:
            logger.info(f"SPPE pair already exists: {pair_hash[:8]}")
            return self._pair_cache[pair_hash]
        
        self._pair_cache[pair_hash] = pair
        
        logger.info(
            f"SPPE pair generated: {intent} (quality={quality_score:.2f})"
        )
        
        return pair
    
    def _assess_quality(
        self,
        plan_confidence: float,
        execution_success: bool,
        verification_score: float,
    ) -> float:
        """
        Assess quality of SPPE pair for training.
        
        Quality combines:
        - Plan confidence (was routing decision high-confidence?)
        - Execution success (did execution complete?)
        - Verification score (did output match expectations?)
        """
        score = plan_confidence * 0.4 + execution_success * 0.3 + verification_score * 0.3
        return score


class TrainingBatchBuilder:
    """Build training batches from SPPE pairs."""
    
    def __init__(self, workspace_id: str, min_batch_size: int = 50):
        """Initialize batch builder."""
        self.workspace_id = workspace_id
        self.min_batch_size = min_batch_size
        self._pending_pairs: list[SPPEPair] = []
    
    def add_pair(self, pair: SPPEPair) -> None:
        """Add SPPE pair to pending batch."""
        if pair.quality_score < 0.50:
            logger.info(f"Rejecting low-quality pair (quality={pair.quality_score:.2f})")
            return
        
        self._pending_pairs.append(pair)
    
    def is_batch_ready(self) -> bool:
        """Check if enough pairs accumulated for training."""
        return len(self._pending_pairs) >= self.min_batch_size
    
    def build_batch(self) -> dict:
        """
        Build training batch from accumulated pairs.
        
        Returns:
            {
                "batch_id": str,
                "workspace_id": str,
                "pairs": list[dict],
                "quality_distribution": dict,
                "size": int,
            }
        """
        batch_id = hashlib.sha256(
            f"{self.workspace_id}|{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]
        
        # Convert pairs to training format
        training_pairs = [
            pair.to_training_format()
            for pair in self._pending_pairs
        ]
        
        # Assess batch quality distribution
        quality_dist = {
            "excellent": sum(1 for p in self._pending_pairs if p.quality_score >= 0.95),
            "good": sum(1 for p in self._pending_pairs if 0.85 <= p.quality_score < 0.95),
            "acceptable": sum(1 for p in self._pending_pairs if 0.70 <= p.quality_score < 0.85),
            "marginal": sum(1 for p in self._pending_pairs if p.quality_score < 0.70),
        }
        
        batch = {
            "batch_id": batch_id,
            "workspace_id": self.workspace_id,
            "pairs": training_pairs,
            "quality_distribution": quality_dist,
            "size": len(training_pairs),
            "created_at": datetime.now().isoformat(),
        }
        
        # Clear pending pairs
        self._pending_pairs = []
        
        logger.info(f"Training batch built: {batch_id} ({batch['size']} pairs)")
        
        return batch


class KaggleTrainingOrchestrator:
    """Orchestrate training batch uploads to Kaggle."""
    
    def __init__(self, workspace_id: str, kaggle_dataset_owner: str):
        """
        Initialize Kaggle orchestration.
        
        Args:
            workspace_id: JimsAI workspace ID
            kaggle_dataset_owner: Kaggle username for dataset uploads
        """
        self.workspace_id = workspace_id
        self.kaggle_dataset_owner = kaggle_dataset_owner
    
    def upload_batch(self, batch: dict) -> dict:
        """
        Upload training batch to Kaggle as a private dataset.

        Requires:
          - KAGGLE_API_TOKEN env var
          - KAGGLE_DATASET_OWNER env var (or KAGGLE_USERNAME)

        Optional:
          - KAGGLE_KERNEL_SLUG env var to trigger a training notebook after upload
        """
        import os
        import json
        import tempfile
        from datetime import datetime as dt

        batch_id = batch["batch_id"]
        logger.info(f"Uploading training batch to KaggleHub: {batch_id}")

        # Validate credentials
        kaggle_token = os.getenv("KAGGLE_API_TOKEN", "").strip()
        dataset_owner = (
            os.getenv("KAGGLE_DATASET_OWNER", "").strip()
            or os.getenv("KAGGLE_USERNAME", "").strip()
            or self.kaggle_dataset_owner
        )

        if not kaggle_token:
            raise RuntimeError(
                "KAGGLE_API_TOKEN env var is required for KaggleTrainingOrchestrator.upload_batch(). "
                "Set it to your Kaggle API token from https://www.kaggle.com/settings"
            )
        if not dataset_owner:
            raise RuntimeError(
                "KAGGLE_DATASET_OWNER (or KAGGLE_USERNAME) env var is required. "
                "Set it to your Kaggle username."
            )

        # Import kagglehub
        try:
            import kagglehub
        except ImportError:
            raise RuntimeError(
                "kagglehub is not installed. Install it with: pip install kagglehub"
            )

        # Write batch to a temp directory and upload
        dataset_slug = f"jims-training-{batch_id}"
        with tempfile.TemporaryDirectory() as tmpdir:
            batch_file = os.path.join(tmpdir, "batch.json")
            with open(batch_file, "w", encoding="utf-8") as f:
                json.dump(batch, f, default=str)

            # Upload to Kaggle as private dataset
            try:
                kagglehub.dataset_upload(
                    handle=f"{dataset_owner}/{dataset_slug}",
                    local_dataset_dir=tmpdir,
                    license_name="proprietary",
                )
                logger.info(f"Uploaded batch {batch_id} to {dataset_owner}/{dataset_slug}")
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to upload batch {batch_id} to Kaggle: {exc}"
                ) from exc

        # Optionally trigger training notebook
        notebook_triggered = False
        kernel_slug = os.getenv("KAGGLE_KERNEL_SLUG", "").strip()
        if kernel_slug:
            try:
                import kaggle  # kaggle CLI package
                kaggle.api.authenticate()
                kaggle.api.kernels_push(kernel_slug)
                notebook_triggered = True
                logger.info(f"Triggered training notebook: {kernel_slug}")
            except Exception as exc:
                logger.warning(
                    f"Could not trigger training notebook {kernel_slug}: {exc}. "
                    "Set KAGGLE_KERNEL_SLUG to a valid kernel slug to enable this."
                )
        else:
            logger.warning(
                "KAGGLE_KERNEL_SLUG not set — training notebook will not be triggered. "
                "Set it to your Kaggle kernel slug to auto-trigger training after upload."
            )

        return {
            "batch_id": batch_id,
            "status": "uploaded",
            "kaggle_dataset": f"{dataset_owner}/{dataset_slug}",
            "uploaded_at": dt.now().isoformat(),
            "notebook_triggered": notebook_triggered,
        }


class CanaryTester:
    """Test new weights with canary traffic before full rollout."""
    
    def __init__(self, workspace_id: str, initial_traffic_percent: float = 0.05):
        """
        Initialize canary testing.
        
        Args:
            workspace_id: JimsAI workspace ID
            initial_traffic_percent: Initial traffic to send to new weights (5%)
        """
        self.workspace_id = workspace_id
        self.traffic_percent = initial_traffic_percent
        self._baseline_metrics: dict = {}
        self._canary_metrics: dict = {}
    
    def start_canary(self, new_weights_id: str) -> dict:
        """Start canary test with new weights."""
        logger.info(
            f"Starting canary test: {self.traffic_percent*100}% traffic → {new_weights_id}"
        )
        
        return {
            "canary_id": hashlib.sha256(new_weights_id.encode()).hexdigest()[:8],
            "new_weights": new_weights_id,
            "traffic_percent": self.traffic_percent,
            "status": "running",
            "started_at": datetime.now().isoformat(),
        }
    
    def record_baseline(self, metrics: dict) -> None:
        """Record baseline metrics from current weights."""
        self._baseline_metrics = metrics
    
    def record_canary(self, metrics: dict) -> None:
        """Record metrics from canary traffic."""
        self._canary_metrics = metrics
    
    def evaluate(self, improvement_threshold: float = 0.02) -> tuple[bool, float]:
        """
        Evaluate if canary performed better than baseline.
        
        Args:
            improvement_threshold: Minimum improvement required (2%)
        
        Returns:
            (should_rollout, improvement_percent)
        """
        if not self._baseline_metrics or not self._canary_metrics:
            return False, 0.0
        
        # Compare key metrics
        baseline_accuracy = self._baseline_metrics.get("retrieval_precision", 0.0)
        canary_accuracy = self._canary_metrics.get("retrieval_precision", 0.0)
        
        improvement = (canary_accuracy - baseline_accuracy) / baseline_accuracy if baseline_accuracy > 0 else 0
        
        should_rollout = improvement >= improvement_threshold
        
        logger.info(
            f"Canary evaluation: "
            f"baseline={baseline_accuracy:.3f}, "
            f"canary={canary_accuracy:.3f}, "
            f"improvement={improvement*100:.1f}% "
            f"(rollout={should_rollout})"
        )
        
        return should_rollout, improvement


class RetrievalQualityMeasurement:
    """Measure retrieval quality per workspace."""
    
    def __init__(self, workspace_id: str):
        """Initialize retrieval quality measurement."""
        self.workspace_id = workspace_id
        self._queries_evaluated = 0
        self._retrieval_hits = 0
        self._retrieval_misses = 0
        self._reranker_misses = 0
    
    def record_retrieval(
        self,
        query: str,
        retrieved_items: list[str],
        expected_item: str,
        retrieved_rank: int,
    ) -> None:
        """
        Record retrieval result for measurement.
        
        Args:
            query: User query
            retrieved_items: Items returned by retrieval
            expected_item: What we expected to find
            retrieved_rank: Position of expected item (0 if not found)
        """
        self._queries_evaluated += 1
        
        if retrieved_rank == 1:
            self._retrieval_hits += 1
        elif retrieved_rank > 1:
            self._reranker_misses += 1
        else:
            self._retrieval_misses += 1
    
    def get_metrics(self) -> dict:
        """Get retrieval quality metrics."""
        total = self._queries_evaluated
        if total == 0:
            return {"recall": 0.0, "mrr": 0.0, "miss_rate": 0.0}
        
        recall = (self._retrieval_hits + self._reranker_misses) / total
        miss_rate = self._retrieval_misses / total
        
        # Mean Reciprocal Rank (simplified)
        mrr = self._retrieval_hits / total if total > 0 else 0.0
        
        return {
            "queries_evaluated": total,
            "recall": recall,
            "mrr": mrr,
            "miss_rate": miss_rate,
            "hits": self._retrieval_hits,
            "reranker_misses": self._reranker_misses,
            "retrieval_misses": self._retrieval_misses,
        }


class TrainingLoopIntegration:
    """
    Complete training loop: SPPE generation → batch building → Kaggle → evaluation.
    
    This is what enables JimsAI's continuous learning advantage.
    """
    
    def __init__(self, workspace_id: str, kaggle_dataset_owner: str):
        """Initialize training loop."""
        self.workspace_id = workspace_id
        self.sppe_generator = SPPEGenerator(workspace_id)
        self.batch_builder = TrainingBatchBuilder(workspace_id)
        self.kaggle = KaggleTrainingOrchestrator(workspace_id, kaggle_dataset_owner)
        self.canary = CanaryTester(workspace_id)
        self.retrieval_quality = RetrievalQualityMeasurement(workspace_id)
    
    def ingest_query_execution(
        self,
        query: str,
        intent: str,
        entities: list,
        target_ir: str,
        plan_steps: list,
        plan_confidence: float,
        execution_output: str,
        execution_success: bool,
        verification_score: float,
    ) -> bool:
        """
        Ingest a completed query execution to training pipeline.
        
        Returns:
            True if pair was added to batch
        """
        # Generate SPPE pair
        pair = self.sppe_generator.generate(
            query=query,
            intent=intent,
            entities=entities,
            target_ir=target_ir,
            plan_steps=plan_steps,
            plan_confidence=plan_confidence,
            execution_output=execution_output,
            execution_success=execution_success,
            verification_score=verification_score,
        )
        
        # Add to batch if quality sufficient
        self.batch_builder.add_pair(pair)
        
        # Check if batch is ready
        if self.batch_builder.is_batch_ready():
            batch = self.batch_builder.build_batch()
            logger.info(f"Training batch ready: {batch['batch_id']}")
            # Would trigger upload to Kaggle here
        
        return True
    
    def get_system_health_score(self) -> dict:
        """Get overall system health score."""
        retrieval_metrics = self.retrieval_quality.get_metrics()
        
        # Composite score (0-100)
        retrieval_score = (1 - retrieval_metrics.get("miss_rate", 0.0)) * 100
        
        return {
            "health_score": retrieval_score,
            "limiting_factor": (
                "retrieval_misses"
                if retrieval_metrics.get("miss_rate", 0.0) > 0.1
                else "normal"
            ),
            "next_action": (
                "Improve retrieval indexing"
                if retrieval_metrics.get("miss_rate", 0.0) > 0.1
                else "Monitor and gather training data"
            ),
            "retrieval_metrics": retrieval_metrics,
        }


# Example usage
if __name__ == "__main__":
    loop = TrainingLoopIntegration(
        workspace_id="test_workspace",
        kaggle_dataset_owner="jimsai_training"
    )
    
    # Simulate query ingestion
    for i in range(100):
        loop.ingest_query_execution(
            query=f"Sample query {i}",
            intent="CODE_GENERATE",
            entities=["function", "test"],
            target_ir="CODE_GENERATE",
            plan_steps=["Route to CODE_GENERATE", "Execute in sandbox"],
            plan_confidence=0.85 + (i % 20) * 0.01,
            execution_output="def test(): pass",
            execution_success=True,
            verification_score=0.90,
        )
    
    # Get health score
    health = loop.get_system_health_score()
    print(f"System Health Score: {health['health_score']:.1f}/100")
    print(f"Limiting Factor: {health['limiting_factor']}")
    print(f"Retrieval Metrics: {health['retrieval_metrics']}")
