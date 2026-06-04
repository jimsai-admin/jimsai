"""
Phase 5 PostgreSQL Database Initialization Script

This script sets up the PostgreSQL database schema for Phase 5 event sourcing,
SPPE training pipeline, and CQRS projections.

Usage:
    python scripts/phase5_db_init.py --connection-string postgresql://user:password@localhost/jimsai
"""

import asyncio
import argparse
from typing import Optional
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
except ImportError:
    logger.error("SQLAlchemy not installed. Install with: pip install sqlalchemy psycopg[binary]")
    exit(1)

# Full database schema for Phase 5
SCHEMA_SQL = """
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

-- Memory Signature Projection (CQRS Read Model)
CREATE TABLE IF NOT EXISTS memory_signature_projection (
    signature_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    structured_content JSONB,
    entities JSONB,
    relations JSONB,
    causal_links JSONB,
    confidence FLOAT,
    source_query TEXT,
    vector_id TEXT,
    supabase_id TEXT,
    r2_key TEXT,
    freshness_epoch INT,
    valid BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    persisted_at TIMESTAMP,
    invalidated_at TIMESTAMP,
    invalidation_reason TEXT,
    INDEX idx_workspace ON memory_signature_projection(workspace_id),
    INDEX idx_valid ON memory_signature_projection(valid)
);

-- SPPE Pair Projection (Training Data)
CREATE TABLE IF NOT EXISTS sppe_pair_projection (
    pair_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    batch_id TEXT,
    semantic_ir JSONB,
    semantic_ir_hash TEXT,
    preference FLOAT,
    output TEXT,
    output_hash TEXT,
    quality_score FLOAT,
    signal_efficiency FLOAT,
    provenance JSONB,
    created_at TIMESTAMP,
    INDEX idx_workspace ON sppe_pair_projection(workspace_id),
    INDEX idx_batch ON sppe_pair_projection(batch_id),
    INDEX idx_quality ON sppe_pair_projection(quality_score)
);

-- Batch Statistics (Training Batches)
CREATE TABLE IF NOT EXISTS batch_statistics (
    batch_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    pair_count INT DEFAULT 0,
    avg_quality FLOAT,
    avg_efficiency FLOAT,
    high_quality_count INT DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    triggered_at TIMESTAMP,
    INDEX idx_workspace ON batch_statistics(workspace_id),
    INDEX idx_status ON batch_statistics(status)
);

-- Review Queue Projection (Human Approvals)
CREATE TABLE IF NOT EXISTS review_queue_projection (
    review_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    item_type TEXT,
    item_id TEXT,
    status TEXT,
    priority INT,
    reviewer_id TEXT,
    decision JSONB,
    feedback TEXT,
    created_at TIMESTAMP,
    completed_at TIMESTAMP,
    INDEX idx_workspace ON review_queue_projection(workspace_id),
    INDEX idx_status ON review_queue_projection(status)
);

-- Provenance Projection (Execution Metrics)
CREATE TABLE IF NOT EXISTS provenance_projection (
    query_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    capability_type TEXT,
    provider TEXT,
    input_hash TEXT,
    output_hash TEXT,
    verification_status TEXT,
    execution_time_ms FLOAT,
    sources JSONB,
    gaps JSONB,
    cache_hit BOOLEAN,
    created_at TIMESTAMP,
    INDEX idx_workspace ON provenance_projection(workspace_id),
    INDEX idx_provider ON provenance_projection(provider)
);

-- Cache Statistics Projection
CREATE TABLE IF NOT EXISTS cache_statistics_projection (
    cache_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    provider TEXT,
    hit_count INT DEFAULT 0,
    miss_count INT DEFAULT 0,
    avg_latency_ms FLOAT,
    last_updated TIMESTAMP,
    INDEX idx_workspace ON cache_statistics_projection(workspace_id)
);

-- Query Metrics Projection (Dashboard)
CREATE TABLE IF NOT EXISTS query_metrics_projection (
    metric_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    date DATE NOT NULL,
    total_queries INT DEFAULT 0,
    t1_used_count INT DEFAULT 0,
    t1_skipped_count INT DEFAULT 0,
    t2_used_count INT DEFAULT 0,
    t2_skipped_count INT DEFAULT 0,
    avg_memory_confidence FLOAT,
    avg_output_confidence FLOAT,
    avg_latency_ms FLOAT,
    cost_total FLOAT,
    created_at TIMESTAMP,
    UNIQUE(workspace_id, date),
    INDEX idx_workspace ON query_metrics_projection(workspace_id),
    INDEX idx_date ON query_metrics_projection(date)
);
"""


async def init_database(connection_string: str) -> None:
    """Initialize the database schema."""
    logger.info(f"Connecting to database: {connection_string}")
    
    try:
        # Create async engine
        engine = create_async_engine(
            connection_string,
            echo=False,
            pool_pre_ping=True
        )
        
        # Execute schema
        async with engine.begin() as conn:
            logger.info("Executing schema SQL...")
            # Split and execute each CREATE TABLE separately
            for statement in SCHEMA_SQL.split(';'):
                statement = statement.strip()
                if statement:
                    try:
                        await conn.execute(text(statement))
                        logger.info(f"✓ Executed: {statement[:60]}...")
                    except Exception as e:
                        logger.error(f"Error executing: {statement[:60]}... - {e}")
        
        logger.info("✅ Database initialization complete!")
        
        # Verify tables were created
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            tables = [row[0] for row in await result.fetchall()]
            logger.info(f"Created tables: {', '.join(sorted(tables))}")
        
        await engine.dispose()
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Initialize Phase 5 PostgreSQL schema")
    parser.add_argument(
        "--connection-string",
        default="postgresql+asyncpg://postgres:postgres@localhost/jimsai",
        help="PostgreSQL connection string (default: postgresql://localhost/jimsai)"
    )
    args = parser.parse_args()
    
    asyncio.run(init_database(args.connection_string))


if __name__ == "__main__":
    main()
