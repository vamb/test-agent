import unittest

from apps.api.settings import AppSettings
from tools.database.postgres import PostgresClient
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.service import HistoricalQueryService


class PostgresRepositoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = AppSettings.from_env().postgres
        cls.db_available = PostgresClient(cls.settings).health_check().ok

    def setUp(self) -> None:
        if not self.db_available:
            self.skipTest("PostgreSQL is not available")
        self.service = HistoricalQueryService(PostgresHistoricalEventRepository(self.settings))

    def test_search_year_with_nearby_window_uses_database(self) -> None:
        result = self.service.search_events_by_year(
            755,
            regions=["东亚", "中东", "中亚"],
            nearby_window=10,
        )

        titles = {event["title"] for event in result["events"]}
        self.assertIn("安史之乱爆发", titles)
        self.assertIn("怛罗斯之战", titles)
        self.assertIn("阿拔斯王朝建立", titles)

    def test_event_detail_includes_sources(self) -> None:
        search_result = self.service.search_events_by_year(755, regions=["东亚"])
        event_id = search_result["events"][0]["id"]

        detail = self.service.get_event_detail(event_id)

        self.assertTrue(detail["found"])
        self.assertGreaterEqual(len(detail["event"]["sources"]), 1)

    def test_contemporary_events_excludes_target_event(self) -> None:
        search_result = self.service.search_events_by_year(755, regions=["东亚"])
        event_id = search_result["events"][0]["id"]

        result = self.service.find_contemporary_events(
            event_id,
            window_years=10,
            regions=["东亚", "中东", "中亚"],
        )

        titles = {event["title"] for event in result["events"]}
        self.assertNotIn("安史之乱爆发", titles)
        self.assertIn("怛罗斯之战", titles)

    def test_related_events_returns_seeded_relations(self) -> None:
        search_result = self.service.search_events_by_year(751, regions=["中亚"])
        event_id = search_result["events"][0]["id"]

        result = self.service.find_related_events(event_id)

        relation_types = {relation["relation_type"] for relation in result["relations"]}
        self.assertIn("conflict_link", relation_types)


if __name__ == "__main__":
    unittest.main()
