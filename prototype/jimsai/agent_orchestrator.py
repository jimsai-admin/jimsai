"""
Autonomous Agent Orchestrator

Main entry point for running the autonomous training agent.

Usage:
    python -m prototype.jimsai.agent_orchestrator [--config config.yaml]

The agent runs continuously, managing the entire training loop.
Only stops when signaled externally (Ctrl+C, shutdown, error).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from .autonomous_training_agent import AutonomousAgentConfig, AutonomousTrainingAgent, run_agent
from .data_source_connectors import create_default_manager
from .pipeline import JimsAIPipeline
from .training_ui_bridge import integrate_with_training_ui


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("autonomous_agent.log"),
    ],
)

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Orchestrates the entire autonomous training system.
    
    Manages:
    - Pipeline initialization
    - Data source connections
    - Training UI bridge
    - Autonomous agent lifecycle
    - Graceful shutdown
    """

    def __init__(self, config: AutonomousAgentConfig | None = None):
        self.config = config or AutonomousAgentConfig()
        self.pipeline: JimsAIPipeline | None = None
        self.agent: AutonomousTrainingAgent | None = None
        self.data_source_manager = None
        self.ui_bridge = None
        self.is_running = False

    async def initialize(self) -> None:
        """Initialize all system components."""
        
        logger.info("🚀 Initializing autonomous training system...")
        
        # Initialize pipeline
        logger.info("📋 Initializing pipeline...")
        self.pipeline = JimsAIPipeline()
        
        # Initialize data sources
        logger.info("🔌 Connecting data sources...")
        self.data_source_manager = create_default_manager(self.pipeline)
        await self.data_source_manager.connect_all()
        
        # Initialize UI bridge
        logger.info("🖥️ Initializing training UI bridge...")
        self.ui_bridge = integrate_with_training_ui(self.pipeline)
        
        # Initialize agent
        logger.info("🤖 Initializing autonomous agent...")
        self.agent = AutonomousTrainingAgent(self.pipeline, self.config)
        
        logger.info("✅ System initialized successfully")

    async def start(self) -> None:
        """Start the autonomous training loop."""
        
        if not self.pipeline or not self.agent:
            await self.initialize()
        
        self.is_running = True
        
        try:
            logger.info("🎯 Starting autonomous training agent...")
            logger.info("")
            logger.info("=" * 80)
            logger.info("AUTONOMOUS TRAINING AGENT RUNNING")
            logger.info("=" * 80)
            logger.info("")
            logger.info("Configuration:")
            logger.info(f"  • Parallel workers: {self.config.parallel_workers}")
            logger.info(f"  • Batch size: {self.config.batch_size}")
            logger.info(f"  • Max docs per cycle: {self.config.max_documents_per_cycle}")
            logger.info(f"  • Data sources: {', '.join(self.config.data_sources)}")
            logger.info("")
            logger.info("The agent will run indefinitely:")
            logger.info("  1. Find data from configured sources")
            logger.info("  2. Ingest in parallel")
            logger.info("  3. Evaluate system state")
            logger.info("  4. Identify gaps")
            logger.info("  5. Target ingestion to address gaps")
            logger.info("  6. Generate training signals")
            logger.info("  7. Train when batch ready")
            logger.info("  8. Await human approval")
            logger.info("  9. Deploy new weights")
            logger.info("  10. Measure improvement")
            logger.info("  11. Repeat")
            logger.info("")
            logger.info("Human reviewers use the Training UI to:")
            logger.info("  • Review ambiguous cases (medium confidence)")
            logger.info("  • Resolve ambiguities")
            logger.info("  • Inject domain expertise")
            logger.info("  • Correct wrong signatures")
            logger.info("")
            logger.info("Press Ctrl+C to stop gracefully")
            logger.info("=" * 80)
            logger.info("")
            
            await run_agent(self.pipeline, self.config)
            
        except KeyboardInterrupt:
            logger.info("\n⏹️ Received shutdown signal")
        except Exception as e:
            logger.error(f"❌ Error during agent execution: {e}", exc_info=True)
            raise
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Gracefully shutdown the system."""
        
        logger.info("\n🛑 Shutting down autonomous training system...")
        
        self.is_running = False
        
        if self.agent:
            self.agent.stop()
        
        if self.data_source_manager:
            await self.data_source_manager.disconnect_all()
        
        logger.info("✅ Shutdown complete")

    def print_status(self) -> None:
        """Print current system status."""
        
        if not self.agent or not self.agent.current_state:
            logger.info("System not yet evaluated")
            return
        
        state = self.agent.current_state
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("CURRENT SYSTEM STATE")
        logger.info("=" * 80)
        logger.info(f"Intent Stability Score:     {state.intent_stability_score:.4f}")
        logger.info(f"Provider Dependency Rate:   {state.provider_dependency_rate:.2%}")
        logger.info(f"Retrieval Accuracy:         {state.retrieval_accuracy:.2%}")
        logger.info(f"World Model Confidence:     {state.world_model_confidence_avg:.4f}")
        logger.info(f"Review Queue Depth:         {state.review_queue_depth}")
        logger.info(f"SPPE Pairs Ready:           {state.sppe_pairs_ready}")
        logger.info("")
        
        if self.agent.identified_gaps:
            logger.info("IDENTIFIED GAPS (Top 5):")
            for gap in sorted(self.agent.identified_gaps, key=lambda g: -g.priority)[:5]:
                logger.info(f"  • [{gap.gap_type}] {gap.name}")
                logger.info(f"    Current: {gap.current_score:.4f}, Need: {gap.threshold:.4f}")
                logger.info(f"    Priority: {gap.priority}/10")
            logger.info("")
        
        if self.ui_bridge:
            stats = self.ui_bridge.get_review_queue_stats()
            logger.info("REVIEW QUEUE STATS:")
            logger.info(f"  • Pending reviews: {stats['total_pending']}")
            logger.info(f"  • Auto-accepted: {stats['auto_accepted']}")
            logger.info(f"  • Corrections collected: {stats['corrections_collected']}")
            logger.info("")
        
        logger.info("=" * 80)


async def main() -> None:
    """Main entry point."""
    
    # Parse arguments (TODO: add argparse for config file support)
    config = AutonomousAgentConfig()
    
    # Create orchestrator
    orchestrator = AgentOrchestrator(config)
    
    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info(f"\n📬 Received signal {signum}")
        asyncio.create_task(orchestrator.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start system
    try:
        await orchestrator.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
