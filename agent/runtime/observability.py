from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from apps.api.settings import ObservabilitySettings


@dataclass(frozen=True)
class TraceContext:
    run_id: str
    trace_id: str
    trace_url: str
    root_observation: Any | None = None


class AgentTelemetry:
    """Langfuse-compatible telemetry adapter."""

    def __init__(
        self,
        settings: ObservabilitySettings | None = None,
        langfuse_client: Any | None = None,
    ) -> None:
        self.settings = settings or ObservabilitySettings()
        self._client = langfuse_client
        self._sdk_available: bool | None = None

    def start_run(
        self,
        run_id: str | None,
        user_input: str,
        model_name: str,
        prompt_version: str,
    ) -> TraceContext | None:
        if not self.settings.langfuse_enabled or not run_id:
            return None
        client = self._langfuse_client()
        trace_id = self._langfuse_trace_id(run_id, client)
        root_observation = self._start_observation(
            parent=client,
            name="agent-run",
            as_type="agent",
            trace_context={"trace_id": trace_id},
            input=user_input,
            metadata={
                "run_id": run_id,
                "model_name": model_name,
                "prompt_version": prompt_version,
            },
        )
        return TraceContext(
            run_id=run_id,
            trace_id=trace_id,
            trace_url=self._trace_url(run_id=run_id, trace_id=trace_id),
            root_observation=root_observation,
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
        if not context:
            return
        observation = self._start_observation(
            parent=context.root_observation or self._langfuse_client(),
            name=f"tool:{tool_name}",
            as_type="tool",
            input=tool_arguments,
            metadata={
                "run_id": context.run_id,
                "step_index": step_index,
                "status": status,
                "error_message": error_message or "",
            },
            usage_details=self._usage_details(usage),
            cost_details=self._cost_details(usage),
        )
        self._end_observation(
            observation,
            output=tool_result,
            status_message=error_message or status,
            metadata={"status": status},
        )

    def record_model_decision(
        self,
        context: TraceContext | None,
        step_index: int,
        model_name: str,
        input_summary: str,
        output_summary: str,
        usage: dict[str, Any] | None = None,
    ) -> None:
        if not context:
            return
        observation = self._start_observation(
            parent=context.root_observation or self._langfuse_client(),
            name=f"model-decision:{step_index}",
            as_type="generation",
            input=input_summary,
            metadata={
                "run_id": context.run_id,
                "step_index": step_index,
                "model_name": model_name,
            },
            usage_details=self._usage_details(usage),
            cost_details=self._cost_details(usage),
        )
        self._end_observation(
            observation,
            output=output_summary,
            status_message="completed",
        )

    def finish_run(
        self,
        context: TraceContext | None,
        answer: str,
        usage: dict[str, Any] | None = None,
    ) -> None:
        if not context:
            return
        self._end_observation(
            context.root_observation,
            output=answer,
            status_message="completed",
            usage_details=self._usage_details(usage),
            cost_details=self._cost_details(usage),
        )
        self.flush()

    def fail_run(self, context: TraceContext | None, error_message: str) -> None:
        if not context:
            return
        self._end_observation(
            context.root_observation,
            output={"error": error_message},
            status_message=error_message,
            level="ERROR",
        )
        self.flush()

    def cancel_run(self, context: TraceContext | None, reason: str) -> None:
        if not context:
            return
        self._end_observation(
            context.root_observation,
            output={"cancelled": True, "reason": reason},
            status_message=reason,
            level="WARNING",
        )
        self.flush()

    def trace_link(self, context: TraceContext | None) -> dict[str, Any] | None:
        if not context or not context.trace_url:
            return None
        return self.trace_link_for_run_id(context.run_id)

    def trace_link_for_run_id(self, run_id: str | None) -> dict[str, Any] | None:
        if not self.settings.langfuse_enabled or not run_id:
            return None
        trace_id = self._langfuse_trace_id(run_id, self._langfuse_client())
        trace_url = self._trace_url(run_id=run_id, trace_id=trace_id)
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
        base_url = self.settings.langfuse_base_url or self.settings.langfuse_host
        if base_url:
            return f"{base_url}/trace/{trace_id}"
        return ""

    def flush(self) -> None:
        client = self._langfuse_client()
        if not client:
            return
        try:
            flush = getattr(client, "flush", None)
            if callable(flush):
                flush()
        except Exception:
            return

    def _langfuse_client(self) -> Any | None:
        if not self.settings.langfuse_enabled:
            return None
        if self._client is not None:
            return self._client
        if not self.settings.langfuse_public_key or not self.settings.langfuse_secret_key:
            return None
        if self._sdk_available is False:
            return None
        try:
            self._prime_langfuse_env()
            from langfuse import get_client

            self._client = get_client()
            self._sdk_available = True
        except Exception:
            self._sdk_available = False
            self._client = None
        return self._client

    def _prime_langfuse_env(self) -> None:
        if self.settings.langfuse_public_key:
            os.environ.setdefault("LANGFUSE_PUBLIC_KEY", self.settings.langfuse_public_key)
        if self.settings.langfuse_secret_key:
            os.environ.setdefault("LANGFUSE_SECRET_KEY", self.settings.langfuse_secret_key)
        base_url = self.settings.langfuse_base_url or self.settings.langfuse_host
        if base_url:
            os.environ.setdefault("LANGFUSE_BASE_URL", base_url)

    def _start_observation(
        self,
        parent: Any | None,
        name: str,
        as_type: str,
        input: Any | None = None,
        metadata: dict[str, Any] | None = None,
        trace_context: dict[str, Any] | None = None,
        usage_details: dict[str, Any] | None = None,
        cost_details: dict[str, Any] | None = None,
    ) -> Any | None:
        if not parent:
            return None
        try:
            starter = getattr(parent, "start_observation", None)
            if not callable(starter):
                return None
            kwargs: dict[str, Any] = {
                "name": name,
                "as_type": as_type,
                "input": input,
                "metadata": metadata or {},
            }
            if trace_context:
                kwargs["trace_context"] = trace_context
            if usage_details:
                kwargs["usage_details"] = usage_details
            if cost_details:
                kwargs["cost_details"] = cost_details
            return starter(**kwargs)
        except Exception:
            return None

    def _end_observation(
        self,
        observation: Any | None,
        output: Any | None = None,
        status_message: str = "",
        level: str | None = None,
        metadata: dict[str, Any] | None = None,
        usage_details: dict[str, Any] | None = None,
        cost_details: dict[str, Any] | None = None,
    ) -> None:
        if not observation:
            return
        try:
            end = getattr(observation, "end", None)
            if not callable(end):
                return
            kwargs: dict[str, Any] = {
                "output": output,
                "status_message": status_message,
            }
            if level:
                kwargs["level"] = level
            if metadata:
                kwargs["metadata"] = metadata
            if usage_details:
                kwargs["usage_details"] = usage_details
            if cost_details:
                kwargs["cost_details"] = cost_details
            end(**kwargs)
        except Exception:
            return

    def _usage_details(self, usage: dict[str, Any] | None) -> dict[str, Any]:
        if not usage:
            return {}
        return {
            "input": int(usage.get("token_input", 0) or 0),
            "output": int(usage.get("token_output", 0) or 0),
        }

    def _cost_details(self, usage: dict[str, Any] | None) -> dict[str, Any]:
        if not usage:
            return {}
        cost = float(usage.get("estimated_cost_usd", 0.0) or 0.0)
        return {"total": cost} if cost > 0 else {}

    def _langfuse_trace_id(self, run_id: str, client: Any | None) -> str:
        try:
            create_trace_id = getattr(client, "create_trace_id", None)
            if callable(create_trace_id):
                return str(create_trace_id(seed=run_id))
        except Exception:
            return run_id
        return run_id
