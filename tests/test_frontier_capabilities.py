"""
Tests for frontier model capability implementations (Phase 3).

Validates that all capability frameworks are implemented and functional.
"""

import pytest
from prototype.jimsai.training_loop import (
    TrainingLoopIntegration,
    SPPEGenerator,
    TrainingBatchBuilder,
    CanaryTester,
    RetrievalQualityMeasurement,
    SPPEPair,
)


class TestTrainingLoopCore:
    """Core training loop tests (primary continuous learning mechanism)."""
    
    def test_sppe_pair_generation(self):
        """Test SPPE pair generation."""
        generator = SPPEGenerator(workspace_id="test")
        pair = generator.generate(
            query="test query",
            intent="TEST",
            entities=[],
            target_ir="TEST",
            plan_steps=["step1"],
            plan_confidence=0.90,
            execution_output="result",
            execution_success=True,
            verification_score=0.95,
        )
        
        assert pair.problem["query"] == "test query"
        assert pair.quality_score > 0.70
    
    def test_training_batch_building(self):
        """Test training batch building."""
        builder = TrainingBatchBuilder(workspace_id="test", min_batch_size=5)
        
        # Create dummy pair
        pair = SPPEPair(
            problem={"query": "test", "intent": "TEST", "entities": []},
            plan={"target_ir": "TEST", "reasoning": [], "confidence": 0.90},
            execution={"success": True, "output": "result", "verification": 0.95},
            quality_score=0.90,
        )
        
        # Add pairs
        for _ in range(5):
            builder.add_pair(pair)
        
        assert builder.is_batch_ready() is True
        
        batch = builder.build_batch()
        assert batch["size"] == 5
    
    def test_canary_evaluation(self):
        """Test canary testing for new weights."""
        tester = CanaryTester(workspace_id="test")
        
        # Record metrics
        tester.record_baseline({"retrieval_precision": 0.85})
        tester.record_canary({"retrieval_precision": 0.88})
        
        # Evaluate
        should_rollout, improvement = tester.evaluate(improvement_threshold=0.02)
        
        assert should_rollout is True
        assert improvement > 0.02
    
    def test_retrieval_quality_measurement(self):
        """Test retrieval quality measurement."""
        measurement = RetrievalQualityMeasurement(workspace_id="test")
        
        # Record successful retrieval
        measurement.record_retrieval(
            query="test",
            retrieved_items=["item1"],
            expected_item="item1",
            retrieved_rank=1,
        )
        
        # Record miss
        measurement.record_retrieval(
            query="test2",
            retrieved_items=["item2"],
            expected_item="item3",
            retrieved_rank=0,
        )
        
        metrics = measurement.get_metrics()
        assert metrics["queries_evaluated"] == 2
        assert metrics["hits"] == 1
        assert metrics["retrieval_misses"] == 1
    
    def test_system_health_score(self):
        """Test system health score calculation."""
        loop = TrainingLoopIntegration(
            workspace_id="test",
            kaggle_dataset_owner="test"
        )
        
        health = loop.get_system_health_score()
        assert "health_score" in health
        assert 0 <= health["health_score"] <= 100


class TestCapabilityFrameworkExistence:
    """Verify all frontier model capability frameworks are implemented."""
    
    def test_training_loop_integration_complete(self):
        """Verify complete training loop integration."""
        loop = TrainingLoopIntegration(
            workspace_id="test",
            kaggle_dataset_owner="test"
        )
        
        # Verify all components
        assert hasattr(loop, "sppe_generator")
        assert hasattr(loop, "batch_builder")
        assert hasattr(loop, "kaggle")
        assert hasattr(loop, "canary")
        assert hasattr(loop, "retrieval_quality")
        assert hasattr(loop, "ingest_query_execution")
        assert hasattr(loop, "get_system_health_score")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
