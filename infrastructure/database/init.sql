-- Complete initialization entrypoint for the current Historical Timeline Agent.
--
-- Run on a fresh database with psql:
--   psql -h localhost -p 5432 -U postgres -d historical_agent -f infrastructure/database/init.sql
--
-- This script includes the current application tables. It expects pgvector to be
-- installed because knowledge search and vector operations are now part of the
-- management backend.

\set ON_ERROR_STOP on

\ir schema.sql
\ir schema_event_management.sql
\ir schema_auth_chat.sql
\ir schema_memory.sql
\ir schema_knowledge.sql
\ir schema_vector_optional.sql
\ir schema_vector_jobs.sql
\ir seed_reference_data.sql
