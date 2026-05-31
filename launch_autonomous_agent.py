"""
LAUNCH SCRIPT FOR AUTONOMOUS TRAINING AGENT

This script demonstrates how to start the autonomous training agent in production.

Usage:
    python launch_autonomous_agent.py

The agent will:
1. Initialize all components (pipeline, data sources, training UI bridge)
2. Start the continuous loop
3. Run indefinitely until stopped (Ctrl+C) or error
4. Generate improvement reports after each deployment
5. Log all activities to file and console

Configuration can be modified by editing AutonomousAgentConfig below.
"""

import asyncio
import sys
from pathlib import Path

# Add workspace to path
workspace_root = Path(__file__).parent
sys.path.insert(0, str(workspace_root))

from prototype.jimsai.agent_orchestrator import AgentOrchestrator
from prototype.jimsai.autonomous_training_agent import AutonomousAgentConfig


async def main():
    """Launch the autonomous training agent."""
    
    # Configure the agent
    config = AutonomousAgentConfig(
        # Data sources to scan
        data_sources=[
            "wikipedia",           # Public knowledge (6M+ articles, 7 languages)
            "opensubtitles",       # Multilingual dialogue (50M+ subtitles)
            "user_interactions",   # Real system usage (highest priority)
            "synthetic_generation" # Groq-generated fallback data
        ],
        
        # Ingestion parallelism
        parallel_workers=8,        # 8 parallel document processors
        batch_size=100,            # Documents per worker batch
        max_documents_per_cycle=5000,  # Maximum per cycle
        
        # Evaluation thresholds (when to flag as needing attention)
        intent_stability_min=0.85,      # Intent classifier consistency
        provider_dependency_max=0.15,   # Max 15% provider calls (15% = world model too sparse)
        retrieval_accuracy_min=0.80,    # Memory retrieval precision
        world_model_confidence_min=0.75, # Causal link confidence
        
        # Gap targeting thresholds
        language_variant_threshold=0.70,   # Per-language performance target
        domain_coverage_threshold=0.65,    # Per-domain coverage target
        capability_coverage_threshold=0.70, # Per-capability coverage target
        
        # Training signal routing
        sppe_quality_threshold=0.80,           # Minimum quality for SPPE pairs
        auto_accept_confidence=0.90,           # > 90% confidence → auto-accept
        human_review_confidence_range=(0.65, 0.90),  # 65-90% → human review
        world_model_candidate_threshold=0.75,  # Minimum for world model
        
        # Training batch thresholds
        sppe_batch_min=1000,          # 1000 SPPE pairs to trigger training
        training_interval_days=7,     # Maximum wait before forced training
        
        # Human approval gate
        require_human_approval=True,  # Weight activation always needs human
        human_approval_timeout_hours=24,  # Timeout for waiting
    )
    
    # Create orchestrator
    orchestrator = AgentOrchestrator(config)
    
    # Start the agent
    await orchestrator.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ Agent stopped")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
