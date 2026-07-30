import importlib.util
import sys
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

    def _tool_registry(self):
        settings = AppSettings.from_env().postgres
        service = HistoricalQueryService(PostgresHistoricalEventRepository(settings))
        return build_historical_tool_registry(service)


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


if __name__ == "__main__":
    unittest.main()
