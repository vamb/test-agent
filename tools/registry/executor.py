from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import Any

from tools.registry.base import RegisteredTool
from tools.registry.base import ToolRegistry


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_name: str
    arguments: dict[str, Any]
    observation: dict[str, Any]
    elapsed_ms: int
    status: str = "completed"
    error_message: str | None = None


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self._thread_pool = ThreadPoolExecutor(max_workers=4)

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        started_at = time.perf_counter()
        try:
            registered_tool = self.registry.get(tool_name)
            validated_arguments = self._validate_arguments(registered_tool, arguments)
            observation = self._execute_with_retry(registered_tool, validated_arguments)
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            return ToolExecutionResult(
                tool_name=tool_name,
                arguments=validated_arguments,
                observation={
                    **observation,
                    "_tool_metadata": {
                        "success": True,
                        "elapsed_ms": elapsed_ms,
                        "attempts": 1,
                    },
                },
                elapsed_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            return ToolExecutionResult(
                tool_name=tool_name,
                arguments=arguments,
                observation={
                    "success": False,
                    "error": {
                        "type": exc.__class__.__name__,
                        "message": str(exc),
                    },
                    "_tool_metadata": {
                        "success": False,
                        "elapsed_ms": elapsed_ms,
                        "attempts": 1,
                    },
                },
                elapsed_ms=elapsed_ms,
                status="failed",
                error_message=str(exc),
            )

    def _execute_with_retry(
        self,
        registered_tool: RegisteredTool,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        attempts = registered_tool.definition.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                future = self._thread_pool.submit(registered_tool.handler, arguments)
                return future.result(timeout=registered_tool.definition.timeout_seconds)
            except TimeoutError as exc:
                last_error = TimeoutError(
                    f"Tool timed out after {registered_tool.definition.timeout_seconds}s"
                )
                future.cancel()
            except Exception as exc:
                last_error = exc

            if not registered_tool.definition.idempotent:
                break
        assert last_error is not None
        raise last_error

    def _validate_arguments(
        self,
        registered_tool: RegisteredTool,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        schema = registered_tool.definition.input_schema
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object.")

        properties = schema.get("properties", {})
        required = schema.get("required", [])
        validated = dict(arguments)

        for name, property_schema in properties.items():
            if name not in validated and "default" in property_schema:
                validated[name] = property_schema["default"]

        missing = [name for name in required if name not in validated or validated[name] is None]
        if missing:
            raise ValueError(f"Missing required tool arguments: {', '.join(missing)}")

        allowed_keys = set(properties)
        unknown_keys = sorted(set(validated) - allowed_keys)
        if unknown_keys:
            raise ValueError(f"Unknown tool arguments: {', '.join(unknown_keys)}")

        for name, value in validated.items():
            self._validate_value(name, value, properties[name])

        return validated

    def _validate_value(
        self,
        name: str,
        value: Any,
        schema: dict[str, Any],
    ) -> None:
        expected_type = schema.get("type")
        if expected_type is None:
            return

        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        if value is None and "null" in expected_types:
            return

        validators = {
            "string": lambda item: isinstance(item, str),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
            "boolean": lambda item: isinstance(item, bool),
            "object": lambda item: isinstance(item, dict),
            "array": lambda item: isinstance(item, list),
        }
        if not any(validators[kind](value) for kind in expected_types if kind in validators):
            raise ValueError(f"Invalid type for argument '{name}'. Expected {expected_types}.")

        if "array" in expected_types and isinstance(value, list):
            item_schema = schema.get("items", {})
            for index, item in enumerate(value):
                self._validate_value(f"{name}[{index}]", item, item_schema)
