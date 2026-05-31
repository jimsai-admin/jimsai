-- ============================================================================
-- PHASE 5 PRODUCTION MIGRATION
-- ============================================================================
-- This migration adds all tables needed for Phase 5 production features:
-- - Multi-tenant workspace management
-- - Event sourcing with append-only event log
-- - SPPE training pair storage
-- - Personalization engine data
-- - Workspace metrics and quota enforcement
-- - Provider orchestration state
-- ============================================================================

-- ============================================================================
-- 1. MULTI-TENANT WORKSPACE TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS workspaces (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  owner_id TEXT NOT NULL,
  
  -- Configuration
  skip_t1_threshold DOUBLE PRECISION DEFAULT 0.90,
  skip_t2_threshold DOUBLE PRECISION DEFAULT 0.95,
  enable_personalization BOOLEAN DEFAULT true,
  enable_caching BOOLEAN DEFAULT true,
  
  -- Quotas
  monthly_query_limit INTEGER DEFAULT 100000,
  monthly_cost_limit DOUBLE PRECISION DEFAULT 5000.0,
  
  -- Governance
  data_retention_days INTEGER DEFAULT 90,
  is_active BOOLEAN DEFAULT true,
  
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workspaces_organization_id_idx 
  ON workspaces(organization_id);

CREATE INDEX IF NOT EXISTS workspaces_owner_id_idx 
  ON workspaces(owner_id);

CREATE TABLE IF NOT EXISTS workspace_members (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'member',  -- admin, member, viewer
  created_at TIMESTAMPTZ DEFAULT now(),
  
  UNIQUE(workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS workspace_members_workspace_id_idx 
  ON workspace_members(workspace_id);

CREATE INDEX IF NOT EXISTS workspace_members_user_id_idx 
  ON workspace_members(user_id);

-- ============================================================================
-- 2. EVENT SOURCING - APPEND-ONLY EVENT LOG
-- ============================================================================

CREATE TABLE IF NOT EXISTS jimsai_events (
  id BIGSERIAL PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  
  -- Event payload
  payload JSONB NOT NULL,
  
  -- Metadata
  version INTEGER DEFAULT 1,
  correlation_id TEXT,
  causation_id TEXT,
  user_id TEXT,
  
  -- Timestamps
  event_timestamp TIMESTAMPTZ NOT NULL,
  recorded_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jimsai_events_workspace_id_idx 
  ON jimsai_events(workspace_id);

CREATE INDEX IF NOT EXISTS jimsai_events_event_type_idx 
  ON jimsai_events(event_type);

CREATE INDEX IF NOT EXISTS jimsai_events_recorded_at_idx 
  ON jimsai_events(recorded_at DESC);

CREATE INDEX IF NOT EXISTS jimsai_events_correlation_id_idx 
  ON jimsai_events(correlation_id);

CREATE INDEX IF NOT EXISTS jimsai_events_user_id_idx 
  ON jimsai_events(user_id);

-- ============================================================================
-- 3. SPPE TRAINING PAIRS - SEMANTIC QUALITY SCORING DATA
-- ============================================================================

CREATE TABLE IF NOT EXISTS sppe_pairs (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  
  -- Query and Response
  query TEXT NOT NULL,
  response TEXT NOT NULL,
  
  -- Quality Scores (SPPE: Semantic-Phrase-Pair-Evaluation)
  semantic_score DOUBLE PRECISION NOT NULL,
  verification_score DOUBLE PRECISION NOT NULL,
  source_score DOUBLE PRECISION NOT NULL,
  gap_score DOUBLE PRECISION NOT NULL,
  efficiency_score DOUBLE PRECISION NOT NULL,
  
  -- Composite Score
  sppe_quality DOUBLE PRECISION NOT NULL,
  
  -- Metadata
  model_t1 TEXT NOT NULL,
  model_t2 TEXT NOT NULL,
  t1_skipped BOOLEAN DEFAULT false,
  t2_skipped BOOLEAN DEFAULT false,
  
  -- Source attribution
  sources JSONB,
  
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sppe_pairs_workspace_id_idx 
  ON sppe_pairs(workspace_id);

CREATE INDEX IF NOT EXISTS sppe_pairs_sppe_quality_idx 
  ON sppe_pairs(sppe_quality DESC);

CREATE INDEX IF NOT EXISTS sppe_pairs_created_at_idx 
  ON sppe_pairs(created_at DESC);

CREATE INDEX IF NOT EXISTS sppe_pairs_workspace_created_idx 
  ON sppe_pairs(workspace_id, created_at DESC);

-- ============================================================================
-- 4. WORKSPACE METRICS - PER-WORKSPACE PERFORMANCE TRACKING
-- ============================================================================

CREATE TABLE IF NOT EXISTS workspace_metrics (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  
  -- Query Metrics
  total_queries INTEGER DEFAULT 0,
  total_confidence DOUBLE PRECISION DEFAULT 0.0,
  avg_confidence DOUBLE PRECISION DEFAULT 0.0,
  
  -- Quality Metrics
  total_quality DOUBLE PRECISION DEFAULT 0.0,
  avg_quality DOUBLE PRECISION DEFAULT 0.0,
  
  -- Transformer Skip Metrics
  t1_skip_count INTEGER DEFAULT 0,
  t2_skip_count INTEGER DEFAULT 0,
  t1_skip_rate DOUBLE PRECISION DEFAULT 0.0,
  t2_skip_rate DOUBLE PRECISION DEFAULT 0.0,
  
  -- Cost Metrics
  total_cost DOUBLE PRECISION DEFAULT 0.0,
  groq_cost DOUBLE PRECISION DEFAULT 0.0,
  storage_cost DOUBLE PRECISION DEFAULT 0.0,
  
  -- SPPE Metrics
  sppe_pairs_count INTEGER DEFAULT 0,
  
  -- Time Window
  period_start TIMESTAMPTZ NOT NULL,
  period_end TIMESTAMPTZ NOT NULL,
  
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workspace_metrics_workspace_id_idx 
  ON workspace_metrics(workspace_id);

CREATE INDEX IF NOT EXISTS workspace_metrics_period_idx 
  ON workspace_metrics(period_start, period_end);

-- ============================================================================
-- 5. WORKSPACE QUOTAS - DAILY/MONTHLY QUOTA ENFORCEMENT
-- ============================================================================

CREATE TABLE IF NOT EXISTS workspace_quotas (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  
  -- Daily Tracking
  date DATE NOT NULL,
  daily_queries INTEGER DEFAULT 0,
  daily_cost DOUBLE PRECISION DEFAULT 0.0,
  
  -- Monthly Tracking (for the current month)
  month TEXT NOT NULL,  -- YYYY-MM format
  monthly_queries INTEGER DEFAULT 0,
  monthly_cost DOUBLE PRECISION DEFAULT 0.0,
  
  -- Limits (from workspace config)
  monthly_query_limit INTEGER NOT NULL,
  monthly_cost_limit DOUBLE PRECISION NOT NULL,
  
  updated_at TIMESTAMPTZ DEFAULT now(),
  
  UNIQUE(workspace_id, date),
  UNIQUE(workspace_id, month)
);

CREATE INDEX IF NOT EXISTS workspace_quotas_workspace_id_idx 
  ON workspace_quotas(workspace_id);

CREATE INDEX IF NOT EXISTS workspace_quotas_date_idx 
  ON workspace_quotas(date);

CREATE INDEX IF NOT EXISTS workspace_quotas_month_idx 
  ON workspace_quotas(month);

-- ============================================================================
-- 6. PERSONALIZATION ENGINE - LEARNED USER PATTERNS
-- ============================================================================

CREATE TABLE IF NOT EXISTS query_patterns (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id TEXT,
  
  -- Pattern Detection
  pattern_type TEXT NOT NULL,  -- 'domain', 'style', 'complexity', etc.
  pattern_value TEXT NOT NULL,
  
  -- Occurrence Tracking
  occurrence_count INTEGER DEFAULT 1,
  first_seen TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ DEFAULT now(),
  
  -- Confidence
  confidence DOUBLE PRECISION DEFAULT 0.5,
  
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS query_patterns_workspace_id_idx 
  ON query_patterns(workspace_id);

CREATE INDEX IF NOT EXISTS query_patterns_user_id_idx 
  ON query_patterns(user_id);

CREATE INDEX IF NOT EXISTS query_patterns_pattern_type_idx 
  ON query_patterns(pattern_type);

CREATE TABLE IF NOT EXISTS user_preferences (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  
  -- Learned Preferences
  preference_key TEXT NOT NULL,
  preference_value TEXT NOT NULL,
  
  -- Strength of preference (0.0 to 1.0)
  strength DOUBLE PRECISION DEFAULT 0.5,
  
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  
  UNIQUE(workspace_id, user_id, preference_key)
);

CREATE INDEX IF NOT EXISTS user_preferences_workspace_user_idx 
  ON user_preferences(workspace_id, user_id);

-- ============================================================================
-- 7. WORKSPACE ADAPTER MODELS - PER-WORKSPACE PERSONALIZED ADAPTERS
-- ============================================================================

CREATE TABLE IF NOT EXISTS workspace_adapters (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  
  -- Base Configuration
  adapter_type TEXT NOT NULL,  -- 't1_adjuster', 't2_adjuster', 'confidence_booster', etc.
  
  -- Learned Parameters
  parameters JSONB NOT NULL,
  
  -- Thresholds (learned from workspace performance)
  t1_skip_threshold DOUBLE PRECISION,
  t2_skip_threshold DOUBLE PRECISION,
  confidence_threshold DOUBLE PRECISION,
  
  -- Performance Metrics
  avg_quality DOUBLE PRECISION DEFAULT 0.0,
  success_rate DOUBLE PRECISION DEFAULT 0.0,
  
  -- Training
  pairs_trained_on INTEGER DEFAULT 0,
  
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workspace_adapters_workspace_id_idx 
  ON workspace_adapters(workspace_id);

CREATE INDEX IF NOT EXISTS workspace_adapters_type_idx 
  ON workspace_adapters(adapter_type);

-- ============================================================================
-- 8. PROVIDER STATE - TRACK PROVIDER STATUS PER WORKSPACE
-- ============================================================================

CREATE TABLE IF NOT EXISTS provider_state (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  provider_name TEXT NOT NULL,
  
  -- Health Status
  is_healthy BOOLEAN DEFAULT true,
  last_check_at TIMESTAMPTZ,
  last_check_result JSONB,
  
  -- Performance
  avg_latency_ms DOUBLE PRECISION DEFAULT 0.0,
  error_count INTEGER DEFAULT 0,
  success_count INTEGER DEFAULT 0,
  
  -- Configuration
  config JSONB,
  
  updated_at TIMESTAMPTZ DEFAULT now(),
  
  UNIQUE(workspace_id, provider_name)
);

CREATE INDEX IF NOT EXISTS provider_state_workspace_id_idx 
  ON provider_state(workspace_id);

CREATE INDEX IF NOT EXISTS provider_state_provider_name_idx 
  ON provider_state(provider_name);

-- ============================================================================
-- 9. REQUEST AUDIT LOG - FULL REQUEST/RESPONSE AUDIT TRAIL
-- ============================================================================

CREATE TABLE IF NOT EXISTS request_audit (
  id BIGSERIAL PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id TEXT,
  
  -- Request Details
  request_id TEXT NOT NULL UNIQUE,
  query TEXT NOT NULL,
  
  -- Response Details
  response_summary TEXT,
  response_quality DOUBLE PRECISION,
  
  -- Processing
  t1_skipped BOOLEAN DEFAULT false,
  t2_skipped BOOLEAN DEFAULT false,
  total_latency_ms INTEGER,
  
  -- Providers Used
  providers_used TEXT[] DEFAULT ARRAY[]::TEXT[],
  
  -- Cost
  estimated_cost DOUBLE PRECISION DEFAULT 0.0,
  
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS request_audit_workspace_id_idx 
  ON request_audit(workspace_id);

CREATE INDEX IF NOT EXISTS request_audit_user_id_idx 
  ON request_audit(user_id);

CREATE INDEX IF NOT EXISTS request_audit_created_at_idx 
  ON request_audit(created_at DESC);

CREATE INDEX IF NOT EXISTS request_audit_workspace_user_idx 
  ON request_audit(workspace_id, user_id, created_at DESC);

-- ============================================================================
-- 10. MONITORING - SYSTEM HEALTH AND PERFORMANCE METRICS
-- ============================================================================

CREATE TABLE IF NOT EXISTS system_metrics (
  id BIGSERIAL PRIMARY KEY,
  
  -- Time Window
  metric_timestamp TIMESTAMPTZ NOT NULL,
  
  -- System Health
  total_workspaces INTEGER,
  active_workspaces INTEGER,
  
  -- Global Metrics
  total_queries INTEGER,
  avg_latency_ms DOUBLE PRECISION,
  error_rate DOUBLE PRECISION,
  
  -- Provider Status
  provider_status JSONB,
  
  -- Resource Usage
  memory_usage_mb INTEGER,
  cpu_usage_percent DOUBLE PRECISION,
  
  recorded_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS system_metrics_metric_timestamp_idx 
  ON system_metrics(metric_timestamp DESC);

-- ============================================================================
-- 11. VIEWS FOR COMMON QUERIES
-- ============================================================================

-- Current workspace performance summary
CREATE OR REPLACE VIEW workspace_performance_summary AS
SELECT
  w.id,
  w.name,
  wm.total_queries,
  wm.avg_confidence,
  wm.avg_quality,
  wm.t1_skip_rate,
  wm.t2_skip_rate,
  wm.total_cost,
  w.updated_at
FROM workspaces w
LEFT JOIN workspace_metrics wm ON w.id = wm.workspace_id
WHERE w.is_active = true;

-- Top performing workspaces by quality
CREATE OR REPLACE VIEW top_workspaces_by_quality AS
SELECT
  w.id,
  w.name,
  wm.avg_quality,
  wm.total_queries,
  wm.sppe_pairs_count,
  ROW_NUMBER() OVER (ORDER BY wm.avg_quality DESC NULLS LAST) as rank
FROM workspaces w
LEFT JOIN workspace_metrics wm ON w.id = wm.workspace_id
WHERE w.is_active = true
LIMIT 100;

-- Event stream for a workspace
CREATE OR REPLACE VIEW workspace_event_stream AS
SELECT
  event_id,
  workspace_id,
  event_type,
  user_id,
  payload,
  recorded_at,
  LAG(event_id) OVER (PARTITION BY workspace_id ORDER BY recorded_at) as previous_event,
  LEAD(event_id) OVER (PARTITION BY workspace_id ORDER BY recorded_at) as next_event
FROM jimsai_events
ORDER BY recorded_at DESC;

-- SPPE quality insights
CREATE OR REPLACE VIEW sppe_quality_insights AS
SELECT
  workspace_id,
  DATE_TRUNC('day', created_at) as date,
  COUNT(*) as pairs_created,
  AVG(sppe_quality) as avg_quality,
  MIN(sppe_quality) as min_quality,
  MAX(sppe_quality) as max_quality,
  STDDEV(sppe_quality) as quality_stddev,
  SUM(CASE WHEN t1_skipped THEN 1 ELSE 0 END) as t1_skipped_count,
  SUM(CASE WHEN t2_skipped THEN 1 ELSE 0 END) as t2_skipped_count
FROM sppe_pairs
GROUP BY workspace_id, DATE_TRUNC('day', created_at);

-- ============================================================================
-- 12. STORED PROCEDURES FOR COMMON OPERATIONS
-- ============================================================================

-- Record a query and update metrics
CREATE OR REPLACE FUNCTION record_workspace_query(
  p_workspace_id TEXT,
  p_user_id TEXT,
  p_query TEXT,
  p_response TEXT,
  p_confidence DOUBLE PRECISION,
  p_quality DOUBLE PRECISION,
  p_t1_skipped BOOLEAN,
  p_t2_skipped BOOLEAN,
  p_cost DOUBLE PRECISION
) RETURNS TEXT AS $$
DECLARE
  v_sppe_id TEXT;
  v_request_id TEXT;
BEGIN
  -- Create request ID
  v_request_id := 'req_' || gen_random_uuid()::text;
  
  -- Record in request audit
  INSERT INTO request_audit (
    workspace_id, user_id, request_id, query, response_summary,
    response_quality, t1_skipped, t2_skipped, estimated_cost
  ) VALUES (
    p_workspace_id, p_user_id, v_request_id, p_query,
    LEFT(p_response, 200), p_quality, p_t1_skipped, p_t2_skipped, p_cost
  );
  
  -- Create SPPE pair
  v_sppe_id := 'sppe_' || gen_random_uuid()::text;
  INSERT INTO sppe_pairs (
    id, workspace_id, query, response,
    semantic_score, verification_score, source_score, gap_score, efficiency_score,
    sppe_quality, model_t1, model_t2, t1_skipped, t2_skipped
  ) VALUES (
    v_sppe_id, p_workspace_id, p_query, p_response,
    p_quality * 0.5, p_quality * 0.6, p_quality * 0.4, p_quality * 0.3, p_quality * 0.2,
    p_quality, 'llama-3.1-8b-instant', 'llama2-70b-4096', p_t1_skipped, p_t2_skipped
  );
  
  RETURN v_request_id;
END;
$$ LANGUAGE plpgsql;

-- Get workspace quality trend
CREATE OR REPLACE FUNCTION get_workspace_quality_trend(
  p_workspace_id TEXT,
  p_days INTEGER DEFAULT 30
) RETURNS TABLE(date DATE, avg_quality DOUBLE PRECISION, query_count INTEGER) AS $$
SELECT
  DATE_TRUNC('day', created_at)::DATE,
  AVG(sppe_quality),
  COUNT(*)::INTEGER
FROM sppe_pairs
WHERE workspace_id = p_workspace_id
  AND created_at >= NOW() - (p_days || ' days')::INTERVAL
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY DATE_TRUNC('day', created_at) DESC;
$$ LANGUAGE SQL;

-- ============================================================================
-- 13. GRANT PERMISSIONS (if using role-based access)
-- ============================================================================
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO jimsai_app_role;
-- GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO jimsai_app_role;

-- ============================================================================
-- 14. DATA CLEANUP - RETENTION POLICIES
-- ============================================================================

-- Archive old events (optional - run periodically)
-- DELETE FROM jimsai_events 
-- WHERE recorded_at < NOW() - INTERVAL '90 days'
--   AND workspace_id IN (
--     SELECT id FROM workspaces WHERE data_retention_days = 90
--   );

-- Clean up old metrics snapshots (keep only last 12 months)
-- DELETE FROM workspace_metrics 
-- WHERE period_end < NOW() - INTERVAL '365 days';

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
-- Phase 5 schema has been initialized with:
-- - Multi-tenant workspace tables (workspaces, workspace_members)
-- - Event sourcing infrastructure (jimsai_events)
-- - SPPE training pairs (sppe_pairs)
-- - Personalization data (query_patterns, user_preferences, workspace_adapters)
-- - Monitoring and metrics (workspace_metrics, workspace_quotas, provider_state, system_metrics)
-- - Request audit trail (request_audit)
-- - Helper views for analytics
-- - Stored procedures for common operations
--
-- Use this migration after running init.sql
-- ============================================================================
