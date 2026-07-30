import json
import unittest
from pathlib import Path

from apps.api.main import (
    admin_import_batch_review,
    admin_list_events,
    create_import_batch,
    parse_import_events,
    preview_import_batch,
)
from apps.api.settings import AppSettings
from tools.database.postgres import PostgresClient
from tools.historical.models import HistoricalEvent


ROOT = Path(__file__).resolve().parents[1]
EXTENDED_SEED_PATH = ROOT / "data" / "imports" / "curated_seed_600_900_extended.json"


class SeedImportDatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = AppSettings.from_env().postgres
        cls.db_available = PostgresClient(cls.settings).health_check().ok

    def test_extended_seed_dataset_is_valid(self) -> None:
        events = json.loads(EXTENDED_SEED_PATH.read_text(encoding="utf-8"))

        self.assertEqual(len(events), 22)
        for event in events:
            parsed = HistoricalEvent.model_validate(event)
            self.assertGreaterEqual(parsed.start_year, 600)
            self.assertLessEqual(parsed.end_year or parsed.start_year, 900)
            self.assertTrue(parsed.sources)

    def test_extended_seed_dataset_can_run_import_review_preview(self) -> None:
        if not self.db_available:
            self.skipTest("PostgreSQL is not available")

        content = EXTENDED_SEED_PATH.read_text(encoding="utf-8")
        parsed = parse_import_events({"input_format": "json", "content": content})
        batch = create_import_batch(
            {
                "filename": EXTENDED_SEED_PATH.name,
                "source_note": "extended-seed-review-test",
                "created_by": "test",
                "events": parsed["events"],
            }
        )
        preview = preview_import_batch(batch["id"])
        review = admin_import_batch_review(batch["id"])
        listed = admin_list_events(import_batch_id=batch["id"], limit=25)

        self.assertTrue(parsed["parsed"])
        self.assertEqual(parsed["count"], 22)
        self.assertEqual(parsed["error_rows"], 0)
        self.assertTrue(batch["created"])
        self.assertEqual(batch["valid_rows"], 22)
        self.assertEqual(preview["count"], 22)
        self.assertTrue(review["found"])
        self.assertEqual(review["review"]["ready_for_manual_review"], False)
        self.assertEqual(listed["count"], 0)


if __name__ == "__main__":
    unittest.main()
