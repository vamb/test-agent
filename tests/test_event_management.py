import unittest
from uuid import uuid4

from apps.api.main import (
    admin_dispute_event,
    admin_update_event,
    admin_verify_source,
)
from apps.api.settings import AppSettings
from tests.test_import_review import valid_import_event
from tools.database.postgres import PostgresClient
from tools.historical.event_management import EventManagementService
from tools.historical.import_review import ImportReviewService
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.service import HistoricalQueryService


class EventManagementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = AppSettings.from_env()
        cls.db_available = PostgresClient(cls.settings.postgres).health_check().ok

    def setUp(self) -> None:
        if not self.db_available:
            self.skipTest("PostgreSQL is not available")

    def _create_managed_event(self, title: str = "测试管理事件") -> str:
        unique_title = f"{title}-{uuid4()}"
        event = valid_import_event(unique_title)
        event["start_year"] = 902
        event["end_year"] = 902
        event["start_date_text"] = "902年"
        event["end_date_text"] = "902年"
        batch = ImportReviewService(self.settings.postgres).create_batch(
            filename="event-management-test.json",
            source_note="unit-test",
            created_by="test",
            events=[event],
        )
        result = ImportReviewService(self.settings.postgres).confirm_import(
            batch["id"],
            confirmed_by="test",
        )
        return result["event_ids"][0]

    def test_update_requires_admin_and_confirmation(self) -> None:
        event_id = self._create_managed_event("测试未授权修改事件")
        service = EventManagementService(self.settings.postgres, self.settings.security)

        no_token = service.update_event(
            event_id,
            {"confirmed": True, "updates": {"summary": "bad"}},
        )
        no_confirm = service.update_event(
            event_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "updates": {"summary": "bad"},
            },
        )

        self.assertFalse(no_token["success"])
        self.assertEqual(no_token["error"], "admin authorization required")
        self.assertFalse(no_confirm["success"])
        self.assertEqual(no_confirm["error"], "explicit confirmation required")

    def test_update_and_dispute_event(self) -> None:
        event_id = self._create_managed_event("测试可管理事件")

        updated = admin_update_event(
            event_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "reason": "unit-test update",
                "updates": {"summary": "已经通过管理接口更新。", "confidence": 0.75},
            },
        )
        disputed = admin_dispute_event(
            event_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "reason": "测试争议标记",
            },
        )

        self.assertTrue(updated["success"])
        self.assertEqual(updated["event"]["summary"], "已经通过管理接口更新。")
        self.assertTrue(disputed["success"])
        service = HistoricalQueryService(PostgresHistoricalEventRepository(self.settings.postgres))
        detail = service.get_event_detail(event_id)
        self.assertEqual(detail["event"]["source_status"], "disputed")

    def test_verify_source_marks_primary_and_reliable(self) -> None:
        event_id = self._create_managed_event("测试来源核验事件")
        detail = HistoricalQueryService(
            PostgresHistoricalEventRepository(self.settings.postgres)
        ).get_event_detail(event_id)
        source_id = detail["event"]["sources"][0]["id"]

        result = admin_verify_source(
            source_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "reason": "unit-test source verify",
                "reliability": 0.9,
            },
        )

        self.assertTrue(result["success"])
        self.assertGreaterEqual(float(result["source"]["reliability"]), 0.9)
        self.assertTrue(result["source"]["is_primary"])


if __name__ == "__main__":
    unittest.main()
