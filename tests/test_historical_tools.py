import unittest

from agent.runtime.simple_historical_agent import SimpleHistoricalAgent
from tools.historical.repository import HistoricalEventRepository
from tools.historical.service import HistoricalQueryService


class HistoricalToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = HistoricalQueryService(HistoricalEventRepository.from_default_sample())

    def test_search_events_by_year_returns_overlapping_range_event(self) -> None:
        result = self.service.search_events_by_year(755)

        titles = {event["title"] for event in result["events"]}
        self.assertIn("安史之乱爆发", titles)
        self.assertNotIn("怛罗斯之战", titles)

    def test_search_events_by_year_with_nearby_window(self) -> None:
        result = self.service.search_events_by_year(
            755,
            regions=["中东", "中亚", "东亚"],
            nearby_window=10,
        )

        titles = {event["title"] for event in result["events"]}
        self.assertIn("安史之乱爆发", titles)
        self.assertIn("怛罗斯之战", titles)
        self.assertIn("阿拔斯王朝建立", titles)

    def test_search_events_by_range_finds_multiple_regions(self) -> None:
        result = self.service.search_events_by_range(600, 650)

        regions = {event["region"] for event in result["events"]}
        self.assertIn("东亚", regions)
        self.assertIn("中东", regions)

    def test_compare_regions_keeps_requested_region_order(self) -> None:
        result = self.service.compare_regions(
            start_year=600,
            end_year=650,
            regions=["中东", "东亚"],
        )

        self.assertEqual([row["region"] for row in result["rows"]], ["中东", "东亚"])
        self.assertGreater(result["rows"][0]["count"], 0)
        self.assertGreater(result["rows"][1]["count"], 0)

    def test_simple_agent_routes_year_question_to_year_tool(self) -> None:
        agent = SimpleHistoricalAgent.from_sample_data()

        response = agent.run("755年中国发生安史之乱时，中东和中亚发生了什么？")

        self.assertEqual(response.steps[0].tool_name, "search_events_by_year")
        self.assertIn("755 年前后 10 年历史事件对照", response.answer)


if __name__ == "__main__":
    unittest.main()
