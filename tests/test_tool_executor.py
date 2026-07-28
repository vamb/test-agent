import time
import unittest

from tools.registry.base import ToolDefinition, ToolRegistry
from tools.registry.executor import ToolExecutor


class ToolExecutorTest(unittest.TestCase):
    def test_execute_applies_defaults_and_validates_arguments(self) -> None:
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="sample_tool",
                description="Sample tool",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
            ),
            lambda args: {"query": args["query"], "limit": args["limit"]},
        )

        result = ToolExecutor(registry).execute("sample_tool", {"query": "唐朝"})

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.arguments["limit"], 10)
        self.assertTrue(result.observation["_tool_metadata"]["success"])

    def test_execute_returns_failure_for_invalid_arguments(self) -> None:
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="sample_tool",
                description="Sample tool",
                input_schema={
                    "type": "object",
                    "properties": {"year": {"type": "integer"}},
                    "required": ["year"],
                },
            ),
            lambda args: {"year": args["year"]},
        )

        result = ToolExecutor(registry).execute("sample_tool", {"year": "755"})

        self.assertEqual(result.status, "failed")
        self.assertFalse(result.observation["success"])
        self.assertIn("Invalid type", result.error_message or "")

    def test_execute_returns_failure_for_timeout(self) -> None:
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="slow_tool",
                description="Slow tool",
                input_schema={"type": "object", "properties": {}, "required": []},
                timeout_seconds=0.01,
                max_retries=0,
            ),
            lambda args: self._slow_result(),
        )

        result = ToolExecutor(registry).execute("slow_tool", {})

        self.assertEqual(result.status, "failed")
        self.assertIn("timed out", result.error_message or "")

    def _slow_result(self) -> dict:
        time.sleep(0.05)
        return {"ok": True}


if __name__ == "__main__":
    unittest.main()
