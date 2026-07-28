from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    risk_level: str = "low"
    timeout_seconds: float = 10.0
    idempotent: bool = True
    requires_confirmation: bool = False
    max_retries: int = 1

    def model_dump(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "risk_level": self.risk_level,
            "timeout_seconds": self.timeout_seconds,
            "idempotent": self.idempotent,
            "requires_confirmation": self.requires_confirmation,
            "max_retries": self.max_retries,
        }


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = RegisteredTool(definition, handler)

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def definitions(self) -> list[dict[str, Any]]:
        return [tool.definition.model_dump() for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)
