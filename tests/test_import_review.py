import unittest
from uuid import uuid4

from apps.api.main import (
    bulk_revalidate_import_staging,
    confirm_import_batch,
    create_import_batch,
    get_import_batch,
    get_import_staging_rows,
    list_import_batches,
    merge_import_staging_row,
    parse_import_events,
    preview_import_batch,
    revalidate_import_batch,
    update_import_staging_row,
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

    def test_list_and_fix_staging_row(self) -> None:
        event = valid_import_event("测试可修正导入事件")
        event["sources"] = []
        service = ImportReviewService(self.settings)
        batch = service.create_batch(
            filename="fix-staging-import.json",
            source_note="unit-test",
            created_by="test",
            events=[event],
        )
        staging = get_import_staging_rows(batch["id"])
        row_id = staging["rows"][0]["id"]

        fixed_event = valid_import_event("测试可修正导入事件")
        updated = update_import_staging_row(row_id, {"raw_payload": fixed_event})
        revalidated = revalidate_import_batch(batch["id"])
        batches = list_import_batches(status="validated", created_by="test", limit=5)

        self.assertTrue(updated["updated"])
        self.assertEqual(updated["row"]["status"], "validated")
        self.assertTrue(revalidated["revalidated"])
        self.assertEqual(revalidated["batch"]["error_rows"], 0)
        self.assertGreaterEqual(batches["total"], 1)

    def test_bulk_revalidate_staging_rows(self) -> None:
        event = valid_import_event("测试批量重校验事件")
        event["sources"] = []
        service = ImportReviewService(self.settings)
        batch = service.create_batch(
            filename="bulk-revalidate-import.json",
            source_note="unit-test",
            created_by="test",
            events=[event],
        )
        staging = get_import_staging_rows(batch["id"])
        row_id = staging["rows"][0]["id"]
        fixed_event = valid_import_event("测试批量重校验事件")
        update_import_staging_row(row_id, {"raw_payload": fixed_event})

        result = bulk_revalidate_import_staging({"batch_id": batch["id"]})

        self.assertTrue(result["success"])
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["validated"], 1)

    def test_parse_import_events_accepts_json_and_csv(self) -> None:
        title = f"测试解析事件-{uuid4()}"
        parsed_json = parse_import_events(
            {
                "input_format": "json",
                "content": {"events": [valid_import_event(title)]},
            }
        )
        csv_content = (
            "title,start_year,end_year,start_date_text,end_date_text,time_precision,"
            "region,polity,modern_country,category,summary,causes,effects,actors,"
            "source_status,confidence,source_title,source_type,citation,excerpt,source_reliability\n"
            f"{title}-CSV,904,904,904年,904年,year,测试地区,测试政权,测试国,"
            "测试分类,CSV解析测试事件,测试原因,测试影响,测试人物,draft,0.8,"
            "测试来源,note,测试引用,测试摘录,0.8\n"
        )
        parsed_csv = parse_import_events({"input_format": "csv", "content": csv_content})

        self.assertTrue(parsed_json["parsed"])
        self.assertEqual(parsed_json["count"], 1)
        self.assertEqual(parsed_json["valid_rows"], 1)
        self.assertTrue(parsed_csv["parsed"])
        self.assertEqual(parsed_csv["count"], 1)
        self.assertEqual(parsed_csv["valid_rows"], 1)
        self.assertEqual(parsed_csv["events"][0]["title"], f"{title}-CSV")

    def test_merge_staging_row_targets_existing_event(self) -> None:
        title = f"测试合并导入事件-{uuid4()}"
        service = ImportReviewService(self.settings)
        existing_event = valid_import_event(title)
        existing_event["start_year"] = 905
        existing_event["end_year"] = 905
        existing_batch = service.create_batch(
            filename="merge-existing-import.json",
            source_note="unit-test",
            created_by="test",
            events=[existing_event],
        )
        imported = service.confirm_import(existing_batch["id"], confirmed_by="test")
        target_event_id = imported["event_ids"][0]

        incoming_event = valid_import_event(title)
        incoming_event["start_year"] = 905
        incoming_event["end_year"] = 905
        incoming_event["summary"] = "合并后应该写入的新摘要。"
        incoming_event["category"] = ["测试分类", "合并分类"]
        incoming_event["sources"][0]["source_title"] = "合并新增来源"
        incoming_event["sources"][0]["citation"] = "合并新增引用"
        merge_batch = service.create_batch(
            filename="merge-new-import.json",
            source_note="unit-test",
            created_by="test",
            events=[incoming_event],
        )
        row_id = get_import_staging_rows(merge_batch["id"])["rows"][0]["id"]

        merged = merge_import_staging_row(
            row_id,
            {
                "strategy": "merge_sources_and_categories",
                "target_event_id": target_event_id,
            },
        )
        confirmed = service.confirm_import(merge_batch["id"], confirmed_by="test")
        detail = HistoricalQueryService(PostgresHistoricalEventRepository(self.settings)).get_event_detail(
            target_event_id
        )

        self.assertTrue(merged["merged"])
        self.assertEqual(merged["row"]["raw_payload"]["id"], target_event_id)
        self.assertTrue(confirmed["imported"])
        self.assertEqual(confirmed["event_ids"], [target_event_id])
        self.assertEqual(detail["event"]["summary"], "合并后应该写入的新摘要。")
        self.assertIn("合并分类", detail["event"]["category"])
        self.assertGreaterEqual(len(detail["event"]["sources"]), 2)

    def test_preview_batch_detects_duplicate_candidates(self) -> None:
        event = valid_import_event("测试重复预览事件")
        service = ImportReviewService(self.settings)
        imported_batch = service.create_batch(
            filename="duplicate-preview-base.json",
            source_note="unit-test",
            created_by="test",
            events=[event],
        )
        service.confirm_import(imported_batch["id"], confirmed_by="test")
        preview_batch = service.create_batch(
            filename="duplicate-preview-new.json",
            source_note="unit-test",
            created_by="test",
            events=[event],
        )

        preview = preview_import_batch(preview_batch["id"])

        self.assertEqual(preview["count"], 1)
        self.assertEqual(preview["duplicate_rows"], 1)
        self.assertTrue(preview["rows"][0]["has_duplicate_candidates"])


if __name__ == "__main__":
    unittest.main()
