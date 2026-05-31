"""
Autonomous Training Agent — Quickstart and Demonstration

This script shows how to:
1. Initialize the autonomous agent
2. Run the continuous training loop
3. Monitor system state
4. Integrate with human training UI
5. Review improvement reports
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add workspace to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from prototype.jimsai.agent_orchestrator import AgentOrchestrator
from prototype.jimsai.autonomous_training_agent import AutonomousAgentConfig
from prototype.jimsai.metrics_reporter import ReportFormatter


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger(__name__)


async def demonstrate_agent() -> None:
    """Run a demonstration of the autonomous agent."""
    
    logger.info("")
    logger.info("=" * 90)
    logger.info("JIMS-AI AUTONOMOUS TRAINING AGENT DEMONSTRATION")
    logger.info("=" * 90)
    logger.info("")
    
    logger.info("This demonstration shows:")
    logger.info("  1. How the autonomous agent finds data from multiple sources")
    logger.info("  2. How parallel workers process documents")
    logger.info("  3. How the system evaluates itself")
    logger.info("  4. How gaps are identified and addressed")
    logger.info("  5. How human reviewers complement automated workers")
    logger.info("  6. How the system improves over time")
    logger.info("")
    
    # Create config with demo settings
    config = AutonomousAgentConfig(
        data_sources=["wikipedia", "opensubtitles", "user_interactions", "synthetic_generation"],
        parallel_workers=4,  # Reduced for demo
        batch_size=50,
        max_documents_per_cycle=500,
        sppe_batch_min=100,  # Reduced for demo
    )
    
    logger.info("Configuration:")
    logger.info(f"  • Data sources: {', '.join(config.data_sources)}")
    logger.info(f"  • Parallel workers: {config.parallel_workers}")
    logger.info(f"  • Batch size: {config.batch_size}")
    logger.info(f"  • Max documents per cycle: {config.max_documents_per_cycle}")
    logger.info("")
    
    # Initialize orchestrator
    logger.info("Initializing system...")
    orchestrator = AgentOrchestrator(config)
    await orchestrator.initialize()
    
    logger.info("")
    logger.info("✅ System initialized successfully")
    logger.info("")
    
    # Show system architecture
    logger.info("SYSTEM ARCHITECTURE:")
    logger.info("  Pipeline ........................... JimsAIPipeline (14+ layers)")
    logger.info("  Data Sources ....................... Wikipedia, OpenSubtitles, User Interactions, Synthetic")
    logger.info("  Ingestion Workers ................. 8 parallel workers (mechanical processing)")
    logger.info("  Memory System ...................... 4-layer architecture (sensory/working/episodic/semantic)")
    logger.info("  Retrieval Engine ................... Multi-index with 6+ scoring signals")
    logger.info("  Training UI Bridge ................ Routes work: auto-accept / human review")
    logger.info("  Human Training UI ................. Reviews ambiguous cases, injects expertise")
    logger.info("  Kaggle Integration ................ Packages training data for training runs")
    logger.info("  Metrics Reporter .................. Tracks improvement across cycles")
    logger.info("")
    
    # Show the separation of concerns
    logger.info("SEPARATION OF CONCERNS:")
    logger.info("")
    logger.info("AUTOMATED WORKERS (Volume work - no judgment):")
    logger.info("  • Bulk ingestion of public datasets")
    logger.info("  • Format conversion and Unicode normalization")
    logger.info("  • Entity extraction at scale")
    logger.info("  • Embedding generation")
    logger.info("  • Routine signature creation")
    logger.info("  • High-confidence SPPE pair acceptance")
    logger.info("")
    logger.info("HUMAN TRAINING UI (Quality work - requires judgment):")
    logger.info("  • Review queue processing")
    logger.info("  • Ambiguity resolution")
    logger.info("  • Quality flagging")
    logger.info("  • Domain expertise injection")
    logger.info("  • Correction of wrong signatures")
    logger.info("  • Approval of weight activation")
    logger.info("")
    
    # Show the continuous loop
    logger.info("CONTINUOUS LOOP (runs indefinitely):")
    logger.info("")
    logger.info("1. 🔍 FIND DATA")
    logger.info("   └─ Agent scans: Wikipedia, OpenSubtitles, user interactions, synthetic generation")
    logger.info("")
    logger.info("2. 📥 INGEST")
    logger.info("   └─ Parallel workers: normalize, embed, extract entities, create signatures")
    logger.info("")
    logger.info("3. 📊 EVALUATE")
    logger.info("   └─ Measure: Intent Stability, Provider Dependency, Retrieval Accuracy, World Model Confidence")
    logger.info("")
    logger.info("4. 🕵️ IDENTIFY GAPS")
    logger.info("   └─ Find weak: domains, languages, capabilities, provider dependencies")
    logger.info("")
    logger.info("5. 🎯 TARGET INGESTION")
    logger.info("   └─ Prioritize data to address identified gaps")
    logger.info("")
    logger.info("6. 🏷️ GENERATE TRAINING SIGNAL")
    logger.info("   └─ Create SPPE pairs + world models: auto-accept (>90%), review (65-90%), reject (<65%)")
    logger.info("")
    logger.info("7. 🚀 TRAIN")
    logger.info("   └─ When batch threshold reached: package for Kaggle, upload, trigger training")
    logger.info("")
    logger.info("8. 👤 HUMAN GATE (only non-autonomous step)")
    logger.info("   └─ Human approves weight activation")
    logger.info("")
    logger.info("9. ⚡ DEPLOY")
    logger.info("   └─ Hot-swap new weights into production")
    logger.info("")
    logger.info("10. 📈 MEASURE IMPROVEMENT")
    logger.info("    └─ Compare metrics before/after, generate directive report")
    logger.info("")
    logger.info("11. 🔄 REPEAT")
    logger.info("")
    
    logger.info("The cycle runs continuously. Only stops:")
    logger.info("  • For human approval at the weight activation gate")
    logger.info("  • On external shutdown signal (Ctrl+C)")
    logger.info("  • On unrecoverable error")
    logger.info("")
    
    logger.info("=" * 90)
    logger.info("To start the full autonomous agent, run:")
    logger.info("")
    logger.info("  python -m prototype.jimsai.agent_orchestrator")
    logger.info("")
    logger.info("=" * 90)
    logger.info("")
    
    # Show example output
    logger.info("EXAMPLE CYCLE OUTPUT:")
    logger.info("")
    
    if orchestrator.agent and orchestrator.agent.current_state:
        formatter = ReportFormatter()
        state_report = formatter.format_system_state_report(orchestrator.agent.current_state)
        print(state_report)
    
    logger.info("")
    logger.info("✅ Demonstration complete")
    logger.info("")


async def main() -> None:
    """Main entry point."""
    try:
        await demonstrate_agent()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
