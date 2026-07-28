-- Optional pgvector extension for semantic retrieval.
-- Run this only after pgvector is installed on the local PostgreSQL server.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE historical_events
  ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE INDEX IF NOT EXISTS idx_historical_events_embedding
  ON historical_events USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

