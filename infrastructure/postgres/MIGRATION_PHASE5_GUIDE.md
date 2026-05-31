# Phase 5 PostgreSQL Migration Guide

## Overview

The `migration_phase5.sql` file extends the base schema (from `init.sql`) with all tables needed for Phase 5 production deployment. This migration adds:

- **Multi-tenant architecture** (workspaces, workspace members)
- **Event sourcing** (append-only event log for CQRS)
- **SPPE training pairs** (semantic quality scoring data)
- **Personalization engine** (learned patterns and preferences)
- **Workspace metrics & quotas** (usage tracking and enforcement)
- **Provider state tracking** (health status per provider per workspace)
- **Request audit trail** (full query/response history)
- **System monitoring** (global health metrics)
- **Helper views** (pre-built queries for analytics)
- **Stored procedures** (common operations automation)

## How to Apply

### Option 1: Using psql (Recommended)
```bash
# Connect to your Supabase PostgreSQL database
psql postgresql://username:password@host:5432/database

# Run the migration
\i infrastructure/postgres/migration_phase5.sql

# Verify tables were created
\dt
```

### Option 2: Using Supabase Dashboard
1. Open Supabase dashboard → SQL Editor
2. Create a new query
3. Copy the entire contents of `migration_phase5.sql`
4. Run the query

### Option 3: Using Python Script
```python
import psycopg2
from pathlib import Path

# Read migration
migration_sql = Path('infrastructure/postgres/migration_phase5.sql').read_text()

# Connect to database
conn = psycopg2.connect(
    dbname="your_db",
    user="your_user",
    password="your_password",
    host="your_host"
)

cursor = conn.cursor()
cursor.execute(migration_sql)
conn.commit()
cursor.close()
conn.close()

print("✓ Migration complete!")
```

## Schema Overview

### 1. **Workspace Tables** (Multi-tenancy)
```
workspaces
├── workspace_members
└── workspace_adapters
```

**Purpose:** Multi-tenant isolation  
**Key Columns:**
- `skip_t1_threshold` - When to skip T1 model
- `skip_t2_threshold` - When to skip T2 model  
- `monthly_query_limit` - Query quota per month
- `monthly_cost_limit` - Cost quota per month

### 2. **Event Sourcing** (Append-only log)
```
jimsai_events
```

**Purpose:** Complete audit trail and event replay  
**Key Columns:**
- `event_type` - Type of event (query_started, query_completed, etc.)
- `payload` - Event data in JSON
- `correlation_id` - Link related events
- `user_id` - Who triggered the event

**Indexes:** event_type, workspace_id, recorded_at, correlation_id

### 3. **SPPE Training Pairs** (Quality scoring)
```
sppe_pairs
```

**Purpose:** Store semantic quality scores for training  
**Key Columns:**
- `sppe_quality` - Composite quality score (0-1)
- `semantic_score` - Semantic relevance (25%)
- `verification_score` - Source verification (30%)
- `source_score` - Source attribution (20%)
- `gap_score` - Coverage gaps (15%)
- `efficiency_score` - Response efficiency (10%)
- `t1_skipped` / `t2_skipped` - Which models were bypassed

**Total Weighting:** 25% + 30% + 20% + 15% + 10% = 100%

### 4. **Personalization** (Learned patterns)
```
query_patterns
├── user_preferences
└── workspace_adapters
```

**Purpose:** Learn from workspace usage patterns  
**Key Data:**
- Recurring query types by domain
- User style preferences (concise vs detailed)
- Optimal threshold settings per workspace

### 5. **Metrics & Quotas** (Usage tracking)
```
workspace_metrics
└── workspace_quotas
```

**Purpose:** Track performance and enforce limits  
**Key Metrics:**
- `avg_quality` - Average response quality
- `avg_confidence` - Model confidence
- `t1_skip_rate` / `t2_skip_rate` - How often models are skipped
- `total_cost` - Monthly cost

### 6. **Provider State** (Health tracking)
```
provider_state
```

**Purpose:** Monitor each provider per workspace  
**Tracks:**
- Health status (healthy/unhealthy)
- Latency average
- Success/error counts

### 7. **Request Audit** (Full history)
```
request_audit
```

**Purpose:** Complete query/response audit trail  
**Keeps:**
- Original query
- Response summary
- Processing details (latency, costs)
- Which providers were used

### 8. **System Metrics** (Global monitoring)
```
system_metrics
```

**Purpose:** Global system health and performance  
**Tracks:**
- Total workspaces and active workspaces
- Global query count and error rate
- Provider status across all workspaces
- Resource usage (memory, CPU)

## Views Included

### `workspace_performance_summary`
Quick view of current performance per workspace:
```sql
SELECT * FROM workspace_performance_summary;
```
**Shows:** Queries, confidence, quality, skip rates, costs per workspace

### `top_workspaces_by_quality`
Top performing workspaces ranked by quality:
```sql
SELECT * FROM top_workspaces_by_quality LIMIT 10;
```

### `workspace_event_stream`
Timeline of all events per workspace:
```sql
SELECT * FROM workspace_event_stream WHERE workspace_id = 'ws_abc' LIMIT 100;
```

### `sppe_quality_insights`
Daily quality trends:
```sql
SELECT * FROM sppe_quality_insights WHERE workspace_id = 'ws_abc' ORDER BY date DESC;
```

## Stored Procedures Included

### `record_workspace_query()`
Record a new query and automatically update all metrics:
```sql
SELECT record_workspace_query(
  'ws_test_001',
  'user_123',
  'What are neural networks?',
  'Neural networks are...',
  0.92,  -- confidence
  0.88,  -- quality
  false, -- t1_skipped
  false  -- t2_skipped
  0.05   -- cost
);
```

### `get_workspace_quality_trend()`
Get quality metrics over time:
```sql
SELECT * FROM get_workspace_quality_trend('ws_test_001', 30);
-- Returns: date, avg_quality, query_count for last 30 days
```

## Integration with Python

### From providers.py - Supabase Adapter
```python
from prototype.jimsai.providers import SupabaseAdapter, SupabaseConfig

adapter = SupabaseAdapter(SupabaseConfig.from_env())

# Append event
event = {
    "event_type": "query_started",
    "query": "What are neural networks?",
    "user_id": "user_123"
}
adapter.append_event(event)

# Get metrics
metrics = adapter.get_metrics("ws_test_001")
print(f"Avg Quality: {metrics['avg_quality']}")
```

### From production_pipeline.py
```python
from services.production_pipeline import ProductionPipeline

pipeline = ProductionPipeline()

# Process request (automatically records to PostgreSQL)
response = pipeline.process_request({
    "workspace_id": "ws_test_001",
    "query": "What are neural networks?",
    "user_id": "user_123"
})

# Quality metrics automatically stored in sppe_pairs table
```

## Index Strategy

All critical columns have indexes for query performance:

| Table | Index | Purpose |
|-------|-------|---------|
| `jimsai_events` | workspace_id, event_type, recorded_at, correlation_id | Event stream queries |
| `sppe_pairs` | workspace_id, sppe_quality, created_at | Quality analytics |
| `workspace_metrics` | workspace_id, period_start/end | Metric lookups |
| `request_audit` | workspace_id, user_id, created_at | Audit trail queries |

## Data Retention

### Recommended Cleanup Schedule
```sql
-- Run monthly to archive old data
DELETE FROM jimsai_events 
WHERE recorded_at < NOW() - INTERVAL '90 days'
  AND workspace_id IN (
    SELECT id FROM workspaces WHERE data_retention_days = 90
  );

-- Run yearly to clean old snapshots
DELETE FROM workspace_metrics 
WHERE period_end < NOW() - INTERVAL '365 days';
```

### Set via Workspace Config
```sql
UPDATE workspaces 
SET data_retention_days = 90 
WHERE id = 'ws_test_001';
```

## Monitoring Queries

### Get workspace health
```sql
SELECT 
  w.name,
  wm.avg_quality,
  wm.t1_skip_rate,
  wm.t2_skip_rate,
  wm.total_queries,
  wm.total_cost
FROM workspaces w
LEFT JOIN workspace_metrics wm ON w.id = wm.workspace_id
WHERE w.is_active = true
ORDER BY wm.avg_quality DESC;
```

### Get provider status
```sql
SELECT 
  workspace_id,
  provider_name,
  is_healthy,
  avg_latency_ms,
  success_count,
  error_count
FROM provider_state
ORDER BY provider_name, workspace_id;
```

### Get cost breakdown
```sql
SELECT 
  workspace_id,
  SUM(estimated_cost) as total_cost,
  COUNT(*) as request_count,
  AVG(response_quality) as avg_quality
FROM request_audit
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY workspace_id
ORDER BY total_cost DESC;
```

### Get quality trend
```sql
SELECT * FROM get_workspace_quality_trend('ws_test_001', 30)
ORDER BY date DESC;
```

## Troubleshooting

### Issue: Table already exists
**Error:** `ERROR: relation "workspaces" already exists`  
**Fix:** Migration is idempotent (uses `IF NOT EXISTS`), but run from clean state

### Issue: Permission denied
**Error:** `ERROR: permission denied for schema public`  
**Fix:** Ensure you're connected with a user that has DDL permissions
```sql
-- From superuser account
GRANT ALL ON SCHEMA public TO jimsai_app_role;
```

### Issue: Foreign key constraint fails
**Error:** `ERROR: insert or update on table violates foreign key`  
**Fix:** Ensure workspace exists before inserting related records
```sql
INSERT INTO workspaces (...) VALUES (...) RETURNING id;
-- Use returned workspace ID for other inserts
```

## Next Steps

1. **Apply migration:**
   ```bash
   psql your_db < infrastructure/postgres/migration_phase5.sql
   ```

2. **Verify tables created:**
   ```sql
   SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
   ```

3. **Initialize workspace:**
   ```sql
   INSERT INTO workspaces (id, organization_id, name, owner_id) 
   VALUES ('ws_test_001', 'org_001', 'Test Workspace', 'user_001');
   ```

4. **Run production pipeline:**
   ```bash
   export JIMSAI_ENV=production
   python services/production_pipeline.py
   ```

5. **Monitor metrics:**
   ```bash
   psql your_db -c "SELECT * FROM workspace_performance_summary;"
   ```

## Files Reference

- **Schema Definition:** `infrastructure/postgres/migration_phase5.sql`
- **Base Schema:** `infrastructure/postgres/init.sql`
- **Supabase Adapter:** `prototype/jimsai/providers.py`
- **Production Pipeline:** `services/production_pipeline.py`
- **Workspace Manager:** `prototype/jimsai/workspaces.py`

---

**Last Updated:** May 31, 2026  
**Status:** Ready for Production  
**Next Phase:** Deploy to staging environment
