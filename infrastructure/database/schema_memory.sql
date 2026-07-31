CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS conversation_summaries (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  conversation_id uuid NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
  summary text NOT NULL,
  source_message_count integer NOT NULL DEFAULT 0,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversation_summaries_user_conversation
  ON conversation_summaries (user_id, conversation_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS user_memories (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  memory_type text NOT NULL DEFAULT 'preference',
  content text NOT NULL,
  status text NOT NULL DEFAULT 'enabled',
  confidence numeric NOT NULL DEFAULT 0.6,
  source_conversation_id uuid REFERENCES chat_conversations(id) ON DELETE SET NULL,
  source_summary_id uuid REFERENCES conversation_summaries(id) ON DELETE SET NULL,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  disabled_at timestamptz,
  deleted_at timestamptz,
  CONSTRAINT user_memories_type CHECK (
    memory_type IN ('preference', 'fact', 'research_interest', 'instruction', 'other')
  ),
  CONSTRAINT user_memories_status CHECK (
    status IN ('candidate', 'enabled', 'disabled', 'deleted')
  ),
  CONSTRAINT user_memories_confidence CHECK (confidence >= 0 AND confidence <= 1)
);

CREATE INDEX IF NOT EXISTS idx_user_memories_user_status
  ON user_memories (user_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_memories_source_conversation
  ON user_memories (source_conversation_id);

CREATE TABLE IF NOT EXISTS memory_sources (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  memory_id uuid NOT NULL REFERENCES user_memories(id) ON DELETE CASCADE,
  source_type text NOT NULL,
  source_id text NOT NULL DEFAULT '',
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT memory_sources_type CHECK (
    source_type IN ('conversation', 'message', 'summary', 'manual', 'import')
  )
);

CREATE INDEX IF NOT EXISTS idx_memory_sources_memory_id
  ON memory_sources (memory_id, source_type);
