import unittest

from apps.api.main import (
    confirm_import_batch,
    create_import_batch,
    get_import_batch,
    get_import_staging_rows,
)
from apps.api.settings import AppSettings
from tools.database.postgres import PostgresClient
from tools.historical.import_review import ImportReviewService
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.service import HistoricalQueryService


def valid_import_event(title: str = "测试导入事件") -> dict:
    return {
        "title": title,
        "start_year": 901,
        "end_year": 901,
        "start_date_text": "901年",
        "end_date_text": "901年",
        "time_precision": "year",
        "region": "测试地区",
        "polity": "测试政权",
        "modern_country": "测试国",
        "category": ["测试分类"],
        "summary": "用于验证数据导入审核流的测试事件。",
        "causes": ["测试原因"],
        "effects": ["测试影响"],
        "actors": ["测试人物"],
        "source_status": "draft",
        "confidence": 0.8,
        "sources": [
            {
                "source_title": "测试来源",
                "source_type": "note",
                "citation": "测试引用",
                "excerpt": "测试摘录",
                "reliability": 0.8,
            }
        ],
    }


class ImportReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = AppSettings.from_env().postgres
        cls.db_available = PostgresClient(cls.settings).health_check().ok

    def setUp(self) -> None:
        if not self.db_available:
            self.skipTest("PostgreSQL is not available")

    def test_create_batch_stages_and_confirms_valid_event(self) -> None:
        batch = create_import_batch(
            {
                "filename": "test-import.json",
                "source_note": "unit-test",
                "created_by": "test",
                "events": [valid_import_event()],
            }
        )

        self.assertTrue(batch["created"])
        self.assertEqual(batch["status"], "validated")
        self.assertEqual(batch["valid_rows"], 1)
        staging = get_import_staging_rows(batch["id"])
        self.assertEqual(staging["rows"][0]["status"], "validated")

        result = confirm_import_batch(batch["id"], {"confirmed_by": "test"})

        self.assertTrue(result["imported"])
        service = HistoricalQueryService(PostgresHistoricalEventRepository(self.settings))
        search = service.search_events_by_year(901, regions=["测试地区"])
        titles = {event["title"] for event in search["events"]}
        self.assertIn("测试导入事件", titles)

    def test_invalid_event_stays_in_staging_and_cannot_import(self) -> None:
        event = valid_import_event("测试无来源事件")
        event["sources"] = []
        service = ImportReviewService(self.settings)

        batch = service.create_batch(
            filename="invalid-import.json",
            source_note="unit-test",
            created_by="test",
            events=[event],
        )
        confirm_result = service.confirm_import(batch["id"], confirmed_by="test")
        fetched = get_import_batch(batch["id"])

        self.assertEqual(batch["status"], "pending")
        self.assertEqual(batch["error_rows"], 1)
        self.assertFalse(confirm_result["imported"])
        self.assertEqual(confirm_result["error"], "batch has validation errors")
        self.assertTrue(fetched["found"])


if __name__ == "__main__":
    unittest.main()
