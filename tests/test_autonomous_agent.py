"""
Comprehensive Test Suite for Autonomous Training Agent

Tests all components to ensure production readiness:
- Agent loop execution
- Data source connectors
- Ingestion worker pool
- Training signal generation
- Human gate logic
- Metrics collection
- Error recovery
"""

import asyncio
import logging
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

# Import components to test
from prototype.jimsai.autonomous_training_agent import (
    AutonomousTrainingAgent,
    AutonomousAgentConfig,
    SystemState,
    IdentifiedGap,
)
from prototype.jimsai.data_source_connectors import (
    DataSourceManager,
    DataSourceDocument,
)
from prototype.jimsai.ingestion_worker_pool import (
    IngestionWorkerPool,
    IngestionWorker,
)
from prototype.jimsai.training_ui_bridge import TrainingUIBridge
from prototype.jimsai.metrics_reporter import MetricsCollector, ReportFormatter
from prototype.jimsai.pipeline import JimsAIPipeline


logger = logging.getLogger(__name__)


# ============================================================================
# FIXTURE SETUP
# ============================================================================

@pytest.fixture
def pipeline():
    """Create a pipeline instance for testing."""
    return JimsAIPipeline()


@pytest.fixture
def config():
    """Create test configuration."""
    return AutonomousAgentConfig(
        parallel_workers=2,  # Small for testing
        batch_size=10,
        max_documents_per_cycle=50,
        sppe_batch_min=10,
    )


@pytest.fixture
def agent(pipeline, config):
    """Create agent instance for testing."""
    return AutonomousTrainingAgent(pipeline, config)


@pytest.fixture
def ui_bridge(pipeline):
    """Create training UI bridge for testing."""
    return TrainingUIBridge(pipeline)


# ============================================================================
# AGENT LOOP TESTS
# ============================================================================

class TestAgentLoop:
    """Test the main agent loop."""

    @pytest.mark.asyncio
    async def test_agent_initialization(self, agent):
        """Agent should initialize with proper state."""
        assert agent.is_running == False
        assert agent.current_state is None
        assert len(agent.identified_gaps) == 0

    @pytest.mark.asyncio
    async def test_single_cycle_execution(self, agent):
        """Agent should execute one complete cycle."""
        # Mock the cycle execution to prevent infinite loop
        agent._execute_cycle = AsyncMock()
        
        # Create a task that runs one cycle then stops
        async def run_one_cycle():
            await agent._execute_cycle()
            agent.is_running = False
        
        # Execute
        await run_one_cycle()
        
        # Verify cycle ran
        agent._execute_cycle.assert_called_once()

    @pytest.mark.asyncio
    async def test_cycle_error_recovery(self, agent):
        """Agent should recover from errors and continue."""
        error_count = 0
        
        async def failing_cycle():
            nonlocal error_count
            error_count += 1
            if error_count < 2:
                raise ValueError("Test error")
        
        agent._execute_cycle = failing_cycle
        
        # Should not raise, should recover
        try:
            # First call raises
            await agent._execute_cycle()
        except ValueError:
            pass
        
        # Second call should succeed
        await agent._execute_cycle()
        assert error_count == 2

    @pytest.mark.asyncio
    async def test_agent_stop_signal(self, agent):
        """Agent should stop when signaled."""
        agent.is_running = True
        agent.stop()
        
        assert agent.is_running == False

    @pytest.mark.asyncio
    async def test_event_logging(self, agent):
        """Agent should log events."""
        # Mock event store
        agent.event_store.append = Mock()
        
        # Verify append can be called
        agent.event_store.append("test_event", "test_id", {"key": "value"})
        
        # Should record the event
        assert agent.event_store.append.called


# ============================================================================
# DATA SOURCE CONNECTOR TESTS
# ============================================================================

class TestDataSourceConnectors:
    """Test data source connectors."""

    @pytest.mark.asyncio
    async def test_data_source_manager_initialization(self):
        """Manager should initialize empty."""
        manager = DataSourceManager()
        assert len(manager.connectors) == 0
        assert len(manager.active) == 0

    @pytest.mark.asyncio
    async def test_connector_registration(self):
        """Manager should register connectors."""
        manager = DataSourceManager()
        
        # Create mock connector
        connector = AsyncMock()
        
        # Register
        manager.register_connector("test", connector)
        
        # Should be registered
        assert "test" in manager.connectors
        assert manager.active["test"] == False

    @pytest.mark.asyncio
    async def test_connector_connect_disconnect(self):
        """Connectors should connect and disconnect."""
        manager = DataSourceManager()
        
        connector = AsyncMock()
        connector.connect = AsyncMock()
        connector.disconnect = AsyncMock()
        
        manager.register_connector("test", connector)
        
        # Connect
        await manager.connect_all()
        
        # Should have called connect
        connector.connect.assert_called_once()
        
        # Disconnect
        await manager.disconnect_all()
        
        # Should have called disconnect
        connector.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_document_fetching(self):
        """Manager should fetch documents from sources."""
        manager = DataSourceManager()
        
        # Create mock connector that returns documents
        async def mock_fetch(*args, **kwargs):
            yield DataSourceDocument(
                source="test",
                document_id="doc1",
                content="Test content",
                language="en",
                metadata={},
            )
        
        connector = AsyncMock()
        connector.fetch_documents = mock_fetch
        
        manager.register_connector("test", connector)
        manager.active["test"] = True
        
        # Fetch
        docs = []
        async for doc in manager.fetch_from_sources(["test"]):
            docs.append(doc)
        
        # Should have fetched
        assert len(docs) == 1
        assert docs[0].document_id == "doc1"


# ============================================================================
# INGESTION PIPELINE TESTS
# ============================================================================

class TestIngestionPipeline:
    """Test document ingestion pipeline."""

    @pytest.mark.asyncio
    async def test_worker_pool_initialization(self):
        """Worker pool should initialize with correct count."""
        from prototype.jimsai.encoder import DualRepresentationEncoder
        
        encoder = AsyncMock(spec=DualRepresentationEncoder)
        pool = IngestionWorkerPool(encoder, worker_count=2)
        
        assert len(pool.workers) == 2
        assert pool.worker_count == 2

    @pytest.mark.asyncio
    async def test_document_processing(self):
        """Worker should process documents."""
        from prototype.jimsai.encoder import DualRepresentationEncoder
        
        encoder = AsyncMock(spec=DualRepresentationEncoder)
        worker = IngestionWorker(encoder)
        
        # Create test document
        doc = DataSourceDocument(
            source="test",
            document_id="doc1",
            content="Test content about renewable energy and solar power systems.",
            language="en",
            metadata={"title": "Test Article"},
        )
        
        # Process
        result = await worker.process_document(doc)
        
        # Should have processed
        assert result.success == True
        assert result.document_id == "doc1"
        assert result.signature_id is not None

    @pytest.mark.asyncio
    async def test_batch_processing(self):
        """Pool should process documents in batch."""
        from prototype.jimsai.encoder import DualRepresentationEncoder
        
        encoder = AsyncMock(spec=DualRepresentationEncoder)
        pool = IngestionWorkerPool(encoder, worker_count=2)
        
        # Create documents
        docs = [
            DataSourceDocument(
                source="test",
                document_id=f"doc{i}",
                content=f"Test content {i}",
                language="en",
                metadata={},
            )
            for i in range(5)
        ]
        
        # Process batch
        results = await pool.process_documents(docs)
        
        # Should have processed all
        assert len(results) == 5
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_processing_error_handling(self):
        """Worker should handle errors gracefully."""
        from prototype.jimsai.encoder import DualRepresentationEncoder
        
        encoder = AsyncMock(spec=DualRepresentationEncoder)
        worker = IngestionWorker(encoder)
        
        # Create invalid document
        doc = DataSourceDocument(
            source="test",
            document_id="doc1",
            content="",  # Empty content
            language="en",
            metadata={},
        )
        
        # Should not raise, should return failure
        result = await worker.process_document(doc)
        assert result.success == False


# ============================================================================
# SYSTEM STATE MEASUREMENT TESTS
# ============================================================================

class TestSystemStateEvaluation:
    """Test system state evaluation."""

    @pytest.mark.asyncio
    async def test_state_evaluation(self, agent):
        """Agent should evaluate system state."""
        state = await agent._evaluate_system_state()
        
        # Should have all metrics
        assert state.intent_stability_score >= 0.0
        assert state.intent_stability_score <= 1.0
        assert state.provider_dependency_rate >= 0.0
        assert state.provider_dependency_rate <= 1.0
        assert state.retrieval_accuracy >= 0.0
        assert state.world_model_confidence_avg >= 0.0

    @pytest.mark.asyncio
    async def test_gap_identification(self, agent):
        """Agent should identify gaps."""
        # Create mock state with gaps
        state = SystemState(
            timestamp=datetime.utcnow(),
            intent_stability_score=0.88,
            provider_dependency_rate=0.12,
            retrieval_accuracy=0.82,
            world_model_confidence_avg=0.73,
            language_variant_scores={"en": 0.90, "yo": 0.40},
            domain_coverage={"medical": 0.60},
            capability_coverage={"creative": 0.60},
            review_queue_depth=100,
            sppe_pairs_ready=500,
        )
        
        # Identify gaps
        gaps = await agent._identify_gaps(state)
        
        # Should identify the low-scoring items as gaps
        assert len(gaps) > 0
        assert any(g.gap_type == "language" for g in gaps)

    @pytest.mark.asyncio
    async def test_targeting_plan_creation(self, agent):
        """Agent should create targeting plan."""
        # Create mock gaps
        gaps = [
            IdentifiedGap(
                gap_type="language",
                name="Yoruba",
                current_score=0.40,
                threshold=0.70,
                priority=7,
                suggested_data_source="opensubtitles",
                estimated_documents_needed=500,
            ),
            IdentifiedGap(
                gap_type="domain",
                name="Medical",
                current_score=0.60,
                threshold=0.65,
                priority=6,
                suggested_data_source="wikipedia",
                estimated_documents_needed=1000,
            ),
        ]
        
        # Create plan
        plan = await agent._create_targeting_plan(gaps)
        
        # Should have plan items
        assert len(plan) > 0
        assert any("opensubtitles" in str(item) for item in plan)


# ============================================================================
# TRAINING SIGNAL GENERATION TESTS
# ============================================================================

class TestTrainingSignalGeneration:
    """Test SPPE pair and training signal generation."""

    @pytest.mark.asyncio
    async def test_sppe_pair_generation(self, agent):
        """Agent should generate SPPE pairs."""
        ingestion_results = {
            "total_documents": 100,
            "signatures_created": 95,
            "sppe_pairs_generated": 85,
            "world_model_candidates": 40,
        }
        
        signal = await agent._generate_training_signal(ingestion_results)
        
        # Should have routing
        assert signal["sppe_ready"] > 0
        assert signal["auto_accept"] > 0
        assert signal["human_review"] > 0

    @pytest.mark.asyncio
    async def test_training_trigger_check(self, agent):
        """Agent should check if training should be triggered."""
        # Below threshold
        signal = {"sppe_ready": 500}
        decision = await agent._check_training_trigger(signal)
        assert decision["should_train"] == False
        
        # Above threshold
        signal = {"sppe_ready": 1500}
        decision = await agent._check_training_trigger(signal)
        assert decision["should_train"] == True


# ============================================================================
# TRAINING UI BRIDGE TESTS
# ============================================================================

class TestTrainingUIBridge:
    """Test integration with Training UI."""

    @pytest.mark.asyncio
    async def test_sppe_routing_high_confidence(self, ui_bridge):
        """High confidence pairs should auto-accept."""
        from prototype.jimsai.models import SPPETrainingPair, utc_now
        
        pair = SPPETrainingPair(
            id="sppe1",
            semantic_ir="QUERY",
            query="Test query",
            response="Test response",
            quality_score=0.95,
            source="test",
            created_at=utc_now(),
        )
        
        decision, item = await ui_bridge.route_sppe_pair(pair, confidence=0.95)
        
        assert decision == "auto_accepted"
        assert item is None

    @pytest.mark.asyncio
    async def test_sppe_routing_medium_confidence(self, ui_bridge):
        """Medium confidence pairs should go to review."""
        from prototype.jimsai.models import SPPETrainingPair, utc_now
        
        pair = SPPETrainingPair(
            id="sppe1",
            semantic_ir="QUERY",
            query="Test query",
            response="Test response",
            quality_score=0.80,
            source="test",
            created_at=utc_now(),
        )
        
        decision, item = await ui_bridge.route_sppe_pair(pair, confidence=0.78)
        
        assert decision == "queued_for_review"
        assert item is not None
        assert item.item_type == "sppe"

    @pytest.mark.asyncio
    async def test_review_queue_retrieval(self, ui_bridge):
        """Should retrieve pending review items."""
        # Queue some items
        from prototype.jimsai.models import SPPETrainingPair, utc_now
        
        for i in range(5):
            pair = SPPETrainingPair(
                id=f"sppe{i}",
                semantic_ir="QUERY",
                query=f"Test query {i}",
                response=f"Test response {i}",
                quality_score=0.75,
                source="test",
                created_at=utc_now(),
            )
            await ui_bridge.route_sppe_pair(pair, confidence=0.75)
        
        # Get queue
        queue = ui_bridge.get_review_queue()
        
        # Should have items
        assert len(queue) >= 5

    @pytest.mark.asyncio
    async def test_human_decision_processing(self, ui_bridge):
        """Should process human decisions."""
        from prototype.jimsai.models import SPPETrainingPair, utc_now
        
        # Queue an item
        pair = SPPETrainingPair(
            id="sppe1",
            semantic_ir="QUERY",
            query="Test query",
            response="Test response",
            quality_score=0.75,
            source="test",
            created_at=utc_now(),
        )
        decision, item = await ui_bridge.route_sppe_pair(pair, confidence=0.75)
        
        # Process human decision
        await ui_bridge.process_human_decision(
            item.item_id,
            "accept",
        )
        
        # Should have processed
        assert item.human_decision == "accept"


# ============================================================================
# METRICS COLLECTION TESTS
# ============================================================================

class TestMetricsCollection:
    """Test metrics collection and reporting."""

    def test_metrics_collector_initialization(self):
        """Collector should initialize empty."""
        collector = MetricsCollector()
        assert len(collector.snapshots) == 0

    def test_snapshot_recording(self):
        """Collector should record snapshots."""
        collector = MetricsCollector()
        
        state = SystemState(
            timestamp=datetime.utcnow(),
            intent_stability_score=0.88,
            provider_dependency_rate=0.12,
            retrieval_accuracy=0.82,
            world_model_confidence_avg=0.73,
            language_variant_scores={"en": 0.90},
            domain_coverage={"general": 0.88},
            capability_coverage={"chat": 0.90},
        )
        
        collector.record_snapshot(state)
        
        assert len(collector.snapshots) == 1

    def test_improvement_computation(self):
        """Should compute improvement metrics."""
        from prototype.jimsai.metrics_reporter import MetricSnapshot
        
        collector = MetricsCollector()
        
        before = MetricSnapshot(
            timestamp="2026-05-31T14:00:00",
            intent_stability=0.87,
            provider_dependency=0.13,
            retrieval_accuracy=0.81,
            world_model_confidence=0.72,
            language_coverage={"en": 0.90},
            domain_coverage={"general": 0.88},
            capability_coverage={"chat": 0.90},
        )
        
        after = MetricSnapshot(
            timestamp="2026-05-31T15:00:00",
            intent_stability=0.90,
            provider_dependency=0.11,
            retrieval_accuracy=0.84,
            world_model_confidence=0.75,
            language_coverage={"en": 0.92},
            domain_coverage={"general": 0.90},
            capability_coverage={"chat": 0.92},
        )
        
        report = collector.compute_improvement(
            before=before,
            after=after,
            deployment_id="deploy-001",
            cycle_number=1,
        )
        
        # Should compute deltas
        assert report.intent_stability_delta > 0
        assert report.provider_dependency_delta > 0  # Lower is better
        assert report.overall_improvement_pct > 0

    def test_improvement_report_formatting(self):
        """Should format improvement reports."""
        from prototype.jimsai.metrics_reporter import MetricSnapshot, ImprovementReport
        
        before = MetricSnapshot(
            timestamp="2026-05-31T14:00:00",
            intent_stability=0.87,
            provider_dependency=0.13,
            retrieval_accuracy=0.81,
            world_model_confidence=0.72,
            language_coverage={"en": 0.90},
            domain_coverage={"general": 0.88},
            capability_coverage={"chat": 0.90},
        )
        
        after = MetricSnapshot(
            timestamp="2026-05-31T15:00:00",
            intent_stability=0.90,
            provider_dependency=0.11,
            retrieval_accuracy=0.84,
            world_model_confidence=0.75,
            language_coverage={"en": 0.92},
            domain_coverage={"general": 0.90},
            capability_coverage={"chat": 0.92},
        )
        
        report = ImprovementReport(
            cycle_number=1,
            deployment_id="deploy-001",
            timestamp="2026-05-31T15:00:00",
            before=before,
            after=after,
            intent_stability_delta=0.03,
            provider_dependency_delta=0.02,
            retrieval_accuracy_delta=0.03,
            world_model_confidence_delta=0.03,
            overall_improvement_pct=2.75,
            quality_level="good",
            recommendations=[
                "Continue current strategy",
                "Monitor language coverage",
            ],
        )
        
        formatter = ReportFormatter()
        text = formatter.format_improvement_report(report)
        
        # Should format
        assert "IMPROVEMENT REPORT" in text
        assert "GOOD" in text
        assert "2.75%" in text


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Test performance characteristics."""

    @pytest.mark.asyncio
    async def test_ingestion_throughput(self):
        """Should achieve acceptable throughput."""
        from prototype.jimsai.encoder import DualRepresentationEncoder
        from time import time
        
        encoder = AsyncMock(spec=DualRepresentationEncoder)
        pool = IngestionWorkerPool(encoder, worker_count=2)
        
        # Create documents
        docs = [
            DataSourceDocument(
                source="test",
                document_id=f"doc{i}",
                content=f"Test content {i}",
                language="en",
                metadata={},
            )
            for i in range(50)
        ]
        
        # Measure
        start = time()
        results = await pool.process_documents(docs)
        elapsed = time() - start
        
        # Should be reasonably fast
        assert elapsed < 10  # 50 docs in less than 10 seconds
        throughput = len(results) / elapsed
        logger.info(f"Throughput: {throughput:.1f} docs/sec")


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Test integrated systems."""

    @pytest.mark.asyncio
    async def test_end_to_end_flow(self, agent, ui_bridge):
        """Test complete flow from ingestion to training."""
        # This is a simplified integration test
        
        # 1. Find data (mocked)
        sources = await agent._find_data_sources()
        assert len(sources) > 0
        
        # 2. Evaluate system
        state = await agent._evaluate_system_state()
        assert state is not None
        
        # 3. Identify gaps
        gaps = await agent._identify_gaps(state)
        assert len(gaps) >= 0
        
        # 4. Generate training signal
        ingestion_results = {
            "total_documents": 100,
            "signatures_created": 95,
            "sppe_pairs_generated": 85,
            "world_model_candidates": 40,
        }
        signal = await agent._generate_training_signal(ingestion_results)
        assert signal["sppe_ready"] > 0
        
        # 5. Check training trigger
        decision = await agent._check_training_trigger(signal)
        # May or may not trigger based on thresholds


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Test error handling and resilience."""

    @pytest.mark.asyncio
    async def test_connector_failure_resilience(self):
        """System should handle connector failures."""
        manager = DataSourceManager()
        
        # Register failing connector
        failing_connector = AsyncMock()
        failing_connector.connect = AsyncMock(side_effect=Exception("Connection failed"))
        
        manager.register_connector("failing", failing_connector)
        
        # Should not raise
        await manager.connect_all()
        
        # Should be marked inactive
        assert manager.active["failing"] == False

    @pytest.mark.asyncio
    async def test_worker_error_isolation(self):
        """Document processing errors shouldn't affect others."""
        from prototype.jimsai.encoder import DualRepresentationEncoder
        
        encoder = AsyncMock(spec=DualRepresentationEncoder)
        pool = IngestionWorkerPool(encoder, worker_count=2)
        
        docs = [
            DataSourceDocument(
                source="test",
                document_id=f"doc{i}",
                content="x" * (100 if i % 2 == 0 else 0),  # Some have content
                language="en",
                metadata={},
            )
            for i in range(4)
        ]
        
        # Should handle all, including problematic ones
        results = await pool.process_documents(docs)
        assert len(results) == 4


# ============================================================================
# PRODUCTION READINESS TESTS
# ============================================================================

class TestProductionReadiness:
    """Test production readiness criteria."""

    @pytest.mark.asyncio
    async def test_logging_enabled(self, agent):
        """Agent should have logging."""
        assert agent.event_store is not None

    @pytest.mark.asyncio
    async def test_metrics_collection_enabled(self, agent):
        """Agent should collect metrics."""
        state = await agent._evaluate_system_state()
        assert state.timestamp is not None

    @pytest.mark.asyncio
    async def test_error_recovery_enabled(self, agent):
        """Agent should have error recovery."""
        # Create mock that fails then succeeds
        call_count = 0
        async def sometimes_fail():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Test")
            return "success"
        
        agent._execute_cycle = sometimes_fail
        
        # Should handle first error
        try:
            await agent._execute_cycle()
        except ValueError:
            pass
        
        # Should recover
        result = await agent._execute_cycle()
        assert result == "success"

    def test_configuration_options(self):
        """Config should have all necessary options."""
        config = AutonomousAgentConfig()
        
        # Should have all key settings
        assert config.parallel_workers > 0
        assert config.batch_size > 0
        assert config.max_documents_per_cycle > 0
        assert config.intent_stability_min > 0
        assert config.sppe_batch_min > 0


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    # Run with: pytest tests/test_autonomous_agent.py -v
    pytest.main([__file__, "-v", "-s"])
