from __future__ import annotations

import json
import time
from typing import Any

from agent.models.base import ModelDecision, ModelUsage, ToolCall


MODEL_PRICE_PER_1M_TOKENS = {
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
}


class OpenAIFunctionCallingAdapter:
    """OpenAI-compatible function calling adapter for the Agent Loop."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4.1-mini",
        base_url: str = "",
        temperature: float = 0.0,
        client: Any | None = None,
    ) -> None:
        self.model_name = model
        self.temperature = temperature
        self.client = client or self._build_client(api_key, base_url)

    def decide(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelDecision:
        started_at = time.perf_counter()
        completion = self.client.chat.completions.create(
            model=self.model_name,
            messages=self._to_openai_messages(messages),
            tools=self._to_openai_tools(tools),
            tool_choice="auto",
            temperature=self.temperature,
        )
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        message = completion.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        usage = self._build_usage(completion, elapsed_ms)

        if tool_calls:
            tool_call = tool_calls[0]
            return ModelDecision(
                action="call_tool",
                reason="Model selected a function call.",
                tool_call=ToolCall(
                    name=tool_call.function.name,
                    arguments=self._parse_arguments(tool_call.function.arguments),
                ),
                usage=usage,
            )

        return ModelDecision(
            action="finish",
            reason="Model returned final content.",
            answer=getattr(message, "content", "") or "",
            usage=usage,
        )

    def _build_client(self, api_key: str, base_url: str) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI SDK is not installed. Run: pip install openai"
            ) from exc

        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAI(**kwargs)

    def _to_openai_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in tools
        ]

    def _to_openai_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        openai_messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "你是历史时间对照 Agent。你必须优先使用工具查询结构化历史事件，"
                    "回答时区分同期、因果、推断和证据强弱。"
                ),
            }
        ]
        for message in messages:
            role = message.get("role")
            if role == "user":
                openai_messages.append(
                    {"role": "user", "content": str(message.get("content", ""))}
                )
            elif role == "assistant" and message.get("tool_calls"):
                openai_messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": message["tool_calls"],
                    }
                )
            elif role == "tool":
                openai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.get("tool_call_id", ""),
                        "content": json.dumps(
                            message.get("content", {}),
                            ensure_ascii=False,
                            default=str,
                        ),
                    }
                )
        return openai_messages

    def _parse_arguments(self, arguments: str) -> dict[str, Any]:
        if not arguments:
            return {}
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid function call arguments: {arguments}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Function call arguments must be a JSON object.")
        return parsed

    def _build_usage(self, completion: Any, elapsed_ms: int) -> ModelUsage:
        raw_usage = getattr(completion, "usage", None)
        token_input = int(getattr(raw_usage, "prompt_tokens", 0) or 0)
        token_output = int(getattr(raw_usage, "completion_tokens", 0) or 0)
        return ModelUsage(
            token_input=token_input,
            token_output=token_output,
            elapsed_ms=elapsed_ms,
            estimated_cost_usd=self._estimate_cost_usd(token_input, token_output),
        )

    def _estimate_cost_usd(self, token_input: int, token_output: int) -> float:
        prices = MODEL_PRICE_PER_1M_TOKENS.get(self.model_name)
        if not prices:
            return 0.0
        cost = (
            token_input / 1_000_000 * prices["input"]
            + token_output / 1_000_000 * prices["output"]
        )
        return round(cost, 8)
