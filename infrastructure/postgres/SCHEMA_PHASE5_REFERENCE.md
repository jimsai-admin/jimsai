# Phase 5 Database Schema - Visual Reference

## Complete Table Relationships

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MULTI-TENANT WORKSPACE LAYER                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────┐      ┌──────────────────────┐                   │
│  │   workspaces         │      │ workspace_members    │                   │
│  ├──────────────────────┤      ├──────────────────────┤                   │
│  │ id (PK)              │      │ id (PK)              │                   │
│  │ org_id               │      │ workspace_id (FK) ───┼─→ workspaces.id │
│  │ name                 │      │ user_id              │                   │
│  │ owner_id             │      │ role                 │                   │
│  │ skip_t1_threshold    │      │ created_at           │                   │
│  │ skip_t2_threshold    │      └──────────────────────┘                   │
│  │ monthly_query_limit  │                                                 │
│  │ monthly_cost_limit   │      ┌──────────────────────┐                   │
│  │ is_active            │      │ workspace_adapters   │                   │
│  │ created_at           │      ├──────────────────────┤                   │
│  │ updated_at           │      │ id (PK)              │                   │
│  └──────────────────────┘      │ workspace_id (FK) ───┼─→ workspaces.id │
│                                 │ adapter_type         │                   │
│  ┌──────────────────────┐      │ parameters           │                   │
│  │ workspace_metrics    │      │ t1_skip_threshold    │                   │
│  ├──────────────────────┤      │ t2_skip_threshold    │                   │
│  │ id (PK)              │      │ avg_quality          │                   │
│  │ workspace_id (FK) ───┼──→───┤ success_rate         │                   │
│  │ total_queries        │      │ pairs_trained_on     │                   │
│  │ avg_confidence       │      └──────────────────────┘                   │
│  │ avg_quality          │                                                 │
│  │ t1_skip_rate         │      ┌──────────────────────┐                   │
│  │ t2_skip_rate         │      │ workspace_quotas     │                   │
│  │ total_cost           │      ├──────────────────────┤                   │
│  │ sppe_pairs_count     │      │ id (PK)              │                   │
│  │ period_start         │      │ workspace_id (FK) ───┼─→ workspaces.id │
│  │ period_end           │      │ date                 │                   │
│  └──────────────────────┘      │ daily_queries        │                   │
│                                 │ daily_cost           │                   │
│                                 │ month                │                   │
│                                 │ monthly_queries      │                   │
│                                 │ monthly_cost         │                   │
│                                 └──────────────────────┘                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         EVENT SOURCING & AUDIT LAYER                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────┐                                                  │
│  │   jimsai_events      │ (Append-only event log)                          │
│  ├──────────────────────┤                                                  │
│  │ id (PK)              │                                                  │
│  │ event_id (UNIQUE)    │                                                  │
│  │ workspace_id (FK) ───┼──→ workspaces.id                                 │
│  │ event_type           │                                                  │
│  │ payload (JSONB)      │                                                  │
│  │ version              │                                                  │
│  │ correlation_id       │ (Links related events)                           │
│  │ causation_id         │ (Cause-effect chain)                             │
│  │ user_id              │                                                  │
│  │ event_timestamp      │                                                  │
│  │ recorded_at          │                                                  │
│  └──────────────────────┘                                                  │
│         ▲                                                                    │
│         │ (Sourced by)                                                      │
│         │                                                                    │
│  ┌──────┴──────────────┐                                                   │
│  │  request_audit      │ (Full query/response audit)                       │
│  ├─────────────────────┤                                                   │
│  │ id (PK)             │                                                   │
│  │ workspace_id (FK) ──┼──→ workspaces.id                                  │
│  │ user_id             │                                                   │
│  │ request_id          │                                                   │
│  │ query               │                                                   │
│  │ response_summary    │                                                   │
│  │ response_quality    │                                                   │
│  │ t1_skipped          │                                                   │
│  │ t2_skipped          │                                                   │
│  │ total_latency_ms    │                                                   │
│  │ providers_used[]    │                                                   │
│  │ estimated_cost      │                                                   │
│  │ created_at          │                                                   │
│  └─────────────────────┘                                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                      SPPE TRAINING DATA & QUALITY LAYER                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────┐                                                  │
│  │    sppe_pairs        │ (Quality scoring training data)                  │
│  ├──────────────────────┤                                                  │
│  │ id (PK)              │                                                  │
│  │ workspace_id (FK) ───┼──→ workspaces.id                                 │
│  │ query                │                                                  │
│  │ response             │                                                  │
│  │ semantic_score (0.25 weight)      ┐                                     │
│  │ verification_score (0.30 weight)  │ ─→ sppe_quality                    │
│  │ source_score (0.20 weight)        │                                     │
│  │ gap_score (0.15 weight)           │                                     │
│  │ efficiency_score (0.10 weight)    ┘                                     │
│  │ sppe_quality         │                                                  │
│  │ model_t1             │                                                  │
│  │ model_t2             │                                                  │
│  │ t1_skipped           │                                                  │
│  │ t2_skipped           │                                                  │
│  │ sources (JSONB)      │                                                  │
│  │ created_at           │                                                  │
│  └──────────────────────┘                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                      PERSONALIZATION ENGINE LAYER                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────┐      ┌──────────────────────┐                   │
│  │  query_patterns      │      │ user_preferences     │                   │
│  ├──────────────────────┤      ├──────────────────────┤                   │
│  │ id (PK)              │      │ id (PK)              │                   │
│  │ workspace_id (FK) ───┼──┐   │ workspace_id (FK) ───┼──┐               │
│  │ user_id              │  │   │ user_id              │  │               │
│  │ pattern_type         │  │   │ preference_key       │  │               │
│  │ pattern_value        │  │   │ preference_value     │  │               │
│  │ occurrence_count     │  │   │ strength             │  │               │
│  │ first_seen           │  │   │ created_at           │  │               │
│  │ last_seen            │  │   │ updated_at           │  │               │
│  │ confidence           │  │   └──────────────────────┘  │               │
│  │ created_at           │  │                              │               │
│  └──────────────────────┘  │                              │               │
│                            └──→ Both use workspace_id    │               │
│                                                           │               │
│  ┌──────────────────────┐                                │               │
│  │ workspace_adapters   │  (Learned per-workspace models)               │
│  ├──────────────────────┤                                │               │
│  │ id (PK)              │                                │               │
│  │ workspace_id (FK) ───┼────────────────────────────────┘               │
│  │ adapter_type         │                                                 │
│  │ parameters (JSONB)   │                                                 │
│  │ t1_skip_threshold    │ ← Personalized from query patterns             │
│  │ t2_skip_threshold    │ ← Personalized from query patterns             │
│  │ confidence_threshold │ ← Personalized from user preferences           │
│  │ avg_quality          │                                                 │
│  │ success_rate         │                                                 │
│  │ pairs_trained_on     │                                                 │
│  │ created_at           │                                                 │
│  │ updated_at           │                                                 │
│  └──────────────────────┘                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                      PROVIDER STATE & MONITORING LAYER                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────┐      ┌──────────────────────┐                   │
│  │  provider_state      │      │  system_metrics      │                   │
│  ├──────────────────────┤      ├──────────────────────┤                   │
│  │ id (PK)              │      │ id (PK)              │                   │
│  │ workspace_id (FK) ───┼──┐   │ metric_timestamp     │                   │
│  │ provider_name        │  │   │ total_workspaces     │                   │
│  │ is_healthy           │  │   │ active_workspaces    │                   │
│  │ last_check_at        │  │   │ total_queries        │                   │
│  │ last_check_result    │  │   │ avg_latency_ms       │                   │
│  │ avg_latency_ms       │  │   │ error_rate           │                   │
│  │ error_count          │  │   │ provider_status      │                   │
│  │ success_count        │  │   │ memory_usage_mb      │                   │
│  │ config (JSONB)       │  │   │ cpu_usage_percent    │                   │
│  │ updated_at           │  │   │ recorded_at          │                   │
│  └──────────────────────┘  │   └──────────────────────┘                   │
│                            └────→ Global metrics                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Index Strategy

### High-Frequency Read Queries
```
jimsai_events:
  - (workspace_id, recorded_at DESC) - Event stream retrieval
  - event_type - Event type filtering
  - correlation_id - Event chain lookup

sppe_pairs:
  - (workspace_id, sppe_quality DESC) - Top quality pairs
  - (workspace_id, created_at DESC) - Recent pairs
  - sppe_quality DESC - Global quality ranking

workspace_metrics:
  - workspace_id - Metric lookup
  - (period_start, period_end) - Time range queries

request_audit:
  - (workspace_id, user_id, created_at DESC) - User audit trail
  - (workspace_id, created_at DESC) - Workspace audit trail
  - user_id - Per-user activity
```

## Data Flow

```
Query Request
    ↓
┌─────────────────────────────────────────┐
│ Production Pipeline                     │
│  - Parse intent (Groq T1)              │
│  - Check confidence & skip threshold   │
│  - If skip: use cached response        │
│  - If not skip: render fluency (T2)    │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Record Events (jimsai_events)           │
│  - QueryStarted                         │
│  - IntentParsed                         │
│  - SkipDecision (T1/T2)                 │
│  - ResponseGenerated                    │
│  - QueryCompleted                       │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Generate SPPE Pair                      │
│  - Calculate quality scores             │
│  - Compute composite sppe_quality       │
│  - Store in sppe_pairs table           │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Update Workspace Metrics                │
│  - Increment query counters             │
│  - Update confidence averages           │
│  - Update quality metrics               │
│  - Update skip rates                    │
│  - Update costs                         │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Personalization Learning                │
│  - Extract query patterns               │
│  - Record user preferences              │
│  - Update workspace_adapters            │
│  - Adjust thresholds if needed          │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Record Audit Trail                      │
│  - Store in request_audit table         │
│  - Link events with correlation_id      │
│  - Track latency and providers          │
└─────────────────────────────────────────┘
    ↓
Response to User
```

## Common Query Patterns

### 1. Get Workspace Health
```sql
SELECT 
  w.id, w.name,
  wm.total_queries,
  wm.avg_quality,
  wm.avg_confidence,
  wm.t1_skip_rate,
  wm.t2_skip_rate,
  wm.total_cost
FROM workspaces w
LEFT JOIN workspace_metrics wm ON w.id = wm.workspace_id
WHERE w.is_active = true
ORDER BY wm.avg_quality DESC;
```

### 2. Get Recent Query Activity
```sql
SELECT 
  event_timestamp,
  event_type,
  user_id,
  payload ->> 'query' as query,
  payload ->> 'confidence' as confidence
FROM jimsai_events
WHERE workspace_id = 'ws_test_001'
  AND event_type = 'QueryCompleted'
ORDER BY event_timestamp DESC
LIMIT 50;
```

### 3. Get SPPE Quality Trend
```sql
SELECT 
  DATE_TRUNC('day', created_at)::DATE as date,
  COUNT(*) as pairs,
  AVG(sppe_quality) as avg_quality,
  MIN(sppe_quality) as min_quality,
  MAX(sppe_quality) as max_quality
FROM sppe_pairs
WHERE workspace_id = 'ws_test_001'
  AND created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY date DESC;
```

### 4. Get Cost Breakdown
```sql
SELECT 
  provider_name,
  COUNT(*) as usage_count,
  AVG(CAST(last_check_result ->> 'latency_ms' AS FLOAT)) as avg_latency,
  SUM(CAST(last_check_result ->> 'cost' AS FLOAT)) as total_cost
FROM provider_state
WHERE workspace_id = 'ws_test_001'
GROUP BY provider_name;
```

### 5. Get Learned Patterns
```sql
SELECT 
  pattern_type,
  pattern_value,
  occurrence_count,
  confidence,
  last_seen
FROM query_patterns
WHERE workspace_id = 'ws_test_001'
ORDER BY occurrence_count DESC
LIMIT 20;
```

## Table Sizes (Estimated)

| Table | Rows per Workspace | Row Size | Annual Size |
|-------|-------------------|----------|------------|
| jimsai_events | 100,000-1M | 500B | 500MB-5GB |
| sppe_pairs | 50,000-500K | 800B | 400MB-4GB |
| request_audit | 50,000-500K | 1KB | 500MB-5GB |
| query_patterns | 100-1K | 300B | ~1MB |
| user_preferences | 100-1K | 200B | ~1MB |
| workspace_metrics | 12-365 | 400B | ~5MB |

**Total per Workspace:** ~1-15GB per year depending on query volume

## Retention Policy

- **Events (jimsai_events):** 90 days (configurable per workspace)
- **SPPE Pairs:** Indefinite (training data)
- **Request Audit:** 30-90 days (audit trail)
- **Metrics Snapshots:** 12 months (annual trend analysis)

---

**Schema Version:** 1.0  
**Last Updated:** May 31, 2026  
**Status:** Ready for Production
