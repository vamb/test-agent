from __future__ import annotations

from typing import Any, Iterator, Protocol

from agent.models.base import ModelAdapter
from agent.runtime.loop import AgentLoop, AgentLoopConfig, AgentRunCancelled
from agent.runtime.observability import AgentTelemetry, TraceContext
from agent.runtime.recorder import AgentRunRecorder
from agent.runtime.simple_historical_agent import AgentResponse, AgentStep
from tools.registry.base import ToolRegistry


class AgentWorkflow(Protocol):
    def run(self, user_input: str) -> AgentResponse:
        ...

    def run_existing(self, user_input: str, run_id: str) -> AgentResponse:
        ...

    def resume_existing(self, run_id: str) -> AgentResponse:
        ...

    def stream(self, user_input: str) -> Iterator[dict[str, Any]]:
        ...


def build_agent_workflow(
    workflow_engine: str,
    model_adapter: ModelAdapter,
    tool_registry: ToolRegistry,
    recorder: AgentRunRecorder | None = None,
    telemetry: AgentTelemetry | None = None,
    config: AgentLoopConfig | None = None,
) -> AgentWorkflow:
    engine = workflow_engine.strip().lower()
    if engine in {"", "loop", "manual"}:
        return AgentLoop(
            model_adapter=model_adapter,
            tool_registry=tool_registry,
            recorder=recorder,
            telemetry=telemetry,
            config=config,
        )
    if engine == "langgraph":
        return LangGraphAgentWorkflow(
            model_adapter=model_adapter,
            tool_registry=tool_registry,
            recorder=recorder,
            telemetry=telemetry,
            config=config,
        )
    raise ValueError(f"Unsupported agent workflow engine: {workflow_engine}")


class LangGraphAgentWorkflow:
    """Experimental LangGraph entry point that preserves the current API contract.

    This adapter keeps AgentLoop's small helper methods as the execution primitives, but
    runs the inner reasoning cycle through LangGraph nodes.
    """

    def __init__(
        self,
        model_adapter: ModelAdapter,
        tool_registry: ToolRegistry,
        recorder: AgentRunRecorder | None = None,
        telemetry: AgentTelemetry | None = None,
        config: AgentLoopConfig | None = None,
    ) -> None:
        self.loop = AgentLoop(
            model_adapter=model_adapter,
            tool_registry=tool_registry,
            recorder=recorder,
            telemetry=telemetry,
            config=config,
        )
        self._graph = self._compile_graph()

    def run(self, user_input: str) -> AgentResponse:
        recorded_run = (
            self.loop.recorder.start_run(
                user_input,
                model_name=self.loop.model_adapter.model_name,
                prompt_version="historical-agent-loop-v1",
            )
            if self.loop.recorder
            else None
        )
        run_id = recorded_run.run_id if recorded_run else None
        trace_context = self.loop.telemetry.start_run(
            run_id,
            user_input=user_input,
            model_name=self.loop.model_adapter.model_name,
            prompt_version="historical-agent-loop-v1",
        )
        try:
            response = self._run_graph_without_recording(
                user_input=user_input,
                run_id=run_id,
                trace_context=trace_context,
            )
        except AgentRunCancelled as exc:
            if self.loop.recorder and run_id:
                self.loop.recorder.cancel_run(run_id, str(exc))
            self.loop.telemetry.cancel_run(trace_context, str(exc))
            raise
        except Exception as exc:
            if self.loop.recorder and run_id:
                self.loop.recorder.fail_run(run_id, str(exc))
            self.loop.telemetry.fail_run(trace_context, str(exc))
            raise

        if self.loop.recorder and run_id:
            self.loop.recorder.finish_run(run_id, response.answer)
        self.loop.telemetry.finish_run(trace_context, response.answer)
        return self.loop._with_observability_links(response, trace_context)

    def run_existing(self, user_input: str, run_id: str) -> AgentResponse:
        trace_context = self.loop.telemetry.start_run(
            run_id,
            user_input=user_input,
            model_name=self.loop.model_adapter.model_name,
            prompt_version="historical-agent-loop-v1",
        )
        try:
            response = self._run_graph_without_recording(
                user_input=user_input,
                run_id=run_id,
                trace_context=trace_context,
            )
        except AgentRunCancelled as exc:
            if self.loop.recorder:
                self.loop.recorder.cancel_run(run_id, str(exc))
            self.loop.telemetry.cancel_run(trace_context, str(exc))
            raise
        except Exception as exc:
            if self.loop.recorder:
                self.loop.recorder.fail_run(run_id, str(exc))
            self.loop.telemetry.fail_run(trace_context, str(exc))
            raise

        if self.loop.recorder:
            self.loop.recorder.finish_run(run_id, response.answer)
        self.loop.telemetry.finish_run(trace_context, response.answer)
        return self.loop._with_observability_links(response, trace_context)

    def resume_existing(self, run_id: str) -> AgentResponse:
        if not self.loop.recorder:
            raise RuntimeError("resume_existing requires an AgentRunRecorder.")
        run = self.loop.recorder.get_run(run_id)
        if not run:
            raise RuntimeError(f"Agent run not found: {run_id}")
        user_input = str(run["user_input"])
        trace_context = self.loop.telemetry.start_run(
            run_id,
            user_input=user_input,
            model_name=self.loop.model_adapter.model_name,
            prompt_version=str(run.get("prompt_version") or "historical-agent-loop-v1"),
        )
        try:
            response = self._run_graph_without_recording(
                user_input=user_input,
                run_id=run_id,
                existing_steps=self.loop._completed_steps_from_run(run),
                trace_context=trace_context,
            )
        except AgentRunCancelled as exc:
            self.loop.recorder.cancel_run(run_id, str(exc))
            self.loop.telemetry.cancel_run(trace_context, str(exc))
            raise
        except Exception as exc:
            self.loop.recorder.fail_run(run_id, str(exc))
            self.loop.telemetry.fail_run(trace_context, str(exc))
            raise

        self.loop.recorder.finish_run(run_id, response.answer)
        self.loop.telemetry.finish_run(trace_context, response.answer)
        return self.loop._with_observability_links(response, trace_context)

    def stream(self, user_input: str) -> Iterator[dict[str, Any]]:
        recorded_run = (
            self.loop.recorder.start_run(
                user_input,
                model_name=self.loop.model_adapter.model_name,
                prompt_version="historical-agent-loop-v1",
            )
            if self.loop.recorder
            else None
        )
        run_id = recorded_run.run_id if recorded_run else None
        trace_context = self.loop.telemetry.start_run(
            run_id,
            user_input=user_input,
            model_name=self.loop.model_adapter.model_name,
            prompt_version="historical-agent-loop-v1",
        )
        yield {
            "event": "run_started",
            "run_id": run_id,
            "trace_id": trace_context.trace_id if trace_context else None,
            "trace_url": trace_context.trace_url if trace_context else "",
        }

        state = self._prepare_state_node(
            {
                "user_input": user_input,
                "run_id": run_id or "",
                "trace_context": trace_context,
            }
        )
        try:
            for _ in range(self.loop.config.max_steps):
                state = self._decide_node(state)
                decision = state.get("decision")
                usage = self.loop._usage_payload(decision.usage)
                if getattr(decision, "action", "") == "finish":
                    state = self._finalize_response_node(state)
                    response = self.loop._with_observability_links(
                        _response_from_graph_result(state),
                        trace_context,
                    )
                    if self.loop.recorder and run_id:
                        self.loop.recorder.finish_run(run_id, response.answer)
                    self.loop.telemetry.finish_run(
                        trace_context,
                        response.answer,
                        usage=usage,
                    )
                    payload = response.as_payload()
                    yield {
                        "event": "final_answer",
                        "run_id": run_id,
                        "answer": response.answer,
                        "events": payload["events"],
                        "references": payload["references"],
                        "links": payload["links"],
                        "step_count": len(response.steps),
                        "usage": usage,
                    }
                    yield {"event": "run_completed", "run_id": run_id}
                    return

                if not getattr(decision, "tool_call", None):
                    raise RuntimeError("Model requested a tool call without tool details.")

                step_index = len(list(state.get("steps", [])))
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
                    "usage": usage,
                }
                state = self._execute_tool_node(state)
                execution = dict(state.get("last_execution") or {})
                yield {
                    "event": "tool_result",
                    "run_id": run_id,
                    "step_index": step_index,
                    "tool_name": str(execution.get("tool_name", "")),
                    "status": str(execution.get("status", "")),
                    "elapsed_ms": int(execution.get("elapsed_ms", 0) or 0),
                    "observation": dict(execution.get("observation") or {}),
                    "error_message": execution.get("error_message"),
                }
                if self._route_after_tool(state) == "max_steps_exceeded":
                    break

            self._max_steps_exceeded_node(state)
        except AgentRunCancelled as exc:
            if self.loop.recorder and run_id:
                self.loop.recorder.cancel_run(run_id, str(exc))
            self.loop.telemetry.cancel_run(trace_context, str(exc))
            yield {
                "event": "run_cancelled",
                "run_id": run_id,
                "error_message": str(exc),
            }
        except Exception as exc:
            if self.loop.recorder and run_id:
                self.loop.recorder.fail_run(run_id, str(exc))
            self.loop.telemetry.fail_run(trace_context, str(exc))
            yield {
                "event": "run_failed",
                "run_id": run_id,
                "error_message": str(exc),
            }

    def _compile_graph(self) -> Any:
        try:
            from langgraph.graph import END, StateGraph
        except Exception as exc:
            raise RuntimeError(
                "AGENT_WORKFLOW_ENGINE=langgraph requires the langgraph package."
            ) from exc

        graph = StateGraph(dict)
        graph.add_node("prepare_state", self._prepare_state_node)
        graph.add_node("decide", self._decide_node)
        graph.add_node("execute_tool", self._execute_tool_node)
        graph.add_node("max_steps_exceeded", self._max_steps_exceeded_node)
        graph.add_node("finalize_response", self._finalize_response_node)
        graph.set_entry_point("prepare_state")
        graph.add_edge("prepare_state", "decide")
        graph.add_conditional_edges(
            "decide",
            self._route_after_decision,
            {
                "execute_tool": "execute_tool",
                "finalize_response": "finalize_response",
            },
        )
        graph.add_conditional_edges(
            "execute_tool",
            self._route_after_tool,
            {
                "decide": "decide",
                "max_steps_exceeded": "max_steps_exceeded",
            },
        )
        graph.add_edge("max_steps_exceeded", END)
        graph.add_edge("finalize_response", END)
        return graph.compile()

    def _prepare_state_node(self, state: dict[str, Any]) -> dict[str, Any]:
        user_input = str(state.get("user_input", ""))
        existing_steps = list(state.get("existing_steps", []))
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_input}]
        for step_index, step in enumerate(existing_steps):
            tool_call_id = f"call_{step_index}"
            messages.append(self.loop._assistant_tool_call_message_from_step(tool_call_id, step))
            messages.append(
                {
                    "role": "tool",
                    "name": step.tool_name,
                    "tool_call_id": tool_call_id,
                    "content": step.observation,
                    "elapsed_ms": 0,
                }
            )
        return {
            **state,
            "user_input": user_input,
            "messages": messages,
            "steps": existing_steps,
            "iteration": len(existing_steps),
            "run_id": str(state.get("run_id", "")),
            "trace_context": state.get("trace_context"),
            "workflow_stage": "prepared",
        }

    def _decide_node(self, state: dict[str, Any]) -> dict[str, Any]:
        run_id = str(state.get("run_id", "")) or None
        self.loop._raise_if_cancelled(run_id)
        messages = list(state.get("messages", []))
        decision = self.loop._decide_with_timing(messages)
        steps = list(state.get("steps", []))
        step_index = len(steps)
        model_input_summary = self.loop._summarize_model_input(messages)
        model_output_summary = self.loop._summarize_model_output(decision)
        trace_context = state.get("trace_context")
        self.loop.telemetry.record_model_decision(
            trace_context,
            step_index=step_index,
            model_name=self.loop.model_adapter.model_name,
            input_summary=model_input_summary,
            output_summary=model_output_summary,
            usage=self.loop._usage_payload(decision.usage),
        )
        return {
            **state,
            "decision": decision,
            "model_input_summary": model_input_summary,
            "model_output_summary": model_output_summary,
            "workflow_stage": "decided",
        }

    def _execute_tool_node(self, state: dict[str, Any]) -> dict[str, Any]:
        decision = state.get("decision")
        if not getattr(decision, "tool_call", None):
            raise RuntimeError("Model requested a tool call without tool details.")
        run_id = str(state.get("run_id", "")) or None
        messages = list(state.get("messages", []))
        steps: list[AgentStep] = list(state.get("steps", []))
        step_index = len(steps)
        tool_call_id = f"call_{step_index}"
        messages.append(self.loop._assistant_tool_call_message(tool_call_id, decision))
        self.loop._raise_if_cancelled(run_id)
        execution = self.loop.executor.execute(
            decision.tool_call.name,
            decision.tool_call.arguments,
        )
        self.loop._raise_if_cancelled(run_id)
        observation = self.loop._trim_observation(execution.observation)
        step = AgentStep(
            tool_name=execution.tool_name,
            tool_arguments=execution.arguments,
            observation=observation,
        )
        self.loop._record_step(
            run_id,
            step_index,
            step,
            status=execution.status,
            error_message=execution.error_message,
            model_input_summary=str(state.get("model_input_summary", "")),
            model_output_summary=str(state.get("model_output_summary", "")),
            token_input=decision.usage.token_input,
            token_output=decision.usage.token_output,
            trace_context=state.get("trace_context"),
            usage=self.loop._usage_payload(decision.usage),
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
        return {
            **state,
            "messages": messages,
            "steps": steps,
            "iteration": len(steps),
            "last_execution": {
                "tool_name": execution.tool_name,
                "status": execution.status,
                "elapsed_ms": execution.elapsed_ms,
                "observation": observation,
                "error_message": execution.error_message,
            },
            "workflow_stage": "tool_executed",
        }

    def _finalize_response_node(self, state: dict[str, Any]) -> dict[str, Any]:
        decision = state.get("decision")
        answer = str(getattr(decision, "answer", "") or "")
        self.loop._raise_if_cancelled(str(state.get("run_id", "")) or None)
        response = AgentResponse(
            answer,
            list(state.get("steps", [])),
            run_id=str(state.get("run_id", "")) or None,
        )
        return {**state, "response": response, "workflow_stage": "finalized"}

    def _max_steps_exceeded_node(self, state: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("当前问题需要更多推理步骤，已达到本轮 Agent 最大工具调用次数。")

    def _route_after_decision(self, state: dict[str, Any]) -> str:
        decision = state.get("decision")
        if getattr(decision, "action", "") == "finish":
            return "finalize_response"
        return "execute_tool"

    def _route_after_tool(self, state: dict[str, Any]) -> str:
        if int(state.get("iteration", 0)) >= self.loop.config.max_steps:
            return "max_steps_exceeded"
        return "decide"

    def _run_graph_without_recording(
        self,
        user_input: str,
        run_id: str | None = None,
        existing_steps: list[AgentStep] | None = None,
        trace_context: TraceContext | None = None,
    ) -> AgentResponse:
        result = self._graph.invoke(
            {
                "user_input": user_input,
                "run_id": run_id or "",
                "existing_steps": existing_steps or [],
                "trace_context": trace_context,
            }
        )
        return _response_from_graph_result(result)


def _response_from_graph_result(result: dict[str, Any]) -> AgentResponse:
    response = result.get("response")
    if not isinstance(response, AgentResponse):
        raise RuntimeError("LangGraph workflow did not return an AgentResponse.")
    return response
