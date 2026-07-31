import unittest
from uuid import uuid4

from apps.api.main import (
    admin_add_source,
    admin_bulk_update_events,
    admin_bulk_verify_sources,
    admin_create_relation,
    admin_data_quality_summary,
    admin_delete_relation,
    admin_delete_source,
    admin_dictionaries,
    admin_dispute_event,
    admin_get_event_detail,
    admin_get_event_changes,
    admin_import_batch_review,
    admin_import_batch_report,
    admin_list_data_quality_issues,
    admin_list_events,
    admin_list_relations,
    admin_overview,
    admin_set_data_quality_issue_action,
    admin_update_relation,
    admin_update_source,
    admin_update_event,
    admin_verify_source,
)
from apps.api.settings import AppSettings
from tests.test_import_review import valid_import_event
from tools.database.postgres import PostgresClient
from tools.historical.event_management import EventManagementService
from tools.historical.event_revision import EventRevisionToolService
from tools.historical.import_review import ImportReviewService
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.service import HistoricalQueryService
from tools.historical.source_revision import SourceRevisionToolService
from tools.historical.tool_registry import build_historical_tool_registry


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

    def test_agent_event_revision_drafts_before_confirmed_apply(self) -> None:
        event_id = self._create_managed_event("测试 Agent 修订草案事件")
        service = EventManagementService(self.settings.postgres, self.settings.security)
        revision_tools = EventRevisionToolService(
            service,
            self.settings.security.admin_api_token,
        )

        draft = revision_tools.draft_event_revision(
            {
                "event_id": event_id,
                "updates": {"summary": "Agent 草案摘要。", "confidence": 0.81},
                "reason": "unit-test agent draft",
                "confirmed_by": "agent-test",
            }
        )
        detail_after_draft = service.get_admin_event_detail(event_id)
        unconfirmed_apply = revision_tools.apply_event_revision(
            {
                "event_id": event_id,
                "updates": {"summary": "不应写入。"},
            }
        )

        self.assertTrue(draft["success"])
        self.assertEqual(draft["next_step"]["tool_name"], "apply_event_revision")
        self.assertTrue(draft["next_step"]["requires_confirmation"])
        self.assertEqual(
            {item["field"] for item in draft["diff"]},
            {"summary", "confidence"},
        )
        self.assertNotEqual(detail_after_draft["event"]["summary"], "Agent 草案摘要。")
        self.assertFalse(unconfirmed_apply["success"])
        self.assertEqual(unconfirmed_apply["error"], "explicit confirmation required")

        applied = revision_tools.apply_event_revision(
            {
                "event_id": event_id,
                "updates": {"summary": "Agent 草案摘要。", "confidence": 0.81},
                "reason": "unit-test agent apply",
                "confirmed_by": "agent-test",
                "confirmed": True,
            }
        )
        changes = service.get_event_changes(event_id)

        self.assertTrue(applied["success"])
        self.assertEqual(applied["event"]["summary"], "Agent 草案摘要。")
        self.assertGreaterEqual(changes["total"], 1)
        self.assertEqual(changes["changes"][0]["action"], "update_event")

    def test_agent_event_revision_tools_are_registered_with_confirmation_policy(self) -> None:
        service = HistoricalQueryService(
            PostgresHistoricalEventRepository(self.settings.postgres)
        )
        registry = build_historical_tool_registry(
            service,
            event_management_service=EventManagementService(
                self.settings.postgres,
                self.settings.security,
            ),
            admin_token=self.settings.security.admin_api_token,
        )
        definitions = {item["name"]: item for item in registry.definitions()}

        self.assertIn("draft_event_revision", definitions)
        self.assertIn("apply_event_revision", definitions)
        self.assertFalse(definitions["draft_event_revision"]["requires_confirmation"])
        self.assertTrue(definitions["apply_event_revision"]["requires_confirmation"])
        self.assertEqual(definitions["apply_event_revision"]["risk_level"], "high")

    def test_agent_source_revision_drafts_before_confirmed_apply(self) -> None:
        event_id = self._create_managed_event("测试 Agent 来源核验事件")
        service = EventManagementService(self.settings.postgres, self.settings.security)
        source_id = service.get_admin_event_detail(event_id)["sources"][0]["id"]
        revision_tools = SourceRevisionToolService(
            service,
            self.settings.security.admin_api_token,
        )

        draft = revision_tools.draft_source_revision(
            {
                "source_id": source_id,
                "updates": {
                    "reliability": 0.86,
                    "is_primary": True,
                    "citation": "Agent 核验后的引用。",
                },
                "reason": "unit-test source draft",
                "confirmed_by": "agent-test",
            }
        )
        detail_after_draft = service.get_admin_event_detail(event_id)
        source_after_draft = next(
            source for source in detail_after_draft["sources"] if source["id"] == source_id
        )
        unconfirmed_apply = revision_tools.apply_source_revision(
            {
                "source_id": source_id,
                "updates": {"citation": "不应写入。"},
            }
        )

        self.assertTrue(draft["success"])
        self.assertEqual(draft["next_step"]["tool_name"], "apply_source_revision")
        self.assertTrue(draft["next_step"]["requires_confirmation"])
        self.assertEqual(
            {item["field"] for item in draft["diff"]},
            {"reliability", "is_primary", "citation"},
        )
        self.assertNotEqual(source_after_draft["citation"], "Agent 核验后的引用。")
        self.assertFalse(unconfirmed_apply["success"])
        self.assertEqual(unconfirmed_apply["error"], "explicit confirmation required")

        applied = revision_tools.apply_source_revision(
            {
                "source_id": source_id,
                "updates": {
                    "reliability": 0.86,
                    "is_primary": True,
                    "citation": "Agent 核验后的引用。",
                },
                "reason": "unit-test source apply",
                "confirmed_by": "agent-test",
                "confirmed": True,
            }
        )
        changes = service.get_event_changes(event_id)

        self.assertTrue(applied["success"])
        self.assertEqual(applied["source"]["citation"], "Agent 核验后的引用。")
        self.assertTrue(applied["source"]["is_primary"])
        self.assertGreaterEqual(changes["total"], 1)
        self.assertEqual(changes["changes"][0]["action"], "update_source")

    def test_agent_source_revision_tools_are_registered_with_confirmation_policy(self) -> None:
        service = HistoricalQueryService(
            PostgresHistoricalEventRepository(self.settings.postgres)
        )
        registry = build_historical_tool_registry(
            service,
            event_management_service=EventManagementService(
                self.settings.postgres,
                self.settings.security,
            ),
            admin_token=self.settings.security.admin_api_token,
        )
        definitions = {item["name"]: item for item in registry.definitions()}

        self.assertIn("draft_source_revision", definitions)
        self.assertIn("apply_source_revision", definitions)
        self.assertFalse(definitions["draft_source_revision"]["requires_confirmation"])
        self.assertTrue(definitions["apply_source_revision"]["requires_confirmation"])
        self.assertEqual(definitions["apply_source_revision"]["risk_level"], "high")

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

    def test_update_event_extended_fields(self) -> None:
        event_id = self._create_managed_event("测试扩展字段事件")

        updated = admin_update_event(
            event_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "reason": "unit-test extended update",
                "updates": {
                    "start_year": 903,
                    "end_year": 904,
                    "start_date_text": "903年",
                    "end_date_text": "904年",
                    "time_precision": "range",
                    "region": "测试新地区",
                    "polity": "测试新政权",
                    "modern_country": "测试新国家",
                    "category": ["测试新分类"],
                    "causes": ["扩展原因"],
                    "effects": ["扩展影响"],
                    "importance_score": 2.5,
                },
            },
        )

        self.assertTrue(updated["success"])
        self.assertEqual(updated["event"]["start_year"], 903)
        self.assertEqual(updated["event"]["end_year"], 904)
        self.assertEqual(updated["event"]["region"], "测试新地区")
        self.assertEqual(updated["event"]["polity"], "测试新政权")
        self.assertIn("测试新分类", updated["event"]["category"])
        self.assertIn("扩展原因", updated["event"]["causes"])

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

    def test_admin_lists_events_and_changes(self) -> None:
        event_id = self._create_managed_event("测试列表事件")
        updated = admin_update_event(
            event_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "updates": {"summary": "列表测试更新。"},
            },
        )
        overview = admin_overview()
        events = admin_list_events(query="测试列表事件", limit=5)
        changes = admin_get_event_changes(event_id)

        self.assertTrue(updated["success"])
        self.assertGreaterEqual(int(overview["events"]["total_events"]), 1)
        self.assertGreaterEqual(events["total"], 1)
        self.assertGreaterEqual(changes["total"], 1)

    def test_admin_events_support_page_pagination(self) -> None:
        first_id = self._create_managed_event("测试分页事件一")
        second_id = self._create_managed_event("测试分页事件二")

        first_page = admin_list_events(query="测试分页事件", page=1, page_size=1)
        second_page = admin_list_events(query="测试分页事件", page=2, page_size=1)

        self.assertGreaterEqual(first_page["total"], 2)
        self.assertEqual(first_page["page"], 1)
        self.assertEqual(first_page["page_size"], 1)
        self.assertEqual(first_page["offset"], 0)
        self.assertEqual(first_page["count"], 1)
        self.assertEqual(second_page["page"], 2)
        self.assertEqual(second_page["offset"], 1)
        self.assertEqual(second_page["count"], 1)
        self.assertNotEqual(first_page["events"][0]["id"], second_page["events"][0]["id"])
        self.assertIn(first_page["events"][0]["id"], {first_id, second_id})
        self.assertIn(second_page["events"][0]["id"], {first_id, second_id})

    def test_data_quality_summary_and_issues(self) -> None:
        event = valid_import_event("测试质量问题事件")
        event["sources"] = []
        event["confidence"] = 0.4
        batch = ImportReviewService(self.settings.postgres).create_batch(
            filename="quality-test.json",
            source_note="unit-test",
            created_by="test",
            events=[event],
        )
        staging = ImportReviewService(self.settings.postgres).list_staging_rows(batch["id"])
        row_id = staging["rows"][0]["id"]
        fixed_payload = valid_import_event("测试质量问题事件")
        fixed_payload["sources"] = []
        fixed_payload["confidence"] = 0.4
        # Insert directly through staging is rejected without sources; create a normal event then remove source.
        event_id = self._create_managed_event("测试质量问题事件")
        admin_update_event(
            event_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "updates": {"confidence": 0.4},
            },
        )
        detail = HistoricalQueryService(
            PostgresHistoricalEventRepository(self.settings.postgres)
        ).get_event_detail(event_id)
        source_id = detail["event"]["sources"][0]["id"]
        admin_delete_source(
            source_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
            },
        )

        summary = admin_data_quality_summary()
        missing_source_issues = admin_list_data_quality_issues(
            issue_type="missing_source",
            limit=200,
        )
        low_confidence_issues = admin_list_data_quality_issues(
            issue_type="low_confidence",
            limit=200,
        )

        self.assertGreaterEqual(summary["issues"]["missing_source"]["count"], 1)
        self.assertGreaterEqual(summary["issues"]["low_confidence"]["count"], 1)
        self.assertTrue(any(issue["target_id"] == event_id for issue in missing_source_issues["issues"]))
        self.assertTrue(any(issue["target_id"] == event_id for issue in low_confidence_issues["issues"]))

    def test_data_quality_issue_action_hides_resolved_issue(self) -> None:
        event_id = self._create_managed_event("测试质量问题处理台账事件")
        detail = HistoricalQueryService(
            PostgresHistoricalEventRepository(self.settings.postgres)
        ).get_event_detail(event_id)
        source_id = detail["event"]["sources"][0]["id"]
        admin_delete_source(
            source_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
            },
        )

        before = admin_list_data_quality_issues(issue_type="missing_source", limit=200)
        issue = next(item for item in before["issues"] if item["target_id"] == event_id)
        resolved = admin_set_data_quality_issue_action(
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "issue_type": issue["issue_type"],
                "target_type": issue["target_type"],
                "target_id": issue["target_id"],
                "status": "resolved",
                "handled_by": "test-admin",
                "reason": "unit-test resolved",
            }
        )
        after = admin_list_data_quality_issues(issue_type="missing_source", limit=200)

        self.assertTrue(resolved["success"])
        self.assertEqual(resolved["action"]["status"], "resolved")
        self.assertFalse(any(item["target_id"] == event_id for item in after["issues"]))

    def test_list_events_by_import_batch_and_duplicate_title_quality(self) -> None:
        first = valid_import_event("测试重复标题质量事件")
        first["start_year"] = 906
        first["end_year"] = 906
        first["polity"] = "测试政权甲"
        second = valid_import_event("测试重复标题质量事件")
        second["start_year"] = 906
        second["end_year"] = 906
        second["polity"] = "测试政权乙"
        batch = ImportReviewService(self.settings.postgres).create_batch(
            filename="duplicate-title-quality.json",
            source_note="unit-test",
            created_by="test",
            events=[first, second],
        )
        imported = ImportReviewService(self.settings.postgres).confirm_import(
            batch["id"],
            confirmed_by="test",
        )

        listed = admin_list_events(import_batch_id=batch["id"], limit=10)
        duplicate_title_issues = admin_list_data_quality_issues(
            issue_type="duplicate_title",
            limit=20,
        )

        self.assertTrue(imported["imported"])
        self.assertEqual(listed["total"], 2)
        self.assertEqual(
            {event["id"] for event in listed["events"]},
            set(imported["event_ids"]),
        )
        self.assertTrue(
            any(issue["title"] == "测试重复标题质量事件" for issue in duplicate_title_issues["issues"])
        )

    def test_import_batch_review_summarizes_seed_quality(self) -> None:
        first = valid_import_event("测试批次核验事件")
        first["start_year"] = 907
        first["end_year"] = 907
        first["polity"] = "测试政权甲"
        first["confidence"] = 0.65
        first["sources"][0]["reliability"] = 0.6
        second = valid_import_event("测试批次核验事件")
        second["start_year"] = 907
        second["end_year"] = 907
        second["polity"] = "测试政权乙"
        batch = ImportReviewService(self.settings.postgres).create_batch(
            filename="batch-review-quality.json",
            source_note="unit-test",
            created_by="test",
            events=[first, second],
        )
        ImportReviewService(self.settings.postgres).confirm_import(
            batch["id"],
            confirmed_by="test",
        )

        review = admin_import_batch_review(batch["id"])

        self.assertTrue(review["found"])
        self.assertEqual(review["count"], 2)
        self.assertEqual(review["review"]["low_confidence_count"], 1)
        self.assertEqual(review["review"]["weak_source_count"], 1)
        self.assertGreaterEqual(review["review"]["duplicate_candidate_count"], 2)
        self.assertTrue(review["review"]["ready_for_manual_review"])

    def test_import_batch_report_tracks_quality_progress(self) -> None:
        first = valid_import_event("测试批次运营报表事件")
        first["start_year"] = 908
        first["end_year"] = 908
        first["confidence"] = 0.64
        second = valid_import_event("测试批次运营报表事件")
        second["start_year"] = 908
        second["end_year"] = 908
        second["polity"] = "测试报表政权乙"
        batch = ImportReviewService(self.settings.postgres).create_batch(
            filename="batch-operations-report.json",
            source_note="unit-test",
            created_by="test",
            events=[first, second],
        )
        imported = ImportReviewService(self.settings.postgres).confirm_import(
            batch["id"],
            confirmed_by="test",
        )
        admin_set_data_quality_issue_action(
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "issue_type": "low_confidence",
                "target_type": "event",
                "target_id": imported["event_ids"][0],
                "status": "resolved",
                "handled_by": "test-admin",
            }
        )

        report = admin_import_batch_report(batch["id"])

        self.assertTrue(report["found"])
        self.assertEqual(report["totals"]["imported_events"], 2)
        self.assertEqual(report["quality"]["low_confidence"]["count"], 1)
        self.assertEqual(report["quality"]["low_confidence"]["handled_count"], 1)
        self.assertGreaterEqual(report["quality"]["duplicate_title"]["count"], 2)
        self.assertGreaterEqual(report["totals"]["quality_issue_count"], 2)
        self.assertIn("regions", report["distributions"])

    def test_dictionaries_and_admin_event_detail(self) -> None:
        source_event_id = self._create_managed_event("测试详情源事件")
        target_event_id = self._create_managed_event("测试详情目标事件")
        relation = admin_create_relation(
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "relation": {
                    "source_event_id": source_event_id,
                    "target_event_id": target_event_id,
                    "relation_type": "contemporary",
                    "explanation": "详情页关系测试。",
                    "confidence": 0.5,
                },
            },
        )
        admin_update_event(
            source_event_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "updates": {"summary": "详情聚合测试更新。"},
            },
        )

        dictionaries = admin_dictionaries()
        detail = admin_get_event_detail(source_event_id)

        self.assertIn("event_statuses", dictionaries)
        self.assertIn("source_types", dictionaries)
        self.assertTrue(detail["found"])
        self.assertEqual(detail["event"]["id"], source_event_id)
        self.assertGreaterEqual(len(detail["sources"]), 1)
        self.assertTrue(any(item["id"] == relation["relation"]["id"] for item in detail["relations"]))
        self.assertGreaterEqual(len(detail["changes"]), 1)
        self.assertIn("embedding", detail)

    def test_source_crud(self) -> None:
        event_id = self._create_managed_event("测试来源 CRUD 事件")
        add_result = admin_add_source(
            event_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "source": {
                    "source_title": "新增测试来源",
                    "source_type": "note",
                    "citation": "新增测试引用",
                    "reliability": 0.6,
                },
            },
        )
        source_id = add_result["source"]["id"]
        update_result = admin_update_source(
            source_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "updates": {"reliability": 0.7, "citation": "更新测试引用"},
            },
        )
        delete_result = admin_delete_source(
            source_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
            },
        )

        self.assertTrue(add_result["success"])
        self.assertTrue(update_result["success"])
        self.assertEqual(update_result["source"]["citation"], "更新测试引用")
        self.assertTrue(delete_result["deleted"])

    def test_bulk_update_events_and_verify_sources(self) -> None:
        first_event_id = self._create_managed_event("测试批量事件一")
        second_event_id = self._create_managed_event("测试批量事件二")
        first_detail = HistoricalQueryService(
            PostgresHistoricalEventRepository(self.settings.postgres)
        ).get_event_detail(first_event_id)
        second_detail = HistoricalQueryService(
            PostgresHistoricalEventRepository(self.settings.postgres)
        ).get_event_detail(second_event_id)
        source_ids = [
            first_detail["event"]["sources"][0]["id"],
            second_detail["event"]["sources"][0]["id"],
        ]

        updated = admin_bulk_update_events(
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "event_ids": [first_event_id, second_event_id],
                "updates": {"source_status": "reviewing", "confidence": 0.72},
            }
        )
        verified = admin_bulk_verify_sources(
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "source_ids": source_ids,
                "reliability": 0.88,
            }
        )

        self.assertTrue(updated["success"])
        self.assertEqual(updated["updated"], 2)
        self.assertTrue(verified["success"])
        self.assertEqual(verified["verified"], 2)

    def test_relation_crud(self) -> None:
        source_event_id = self._create_managed_event("测试关系源事件")
        target_event_id = self._create_managed_event("测试关系目标事件")
        created = admin_create_relation(
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "relation": {
                    "source_event_id": source_event_id,
                    "target_event_id": target_event_id,
                    "relation_type": "contemporary",
                    "explanation": "两个测试事件同年发生。",
                    "confidence": 0.6,
                },
            },
        )
        relation_id = created["relation"]["id"]
        listed = admin_list_relations(event_id=source_event_id, limit=5)
        updated = admin_update_relation(
            relation_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
                "updates": {"confidence": 0.8, "explanation": "更新后的关系说明。"},
            },
        )
        deleted = admin_delete_relation(
            relation_id,
            {
                "admin_token": self.settings.security.admin_api_token,
                "confirmed": True,
                "confirmed_by": "test-admin",
            },
        )

        self.assertTrue(created["success"])
        self.assertGreaterEqual(listed["total"], 1)
        self.assertTrue(updated["success"])
        self.assertEqual(float(updated["relation"]["confidence"]), 0.8)
        self.assertTrue(deleted["deleted"])


if __name__ == "__main__":
    unittest.main()
