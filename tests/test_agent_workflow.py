import importlib.util
import sys
import types
import unittest
from unittest.mock import patch

from agent.models.rule_based_adapter import RuleBasedModelAdapter
from agent.runtime.loop import AgentLoop
from agent.runtime.workflow import LangGraphAgentWorkflow, build_agent_workflow
from apps.api.settings import AppSettings, AgentRuntimeSettings
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.service import HistoricalQueryService
from tools.historical.tool_registry import build_historical_tool_registry


class AgentWorkflowTest(unittest.TestCase):
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

    def test_langgraph_adapter_compiles_three_node_pipeline(self) -> None:
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
            ["prepare_state", "execute_agent_loop", "finalize_response"],
        )
        self.assertEqual(
            workflow._graph.edges,
            [
                ("prepare_state", "execute_agent_loop"),
                ("execute_agent_loop", "finalize_response"),
                ("finalize_response", "__end__"),
            ],
        )

    def _tool_registry(self):
        settings = AppSettings.from_env().postgres
        service = HistoricalQueryService(PostgresHistoricalEventRepository(settings))
        return build_historical_tool_registry(service)


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
        self.entry_point = entry_point

    def invoke(self, state: dict) -> dict:
        current = self.entry_point
        result = dict(state)
        while current != "__end__":
            node = self.nodes[current]
            result = node(result)
            next_edges = [target for source, target in self.edges if source == current]
            current = next_edges[0] if next_edges else "__end__"
        return result


class FakeStateGraph:
    def __init__(self, state_type: object) -> None:
        self.state_type = state_type
        self.nodes: dict[str, object] = {}
        self.edges: list[tuple[str, str]] = []
        self.entry_point = ""

    def add_node(self, name: str, node: object) -> None:
        self.nodes[name] = node

    def set_entry_point(self, name: str) -> None:
        self.entry_point = name

    def add_edge(self, source: str, target: str) -> None:
        self.edges.append((source, target))

    def compile(self) -> FakeCompiledGraph:
        return FakeCompiledGraph(self.nodes, self.edges, self.entry_point)


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


if __name__ == "__main__":
    unittest.main()
