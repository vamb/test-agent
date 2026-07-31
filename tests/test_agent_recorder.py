import unittest

from agent.runtime.recorder import AgentRunRecorder
from agent.runtime.simple_historical_agent import SimpleHistoricalAgent
from apps.api.settings import AppSettings
from tools.database.postgres import PostgresClient


class AgentRecorderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = AppSettings.from_env().postgres
        cls.db_available = PostgresClient(cls.settings).health_check().ok

    def setUp(self) -> None:
        if not self.db_available:
            self.skipTest("PostgreSQL is not available")

    def test_agent_run_is_recorded(self) -> None:
        agent = SimpleHistoricalAgent.from_postgres(record_runs=True)

        response = agent.run("755年中国发生安史之乱时，中东和中亚发生了什么？")

        self.assertIsNotNone(response.run_id)
        recorder = AgentRunRecorder(self.settings)
        run = recorder.get_run(response.run_id or "")
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run["status"], "completed")
        self.assertEqual(len(run["steps"]), 1)
        self.assertEqual(run["steps"][0]["tool_name"], "search_events_by_year")

    def test_cancel_run_prevents_completion_overwrite(self) -> None:
        recorder = AgentRunRecorder(self.settings)
        recorded_run = recorder.start_run("cancel me")

        cancelled = recorder.cancel_run(recorded_run.run_id, "test cancellation")
        recorder.finish_run(recorded_run.run_id, "should not overwrite")
        run = recorder.get_run(recorded_run.run_id)

        self.assertTrue(cancelled)
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run["status"], "cancelled")
        self.assertEqual(run["error_message"], "test cancellation")
        self.assertIsNone(run["final_answer"])

    def test_security_event_is_recorded_and_listed(self) -> None:
        recorder = AgentRunRecorder(self.settings)
        recorded_run = recorder.start_run("security audit me")

        event_id = recorder.record_security_event(
            event_type="security_blocked",
            category="prompt_injection",
            reason="unit-test security reason",
            run_id=recorded_run.run_id,
            metadata={"source": "unit-test"},
        )
        events = recorder.list_security_events(recorded_run.run_id)

        self.assertTrue(event_id)
        self.assertEqual(events[0]["event_type"], "security_blocked")
        self.assertEqual(events[0]["category"], "prompt_injection")
        self.assertEqual(events[0]["metadata"]["source"], "unit-test")


if __name__ == "__main__":
    unittest.main()
