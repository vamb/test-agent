-- Vector rebuild job table for admin-managed embedding refresh tasks.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS vector_rebuild_jobs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  target text NOT NULL,
  item_limit integer NOT NULL DEFAULT 100,
  status text NOT NULL DEFAULT 'pending',
  processed_events integer NOT NULL DEFAULT 0,
  processed_chunks integer NOT NULL DEFAULT 0,
  error_message text NOT NULL DEFAULT '',
  created_by text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz,
  CONSTRAINT vector_rebuild_jobs_target CHECK (target IN ('knowledge', 'events', 'all')),
  CONSTRAINT vector_rebuild_jobs_status CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  CONSTRAINT vector_rebuild_jobs_item_limit CHECK (item_limit > 0)
);

CREATE INDEX IF NOT EXISTS idx_vector_rebuild_jobs_status
  ON vector_rebuild_jobs (status);
