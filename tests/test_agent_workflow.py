import importlib.util
import sys
import types
import unittest
from unittest.mock import patch

from agent.models.base import ModelDecision, ToolCall
from agent.models.rule_based_adapter import RuleBasedModelAdapter
from agent.runtime.loop import AgentLoop
from agent.runtime.recorder import AgentRunRecorder
from agent.runtime.workflow import LangGraphAgentWorkflow, build_agent_workflow
from apps.api.settings import AppSettings, AgentRuntimeSettings
from tools.database.postgres import PostgresClient
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.service import HistoricalQueryService
from tools.historical.tool_registry import build_historical_tool_registry
from tools.registry.base import ToolDefinition, ToolRegistry


class AgentWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = AppSettings.from_env()
        cls.db_available = PostgresClient(cls.settings.postgres).health_check().ok

    def test_runtime_settings_default_to_manual_loop(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = AgentRuntimeSettings.from_env()

        self.assertEqual(settings.workflow_engine, "loop")

    def test_factory_returns_manual_loop_by_default(self) -> None:
        workflow = build_agent_workflow(
            workflow_engine="loop",
            model_adapter=RuleBasedModelAdapter(),
            tool_registry=self._tool_registry(),
        )

        self.assertIsInstance(workflow, AgentLoop)

    def test_factory_rejects_unknown_engine(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported agent workflow engine"):
            build_agent_workflow(
                workflow_engine="unknown",
                model_adapter=RuleBasedModelAdapter(),
                tool_registry=self._tool_registry(),
            )

    def test_langgraph_adapter_requires_langgraph_package(self) -> None:
        if _module_available("langgraph.graph") or "langgraph.graph" in sys.modules:
            self.skipTest("langgraph is installed in this environment")

        with self.assertRaisesRegex(RuntimeError, "requires the langgraph package"):
            LangGraphAgentWorkflow(
                model_adapter=RuleBasedModelAdapter(),
                tool_registry=self._tool_registry(),
            )

    def test_langgraph_adapter_compiles_decision_tool_pipeline(self) -> None:
        fake_graph_module = types.ModuleType("langgraph.graph")
        fake_graph_module.END = "__end__"
        fake_graph_module.StateGraph = FakeStateGraph
        fake_langgraph_module = types.ModuleType("langgraph")
        fake_langgraph_module.graph = fake_graph_module

        with patch.dict(
            sys.modules,
            {
                "langgraph": fake_langgraph_module,
                "langgraph.graph": fake_graph_module,
            },
        ):
            workflow = LangGraphAgentWorkflow(
                model_adapter=RuleBasedModelAdapter(),
                tool_registry=self._tool_registry(),
            )

        self.assertEqual(
            workflow._graph.node_names,
            [
                "prepare_state",
                "decide",
                "execute_tool",
                "confirmation_required",
                "max_steps_exceeded",
                "finalize_response",
            ],
        )
        self.assertEqual(
            workflow._graph.edges,
            [
                ("prepare_state", "decide"),
                ("confirmation_required", "__end__"),
                ("max_steps_exceeded", "__end__"),
                ("finalize_response", "__end__"),
            ],
        )
        self.assertEqual(
            workflow._graph.conditional_sources,
            ["decide", "execute_tool"],
        )

    def test_langgraph_adapter_runs_decision_tool_pipeline(self) -> None:
        with _fake_langgraph_modules():
            workflow = LangGraphAgentWorkflow(
                model_adapter=RuleBasedModelAdapter(),
                tool_registry=self._tool_registry(),
            )

        response = workflow.run("755年中国发生安史之乱时，中东和中亚发生了什么？")

        self.assertIn("安史之乱爆发", response.answer)
        self.assertEqual([step.tool_name for step in response.steps], ["search_events_by_year"])

    def test_langgraph_adapter_stream_emits_sse_compatible_events(self) -> None:
        with _fake_langgraph_modules():
            workflow = LangGraphAgentWorkflow(
                model_adapter=RuleBasedModelAdapter(),
                tool_registry=self._tool_registry(),
            )

        events = list(workflow.stream("755年中国发生安史之乱时，中东和中亚发生了什么？"))
        event_names = [event["event"] for event in events]
        final_event = [event for event in events if event["event"] == "final_answer"][0]

        self.assertEqual(event_names[0], "run_started")
        self.assertIn("step_started", event_names)
        self.assertIn("tool_called", event_names)
        self.assertIn("tool_result", event_names)
        self.assertIn("final_answer", event_names)
        self.assertEqual(event_names[-1], "run_completed")
        self.assertIn("安史之乱爆发", final_event["answer"])
        self.assertTrue(any(event["title"] == "安史之乱爆发" for event in final_event["events"]))
        self.assertIn("references", final_event)
        self.assertIn("links", final_event)

    def test_langgraph_confirmation_node_pauses_risky_tool(self) -> None:
        calls: list[dict] = []
        with _fake_langgraph_modules():
            workflow = LangGraphAgentWorkflow(
                model_adapter=DangerousToolAdapter(),
                tool_registry=self._dangerous_tool_registry(calls),
            )

        response = workflow.run("删除一条数据")
        payload = response.as_payload()

        self.assertEqual(calls, [])
        self.assertIn("需要人工确认", response.answer)
        self.assertTrue(any(link["type"] == "confirmation_required" for link in payload["links"]))

    def test_langgraph_stream_emits_confirmation_required_event(self) -> None:
        calls: list[dict] = []
        with _fake_langgraph_modules():
            workflow = LangGraphAgentWorkflow(
                model_adapter=DangerousToolAdapter(),
                tool_registry=self._dangerous_tool_registry(calls),
            )

        events = list(workflow.stream("删除一条数据"))
        event_names = [event["event"] for event in events]
        confirmation = [event for event in events if event["event"] == "confirmation_required"][0]

        self.assertEqual(calls, [])
        self.assertIn("confirmation_required", event_names)
        self.assertNotIn("tool_result", event_names)
        self.assertEqual(confirmation["tool_name"], "dangerous_write")
        self.assertIn("需要人工确认", confirmation["answer"])

    def test_langgraph_confirm_existing_resumes_waiting_run(self) -> None:
        if not self.db_available:
            self.skipTest("PostgreSQL is not available")
        calls: list[dict] = []
        recorder = AgentRunRecorder(self.settings.postgres)
        with _fake_langgraph_modules():
            workflow = LangGraphAgentWorkflow(
                model_adapter=ConfirmableDangerousToolAdapter(),
                tool_registry=self._dangerous_tool_registry(calls),
                recorder=recorder,
            )

        pending = workflow.run("删除一条数据")
        waiting_run = recorder.get_run(pending.run_id)
        confirmed = workflow.confirm_existing(str(pending.run_id))
        completed_run = recorder.get_run(str(pending.run_id))

        self.assertIsNotNone(waiting_run)
        assert waiting_run is not None
        self.assertEqual(waiting_run["status"], "waiting_for_user")
        self.assertEqual(calls, [{"target_id": "event-1", "confirmed": True}])
        self.assertIn("危险操作已执行", confirmed.answer)
        self.assertIsNotNone(completed_run)
        assert completed_run is not None
        self.assertEqual(completed_run["status"], "completed")
        self.assertEqual(completed_run["steps"][0]["status"], "completed")
        self.assertTrue(completed_run["steps"][0]["tool_arguments"]["confirmed"])

    def _tool_registry(self):
        settings = AppSettings.from_env().postgres
        service = HistoricalQueryService(PostgresHistoricalEventRepository(settings))
        return build_historical_tool_registry(service)

    def _dangerous_tool_registry(self, calls: list[dict]) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="dangerous_write",
                description="Dangerous write test tool",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target_id": {"type": "string"},
                        "confirmed": {"type": "boolean", "default": False},
                    },
                    "required": ["target_id"],
                },
                risk_level="high",
                requires_confirmation=True,
            ),
            lambda payload: calls.append(payload) or {"success": True},
        )
        return registry


class FakeCompiledGraph:
    def __init__(
        self,
        nodes: dict[str, object],
        edges: list[tuple[str, str]],
        entry_point: str,
    ) -> None:
        self.nodes = nodes
        self.node_names = list(nodes.keys())
        self.edges = edges
        self.conditional_edges: dict[str, tuple[object, dict[str, str]]] = {}
        self.entry_point = entry_point
        self.conditional_sources: list[str] = []

    def invoke(self, state: dict) -> dict:
        current = self.entry_point
        result = dict(state)
        while current != "__end__":
            node = self.nodes[current]
            result = node(result)
            if current in self.conditional_edges:
                router, path_map = self.conditional_edges[current]
                route = router(result)
                current = path_map[route]
            else:
                next_edges = [target for source, target in self.edges if source == current]
                current = next_edges[0] if next_edges else "__end__"
        return result


class FakeStateGraph:
    def __init__(self, state_type: object) -> None:
        self.state_type = state_type
        self.nodes: dict[str, object] = {}
        self.edges: list[tuple[str, str]] = []
        self.conditional_edges: dict[str, tuple[object, dict[str, str]]] = {}
        self.entry_point = ""

    def add_node(self, name: str, node: object) -> None:
        self.nodes[name] = node

    def set_entry_point(self, name: str) -> None:
        self.entry_point = name

    def add_edge(self, source: str, target: str) -> None:
        self.edges.append((source, target))

    def add_conditional_edges(
        self,
        source: str,
        router: object,
        path_map: dict[str, str],
    ) -> None:
        self.conditional_edges[source] = (router, path_map)

    def compile(self) -> FakeCompiledGraph:
        graph = FakeCompiledGraph(self.nodes, self.edges, self.entry_point)
        graph.conditional_edges = self.conditional_edges
        graph.conditional_sources = list(self.conditional_edges.keys())
        return graph


class DangerousToolAdapter:
    model_name = "dangerous-tool-test"

    def decide(self, messages: list[dict], tools: list[dict]) -> ModelDecision:
        return ModelDecision(
            action="call_tool",
            reason="test confirmation gate",
            tool_call=ToolCall(
                name="dangerous_write",
                arguments={"target_id": "event-1"},
            ),
        )


class ConfirmableDangerousToolAdapter:
    model_name = "confirmable-dangerous-tool-test"

    def decide(self, messages: list[dict], tools: list[dict]) -> ModelDecision:
        if any(message.get("role") == "tool" for message in messages):
            return ModelDecision(
                action="finish",
                reason="tool completed",
                answer="危险操作已执行。",
            )
        return ModelDecision(
            action="call_tool",
            reason="test confirmation resume",
            tool_call=ToolCall(
                name="dangerous_write",
                arguments={"target_id": "event-1"},
            ),
        )


def _fake_langgraph_modules():
    fake_graph_module = types.ModuleType("langgraph.graph")
    fake_graph_module.END = "__end__"
    fake_graph_module.StateGraph = FakeStateGraph
    fake_langgraph_module = types.ModuleType("langgraph")
    fake_langgraph_module.graph = fake_graph_module
    return patch.dict(
        sys.modules,
        {
            "langgraph": fake_langgraph_module,
            "langgraph.graph": fake_graph_module,
        },
    )


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


if __name__ == "__main__":
    unittest.main()
