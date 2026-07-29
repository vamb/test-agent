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
            "schema_knowledge.sql",
            "schema_vector_optional.sql",
            "schema_vector_jobs.sql",
            "seed_reference_data.sql",
        ):
            self.assertIn(f"\\ir {filename}", init_sql)

    def test_schema_declares_management_indexes_and_tables(self) -> None:
        base_schema = (DATABASE_DIR / "schema.sql").read_text(encoding="utf-8")
        management_schema = (DATABASE_DIR / "schema_event_management.sql").read_text(encoding="utf-8")
        knowledge_schema = (DATABASE_DIR / "schema_knowledge.sql").read_text(encoding="utf-8")
        vector_jobs_schema = (DATABASE_DIR / "schema_vector_jobs.sql").read_text(encoding="utf-8")

        self.assertIn("idx_historical_events_import_batch", base_schema)
        self.assertIn("idx_historical_events_title_year", base_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS event_change_logs", management_schema)
        self.assertIn("idx_event_change_logs_created_at", management_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS knowledge_documents", knowledge_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS knowledge_chunks", knowledge_schema)
        self.assertIn("idx_knowledge_documents_status", knowledge_schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS vector_rebuild_jobs", vector_jobs_schema)


if __name__ == "__main__":
    unittest.main()
