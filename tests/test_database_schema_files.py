import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE_DIR = ROOT / "infrastructure" / "database"


class DatabaseSchemaFilesTest(unittest.TestCase):
    def test_complete_init_includes_current_backend_schema_files(self) -> None:
        init_sql = (DATABASE_DIR / "init.sql").read_text(encoding="utf-8")

        for filename in (
            "schema.sql",
            "schema_event_management.sql",
            "schema_auth_chat.sql",
            "schema_knowledge.sql",
            "schema_vector_optional.sql",
            "schema_vector_jobs.sql",
            "seed_reference_data.sql",
        ):
            self.assertIn(f"\\ir {filename}", init_sql)

    def test_schema_declares_management_indexes_and_tables(self) -> None:
        base_schema = (DATABASE_DIR / "schema.sql").read_text(encoding="utf-8")
        management_schema = (DATABASE_DIR / "schema_event_management.sql").read_text(encoding="utf-8")
        auth_chat_schema = (DATABASE_DIR / "schema_auth_chat.sql").read_text(encoding="utf-8")
        knowledge_schema = (DATABASE_DIR / "schema_knowledge.sql").read_text(encoding="utf-8")
        vector_jobs_schema = (DATABASE_DIR / "schema_vector_jobs.sql").read_text(encoding="utf-8")

        self.assertIn("idx_historical_events_import_batch", base_schema)
        self.assertIn("idx_historical_events_title_year", base_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS event_change_logs", management_schema)
        self.assertIn("idx_event_change_logs_created_at", management_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS data_quality_issue_actions", management_schema)
        self.assertIn("CONSTRAINT data_quality_issue_actions_status", management_schema)
        self.assertIn("idx_data_quality_issue_actions_target", management_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS users", auth_chat_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS user_sessions", auth_chat_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS chat_groups", auth_chat_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS chat_conversations", auth_chat_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS chat_messages", auth_chat_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS chat_message_artifacts", auth_chat_schema)
        self.assertIn("ADD COLUMN IF NOT EXISTS conversation_id", auth_chat_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS knowledge_documents", knowledge_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS knowledge_chunks", knowledge_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS knowledge_document_versions", knowledge_schema)
        self.assertIn("current_version integer NOT NULL DEFAULT 1", knowledge_schema)
        self.assertIn("idx_knowledge_document_versions_document_id", knowledge_schema)
        self.assertIn("idx_knowledge_documents_status", knowledge_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS vector_rebuild_jobs", vector_jobs_schema)
        self.assertIn("CONSTRAINT vector_rebuild_jobs_target", vector_jobs_schema)
        self.assertIn("CONSTRAINT vector_rebuild_jobs_status", vector_jobs_schema)
        self.assertIn("CONSTRAINT vector_rebuild_jobs_item_limit", vector_jobs_schema)

    def test_vector_jobs_runtime_fallback_matches_schema_constraints(self) -> None:
        service_source = (ROOT / "knowledge" / "service.py").read_text(encoding="utf-8")

        self.assertIn("CONSTRAINT vector_rebuild_jobs_target", service_source)
        self.assertIn("CONSTRAINT vector_rebuild_jobs_status", service_source)
        self.assertIn("CONSTRAINT vector_rebuild_jobs_item_limit", service_source)


if __name__ == "__main__":
    unittest.main()
