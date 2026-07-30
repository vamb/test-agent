-- Event management audit records.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS event_change_logs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  event_id uuid REFERENCES historical_events(id) ON DELETE SET NULL,
  action text NOT NULL,
  changed_by text NOT NULL DEFAULT '',
  before_payload jsonb,
  after_payload jsonb,
  reason text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_event_change_logs_event_id
  ON event_change_logs (event_id);

CREATE INDEX IF NOT EXISTS idx_event_change_logs_action
  ON event_change_logs (action);

CREATE INDEX IF NOT EXISTS idx_event_change_logs_created_at
  ON event_change_logs (created_at DESC);

CREATE TABLE IF NOT EXISTS data_quality_issue_actions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  issue_key text NOT NULL UNIQUE,
  issue_type text NOT NULL,
  target_type text NOT NULL,
  target_id text NOT NULL,
  status text NOT NULL DEFAULT 'open',
  handled_by text NOT NULL DEFAULT '',
  reason text NOT NULL DEFAULT '',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT data_quality_issue_actions_status
    CHECK (status IN ('open', 'resolved', 'ignored', 'snoozed'))
);

CREATE INDEX IF NOT EXISTS idx_data_quality_issue_actions_status
  ON data_quality_issue_actions (status);

CREATE INDEX IF NOT EXISTS idx_data_quality_issue_actions_issue_type
  ON data_quality_issue_actions (issue_type);

CREATE INDEX IF NOT EXISTS idx_data_quality_issue_actions_target
  ON data_quality_issue_actions (target_type, target_id);
