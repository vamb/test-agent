import json
import unittest
from types import SimpleNamespace

from agent.models.openai_function_calling_adapter import OpenAIFunctionCallingAdapter


class FakeCompletions:
    def __init__(self) -> None:
        self.last_request = {}

    def create(self, **kwargs):
        self.last_request = kwargs
        message = SimpleNamespace(
            content=None,
            tool_calls=[
                SimpleNamespace(
                    function=SimpleNamespace(
                        name="search_events_by_year",
                        arguments=json.dumps({"year": 755, "nearby_window": 10}),
                    )
                )
            ],
        )
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=25)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions())


class OpenAIFunctionCallingAdapterTest(unittest.TestCase):
    def test_decide_returns_structured_tool_call(self) -> None:
        client = FakeClient()
        adapter = OpenAIFunctionCallingAdapter(api_key="test", client=client)

        decision = adapter.decide(
            messages=[{"role": "user", "content": "755年发生了什么？"}],
            tools=[
                {
                    "name": "search_events_by_year",
                    "description": "Search by year",
                    "input_schema": {
                        "type": "object",
                        "properties": {"year": {"type": "integer"}},
                        "required": ["year"],
                    },
                }
            ],
        )

        self.assertEqual(decision.action, "call_tool")
        self.assertIsNotNone(decision.tool_call)
        self.assertEqual(decision.tool_call.name, "search_events_by_year")
        self.assertEqual(decision.tool_call.arguments["year"], 755)
        self.assertEqual(decision.usage.token_input, 100)
        self.assertEqual(decision.usage.token_output, 25)
        self.assertGreaterEqual(decision.usage.elapsed_ms, 0)
        self.assertGreater(decision.usage.estimated_cost_usd, 0)
        self.assertEqual(
            client.chat.completions.last_request["tools"][0]["function"]["name"],
            "search_events_by_year",
        )

    def test_system_prompt_marks_external_context_as_untrusted(self) -> None:
        client = FakeClient()
        adapter = OpenAIFunctionCallingAdapter(api_key="test", client=client)

        adapter.decide(
            messages=[{"role": "user", "content": "查询历史资料"}],
            tools=[
                {
                    "name": "search_events_by_year",
                    "description": "Search by year",
                    "input_schema": {
                        "type": "object",
                        "properties": {"year": {"type": "integer"}},
                        "required": ["year"],
                    },
                }
            ],
        )

        system_prompt = client.chat.completions.last_request["messages"][0]["content"]
        self.assertIn("不可信指令", system_prompt)
        self.assertIn("不得自行设置 confirmed=true", system_prompt)


if __name__ == "__main__":
    unittest.main()
