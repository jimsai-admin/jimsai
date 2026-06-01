-- ============================================================================
-- JIMS-AI Supabase Schema
-- ============================================================================
-- Single source of truth for the production Supabase/Postgres schema.
-- Safe to run more than once: tables, indexes, views, and functions are
-- declared with IF NOT EXISTS / OR REPLACE where supported.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================================
-- Runtime storage used by the Lambda API and training panels
-- ============================================================================

CREATE TABLE IF NOT EXISTS signatures (
  id TEXT PRIMARY KEY,
  provenance TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL,
  modality TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS execution_traces (
  id BIGSERIAL PRIMARY KEY,
  trace_id TEXT NOT NULL,
  service TEXT NOT NULL,
  stage TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS training_panel_items (
  id TEXT PRIMARY KEY,
  panel TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  subtitle TEXT NOT NULL DEFAULT '',
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS training_panel_items_panel_created_idx
  ON training_panel_items(panel, created_at DESC, id DESC);

-- ============================================================================
-- Workspace and tenancy
-- ============================================================================

CREATE TABLE IF NOT EXISTS workspaces (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  owner_id TEXT NOT NULL,
  skip_t1_threshold DOUBLE PRECISION DEFAULT 0.90,
  skip_t2_threshold DOUBLE PRECISION DEFAULT 0.95,
  enable_personalization BOOLEAN DEFAULT true,
  enable_caching BOOLEAN DEFAULT true,
  monthly_query_limit INTEGER DEFAULT 100000,
  monthly_cost_limit DOUBLE PRECISION DEFAULT 5000.0,
  data_retention_days INTEGER DEFAULT 90,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workspaces_organization_id_idx ON workspaces(organization_id);
CREATE INDEX IF NOT EXISTS workspaces_owner_id_idx ON workspaces(owner_id);

CREATE TABLE IF NOT EXISTS workspace_members (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'member',
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS workspace_members_workspace_id_idx ON workspace_members(workspace_id);
CREATE INDEX IF NOT EXISTS workspace_members_user_id_idx ON workspace_members(user_id);

-- ============================================================================
-- Event sourcing and audit
-- ============================================================================

CREATE TABLE IF NOT EXISTS jimsai_events (
  id BIGSERIAL PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  version INTEGER DEFAULT 1,
  correlation_id TEXT,
  causation_id TEXT,
  user_id TEXT,
  event_timestamp TIMESTAMPTZ NOT NULL,
  recorded_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jimsai_events_workspace_id_idx ON jimsai_events(workspace_id);
CREATE INDEX IF NOT EXISTS jimsai_events_event_type_idx ON jimsai_events(event_type);
CREATE INDEX IF NOT EXISTS jimsai_events_recorded_at_idx ON jimsai_events(recorded_at DESC);
CREATE INDEX IF NOT EXISTS jimsai_events_correlation_id_idx ON jimsai_events(correlation_id);
CREATE INDEX IF NOT EXISTS jimsai_events_user_id_idx ON jimsai_events(user_id);

CREATE TABLE IF NOT EXISTS request_audit (
  id BIGSERIAL PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id TEXT,
  request_id TEXT NOT NULL UNIQUE,
  query TEXT NOT NULL,
  response_summary TEXT,
  response_quality DOUBLE PRECISION,
  t1_skipped BOOLEAN DEFAULT false,
  t2_skipped BOOLEAN DEFAULT false,
  total_latency_ms INTEGER,
  providers_used TEXT[] DEFAULT ARRAY[]::TEXT[],
  estimated_cost DOUBLE PRECISION DEFAULT 0.0,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS request_audit_workspace_id_idx ON request_audit(workspace_id);
CREATE INDEX IF NOT EXISTS request_audit_user_id_idx ON request_audit(user_id);
CREATE INDEX IF NOT EXISTS request_audit_created_at_idx ON request_audit(created_at DESC);
CREATE INDEX IF NOT EXISTS request_audit_workspace_user_idx ON request_audit(workspace_id, user_id, created_at DESC);

-- ============================================================================
-- Training data and memory
-- ============================================================================

CREATE TABLE IF NOT EXISTS sppe_pairs (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  query TEXT NOT NULL,
  response TEXT NOT NULL,
  semantic_score DOUBLE PRECISION NOT NULL,
  verification_score DOUBLE PRECISION NOT NULL,
  source_score DOUBLE PRECISION NOT NULL,
  gap_score DOUBLE PRECISION NOT NULL,
  efficiency_score DOUBLE PRECISION NOT NULL,
  sppe_quality DOUBLE PRECISION NOT NULL,
  model_t1 TEXT NOT NULL,
  model_t2 TEXT NOT NULL,
  t1_skipped BOOLEAN DEFAULT false,
  t2_skipped BOOLEAN DEFAULT false,
  sources JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sppe_pairs_workspace_id_idx ON sppe_pairs(workspace_id);
CREATE INDEX IF NOT EXISTS sppe_pairs_sppe_quality_idx ON sppe_pairs(sppe_quality DESC);
CREATE INDEX IF NOT EXISTS sppe_pairs_created_at_idx ON sppe_pairs(created_at DESC);
CREATE INDEX IF NOT EXISTS sppe_pairs_workspace_created_idx ON sppe_pairs(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS memory_signatures (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  user_id TEXT,
  title TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  entities JSONB DEFAULT '[]'::jsonb,
  relations JSONB DEFAULT '[]'::jsonb,
  tags JSONB DEFAULT '[]'::jsonb,
  source TEXT,
  trust_score DOUBLE PRECISION DEFAULT 0.5,
  approval_status TEXT NOT NULL DEFAULT 'candidate',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS memory_signatures_workspace_idx ON memory_signatures(workspace_id);
CREATE INDEX IF NOT EXISTS memory_signatures_user_idx ON memory_signatures(user_id);
CREATE INDEX IF NOT EXISTS memory_signatures_approval_idx ON memory_signatures(approval_status);
CREATE INDEX IF NOT EXISTS memory_signatures_created_idx ON memory_signatures(created_at DESC);

CREATE TABLE IF NOT EXISTS memory_chunks (
  id TEXT PRIMARY KEY,
  signature_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  chunk_text TEXT NOT NULL,
  chunk_index INTEGER NOT NULL DEFAULT 0,
  vector_id TEXT,
  embedding_model TEXT,
  artifact_id TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS memory_chunks_signature_idx ON memory_chunks(signature_id);
CREATE INDEX IF NOT EXISTS memory_chunks_workspace_idx ON memory_chunks(workspace_id);
CREATE INDEX IF NOT EXISTS memory_chunks_vector_idx ON memory_chunks(vector_id);

CREATE TABLE IF NOT EXISTS retrieval_events (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  user_id TEXT,
  query TEXT NOT NULL,
  query_embedding_model TEXT,
  retrieved_ids JSONB DEFAULT '[]'::jsonb,
  selected_ids JSONB DEFAULT '[]'::jsonb,
  answer_id TEXT,
  confidence DOUBLE PRECISION,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS retrieval_events_workspace_created_idx ON retrieval_events(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS retrieval_events_user_created_idx ON retrieval_events(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS retrieval_misses (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  user_id TEXT,
  query TEXT NOT NULL,
  reason TEXT,
  expected_answer TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TIMESTAMPTZ DEFAULT now(),
  resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS retrieval_misses_workspace_status_idx ON retrieval_misses(workspace_id, status);
CREATE INDEX IF NOT EXISTS retrieval_misses_created_idx ON retrieval_misses(created_at DESC);

CREATE TABLE IF NOT EXISTS user_feedback (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  user_id TEXT,
  thread_id TEXT,
  trace_id TEXT,
  query TEXT,
  answer TEXT,
  rating TEXT,
  feedback TEXT,
  learn_this BOOLEAN DEFAULT false,
  payload JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE user_feedback ADD COLUMN IF NOT EXISTS thread_id TEXT;
ALTER TABLE user_feedback ADD COLUMN IF NOT EXISTS trace_id TEXT;
CREATE INDEX IF NOT EXISTS user_feedback_workspace_created_idx ON user_feedback(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS user_feedback_learn_this_idx ON user_feedback(learn_this);
CREATE INDEX IF NOT EXISTS user_feedback_thread_idx ON user_feedback(thread_id);

CREATE TABLE IF NOT EXISTS chat_threads (
  id TEXT PRIMARY KEY,
  workspace_id TEXT,
  user_id TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_threads_user_updated_idx ON chat_threads(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS chat_threads_workspace_updated_idx ON chat_threads(workspace_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
  id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
  workspace_id TEXT,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  trace_id TEXT,
  confidence DOUBLE PRECISION,
  sources JSONB DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_messages_thread_created_idx ON chat_messages(thread_id, created_at ASC);
CREATE INDEX IF NOT EXISTS chat_messages_user_created_idx ON chat_messages(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS chat_messages_trace_idx ON chat_messages(trace_id);

-- ============================================================================
-- Autonomous training service state
-- ============================================================================

CREATE TABLE IF NOT EXISTS autonomous_runs (
  id TEXT PRIMARY KEY,
  run_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running',
  started_at TIMESTAMPTZ DEFAULT now(),
  finished_at TIMESTAMPTZ,
  metrics JSONB DEFAULT '{}'::jsonb,
  error TEXT
);

CREATE INDEX IF NOT EXISTS autonomous_runs_status_idx ON autonomous_runs(status);
CREATE INDEX IF NOT EXISTS autonomous_runs_started_idx ON autonomous_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS autonomous_jobs (
  id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  priority INTEGER DEFAULT 100,
  payload JSONB DEFAULT '{}'::jsonb,
  attempts INTEGER DEFAULT 0,
  max_attempts INTEGER DEFAULT 3,
  scheduled_at TIMESTAMPTZ DEFAULT now(),
  locked_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS autonomous_jobs_status_schedule_idx ON autonomous_jobs(status, scheduled_at, priority);
CREATE INDEX IF NOT EXISTS autonomous_jobs_type_idx ON autonomous_jobs(job_type);

CREATE TABLE IF NOT EXISTS ingestion_cursors (
  id TEXT PRIMARY KEY,
  source_name TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  cursor_value TEXT,
  payload JSONB DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(source_name, workspace_id)
);

CREATE TABLE IF NOT EXISTS training_batches (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  task_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'candidate',
  item_count INTEGER DEFAULT 0,
  storage_url TEXT,
  manifest JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS training_batches_workspace_status_idx ON training_batches(workspace_id, status);
CREATE INDEX IF NOT EXISTS training_batches_task_idx ON training_batches(task_type);

CREATE TABLE IF NOT EXISTS training_artifacts (
  artifact_id TEXT PRIMARY KEY,
  task_type TEXT NOT NULL,
  kaggle_run_id TEXT,
  model_type TEXT NOT NULL,
  base_model TEXT,
  storage_url TEXT NOT NULL,
  manifest_url TEXT,
  metrics JSONB DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'candidate',
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  activated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS training_artifacts_task_status_idx ON training_artifacts(task_type, status);
CREATE INDEX IF NOT EXISTS training_artifacts_created_idx ON training_artifacts(created_at DESC);

CREATE TABLE IF NOT EXISTS evaluation_reports (
  id TEXT PRIMARY KEY,
  artifact_id TEXT,
  workspace_id TEXT,
  report_type TEXT NOT NULL,
  metrics JSONB DEFAULT '{}'::jsonb,
  summary TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS evaluation_reports_artifact_idx ON evaluation_reports(artifact_id);
CREATE INDEX IF NOT EXISTS evaluation_reports_created_idx ON evaluation_reports(created_at DESC);

CREATE TABLE IF NOT EXISTS approval_queue (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  item_type TEXT NOT NULL,
  item_id TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  payload JSONB DEFAULT '{}'::jsonb,
  confidence DOUBLE PRECISION,
  status TEXT NOT NULL DEFAULT 'pending',
  reviewer_id TEXT,
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS approval_queue_workspace_status_idx ON approval_queue(workspace_id, status);
CREATE INDEX IF NOT EXISTS approval_queue_item_idx ON approval_queue(item_type, item_id);
CREATE INDEX IF NOT EXISTS approval_queue_created_idx ON approval_queue(created_at DESC);

-- ============================================================================
-- Metrics, quotas, personalization, and provider state
-- ============================================================================

CREATE TABLE IF NOT EXISTS workspace_metrics (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  total_queries INTEGER DEFAULT 0,
  total_confidence DOUBLE PRECISION DEFAULT 0.0,
  avg_confidence DOUBLE PRECISION DEFAULT 0.0,
  total_quality DOUBLE PRECISION DEFAULT 0.0,
  avg_quality DOUBLE PRECISION DEFAULT 0.0,
  t1_skip_count INTEGER DEFAULT 0,
  t2_skip_count INTEGER DEFAULT 0,
  t1_skip_rate DOUBLE PRECISION DEFAULT 0.0,
  t2_skip_rate DOUBLE PRECISION DEFAULT 0.0,
  total_cost DOUBLE PRECISION DEFAULT 0.0,
  groq_cost DOUBLE PRECISION DEFAULT 0.0,
  storage_cost DOUBLE PRECISION DEFAULT 0.0,
  sppe_pairs_count INTEGER DEFAULT 0,
  period_start TIMESTAMPTZ NOT NULL,
  period_end TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workspace_metrics_workspace_id_idx ON workspace_metrics(workspace_id);
CREATE INDEX IF NOT EXISTS workspace_metrics_period_idx ON workspace_metrics(period_start, period_end);

CREATE TABLE IF NOT EXISTS workspace_quotas (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  daily_queries INTEGER DEFAULT 0,
  daily_cost DOUBLE PRECISION DEFAULT 0.0,
  month TEXT NOT NULL,
  monthly_queries INTEGER DEFAULT 0,
  monthly_cost DOUBLE PRECISION DEFAULT 0.0,
  monthly_query_limit INTEGER NOT NULL,
  monthly_cost_limit DOUBLE PRECISION NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(workspace_id, date),
  UNIQUE(workspace_id, month)
);

CREATE INDEX IF NOT EXISTS workspace_quotas_workspace_id_idx ON workspace_quotas(workspace_id);
CREATE INDEX IF NOT EXISTS workspace_quotas_date_idx ON workspace_quotas(date);
CREATE INDEX IF NOT EXISTS workspace_quotas_month_idx ON workspace_quotas(month);

CREATE TABLE IF NOT EXISTS query_patterns (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id TEXT,
  pattern_type TEXT NOT NULL,
  pattern_value TEXT NOT NULL,
  occurrence_count INTEGER DEFAULT 1,
  first_seen TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ DEFAULT now(),
  confidence DOUBLE PRECISION DEFAULT 0.5,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS query_patterns_workspace_id_idx ON query_patterns(workspace_id);
CREATE INDEX IF NOT EXISTS query_patterns_user_id_idx ON query_patterns(user_id);
CREATE INDEX IF NOT EXISTS query_patterns_pattern_type_idx ON query_patterns(pattern_type);

CREATE TABLE IF NOT EXISTS user_preferences (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  preference_key TEXT NOT NULL,
  preference_value TEXT NOT NULL,
  strength DOUBLE PRECISION DEFAULT 0.5,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(workspace_id, user_id, preference_key)
);

CREATE INDEX IF NOT EXISTS user_preferences_workspace_user_idx ON user_preferences(workspace_id, user_id);

CREATE TABLE IF NOT EXISTS workspace_adapters (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  adapter_type TEXT NOT NULL,
  parameters JSONB NOT NULL,
  t1_skip_threshold DOUBLE PRECISION,
  t2_skip_threshold DOUBLE PRECISION,
  confidence_threshold DOUBLE PRECISION,
  avg_quality DOUBLE PRECISION DEFAULT 0.0,
  success_rate DOUBLE PRECISION DEFAULT 0.0,
  pairs_trained_on INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workspace_adapters_workspace_id_idx ON workspace_adapters(workspace_id);
CREATE INDEX IF NOT EXISTS workspace_adapters_type_idx ON workspace_adapters(adapter_type);

CREATE TABLE IF NOT EXISTS provider_state (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  provider_name TEXT NOT NULL,
  is_healthy BOOLEAN DEFAULT true,
  last_check_at TIMESTAMPTZ,
  last_check_result JSONB,
  avg_latency_ms DOUBLE PRECISION DEFAULT 0.0,
  error_count INTEGER DEFAULT 0,
  success_count INTEGER DEFAULT 0,
  config JSONB,
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(workspace_id, provider_name)
);

CREATE INDEX IF NOT EXISTS provider_state_workspace_id_idx ON provider_state(workspace_id);
CREATE INDEX IF NOT EXISTS provider_state_provider_name_idx ON provider_state(provider_name);

CREATE TABLE IF NOT EXISTS system_metrics (
  id BIGSERIAL PRIMARY KEY,
  metric_timestamp TIMESTAMPTZ NOT NULL,
  total_workspaces INTEGER,
  active_workspaces INTEGER,
  total_queries INTEGER,
  avg_latency_ms DOUBLE PRECISION,
  error_rate DOUBLE PRECISION,
  provider_status JSONB,
  memory_usage_mb INTEGER,
  cpu_usage_percent DOUBLE PRECISION,
  recorded_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS system_metrics_metric_timestamp_idx ON system_metrics(metric_timestamp DESC);

-- ============================================================================
-- Views
-- ============================================================================

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

CREATE OR REPLACE VIEW top_workspaces_by_quality AS
SELECT
  w.id,
  w.name,
  wm.avg_quality,
  wm.total_queries,
  wm.sppe_pairs_count,
  ROW_NUMBER() OVER (ORDER BY wm.avg_quality DESC NULLS LAST) AS rank
FROM workspaces w
LEFT JOIN workspace_metrics wm ON w.id = wm.workspace_id
WHERE w.is_active = true
LIMIT 100;

CREATE OR REPLACE VIEW workspace_event_stream AS
SELECT
  event_id,
  workspace_id,
  event_type,
  user_id,
  payload,
  recorded_at,
  LAG(event_id) OVER (PARTITION BY workspace_id ORDER BY recorded_at) AS previous_event,
  LEAD(event_id) OVER (PARTITION BY workspace_id ORDER BY recorded_at) AS next_event
FROM jimsai_events
ORDER BY recorded_at DESC;

CREATE OR REPLACE VIEW sppe_quality_insights AS
SELECT
  workspace_id,
  DATE_TRUNC('day', created_at) AS date,
  COUNT(*) AS pairs_created,
  AVG(sppe_quality) AS avg_quality,
  MIN(sppe_quality) AS min_quality,
  MAX(sppe_quality) AS max_quality,
  STDDEV(sppe_quality) AS quality_stddev,
  SUM(CASE WHEN t1_skipped THEN 1 ELSE 0 END) AS t1_skipped_count,
  SUM(CASE WHEN t2_skipped THEN 1 ELSE 0 END) AS t2_skipped_count
FROM sppe_pairs
GROUP BY workspace_id, DATE_TRUNC('day', created_at);

-- ============================================================================
-- Functions
-- ============================================================================

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
  v_request_id := 'req_' || gen_random_uuid()::text;

  INSERT INTO request_audit (
    workspace_id, user_id, request_id, query, response_summary,
    response_quality, t1_skipped, t2_skipped, estimated_cost
  ) VALUES (
    p_workspace_id, p_user_id, v_request_id, p_query,
    LEFT(p_response, 200), p_quality, p_t1_skipped, p_t2_skipped, p_cost
  );

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
-- End schema
-- ============================================================================
