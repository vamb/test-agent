CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  username text NOT NULL UNIQUE,
  email text NOT NULL DEFAULT '',
  display_name text NOT NULL DEFAULT '',
  password_hash text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  role text NOT NULL DEFAULT 'user',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  last_login_at timestamptz,
  CONSTRAINT users_status CHECK (status IN ('active', 'disabled')),
  CONSTRAINT users_role CHECK (role IN ('user', 'admin'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
  ON users (lower(email))
  WHERE email <> '';

CREATE TABLE IF NOT EXISTS user_sessions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_token_hash text NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz,
  user_agent text NOT NULL DEFAULT '',
  ip_address text NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions (expires_at);

CREATE TABLE IF NOT EXISTS chat_groups (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title text NOT NULL,
  description text NOT NULL DEFAULT '',
  pinned boolean NOT NULL DEFAULT false,
  archived boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_groups_user_id ON chat_groups (user_id, archived, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_conversations (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  group_id uuid REFERENCES chat_groups(id) ON DELETE SET NULL,
  title text NOT NULL DEFAULT '新会话',
  summary text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT 'active',
  last_message_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chat_conversations_status CHECK (status IN ('active', 'archived'))
);

CREATE INDEX IF NOT EXISTS idx_chat_conversations_user_id
  ON chat_conversations (user_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_conversations_group_id
  ON chat_conversations (group_id);

CREATE TABLE IF NOT EXISTS chat_messages (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  conversation_id uuid NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role text NOT NULL,
  content text NOT NULL DEFAULT '',
  content_format text NOT NULL DEFAULT 'markdown',
  status text NOT NULL DEFAULT 'done',
  agent_run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
  parent_message_id uuid REFERENCES chat_messages(id) ON DELETE SET NULL,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chat_messages_role CHECK (role IN ('user', 'assistant', 'system', 'tool')),
  CONSTRAINT chat_messages_status CHECK (status IN ('streaming', 'done', 'error', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_id
  ON chat_messages (conversation_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id
  ON chat_messages (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_agent_run_id
  ON chat_messages (agent_run_id);

CREATE TABLE IF NOT EXISTS chat_message_artifacts (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  message_id uuid NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
  artifact_type text NOT NULL,
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chat_message_artifacts_type CHECK (
    artifact_type IN ('event', 'reference', 'link', 'trace', 'table', 'metadata')
  )
);

CREATE INDEX IF NOT EXISTS idx_chat_message_artifacts_message_id
  ON chat_message_artifacts (message_id, artifact_type);

ALTER TABLE agent_runs
  ADD COLUMN IF NOT EXISTS conversation_id uuid REFERENCES chat_conversations(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS input_message_id uuid REFERENCES chat_messages(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS output_message_id uuid REFERENCES chat_messages(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_agent_runs_conversation_id
  ON agent_runs (conversation_id);
