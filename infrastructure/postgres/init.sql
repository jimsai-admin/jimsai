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
