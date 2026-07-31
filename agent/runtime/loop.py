from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from typing import Any, Iterator

from agent.models.base import ModelAdapter
from agent.models.base import ModelUsage
from agent.runtime.recorder import AgentRunRecorder
from agent.runtime.observability import AgentTelemetry, TraceContext
from agent.runtime.security import (
    PromptSecurityGuard,
    SecurityDecision,
    annotate_untrusted_observation,
)
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
        self.security_guard = PromptSecurityGuard()

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
            security = self.security_guard.assess_user_input(user_input)
            if not security.allowed:
                return self._security_blocked_response(security, run_id, trace_context)
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

        if self.recorder and run_id and not self._response_requires_confirmation(response):
            self.recorder.finish_run(run_id, response.answer)
        if not self._response_requires_confirmation(response):
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
            security = self.security_guard.assess_user_input(user_input)
            if not security.allowed:
                return self._security_blocked_response(security, run_id, trace_context)
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

        if self.recorder and not self._response_requires_confirmation(response):
            self.recorder.finish_run(run_id, response.answer)
        if not self._response_requires_confirmation(response):
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
            security = self.security_guard.assess_user_input(str(run["user_input"]))
            if not security.allowed:
                return self._security_blocked_response(security, run_id, trace_context)
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

        if not self._response_requires_confirmation(response):
            self.recorder.finish_run(run_id, response.answer)
            self.telemetry.finish_run(trace_context, response.answer)
        response = self._with_observability_links(response, trace_context)
        return response

    def confirm_existing(self, run_id: str) -> AgentResponse:
        if not self.recorder:
            raise RuntimeError("confirm_existing requires an AgentRunRecorder.")
        existing_run = self.recorder.get_run(run_id)
        if not existing_run:
            raise RuntimeError(f"Agent run not found: {run_id}")
        pending_confirmation = self._pending_confirmation_from_run(existing_run)
        if not pending_confirmation:
            raise RuntimeError(f"Agent run is not waiting for confirmation: {run_id}")
        claimed = self.recorder.claim_waiting_run(run_id)
        if not claimed:
            raise RuntimeError(f"Agent run is not waiting for confirmation: {run_id}")

        trace_context = self.telemetry.start_run(
            run_id,
            user_input=str(existing_run["user_input"]),
            model_name=self.model_adapter.model_name,
            prompt_version=str(existing_run.get("prompt_version") or "historical-agent-loop-v1"),
        )
        try:
            existing_steps = self._completed_steps_from_run(existing_run)
            execution = self.executor.execute(
                pending_confirmation["tool_name"],
                {**pending_confirmation["tool_arguments"], "confirmed": True},
            )
            observation = self._trim_observation(execution.observation)
            confirmed_step = AgentStep(
                tool_name=execution.tool_name,
                tool_arguments=execution.arguments,
                observation=observation,
            )
            self._record_step(
                run_id,
                int(pending_confirmation["step_index"]),
                confirmed_step,
                status=execution.status,
                error_message=execution.error_message,
                trace_context=trace_context,
            )
            existing_steps.append(confirmed_step)
            response = self._run_without_recording(
                str(existing_run["user_input"]),
                run_id=run_id,
                existing_steps=existing_steps,
                trace_context=trace_context,
            )
        except Exception as exc:
            self.recorder.fail_run(run_id, str(exc))
            self.telemetry.fail_run(trace_context, str(exc))
            raise

        self.recorder.finish_run(run_id, response.answer)
        self.telemetry.finish_run(trace_context, response.answer)
        return self._with_observability_links(response, trace_context)

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
            security = self.security_guard.assess_user_input(user_input)
            if not security.allowed:
                response = self._security_blocked_response(security, run_id, trace_context)
                payload = response.as_payload()
                yield {
                    "event": "run_failed",
                    "run_id": run_id,
                    "answer": response.answer,
                    "events": payload["events"],
                    "references": payload["references"],
                    "links": payload["links"],
                    "error_message": response.answer,
                }
                return
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
                    yield from _answer_delta_events(answer, run_id)
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

                tool_security = self._assess_decision_tool_call(decision)
                if not tool_security.allowed:
                    response = self._security_blocked_response(tool_security, run_id, trace_context)
                    payload = response.as_payload()
                    yield {
                        "event": "run_failed",
                        "run_id": run_id,
                        "answer": response.answer,
                        "events": payload["events"],
                        "references": payload["references"],
                        "links": payload["links"],
                        "error_message": response.answer,
                    }
                    return

                if self._decision_requires_confirmation(decision):
                    response = self._confirmation_required_response(
                        decision=decision,
                        run_id=run_id,
                        steps=steps,
                        model_input_summary=model_input_summary,
                        model_output_summary=model_output_summary,
                        trace_context=trace_context,
                        usage=self._usage_payload(decision.usage),
                    )
                    payload = response.as_payload()
                    confirmation_context = self._confirmation_context_from_response(response)
                    yield {
                        "event": "confirmation_required",
                        "run_id": run_id,
                        "answer": response.answer,
                        "events": payload["events"],
                        "references": payload["references"],
                        "links": self._merge_links(
                            payload["links"],
                            self._observability_links(trace_context),
                        ),
                        "step_count": len(steps),
                        "tool_name": decision.tool_call.name,
                        "tool_arguments": decision.tool_call.arguments,
                        "confirmation_context": confirmation_context,
                    }
                    return

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

            tool_security = self._assess_decision_tool_call(decision)
            if not tool_security.allowed:
                return self._security_blocked_response(tool_security, run_id, trace_context)

            if self._decision_requires_confirmation(decision):
                return self._confirmation_required_response(
                    decision=decision,
                    run_id=run_id,
                    steps=steps,
                    model_input_summary=model_input_summary,
                    model_output_summary=model_output_summary,
                    trace_context=trace_context,
                    usage=self._usage_payload(decision.usage),
                )

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
        return annotate_untrusted_observation(result, "tool_observation")

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

    def _decision_requires_confirmation(self, decision: Any) -> bool:
        tool_call = getattr(decision, "tool_call", None)
        if not tool_call:
            return False
        arguments = dict(getattr(tool_call, "arguments", {}) or {})
        if arguments.get("confirmed") is True:
            return False
        try:
            definition = self.tool_registry.get(str(tool_call.name)).definition
        except Exception:
            return False
        return definition.requires_confirmation or definition.risk_level == "high"

    def _response_requires_confirmation(self, response: AgentResponse) -> bool:
        return any(link.get("type") == "confirmation_required" for link in response.links or [])

    def _assess_decision_tool_call(self, decision: Any) -> SecurityDecision:
        tool_call = getattr(decision, "tool_call", None)
        if not tool_call:
            return SecurityDecision(allowed=True)
        return self.security_guard.assess_model_tool_call(
            str(tool_call.name),
            dict(getattr(tool_call, "arguments", {}) or {}),
            self.tool_registry,
        )

    def _security_blocked_response(
        self,
        decision: SecurityDecision,
        run_id: str | None,
        trace_context: TraceContext | None,
    ) -> AgentResponse:
        message = f"安全策略已拦截：{decision.reason}"
        if self.recorder and run_id:
            self.recorder.fail_run(run_id, message)
            self.recorder.record_security_event(
                event_type="security_blocked",
                category=decision.category,
                reason=decision.reason,
                run_id=run_id,
                metadata={"answer": message},
            )
        self.telemetry.fail_run(trace_context, message)
        return AgentResponse(
            answer=message,
            steps=[],
            run_id=run_id,
            links=[
                {
                    "type": "security_blocked",
                    "target_id": decision.category,
                    "title": "Security Policy Blocked",
                    "href": "",
                    "external": False,
                    "reason": decision.reason,
                }
            ],
        )

    def _confirmation_required_response(
        self,
        decision: Any,
        run_id: str | None,
        steps: list[AgentStep],
        model_input_summary: str,
        model_output_summary: str,
        trace_context: TraceContext | None,
        usage: dict[str, Any] | None = None,
    ) -> AgentResponse:
        tool_call = decision.tool_call
        tool_name = str(tool_call.name)
        tool_arguments = dict(tool_call.arguments or {})
        message = (
            f"工具 `{tool_name}` 需要人工确认后才能执行。"
            "请确认操作风险和参数后，带 `confirmed: true` 重新提交。"
        )
        confirmation_context = self._confirmation_context_from_steps(
            tool_name,
            tool_arguments,
            steps,
        )
        confirmation_observation = {
            "confirmation_required": True,
            "tool_name": tool_name,
            "tool_arguments": tool_arguments,
            "confirmation_context": confirmation_context,
        }
        self._record_step(
            run_id,
            len(steps),
            AgentStep(
                tool_name=tool_name,
                tool_arguments=tool_arguments,
                observation=confirmation_observation,
            ),
            status="skipped",
            error_message=message,
            model_input_summary=model_input_summary,
            model_output_summary=model_output_summary,
            trace_context=trace_context,
            usage=usage,
        )
        if self.recorder and run_id:
            self.recorder.wait_for_user(run_id, message)
        return AgentResponse(
            answer=message,
            steps=list(steps),
            run_id=run_id,
            links=[
                {
                    "type": "confirmation_required",
                    "target_id": tool_name,
                    "title": "Human Confirmation Required",
                    "href": "",
                    "external": False,
                    "tool_name": tool_name,
                    "tool_arguments": tool_arguments,
                    "confirmation_context": confirmation_context,
                }
            ],
        )

    def _confirmation_context_from_response(self, response: AgentResponse) -> dict[str, Any]:
        for link in response.links or []:
            if link.get("type") == "confirmation_required":
                context = link.get("confirmation_context")
                return dict(context) if isinstance(context, dict) else {}
        return {}

    def _confirmation_context_from_steps(
        self,
        tool_name: str,
        tool_arguments: dict[str, Any],
        steps: list[AgentStep],
    ) -> dict[str, Any]:
        for step in reversed(steps):
            observation = dict(step.observation or {})
            next_step = dict(observation.get("next_step") or {})
            if next_step.get("tool_name") != tool_name:
                continue
            next_arguments = dict(next_step.get("arguments") or {})
            if str(next_arguments.get("event_id", "")) != str(tool_arguments.get("event_id", "")):
                continue
            if str(next_arguments.get("source_id", "")) != str(tool_arguments.get("source_id", "")):
                continue
            if tool_name == "apply_event_revision":
                return {
                    "kind": "event_revision",
                    "title": "事件修订草案",
                    "target_id": observation.get("event_id", ""),
                    "target_title": observation.get("event_title", ""),
                    "target_label": "历史事件",
                    "diff": observation.get("diff", []),
                    "updates": observation.get("updates", {}),
                    "reason": observation.get("reason", ""),
                    "risk": "会修改事件主记录，并写入 event_change_logs 审计日志。",
                }
            if tool_name == "apply_source_revision":
                return {
                    "kind": "source_revision",
                    "title": "来源核验草案",
                    "target_id": observation.get("source_id", ""),
                    "target_title": observation.get("source_title", ""),
                    "event_id": observation.get("event_id", ""),
                    "target_label": "事件来源",
                    "diff": observation.get("diff", []),
                    "updates": observation.get("updates", {}),
                    "reason": observation.get("reason", ""),
                    "risk": "会修改来源记录，并写入 event_change_logs 审计日志。",
                }
        return {
            "kind": "generic_tool",
            "title": "高风险工具调用",
            "target_id": str(tool_arguments.get("event_id") or tool_arguments.get("source_id") or ""),
            "target_title": "",
            "target_label": "工具参数",
            "diff": [],
            "updates": dict(tool_arguments.get("updates") or {}),
            "reason": str(tool_arguments.get("reason", "")),
            "risk": "该工具被标记为高风险，确认后才会执行。",
        }

    def _pending_confirmation_from_run(self, run: dict[str, Any]) -> dict[str, Any] | None:
        for step in reversed(run.get("steps", [])):
            if step.get("status") != "skipped":
                continue
            result = dict(step.get("tool_result") or {})
            if result.get("confirmation_required") is True:
                return {
                    "step_index": int(step.get("step_index", 0) or 0),
                    "tool_name": str(step.get("tool_name", "")),
                    "tool_arguments": dict(step.get("tool_arguments") or {}),
                }
        return None

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


def _answer_delta_events(answer: str, run_id: str | None) -> Iterator[dict[str, Any]]:
    if not answer:
        return
    chunk_size = 36
    for index in range(0, len(answer), chunk_size):
        yield {
            "event": "answer_delta",
            "run_id": run_id,
            "delta": answer[index : index + chunk_size],
        }
