from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from typing import Any, Iterator

from agent.models.base import ModelAdapter
from agent.models.base import ModelUsage
from agent.runtime.recorder import AgentRunRecorder
from agent.runtime.observability import AgentTelemetry, TraceContext
from agent.runtime.simple_historical_agent import AgentResponse, AgentStep
from agent.runtime.structured_response import build_structured_response
from tools.registry.base import ToolRegistry
from tools.registry.executor import ToolExecutor


@dataclass(frozen=True)
class AgentLoopConfig:
    max_steps: int = 8
    max_observation_items: int = 20


class AgentRunCancelled(RuntimeError):
    pass


class AgentLoop:
    def __init__(
        self,
        model_adapter: ModelAdapter,
        tool_registry: ToolRegistry,
        recorder: AgentRunRecorder | None = None,
        config: AgentLoopConfig | None = None,
        telemetry: AgentTelemetry | None = None,
    ) -> None:
        self.model_adapter = model_adapter
        self.tool_registry = tool_registry
        self.executor = ToolExecutor(tool_registry)
        self.recorder = recorder
        self.config = config or AgentLoopConfig()
        self.telemetry = telemetry or AgentTelemetry()

    def run(self, user_input: str) -> AgentResponse:
        recorded_run = (
            self.recorder.start_run(
                user_input,
                model_name=self.model_adapter.model_name,
                prompt_version="historical-agent-loop-v1",
            )
            if self.recorder
            else None
        )
        run_id = recorded_run.run_id if recorded_run else None
        trace_context = self.telemetry.start_run(
            run_id,
            user_input=user_input,
            model_name=self.model_adapter.model_name,
            prompt_version="historical-agent-loop-v1",
        )
        try:
            response = self._run_without_recording(
                user_input,
                run_id=run_id,
                trace_context=trace_context,
            )
        except AgentRunCancelled as exc:
            if self.recorder and run_id:
                self.recorder.cancel_run(run_id, str(exc))
            self.telemetry.cancel_run(trace_context, str(exc))
            raise
        except Exception as exc:
            if self.recorder and run_id:
                self.recorder.fail_run(run_id, str(exc))
            self.telemetry.fail_run(trace_context, str(exc))
            raise

        if self.recorder and run_id:
            self.recorder.finish_run(run_id, response.answer)
        self.telemetry.finish_run(trace_context, response.answer)
        response = self._with_observability_links(response, trace_context)
        return response

    def run_existing(self, user_input: str, run_id: str) -> AgentResponse:
        trace_context = self.telemetry.start_run(
            run_id,
            user_input=user_input,
            model_name=self.model_adapter.model_name,
            prompt_version="historical-agent-loop-v1",
        )
        try:
            response = self._run_without_recording(
                user_input,
                run_id=run_id,
                trace_context=trace_context,
            )
        except AgentRunCancelled as exc:
            if self.recorder:
                self.recorder.cancel_run(run_id, str(exc))
            self.telemetry.cancel_run(trace_context, str(exc))
            raise
        except Exception as exc:
            if self.recorder:
                self.recorder.fail_run(run_id, str(exc))
            self.telemetry.fail_run(trace_context, str(exc))
            raise

        if self.recorder:
            self.recorder.finish_run(run_id, response.answer)
        self.telemetry.finish_run(trace_context, response.answer)
        response = self._with_observability_links(response, trace_context)
        return response

    def resume_existing(self, run_id: str) -> AgentResponse:
        if not self.recorder:
            raise RuntimeError("resume_existing requires an AgentRunRecorder.")
        run = self.recorder.get_run(run_id)
        if not run:
            raise RuntimeError(f"Agent run not found: {run_id}")
        trace_context = self.telemetry.start_run(
            run_id,
            user_input=str(run["user_input"]),
            model_name=self.model_adapter.model_name,
            prompt_version=str(run.get("prompt_version") or "historical-agent-loop-v1"),
        )
        try:
            response = self._run_without_recording(
                str(run["user_input"]),
                run_id=run_id,
                existing_steps=self._completed_steps_from_run(run),
                trace_context=trace_context,
            )
        except AgentRunCancelled as exc:
            self.recorder.cancel_run(run_id, str(exc))
            self.telemetry.cancel_run(trace_context, str(exc))
            raise
        except Exception as exc:
            self.recorder.fail_run(run_id, str(exc))
            self.telemetry.fail_run(trace_context, str(exc))
            raise

        self.recorder.finish_run(run_id, response.answer)
        self.telemetry.finish_run(trace_context, response.answer)
        response = self._with_observability_links(response, trace_context)
        return response

    def stream(self, user_input: str) -> Iterator[dict[str, Any]]:
        recorded_run = (
            self.recorder.start_run(
                user_input,
                model_name=self.model_adapter.model_name,
                prompt_version="historical-agent-loop-v1",
            )
            if self.recorder
            else None
        )
        run_id = recorded_run.run_id if recorded_run else None
        trace_context = self.telemetry.start_run(
            run_id,
            user_input=user_input,
            model_name=self.model_adapter.model_name,
            prompt_version="historical-agent-loop-v1",
        )
        yield {
            "event": "run_started",
            "run_id": run_id,
            "trace_id": trace_context.trace_id if trace_context else None,
            "trace_url": trace_context.trace_url if trace_context else "",
        }

        messages: list[dict[str, Any]] = [{"role": "user", "content": user_input}]
        steps: list[AgentStep] = []
        try:
            for _ in range(self.config.max_steps):
                self._raise_if_cancelled(run_id)
                decision = self._decide_with_timing(messages)
                step_index = len(steps)
                model_input_summary = self._summarize_model_input(messages)
                model_output_summary = self._summarize_model_output(decision)
                self.telemetry.record_model_decision(
                    trace_context,
                    step_index=step_index,
                    model_name=self.model_adapter.model_name,
                    input_summary=model_input_summary,
                    output_summary=model_output_summary,
                    usage=self._usage_payload(decision.usage),
                )

                if decision.action == "finish":
                    self._raise_if_cancelled(run_id)
                    answer = decision.answer or ""
                    if self.recorder and run_id:
                        self.recorder.finish_run(run_id, answer)
                    self.telemetry.finish_run(
                        trace_context,
                        answer,
                        usage=self._usage_payload(decision.usage),
                    )
                    structured = build_structured_response(answer, steps, run_id)
                    links = self._merge_links(
                        structured["links"],
                        self._observability_links(trace_context),
                    )
                    yield {
                        "event": "final_answer",
                        "run_id": run_id,
                        "answer": answer,
                        "events": structured["events"],
                        "references": structured["references"],
                        "links": links,
                        "step_count": len(steps),
                        "usage": self._usage_payload(decision.usage),
                    }
                    yield {"event": "run_completed", "run_id": run_id}
                    return

                if not decision.tool_call:
                    raise RuntimeError("Model requested a tool call without tool details.")

                tool_call_id = f"call_{step_index}"
                yield {
                    "event": "step_started",
                    "run_id": run_id,
                    "step_index": step_index,
                    "tool_name": decision.tool_call.name,
                }
                yield {
                    "event": "tool_called",
                    "run_id": run_id,
                    "step_index": step_index,
                    "tool_call_id": tool_call_id,
                    "tool_name": decision.tool_call.name,
                    "tool_arguments": decision.tool_call.arguments,
                    "usage": self._usage_payload(decision.usage),
                }

                messages.append(self._assistant_tool_call_message(tool_call_id, decision))
                self._raise_if_cancelled(run_id)
                execution = self.executor.execute(
                    decision.tool_call.name,
                    decision.tool_call.arguments,
                )
                self._raise_if_cancelled(run_id)
                observation = self._trim_observation(execution.observation)
                step = AgentStep(
                    tool_name=execution.tool_name,
                    tool_arguments=execution.arguments,
                    observation=observation,
                )
                self._record_step(
                    run_id,
                    step_index,
                    step,
                    status=execution.status,
                    error_message=execution.error_message,
                    model_input_summary=model_input_summary,
                    model_output_summary=model_output_summary,
                    token_input=decision.usage.token_input,
                    token_output=decision.usage.token_output,
                    trace_context=trace_context,
                    usage=self._usage_payload(decision.usage),
                )
                steps.append(step)
                messages.append(
                    {
                        "role": "tool",
                        "name": execution.tool_name,
                        "tool_call_id": tool_call_id,
                        "content": observation,
                        "elapsed_ms": execution.elapsed_ms,
                    }
                )
                yield {
                    "event": "tool_result",
                    "run_id": run_id,
                    "step_index": step_index,
                    "tool_name": execution.tool_name,
                    "status": execution.status,
                    "elapsed_ms": execution.elapsed_ms,
                    "observation": observation,
                    "error_message": execution.error_message,
                }

            raise RuntimeError("当前问题需要更多推理步骤，已达到本轮 Agent 最大工具调用次数。")
        except AgentRunCancelled as exc:
            if self.recorder and run_id:
                self.recorder.cancel_run(run_id, str(exc))
            self.telemetry.cancel_run(trace_context, str(exc))
            yield {
                "event": "run_cancelled",
                "run_id": run_id,
                "error_message": str(exc),
            }
        except Exception as exc:
            if self.recorder and run_id:
                self.recorder.fail_run(run_id, str(exc))
            self.telemetry.fail_run(trace_context, str(exc))
            yield {
                "event": "run_failed",
                "run_id": run_id,
                "error_message": str(exc),
            }

    def _run_without_recording(
        self,
        user_input: str,
        run_id: str | None = None,
        existing_steps: list[AgentStep] | None = None,
        trace_context: TraceContext | None = None,
    ) -> AgentResponse:
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_input}]
        steps: list[AgentStep] = existing_steps or []
        for step_index, step in enumerate(steps):
            tool_call_id = f"call_{step_index}"
            messages.append(self._assistant_tool_call_message_from_step(tool_call_id, step))
            messages.append(
                {
                    "role": "tool",
                    "name": step.tool_name,
                    "tool_call_id": tool_call_id,
                    "content": step.observation,
                    "elapsed_ms": 0,
                }
            )

        for _ in range(len(steps), self.config.max_steps):
            self._raise_if_cancelled(run_id)
            decision = self._decide_with_timing(messages)
            step_index = len(steps)
            model_input_summary = self._summarize_model_input(messages)
            model_output_summary = self._summarize_model_output(decision)
            self.telemetry.record_model_decision(
                trace_context,
                step_index=step_index,
                model_name=self.model_adapter.model_name,
                input_summary=model_input_summary,
                output_summary=model_output_summary,
                usage=self._usage_payload(decision.usage),
            )

            if decision.action == "finish":
                self._raise_if_cancelled(run_id)
                return AgentResponse(decision.answer or "", steps, run_id=run_id)

            if not decision.tool_call:
                raise RuntimeError("Model requested a tool call without tool details.")

            tool_call_id = f"call_{len(steps)}"
            messages.append(self._assistant_tool_call_message(tool_call_id, decision))
            self._raise_if_cancelled(run_id)
            execution = self.executor.execute(
                decision.tool_call.name,
                decision.tool_call.arguments,
            )
            self._raise_if_cancelled(run_id)
            observation = self._trim_observation(execution.observation)
            step = AgentStep(
                tool_name=execution.tool_name,
                tool_arguments=execution.arguments,
                observation=observation,
            )
            self._record_step(
                run_id,
                len(steps),
                    step,
                    status=execution.status,
                    error_message=execution.error_message,
                    model_input_summary=model_input_summary,
                    model_output_summary=model_output_summary,
                    token_input=decision.usage.token_input,
                    token_output=decision.usage.token_output,
                trace_context=trace_context,
                usage=self._usage_payload(decision.usage),
            )
            steps.append(step)
            messages.append(
                {
                    "role": "tool",
                    "name": execution.tool_name,
                    "tool_call_id": tool_call_id,
                    "content": observation,
                    "elapsed_ms": execution.elapsed_ms,
                }
            )

        answer = "当前问题需要更多推理步骤，已达到本轮 Agent 最大工具调用次数。"
        raise RuntimeError(answer)

    def _record_step(
        self,
        run_id: str | None,
        step_index: int,
        step: AgentStep,
        status: str = "completed",
        error_message: str | None = None,
        model_input_summary: str = "",
        model_output_summary: str = "",
        token_input: int = 0,
        token_output: int = 0,
        trace_context: TraceContext | None = None,
        usage: dict[str, Any] | None = None,
    ) -> None:
        if self.recorder and run_id:
            self.recorder.record_tool_step(
                run_id=run_id,
                step_index=step_index,
                tool_name=step.tool_name,
                tool_arguments=step.tool_arguments,
                tool_result=step.observation,
                status=status,
                error_message=error_message,
                model_input_summary=model_input_summary,
                model_output_summary=model_output_summary,
                token_input=token_input,
                token_output=token_output,
            )
        self.telemetry.record_tool_step(
            trace_context,
            step_index=step_index,
            tool_name=step.tool_name,
            tool_arguments=step.tool_arguments,
            tool_result=step.observation,
            status=status,
            error_message=error_message,
            usage=usage,
        )

    def _with_observability_links(
        self,
        response: AgentResponse,
        trace_context: TraceContext | None,
    ) -> AgentResponse:
        links = self._merge_links(
            response.as_payload()["links"],
            self._observability_links(trace_context),
        )
        return replace(response, links=links)

    def _observability_links(self, trace_context: TraceContext | None) -> list[dict[str, Any]]:
        link = self.telemetry.trace_link(trace_context)
        return [link] if link else []

    def _merge_links(
        self,
        base_links: list[dict[str, Any]],
        extra_links: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = list(base_links)
        seen = {(str(link.get("type", "")), str(link.get("href", ""))) for link in result}
        for link in extra_links:
            key = (str(link.get("type", "")), str(link.get("href", "")))
            if key not in seen:
                seen.add(key)
                result.append(link)
        return result

    def _trim_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        result = dict(observation)
        for key in ("events", "relations", "rows"):
            items = result.get(key)
            if isinstance(items, list) and len(items) > self.config.max_observation_items:
                result[key] = items[: self.config.max_observation_items]
                result[f"{key}_truncated"] = True
        return result

    def _json_dumps(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    def _decide_with_timing(self, messages: list[dict[str, Any]]) -> Any:
        model_started_at = time.perf_counter()
        decision = self.model_adapter.decide(
            messages=messages,
            tools=self.tool_registry.definitions(),
        )
        model_elapsed_ms = int((time.perf_counter() - model_started_at) * 1000)
        if decision.usage.elapsed_ms != 0:
            return decision
        return replace(
            decision,
            usage=ModelUsage(
                token_input=decision.usage.token_input,
                token_output=decision.usage.token_output,
                elapsed_ms=model_elapsed_ms,
                estimated_cost_usd=decision.usage.estimated_cost_usd,
            ),
        )

    def _assistant_tool_call_message(self, tool_call_id: str, decision: Any) -> dict[str, Any]:
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": decision.tool_call.name,
                        "arguments": self._json_dumps(decision.tool_call.arguments),
                    },
                }
            ],
        }

    def _assistant_tool_call_message_from_step(
        self,
        tool_call_id: str,
        step: AgentStep,
    ) -> dict[str, Any]:
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": step.tool_name,
                        "arguments": self._json_dumps(step.tool_arguments),
                    },
                }
            ],
        }

    def _usage_payload(self, usage: ModelUsage) -> dict[str, Any]:
        return {
            "token_input": usage.token_input,
            "token_output": usage.token_output,
            "elapsed_ms": usage.elapsed_ms,
            "estimated_cost_usd": usage.estimated_cost_usd,
        }

    def _raise_if_cancelled(self, run_id: str | None) -> None:
        if self.recorder and run_id and self.recorder.is_cancelled(run_id):
            raise AgentRunCancelled("Agent run was cancelled.")

    def _summarize_model_input(self, messages: list[dict[str, Any]]) -> str:
        summary = {
            "message_count": len(messages),
            "roles": [str(message.get("role", "")) for message in messages],
        }
        return self._json_dumps(summary)

    def _summarize_model_output(self, decision: Any) -> str:
        summary = {
            "action": decision.action,
            "reason": decision.reason,
            "tool_name": decision.tool_call.name if decision.tool_call else None,
            "answer_preview": (decision.answer or "")[:120],
            "model_elapsed_ms": decision.usage.elapsed_ms,
            "estimated_cost_usd": decision.usage.estimated_cost_usd,
        }
        return self._json_dumps(summary)

    def _completed_steps_from_run(self, run: dict[str, Any]) -> list[AgentStep]:
        steps = []
        for step in run.get("steps", []):
            if step.get("status") != "completed":
                continue
            if step.get("step_type") != "tool_call":
                continue
            steps.append(
                AgentStep(
                    tool_name=str(step.get("tool_name", "")),
                    tool_arguments=dict(step.get("tool_arguments") or {}),
                    observation=dict(step.get("tool_result") or {}),
                )
            )
        return steps
