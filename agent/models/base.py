from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelUsage:
    token_input: int = 0
    token_output: int = 0
    elapsed_ms: int = 0
    estimated_cost_usd: float = 0.0


@dataclass(frozen=True)
class ModelDecision:
    action: Literal["call_tool", "finish"]
    reason: str
    tool_call: ToolCall | None = None
    answer: str | None = None
    usage: ModelUsage = field(default_factory=ModelUsage)


class ModelAdapter(Protocol):
    model_name: str

    def decide(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelDecision:
        """Return the next model decision for the agent loop."""
