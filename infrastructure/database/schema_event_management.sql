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

