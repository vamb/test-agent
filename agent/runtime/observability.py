from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.api.settings import ObservabilitySettings


@dataclass(frozen=True)
class TraceContext:
    run_id: str
    trace_id: str
    trace_url: str


class AgentTelemetry:
    """Langfuse-compatible telemetry adapter.

    The first version only creates stable trace metadata and links. Later, this class can
    call the Langfuse SDK without changing AgentLoop, API payloads, or frontend rendering.
    """

    def __init__(self, settings: ObservabilitySettings | None = None) -> None:
        self.settings = settings or ObservabilitySettings()

    def start_run(
        self,
        run_id: str | None,
        user_input: str,
        model_name: str,
        prompt_version: str,
    ) -> TraceContext | None:
        if not self.settings.langfuse_enabled or not run_id:
            return None
        trace_id = run_id
        return TraceContext(
            run_id=run_id,
            trace_id=trace_id,
            trace_url=self._trace_url(run_id=run_id, trace_id=trace_id),
        )

    def record_tool_step(
        self,
        context: TraceContext | None,
        step_index: int,
        tool_name: str,
        tool_arguments: dict[str, Any],
        tool_result: dict[str, Any],
        status: str,
        error_message: str | None = None,
        usage: dict[str, Any] | None = None,
    ) -> None:
        return None

    def finish_run(
        self,
        context: TraceContext | None,
        answer: str,
        usage: dict[str, Any] | None = None,
    ) -> None:
        return None

    def fail_run(self, context: TraceContext | None, error_message: str) -> None:
        return None

    def cancel_run(self, context: TraceContext | None, reason: str) -> None:
        return None

    def trace_link(self, context: TraceContext | None) -> dict[str, Any] | None:
        if not context or not context.trace_url:
            return None
        return self.trace_link_for_run_id(context.run_id)

    def trace_link_for_run_id(self, run_id: str | None) -> dict[str, Any] | None:
        if not self.settings.langfuse_enabled or not run_id:
            return None
        trace_url = self._trace_url(run_id=run_id, trace_id=run_id)
        if not trace_url:
            return None
        return {
            "type": "langfuse_trace",
            "target_id": run_id,
            "title": "Langfuse Trace",
            "href": trace_url,
            "external": True,
        }

    def _trace_url(self, run_id: str, trace_id: str) -> str:
        template = self.settings.langfuse_trace_url_template
        if template:
            return template.format(run_id=run_id, trace_id=trace_id)
        if self.settings.langfuse_host:
            return f"{self.settings.langfuse_host}/trace/{trace_id}"
        return ""
