"""
Phase 5 Build & Test Orchestration Script

Main entry point for:
1. Setting up PostgreSQL database
2. Initializing EventStore
3. Running integration tests with real prompts
4. Collecting and refining metrics

Usage:
    python scripts/build_phase5.py --db-init --run-tests --export-results
    
Or step-by-step:
    python scripts/build_phase5.py --db-init
    python scripts/build_phase5.py --run-tests
    python scripts/build_phase5.py --export-results
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add workspace root to path
WORKSPACE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

logger = logging.getLogger(__name__)


async def initialize_database(connection_string: str) -> bool:
    """Initialize PostgreSQL database schema."""
    try:
        logger.info("📦 Initializing PostgreSQL database...")
        
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        
        # Convert to async connection string if needed
        if connection_string.startswith("postgresql://"):
            connection_string = connection_string.replace("postgresql://", "postgresql+asyncpg://")
        
        logger.info(f"Connection: {connection_string.split('@')[1] if '@' in connection_string else 'local'}")
        
        engine = create_async_engine(
            connection_string,
            echo=False,
            pool_pre_ping=True
        )
        
        # Read schema from PHASE5_QUICKSTART.md or use inline schema
        schema_sql = """
        -- Event Store (Append-Only Log)
        CREATE TABLE IF NOT EXISTS events (
            id BIGSERIAL PRIMARY KEY,
            event_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            aggregate_type TEXT NOT NULL,
            data JSONB NOT NULL,
            metadata JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            version INT NOT NULL,
            workspace_id TEXT,
            INDEX idx_aggregate ON events(aggregate_id),
            INDEX idx_type ON events(event_type),
            INDEX idx_time ON events(created_at),
            INDEX idx_workspace ON events(workspace_id)
        );

        CREATE TABLE IF NOT EXISTS memory_signature_projection (
            signature_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            structured_content JSONB,
            entities JSONB,
            relations JSONB,
            confidence FLOAT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sppe_pair_projection (
            pair_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            batch_id TEXT,
            quality_score FLOAT,
            signal_efficiency FLOAT,
            created_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS batch_statistics (
            batch_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            pair_count INT DEFAULT 0,
            avg_quality FLOAT,
            avg_efficiency FLOAT,
            created_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS review_queue_projection (
            review_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            item_type TEXT,
            status TEXT,
            created_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS provenance_projection (
            query_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            provider TEXT,
            verification_status TEXT,
            execution_time_ms FLOAT,
            created_at TIMESTAMP
        );
        """
        
        async with engine.begin() as conn:
            for statement in schema_sql.split(';'):
                statement = statement.strip()
                if statement:
                    try:
                        await conn.execute(text(statement))
                    except Exception as e:
                        logger.debug(f"Note: {statement[:40]}... {e}")
        
        await engine.dispose()
        logger.info("✅ Database initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        logger.error("Make sure PostgreSQL is running and connection string is correct")
        return False


async def initialize_event_store(connection_string: str) -> Optional[object]:
    """Initialize EventStore with database backend."""
    try:
        logger.info("🔧 Initializing EventStore...")
        
        from prototype.jimsai.eventing import EventStore
        from sqlalchemy.ext.asyncio import create_async_engine
        
        # Convert connection string to async
        if connection_string.startswith("postgresql://"):
            connection_string = connection_string.replace("postgresql://", "postgresql+asyncpg://")
        
        engine = create_async_engine(
            connection_string,
            echo=False,
            pool_pre_ping=True
        )
        
        # Create event store
        event_store = EventStore(engine)
        logger.info("✅ EventStore initialized")
        
        return event_store
        
    except Exception as e:
        logger.error(f"❌ EventStore initialization failed: {e}")
        return None


async def run_integration_tests(event_store) -> Optional[dict]:
    """Run Phase 5 integration tests."""
    try:
        logger.info("\n🧪 Running Phase 5 Integration Tests...")
        logger.info(f"Test start: {datetime.utcnow().isoformat()}")
        
        from prototype.jimsai.phase5_integration import initialize_phase5
        from tests.phase5_integration_test import Phase5TestRunner, REAL_WORLD_PROMPTS
        
        # Initialize Phase 5 pipeline
        pipeline = await initialize_phase5(event_store, workspace_id="test-workspace")
        logger.info("✅ Phase 5 pipeline initialized")
        
        # Create test runner
        runner = Phase5TestRunner(pipeline, workspace_id="test-workspace")
        
        # Run all tests
        logger.info(f"📋 Executing {len(REAL_WORLD_PROMPTS)} real-world prompts...")
        summary = await runner.run_all_tests()
        
        # Print summary
        runner.print_summary(summary)
        
        return summary
        
    except Exception as e:
        logger.error(f"❌ Integration tests failed: {e}", exc_info=True)
        return None


def analyze_results(summary: dict) -> None:
    """Analyze test results and provide recommendations."""
    if not summary:
        return
    
    logger.info("\n" + "="*80)
    logger.info("PHASE 5 ANALYSIS & RECOMMENDATIONS")
    logger.info("="*80)
    
    metrics = summary.get("metrics", {})
    opt = summary.get("transformer_optimization", {})
    
    logger.info("\n📈 Key Insights:")
    
    # T1 Analysis
    t1_skip_rate = opt.get("t1_skip_rate", 0)
    if t1_skip_rate > 0.50:
        logger.info(f"  ✅ T1 Skip Rate: {t1_skip_rate:.1%} - Excellent! Memory handling is strong")
    elif t1_skip_rate > 0.30:
        logger.info(f"  ⚠️  T1 Skip Rate: {t1_skip_rate:.1%} - Good, can be optimized further")
    else:
        logger.info(f"  ⚡ T1 Skip Rate: {t1_skip_rate:.1%} - Consider improving memory confidence")
    
    # T2 Analysis
    t2_skip_rate = opt.get("t2_skip_rate", 0)
    if t2_skip_rate > 0.60:
        logger.info(f"  ✅ T2 Skip Rate: {t2_skip_rate:.1%} - Excellent! CSSE verification is working")
    elif t2_skip_rate > 0.40:
        logger.info(f"  ⚠️  T2 Skip Rate: {t2_skip_rate:.1%} - Good, can be improved")
    else:
        logger.info(f"  ⚡ T2 Skip Rate: {t2_skip_rate:.1%} - CSSE thresholds may need adjustment")
    
    # SPPE Analysis
    sppe_generated = metrics.get("sppe_pairs_generated", 0)
    total_queries = metrics.get("total_queries", 0)
    if total_queries > 0:
        pair_rate = sppe_generated / total_queries
        logger.info(f"  📚 SPPE Pairs Generated: {sppe_generated}/{total_queries} ({pair_rate:.1%})")
    
    # Latency Analysis
    avg_latency = metrics.get("avg_latency_ms", 0)
    if avg_latency < 200:
        logger.info(f"  ⚡ Avg Latency: {avg_latency:.0f}ms - Excellent performance")
    elif avg_latency < 500:
        logger.info(f"  ✅ Avg Latency: {avg_latency:.0f}ms - Good")
    else:
        logger.info(f"  ⚠️  Avg Latency: {avg_latency:.0f}ms - Could be optimized")
    
    logger.info("\n💡 Recommendations:")
    
    if t1_skip_rate < 0.40:
        logger.info("  1. Increase memory ingestion - more facts = higher confidence")
        logger.info("  2. Fine-tune T1 skip threshold from 0.90 to 0.85")
        logger.info("  3. Add more query patterns to memory")
    
    if t2_skip_rate < 0.50:
        logger.info("  1. Verify CSSE verification is working correctly")
        logger.info("  2. Increase source requirements for T2 skip")
        logger.info("  3. Improve confidence scoring in verification layer")
    
    if avg_latency > 400:
        logger.info("  1. Consider caching frequently accessed queries")
        logger.info("  2. Optimize provider responses")
        logger.info("  3. Use local solvers (Z3) instead of remote calls")
    
    logger.info("\n🎯 Next Steps:")
    logger.info("  1. Deploy to staging environment")
    logger.info("  2. Collect metrics over 1 week")
    logger.info("  3. Refine skip decision thresholds")
    logger.info("  4. Train initial model with generated SPPE pairs")
    logger.info("  5. Deploy to production with gradual rollout")
    
    logger.info("="*80 + "\n")


def main():
    """Main orchestration function."""
    parser = argparse.ArgumentParser(
        description="Phase 5 Build & Test Orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline (init DB, run tests, analyze)
  python scripts/build_phase5.py --full

  # Step by step
  python scripts/build_phase5.py --db-init
  python scripts/build_phase5.py --run-tests
  python scripts/build_phase5.py --analyze

  # With custom database
  python scripts/build_phase5.py --db-init --db-url postgresql://user:pass@host/db
        """
    )
    
    parser.add_argument("--full", action="store_true", help="Run full pipeline (init + tests + analyze)")
    parser.add_argument("--db-init", action="store_true", help="Initialize database only")
    parser.add_argument("--run-tests", action="store_true", help="Run integration tests only")
    parser.add_argument("--analyze", action="store_true", help="Analyze results only")
    parser.add_argument("--db-url", default="postgresql://postgres:postgres@localhost/jimsai", help="Database URL")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if args.full:
        args.db_init = True
        args.run_tests = True
        args.analyze = True
    
    if not any([args.db_init, args.run_tests, args.analyze]):
        parser.print_help()
        return 1
    
    logger.info("\n" + "="*80)
    logger.info("PHASE 5 BUILD & TEST ORCHESTRATION")
    logger.info("="*80 + "\n")
    
    try:
        # Database initialization
        if args.db_init:
            logger.info("Step 1: Database Initialization")
            db_ok = asyncio.run(initialize_database(args.db_url))
            if not db_ok:
                logger.error("Database initialization failed. Exiting.")
                return 1
        
        # Initialize event store and run tests
        if args.run_tests:
            logger.info("\nStep 2: Initialize EventStore & Run Tests")
            event_store = asyncio.run(initialize_event_store(args.db_url))
            
            if not event_store:
                logger.error("EventStore initialization failed. Exiting.")
                return 1
            
            summary = asyncio.run(run_integration_tests(event_store))
            
            if summary and args.analyze:
                logger.info("\nStep 3: Analyze Results")
                analyze_results(summary)
            
            # Export results
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            results_file = WORKSPACE_ROOT / f"phase5_test_results_{timestamp}.json"
            
            if summary:
                import json
                with open(results_file, 'w') as f:
                    json.dump(summary, f, indent=2)
                logger.info(f"✅ Results saved to: {results_file}")
        
        logger.info("\n" + "="*80)
        logger.info("✅ PHASE 5 BUILD COMPLETE")
        logger.info("="*80 + "\n")
        return 0
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"\n❌ Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
