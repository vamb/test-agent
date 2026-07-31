-- Security audit records for prompt/tool policy enforcement.

CREATE TABLE IF NOT EXISTS security_audit_logs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
  user_id text NOT NULL DEFAULT '',
  event_type text NOT NULL,
  category text NOT NULL DEFAULT '',
  reason text NOT NULL DEFAULT '',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_security_audit_logs_run_id
  ON security_audit_logs (run_id);

CREATE INDEX IF NOT EXISTS idx_security_audit_logs_category
  ON security_audit_logs (category);

CREATE INDEX IF NOT EXISTS idx_security_audit_logs_created_at
  ON security_audit_logs (created_at DESC);
