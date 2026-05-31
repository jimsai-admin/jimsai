# Phase 5 Implementation Quick Start Guide

**Status**: MVP Phase 5 Foundation Complete  
**Next Step**: Connect components and test end-to-end  

---

## What's Been Built

### ✅ Event Sourcing Foundation
```
prototype/jimsai/eventing/
  ├── __init__.py (exports)
  ├── events.py (40+ domain event types)
  ├── event_store.py (append-only log with projections)
  └── projections.py (4 CQRS read models)
```

**Events Implemented**:
- Query lifecycle: UserQueryReceived, QueryRooted
- Memory: SemanticSignatureCreated, MemoryIngested, SignatureInvalidated
- Verification: ProvenanceRecorded, ExecutionCached
- Reviews: HumanReviewRequested, HumanReviewCompleted
- Training: SPPEPairGenerated, TrainingTriggered, ModelActivated
- Generation: ImageGenerated, VideoGenerated, CreativeWritingGenerated
- Optimization: T1SkipDecided, T2SkipDecided

**Projections Implemented**:
- MemorySignatureProjection (materialized signature view)
- SPPEPairProjection (training pair statistics)
- ReviewQueueProjection (review status tracking)
- ProvenanceProjection (execution metrics)

### ✅ SPPE Pipeline
```
prototype/jimsai/training/
  └── sppe_generator.py (pair generation + scoring)
```

**Components**:
- SPPEPairGenerator: Create (Semantic IR, Preference, Output) triples
- Quality scoring: 0-1 based on verification + sources + confidence
- Signal efficiency: How informative for training
- SPPEBatchStore: Group pairs into batches for training

### ✅ Creative Writing Adapter
```
services/creative-writing/
  └── adapter.py (style-based content generation)
```

**Features**:
- Deterministic generation (templates + CSSE)
- Optional T2 for complex language
- Style types: poetic, technical, conversational, academic
- Verification: Content bounds checking
- Event logging for SPPE pair generation

---

## Architecture: Data Flow

```
User Query
  ↓
[1] Query Processing
    ├─ T1 Intent Parser (optional, skipped if confidence > 0.9)
    ├─ L1 Semantic Encoder
    ├─ L2 Memory Layer
    └─ Trace recorded to event store
  ↓
[2] Routing & Execution
    ├─ Capability Router decides route
    ├─ Provider execution (web search, docker, z3, etc.)
    ├─ Results cached
    └─ ProvenanceRecorded event emitted
  ↓
[3] CSSE Verification
    ├─ Verify facts vs sources
    ├─ Identify gaps
    ├─ High-confidence output prepared
    └─ Output confidence tracked
  ↓
[4] Optional T2 Rendering
    ├─ T2 skipped if CSSE confidence > 0.95
    ├─ T2 used for fluency/style (optional)
    └─ T2SkipDecided or T2Used event emitted
  ↓
[5] SPPE Pair Generation
    ├─ SPPEPairGenerator scores output quality
    ├─ Preference signal extracted
    ├─ Pair added to training batch
    └─ SPPEPairGenerated event emitted
  ↓
[6] Training Trigger Check
    ├─ Batch reaches 1000 pairs? → Trigger training
    ├─ Quality avg >= 0.80? → Trigger training
    ├─ 7 days elapsed? → Trigger training
    ├─ HumanReviewRequested event (training needs approval)
    └─ Wait for HumanReviewCompleted
  ↓
[7] Kaggle Training & Artifact Validation
    ├─ Start Kaggle job with SPPE batch
    ├─ Train encoder/reranker/world-model
    ├─ Validate against holdout test set
    ├─ ArtifactValidated event emitted
    ├─ Request human approval (ArtifactActivationRequested)
    └─ Hot-swap artifacts (ModelActivated event)
  ↓
[8] Memory & Event Stream
    ├─ All events appended to PostgreSQL event store
    ├─ Projections update read models
    ├─ Cache invalidation cascades
    └─ Audit trail complete
```

---

## Database Schema Setup

### Required Tables

```sql
-- Event store (append-only)
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    data JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    version INT NOT NULL,
    INDEX idx_aggregate (aggregate_id),
    INDEX idx_type (event_type),
    INDEX idx_time (created_at)
);

-- Projections (read models)
CREATE TABLE memory_signature_projection (
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
    invalidation_reason TEXT
);

CREATE TABLE sppe_pair_projection (
    pair_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    batch_id TEXT,
    quality_score FLOAT,
    signal_efficiency FLOAT,
    created_at TIMESTAMP
);

CREATE TABLE batch_statistics (
    batch_id TEXT PRIMARY KEY,
    pair_count INT DEFAULT 0,
    avg_quality FLOAT,
    avg_efficiency FLOAT,
    high_quality_count INT DEFAULT 0,
    updated_at TIMESTAMP
);

CREATE TABLE review_queue_projection (
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
    completed_at TIMESTAMP
);

CREATE TABLE provenance_projection (
    query_id TEXT PRIMARY KEY,
    capability_type TEXT,
    provider TEXT,
    input_hash TEXT,
    output_hash TEXT,
    verification_status TEXT,
    execution_time_ms FLOAT,
    cost FLOAT,
    created_at TIMESTAMP
);

CREATE TABLE cache_statistics_projection (
    cache_key TEXT PRIMARY KEY,
    workspace_id TEXT,
    hit_count INT DEFAULT 0,
    age_seconds INT,
    updated_at TIMESTAMP
);

CREATE TABLE query_metrics_projection (
    query_id TEXT PRIMARY KEY,
    workspace_id TEXT,
    used_t1 BOOLEAN,
    used_t2 BOOLEAN,
    memory_confidence FLOAT,
    output_confidence FLOAT,
    created_at TIMESTAMP
);

-- Training batches
CREATE TABLE sppe_batches (
    batch_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    status TEXT,  -- "open", "training", "completed", "failed"
    created_at TIMESTAMP,
    training_started_at TIMESTAMP,
    training_completed_at TIMESTAMP,
    pair_count INT DEFAULT 0
);

CREATE TABLE sppe_pairs (
    pair_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    semantic_ir_hash TEXT,
    output_hash TEXT,
    quality_score FLOAT,
    signal_efficiency FLOAT,
    provenance JSONB,
    created_at TIMESTAMP,
    FOREIGN KEY (batch_id) REFERENCES sppe_batches(batch_id)
);

-- Review queue
CREATE TABLE review_queue (
    review_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    item_type TEXT,
    item_id TEXT,
    priority INT,
    created_at TIMESTAMP,
    completed_at TIMESTAMP,
    reviewer_id TEXT,
    decision JSONB,
    status TEXT  -- "pending", "completed"
);

-- Workspace governance
CREATE TABLE workspace_governance (
    workspace_id TEXT PRIMARY KEY,
    provider_quotas JSONB,
    training_budget INT,
    approval_thresholds JSONB,
    audit_enabled BOOLEAN,
    created_at TIMESTAMP
);
```

---

## Integration: Connect Components

### 1. Initialize Event Store in App
```python
# prototype/app.py
from prototype.jimsai.eventing import EventStore
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# Setup
engine = create_async_engine("postgresql+asyncpg://...")
async_session = AsyncSession(engine)

# Initialize event store
event_store = await EventStore.create(async_session)

# Register projections
from prototype.jimsai.eventing import (
    MemorySignatureProjection,
    SPPEPairProjection,
    ReviewQueueProjection,
)

event_store.register_projection(MemorySignatureProjection(async_session))
event_store.register_projection(SPPEPairProjection(async_session))
event_store.register_projection(ReviewQueueProjection(async_session))
```

### 2. Hook SPPE Generation into Query Flow
```python
# After query execution and verification
from prototype.jimsai.training.sppe_generator import SPPEPairGenerator

sppe_generator = SPPEPairGenerator(event_store)

# In query handler
pair = await sppe_generator.generate_pair(
    query=user_query,
    semantic_ir=query_trace.semantic_ir,
    output=final_output,
    trace=query_trace
)

# Store pair
batch_id = await sppe_batch_store.add_pair(pair, workspace_id)

# Event emitted automatically (see sppe_generator.py line ~80)
await event_store.append(SPPEPairGenerated(
    aggregate_id=pair.pair_id,
    pair_id=pair.pair_id,
    workspace_id=workspace_id,
    semantic_ir_hash=pair.semantic_ir_hash,
    output_hash=pair.output_hash,
    quality_score=pair.quality_score,
    signal_efficiency=pair.signal_efficiency,
    batch_id=batch_id,
))
```

### 3. Creative Writing in Capability Router
```python
# services/capability_router.py
from services.creative_writing.adapter import CreativeWritingAdapter

creative_adapter = CreativeWritingAdapter(
    t2_renderer=t2_renderer,
    csse=csse,
    event_store=event_store
)

# When route = "creative_writing"
output = await creative_adapter.generate(
    request=CreativeRequest(
        prompt=user_query,
        style="conversational",
        length="medium"
    ),
    trace=execution_trace,
    workspace_id=workspace_id
)
```

---

## Testing the Integration

### 1. Unit Test: Event Store
```python
# tests/test_event_store.py
async def test_event_append_and_retrieve():
    from prototype.jimsai.eventing import EventStore
    from prototype.jimsai.eventing.events import UserQueryReceived
    
    store = await EventStore.create(db_session)
    
    # Append event
    event = UserQueryReceived(
        aggregate_id="workspace_123",
        workspace_id="workspace_123",
        user_id="user_123",
        query="What is machine learning?"
    )
    
    result = await store.append(event)
    assert result["event_type"] == "UserQueryReceived"
    
    # Retrieve
    events = await store.get_aggregate_events("workspace_123")
    assert len(events) >= 1
```

### 2. Integration Test: SPPE Pipeline
```python
# tests/test_sppe_pipeline.py
async def test_sppe_pair_generation_and_scoring():
    from prototype.jimsai.training.sppe_generator import (
        SPPEPairGenerator, ExecutionTrace
    )
    from uuid import uuid4
    
    generator = SPPEPairGenerator(event_store)
    
    trace = ExecutionTrace(
        query_id=uuid4(),
        query="What is 2+2?",
        semantic_confidence=0.95,
        verification_status="verified",
        sources=["math_solver"],
        hallucination_gaps=[],
        route_type="math_science",
        provider="z3"
    )
    
    pair = await generator.generate_pair(
        query="What is 2+2?",
        semantic_ir={"intent": "calculation", "entities": ["2", "2"]},
        output="4",
        trace=trace
    )
    
    assert pair.quality_score > 0.8
    assert pair.signal_efficiency > 0.5
```

### 3. End-to-End: Creative Writing
```python
# tests/test_creative_writing.py
async def test_creative_generation():
    from services.creative_writing.adapter import (
        CreativeWritingAdapter, CreativeRequest
    )
    
    adapter = CreativeWritingAdapter(
        t2_renderer=mock_t2,
        csse=mock_csse,
        event_store=mock_event_store
    )
    
    output = await adapter.generate(
        request=CreativeRequest(
            prompt="Describe the sunrise",
            style="poetic",
            length="medium"
        )
    )
    
    assert len(output.content) > 0
    assert output.style == "poetic"
    assert output.confidence > 0.7
```

---

## Monitoring & Observability

### Dashboard Queries

```python
# Get transformer thinning metrics
async def get_transformer_metrics(workspace_id):
    result = await event_store.db.execute("""
        SELECT 
            used_t1, used_t2,
            COUNT(*) as count
        FROM query_metrics_projection
        WHERE workspace_id = %s
        GROUP BY used_t1, used_t2
    """, workspace_id)
    
    # Analyze results
    # {"used_t1": False, "used_t2": False, "count": 125}  # 125 fully deterministic
    # {"used_t1": True, "used_t2": False, "count": 30}    # 30 T1 only
```

### Health Check
```python
async def check_system_health():
    # Event store health
    event_stats = await event_store.get_event_statistics()
    
    # Projection lag
    latest_event = event_stats["total_events"]
    projected_items = await db.count("memory_signature_projection")
    
    # Cache effectiveness
    cache_metrics = await projections.get_cache_metrics(workspace_id)
    
    # SPPE pair quality
    batch_stats = await batch_store.get_batch(current_batch_id)
    
    return {
        "event_count": event_stats["total_events"],
        "projection_lag": latest_event - projected_items,
        "cache_hit_rate": cache_metrics["cache_hit_rate"],
        "sppe_quality": batch_stats["quality_avg"],
    }
```

---

## Next Steps (Week-by-Week)

### Week 1: Database & Initialization
- [ ] Create PostgreSQL tables (above schema)
- [ ] Test EventStore.create() with real DB
- [ ] Verify projections fire on events
- [ ] Set up audit trail logging

### Week 2: SPPE Integration
- [ ] Hook sppe_generator into query handler
- [ ] Implement batch_store.add_pair()
- [ ] Test pair quality scoring
- [ ] Verify SPPE batch formation

### Week 3: Review Queue
- [ ] Create review_queue API endpoints
- [ ] Build review queue UI (React)
- [ ] Test approval workflows
- [ ] Implement review queue projection

### Week 4: Training Orchestration
- [ ] Implement training trigger logic
- [ ] Integrate Kaggle job submission
- [ ] Add artifact validation
- [ ] Test training approval flow

### Week 5: Creative Writing
- [ ] Integrate adapter into capability router
- [ ] Test deterministic vs T2 routing
- [ ] Verify style constraints
- [ ] Add to event logging

### Week 6-8: Transformer Thinning
- [ ] Implement T1/T2 skip decisions
- [ ] Add metrics tracking
- [ ] Monitor skip rates
- [ ] Optimize based on metrics

---

## Command Reference

### Run Tests
```bash
# All Phase 5 tests
pytest tests/phase5/ -v

# Event store only
pytest tests/phase5/test_event_store.py -v

# SPPE pipeline only
pytest tests/phase5/test_sppe_generator.py -v
```

### Database
```bash
# Create tables
psql -f /path/to/schema.sql

# Check event store
psql -c "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"

# View recent events
psql -c "SELECT * FROM events ORDER BY created_at DESC LIMIT 10"
```

### Monitoring
```bash
# Event statistics
psql -c "SELECT * FROM events GROUP BY event_type ORDER BY count DESC"

# SPPE batch status
psql -c "SELECT batch_id, pair_count, avg_quality FROM batch_statistics"

# Training queue
psql -c "SELECT * FROM review_queue WHERE item_type = 'training' AND status = 'pending'"
```

---

## Architecture Principles Implemented

### ✅ Immutability
- Events are append-only (no updates/deletes)
- Complete audit trail
- Deterministic replay for debugging

### ✅ Separation of Concerns
- Event store (write model) separate from projections (read models)
- Domain events vs infrastructure events
- Clean interfaces between components

### ✅ Scalability
- Event log can be distributed
- Projections can be parallelized
- Eventual consistency OK for analytics

### ✅ Observability
- Every action creates an event
- Full traceability of decisions
- Metrics derived from event stream

### ✅ Extensibility
- New event types easily added
- New projections can be layered on
- No breaking changes to event store

---

## Known Limitations & TODOs

### Current Phase 5
- ✅ Event sourcing foundation
- ✅ SPPE pipeline
- ✅ Creative writing adapter
- ⏳ Approval UI (partially)
- ⏳ Full training orchestration
- ⏳ Artifact hot-swap
- ⏳ Transformer thinning (logic exists, not fully integrated)

### Future Work
- [ ] Event schema versioning (handle migrations)
- [ ] Snapshot storage (for large aggregates)
- [ ] Distributed event store (Kafka/EventStoreDB)
- [ ] Analytics on event stream (complex queries)
- [ ] Dead-letter queue for failed handlers
- [ ] Event bus for cross-service communication

---

**Phase 5 MVP Foundation is Ready!** 🚀

Next: Connect components end-to-end, test with real queries, then scale to full production.
