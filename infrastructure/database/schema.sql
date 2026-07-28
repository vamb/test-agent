-- Historical Timeline Agent database schema.
-- Design goals:
-- 1. Support fuzzy historical dates and BCE years.
-- 2. Keep ancient polities separate from modern countries.
-- 3. Make every conclusion traceable to sources.
-- 4. Allow import review before data becomes visible to the Agent.
-- 5. Keep Agent execution records for debugging and evaluation.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TYPE time_precision AS ENUM (
  'day',
  'month',
  'year',
  'decade',
  'century',
  'range',
  'approximate',
  'unknown'
);

CREATE TYPE event_status AS ENUM (
  'draft',
  'reviewing',
  'verified',
  'disputed',
  'archived'
);

CREATE TYPE source_type AS ENUM (
  'book',
  'paper',
  'primary_source',
  'encyclopedia',
  'website',
  'dataset',
  'note'
);

CREATE TYPE relation_type AS ENUM (
  'cause',
  'effect',
  'contemporary',
  'influence',
  'trade_link',
  'conflict_link',
  'migration_link',
  'religion_link',
  'technology_link',
  'uncertain'
);

CREATE TYPE import_status AS ENUM (
  'pending',
  'validated',
  'imported',
  'rejected'
);

CREATE TYPE agent_run_status AS ENUM (
  'pending',
  'running',
  'waiting_for_user',
  'completed',
  'failed',
  'cancelled'
);

CREATE TYPE agent_step_status AS ENUM (
  'running',
  'completed',
  'failed',
  'skipped'
);

CREATE TYPE tool_risk_level AS ENUM (
  'low',
  'medium',
  'high'
);

CREATE TABLE regions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL UNIQUE,
  parent_region_id uuid REFERENCES regions(id) ON DELETE SET NULL,
  description text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE modern_countries (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL UNIQUE,
  iso_code text UNIQUE,
  region_id uuid REFERENCES regions(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE polities (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL,
  name_original text NOT NULL DEFAULT '',
  polity_type text NOT NULL DEFAULT 'polity',
  region_id uuid REFERENCES regions(id) ON DELETE SET NULL,
  start_year integer,
  end_year integer,
  description text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT polities_year_order CHECK (
    start_year IS NULL
    OR end_year IS NULL
    OR start_year <= end_year
  ),
  CONSTRAINT polities_unique_name_period UNIQUE (name, start_year, end_year)
);

CREATE TABLE polity_modern_country_links (
  polity_id uuid NOT NULL REFERENCES polities(id) ON DELETE CASCADE,
  modern_country_id uuid NOT NULL REFERENCES modern_countries(id) ON DELETE CASCADE,
  note text NOT NULL DEFAULT '',
  PRIMARY KEY (polity_id, modern_country_id)
);

CREATE TABLE categories (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL UNIQUE,
  parent_category_id uuid REFERENCES categories(id) ON DELETE SET NULL,
  description text NOT NULL DEFAULT ''
);

CREATE TABLE actors (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL,
  actor_type text NOT NULL DEFAULT 'person',
  polity_id uuid REFERENCES polities(id) ON DELETE SET NULL,
  start_year integer,
  end_year integer,
  description text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT actors_year_order CHECK (
    start_year IS NULL
    OR end_year IS NULL
    OR start_year <= end_year
  ),
  CONSTRAINT actors_unique_name_type UNIQUE (name, actor_type, polity_id)
);

CREATE TABLE import_batches (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  filename text NOT NULL,
  source_note text NOT NULL DEFAULT '',
  status import_status NOT NULL DEFAULT 'pending',
  total_rows integer NOT NULL DEFAULT 0,
  valid_rows integer NOT NULL DEFAULT 0,
  error_rows integer NOT NULL DEFAULT 0,
  created_by text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  validated_at timestamptz,
  imported_at timestamptz
);

CREATE TABLE historical_events (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  title text NOT NULL,
  canonical_title text NOT NULL DEFAULT '',
  start_year integer NOT NULL,
  start_month integer,
  start_day integer,
  end_year integer,
  end_month integer,
  end_day integer,
  start_date_text text NOT NULL DEFAULT '',
  end_date_text text NOT NULL DEFAULT '',
  time_precision time_precision NOT NULL DEFAULT 'year',
  is_approximate boolean NOT NULL DEFAULT false,
  region_id uuid REFERENCES regions(id) ON DELETE SET NULL,
  polity_id uuid REFERENCES polities(id) ON DELETE SET NULL,
  primary_modern_country_id uuid REFERENCES modern_countries(id) ON DELETE SET NULL,
  location_text text NOT NULL DEFAULT '',
  summary text NOT NULL,
  causes text[] NOT NULL DEFAULT '{}',
  effects text[] NOT NULL DEFAULT '{}',
  status event_status NOT NULL DEFAULT 'draft',
  confidence numeric(3,2) NOT NULL DEFAULT 0.50,
  importance_score numeric(4,2) NOT NULL DEFAULT 1.00,
  visibility text NOT NULL DEFAULT 'public',
  language text NOT NULL DEFAULT 'zh',
  notes text NOT NULL DEFAULT '',
  import_batch_id uuid REFERENCES import_batches(id) ON DELETE SET NULL,
  search_text tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', coalesce(title, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(canonical_title, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(summary, '')), 'B')
    || setweight(to_tsvector('simple', coalesce(location_text, '')), 'C')
  ) STORED,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT historical_events_year_order CHECK (
    end_year IS NULL OR start_year <= end_year
  ),
  CONSTRAINT historical_events_start_month CHECK (
    start_month IS NULL OR start_month BETWEEN 1 AND 12
  ),
  CONSTRAINT historical_events_end_month CHECK (
    end_month IS NULL OR end_month BETWEEN 1 AND 12
  ),
  CONSTRAINT historical_events_start_day CHECK (
    start_day IS NULL OR start_day BETWEEN 1 AND 31
  ),
  CONSTRAINT historical_events_end_day CHECK (
    end_day IS NULL OR end_day BETWEEN 1 AND 31
  ),
  CONSTRAINT historical_events_confidence CHECK (confidence >= 0 AND confidence <= 1),
  CONSTRAINT historical_events_importance CHECK (importance_score >= 0)
);

CREATE TABLE event_aliases (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  event_id uuid NOT NULL REFERENCES historical_events(id) ON DELETE CASCADE,
  alias text NOT NULL,
  language text NOT NULL DEFAULT 'zh',
  note text NOT NULL DEFAULT '',
  UNIQUE (event_id, alias, language)
);

CREATE TABLE event_categories (
  event_id uuid NOT NULL REFERENCES historical_events(id) ON DELETE CASCADE,
  category_id uuid NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
  PRIMARY KEY (event_id, category_id)
);

CREATE TABLE event_actors (
  event_id uuid NOT NULL REFERENCES historical_events(id) ON DELETE CASCADE,
  actor_id uuid NOT NULL REFERENCES actors(id) ON DELETE RESTRICT,
  role text NOT NULL DEFAULT '',
  PRIMARY KEY (event_id, actor_id, role)
);

CREATE TABLE event_sources (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  event_id uuid NOT NULL REFERENCES historical_events(id) ON DELETE CASCADE,
  source_title text NOT NULL,
  source_type source_type NOT NULL,
  author text NOT NULL DEFAULT '',
  publisher text NOT NULL DEFAULT '',
  published_year integer,
  url text NOT NULL DEFAULT '',
  citation text NOT NULL DEFAULT '',
  excerpt text NOT NULL DEFAULT '',
  page_ref text NOT NULL DEFAULT '',
  reliability numeric(3,2) NOT NULL DEFAULT 0.50,
  is_primary boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT event_sources_reliability CHECK (reliability >= 0 AND reliability <= 1)
);

CREATE TABLE event_relations (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  source_event_id uuid NOT NULL REFERENCES historical_events(id) ON DELETE CASCADE,
  target_event_id uuid NOT NULL REFERENCES historical_events(id) ON DELETE CASCADE,
  relation_type relation_type NOT NULL,
  explanation text NOT NULL,
  confidence numeric(3,2) NOT NULL DEFAULT 0.50,
  evidence_source_id uuid REFERENCES event_sources(id) ON DELETE SET NULL,
  is_directional boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT event_relations_no_self CHECK (source_event_id <> target_event_id),
  CONSTRAINT event_relations_confidence CHECK (confidence >= 0 AND confidence <= 1),
  CONSTRAINT event_relations_unique UNIQUE (
    source_event_id,
    target_event_id,
    relation_type
  )
);

CREATE TABLE import_event_staging (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  import_batch_id uuid NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
  row_number integer NOT NULL,
  raw_payload jsonb NOT NULL,
  normalized_payload jsonb,
  validation_errors text[] NOT NULL DEFAULT '{}',
  status import_status NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (import_batch_id, row_number)
);

CREATE TABLE tools (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL UNIQUE,
  description text NOT NULL,
  risk_level tool_risk_level NOT NULL DEFAULT 'low',
  requires_confirmation boolean NOT NULL DEFAULT false,
  enabled boolean NOT NULL DEFAULT true,
  input_schema jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agent_runs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id text NOT NULL DEFAULT '',
  user_input text NOT NULL,
  status agent_run_status NOT NULL DEFAULT 'pending',
  final_answer text,
  error_message text,
  model_name text NOT NULL DEFAULT '',
  prompt_version text NOT NULL DEFAULT '',
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);

CREATE TABLE agent_steps (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  step_index integer NOT NULL,
  step_type text NOT NULL,
  status agent_step_status NOT NULL DEFAULT 'running',
  tool_name text,
  tool_arguments jsonb,
  tool_result jsonb,
  model_input_summary text,
  model_output_summary text,
  error_message text,
  token_input integer NOT NULL DEFAULT 0,
  token_output integer NOT NULL DEFAULT 0,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  UNIQUE (run_id, step_index)
);

CREATE TABLE evaluation_cases (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  case_key text NOT NULL UNIQUE,
  user_input text NOT NULL,
  expected_tools text[] NOT NULL DEFAULT '{}',
  forbidden_tools text[] NOT NULL DEFAULT '{}',
  expected_answer_points text[] NOT NULL DEFAULT '{}',
  max_steps integer NOT NULL DEFAULT 8,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evaluation_runs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  case_id uuid NOT NULL REFERENCES evaluation_cases(id) ON DELETE CASCADE,
  agent_run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
  score numeric(4,2),
  passed boolean,
  notes text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_historical_events_updated_at
BEFORE UPDATE ON historical_events
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_tools_updated_at
BEFORE UPDATE ON tools
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_regions_parent ON regions (parent_region_id);
CREATE INDEX idx_modern_countries_region ON modern_countries (region_id);
CREATE INDEX idx_polities_region ON polities (region_id);
CREATE INDEX idx_polities_years ON polities (start_year, end_year);
CREATE INDEX idx_actors_polity ON actors (polity_id);
CREATE INDEX idx_import_batches_status ON import_batches (status);

CREATE INDEX idx_historical_events_years
  ON historical_events (start_year, end_year);

CREATE INDEX idx_historical_events_region
  ON historical_events (region_id);

CREATE INDEX idx_historical_events_polity
  ON historical_events (polity_id);

CREATE INDEX idx_historical_events_modern_country
  ON historical_events (primary_modern_country_id);

CREATE INDEX idx_historical_events_status
  ON historical_events (status);

CREATE INDEX idx_historical_events_importance
  ON historical_events (importance_score DESC);

CREATE INDEX idx_historical_events_search_text
  ON historical_events USING gin (search_text);

CREATE INDEX idx_event_aliases_alias ON event_aliases (alias);
CREATE INDEX idx_event_categories_category ON event_categories (category_id);
CREATE INDEX idx_event_actors_actor ON event_actors (actor_id);
CREATE INDEX idx_event_sources_event_id ON event_sources (event_id);
CREATE INDEX idx_event_sources_type ON event_sources (source_type);
CREATE INDEX idx_event_relations_source ON event_relations (source_event_id);
CREATE INDEX idx_event_relations_target ON event_relations (target_event_id);
CREATE INDEX idx_event_relations_type ON event_relations (relation_type);
CREATE INDEX idx_import_event_staging_batch ON import_event_staging (import_batch_id);
CREATE INDEX idx_agent_runs_status ON agent_runs (status);
CREATE INDEX idx_agent_steps_run_id ON agent_steps (run_id);
CREATE INDEX idx_evaluation_runs_case_id ON evaluation_runs (case_id);
