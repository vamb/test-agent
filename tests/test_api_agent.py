import unittest

from apps.api.main import (
    _sse_events,
    cancel_agent_run,
    find_contemporary_events,
    find_related_events,
    get_agent_run,
    query_agent,
)
from apps.api.settings import AppSettings
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.service import HistoricalQueryService


class ApiAgentTest(unittest.TestCase):
    def test_query_agent_records_run(self) -> None:
        response = query_agent(
            {"input": "755年中国发生安史之乱时，中东和中亚发生了什么？"}
        )

        self.assertIn("run_id", response)
        self.assertIn("安史之乱爆发", response["answer"])
        self.assertTrue(any(event["title"] == "安史之乱爆发" for event in response["events"]))
        self.assertIn("references", response)
        self.assertIn("links", response)
        run = get_agent_run(response["run_id"])
        self.assertTrue(run["found"])
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["steps"][0]["tool_name"], "search_events_by_year")
        self.assertIn("message_count", run["steps"][0]["model_input_summary"])
        self.assertIn("estimated_cost_usd", run["steps"][0]["model_output_summary"])
        self.assertEqual(run["steps"][0]["token_input"], 0)
        self.assertEqual(run["steps"][0]["token_output"], 0)

    def test_sse_event_format(self) -> None:
        chunks = list(
            _sse_events(
                [
                    {
                        "event": "final_answer",
                        "run_id": "run-1",
                        "answer": "安史之乱爆发",
                    }
                ]
            )
        )

        self.assertEqual(len(chunks), 1)
        self.assertIn("event: final_answer", chunks[0])
        self.assertIn("data:", chunks[0])
        self.assertIn("安史之乱爆发", chunks[0])

    def test_cancel_agent_run_endpoint(self) -> None:
        response = query_agent(
            {"input": "755年中国发生安史之乱时，中东和中亚发生了什么？"}
        )

        result = cancel_agent_run(response["run_id"], {"reason": "too late"})

        self.assertFalse(result["cancelled"])
        self.assertEqual(result["status"], "unchanged")

    def test_event_relation_api_helpers(self) -> None:
        service = HistoricalQueryService(
            PostgresHistoricalEventRepository(AppSettings.from_env().postgres)
        )
        search = service.search_events_by_year(751, regions=["中亚"])
        event_id = search["events"][0]["id"]

        contemporary = find_contemporary_events(
            event_id,
            window_years=10,
            regions=["东亚", "中东", "中亚"],
        )
        relations = find_related_events(event_id)

        self.assertGreaterEqual(contemporary["count"], 1)
        self.assertGreaterEqual(relations["count"], 1)


if __name__ == "__main__":
    unittest.main()
