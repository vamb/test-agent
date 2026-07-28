import unittest
from typing import Any

from agent.models.base import ModelDecision, ToolCall
from agent.models.rule_based_adapter import RuleBasedModelAdapter
from agent.runtime.loop import AgentLoop, AgentLoopConfig
from agent.runtime.recorder import AgentRunRecorder
from apps.api.settings import AppSettings
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.service import HistoricalQueryService
from tools.historical.tool_registry import build_historical_tool_registry
from tools.registry.executor import ToolExecutor


class AgentLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        settings = AppSettings.from_env().postgres
        service = HistoricalQueryService(PostgresHistoricalEventRepository(settings))
        self.agent = AgentLoop(
            model_adapter=RuleBasedModelAdapter(),
            tool_registry=build_historical_tool_registry(service),
            config=AgentLoopConfig(max_steps=8),
        )

    def test_year_query_calls_year_tool(self) -> None:
        response = self.agent.run("755年中国发生安史之乱时，中东和中亚发生了什么？")

        self.assertEqual([step.tool_name for step in response.steps], ["search_events_by_year"])
        self.assertIn("安史之乱爆发", response.answer)
        self.assertIn("区分同期与因果", response.answer)

    def test_relation_query_uses_detail_and_relations(self) -> None:
        response = self.agent.run("怛罗斯之战和唐朝、中亚、阿拉伯帝国有什么关系？")
        called_tools = [step.tool_name for step in response.steps]

        self.assertIn("resolve_event", called_tools)
        self.assertIn("get_event_detail", called_tools)
        self.assertIn("search_events_by_year", called_tools)
        self.assertIn("find_related_events", called_tools)
        self.assertIn("证据强弱", response.answer)
        self.assertIn("阿拔斯王朝", response.answer)

    def test_loop_raises_when_max_steps_exceeded(self) -> None:
        settings = AppSettings.from_env().postgres
        service = HistoricalQueryService(PostgresHistoricalEventRepository(settings))
        agent = AgentLoop(
            model_adapter=AlwaysCallToolAdapter(),
            tool_registry=build_historical_tool_registry(service),
            config=AgentLoopConfig(max_steps=1),
        )

        with self.assertRaisesRegex(RuntimeError, "最大工具调用次数"):
            agent.run("一直调用工具")

    def test_stream_emits_step_and_final_events(self) -> None:
        events = list(
            self.agent.stream("755年中国发生安史之乱时，中东和中亚发生了什么？")
        )
        event_names = [event["event"] for event in events]

        self.assertEqual(event_names[0], "run_started")
        self.assertIn("step_started", event_names)
        self.assertIn("tool_called", event_names)
        self.assertIn("tool_result", event_names)
        self.assertIn("final_answer", event_names)
        self.assertEqual(event_names[-1], "run_completed")
        final_event = [event for event in events if event["event"] == "final_answer"][0]
        self.assertIn("安史之乱爆发", final_event["answer"])

    def test_stream_emits_cancelled_when_run_is_cancelled(self) -> None:
        settings = AppSettings.from_env().postgres
        service = HistoricalQueryService(PostgresHistoricalEventRepository(settings))
        recorder = AgentRunRecorder(settings)
        agent = AgentLoop(
            model_adapter=AlwaysCallToolAdapter(),
            tool_registry=build_historical_tool_registry(service),
            recorder=recorder,
            config=AgentLoopConfig(max_steps=3),
        )

        stream = agent.stream("取消测试")
        first_event = next(stream)
        recorder.cancel_run(first_event["run_id"], "user cancelled")
        remaining_events = list(stream)

        self.assertEqual(first_event["event"], "run_started")
        self.assertEqual(remaining_events[-1]["event"], "run_cancelled")
        run = recorder.get_run(first_event["run_id"])
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run["status"], "cancelled")

    def test_resume_existing_run_uses_recorded_tool_steps(self) -> None:
        settings = AppSettings.from_env().postgres
        service = HistoricalQueryService(PostgresHistoricalEventRepository(settings))
        recorder = AgentRunRecorder(settings)
        agent = AgentLoop(
            model_adapter=RuleBasedModelAdapter(),
            tool_registry=build_historical_tool_registry(service),
            recorder=recorder,
            config=AgentLoopConfig(max_steps=8),
        )
        user_input = "怛罗斯之战和唐朝、中亚、阿拉伯帝国有什么关系？"
        recorded = recorder.create_pending_run(user_input)
        claimed = recorder.claim_pending_run(recorded.run_id)
        assert claimed is not None

        registry = build_historical_tool_registry(service)
        resolve_result = ToolExecutor(registry).execute(
            "resolve_event",
            {"query": user_input},
        )
        recorder.record_tool_step(
            run_id=recorded.run_id,
            step_index=0,
            tool_name="resolve_event",
            tool_arguments=resolve_result.arguments,
            tool_result=resolve_result.observation,
        )

        response = agent.resume_existing(recorded.run_id)
        run = recorder.get_run(recorded.run_id)

        self.assertEqual(response.steps[0].tool_name, "resolve_event")
        self.assertEqual(response.steps[1].tool_name, "get_event_detail")
        self.assertIn("证据强弱", response.answer)
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["steps"][0]["tool_name"], "resolve_event")
        self.assertEqual(run["steps"][1]["tool_name"], "get_event_detail")


class AlwaysCallToolAdapter:
    model_name = "always-call-tool-test"

    def decide(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelDecision:
        return ModelDecision(
            action="call_tool",
            reason="test",
            tool_call=ToolCall(
                name="search_events_by_year",
                arguments={"year": 755},
            ),
        )


if __name__ == "__main__":
    unittest.main()
