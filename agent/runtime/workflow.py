from __future__ import annotations

from typing import Any, Iterator, Protocol

from agent.models.base import ModelAdapter
from agent.runtime.loop import AgentLoop, AgentLoopConfig
from agent.runtime.observability import AgentTelemetry
from agent.runtime.recorder import AgentRunRecorder
from agent.runtime.simple_historical_agent import AgentResponse
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

    This adapter keeps the proven AgentLoop as the execution core, but runs it through a
    LangGraph state pipeline. The node boundaries are intentionally coarse for now so API,
    worker, telemetry, and checkpoint behavior can switch engines before decision/tool
    execution are split into smaller graph nodes.
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
        result = self._graph.invoke({"mode": "run", "user_input": user_input})
        return _response_from_graph_result(result)

    def run_existing(self, user_input: str, run_id: str) -> AgentResponse:
        result = self._graph.invoke({
            "mode": "run_existing",
            "user_input": user_input,
            "run_id": run_id,
        })
        return _response_from_graph_result(result)

    def resume_existing(self, run_id: str) -> AgentResponse:
        result = self._graph.invoke({"mode": "resume_existing", "run_id": run_id})
        return _response_from_graph_result(result)

    def stream(self, user_input: str) -> Iterator[dict[str, Any]]:
        yield from self.loop.stream(user_input)

    def _compile_graph(self) -> Any:
        try:
            from langgraph.graph import END, StateGraph
        except Exception as exc:
            raise RuntimeError(
                "AGENT_WORKFLOW_ENGINE=langgraph requires the langgraph package."
            ) from exc

        graph = StateGraph(dict)
        graph.add_node("prepare_state", self._prepare_state_node)
        graph.add_node("execute_agent_loop", self._execute_agent_loop_node)
        graph.add_node("finalize_response", self._finalize_response_node)
        graph.set_entry_point("prepare_state")
        graph.add_edge("prepare_state", "execute_agent_loop")
        graph.add_edge("execute_agent_loop", "finalize_response")
        graph.add_edge("finalize_response", END)
        return graph.compile()

    def _prepare_state_node(self, state: dict[str, Any]) -> dict[str, Any]:
        mode = str(state.get("mode", "run"))
        return {
            **state,
            "mode": mode,
            "user_input": str(state.get("user_input", "")),
            "run_id": str(state.get("run_id", "")),
            "workflow_stage": "prepared",
        }

    def _execute_agent_loop_node(self, state: dict[str, Any]) -> dict[str, Any]:
        mode = str(state.get("mode", "run"))
        if mode == "run_existing":
            response = self.loop.run_existing(
                str(state.get("user_input", "")),
                str(state.get("run_id", "")),
            )
        elif mode == "resume_existing":
            response = self.loop.resume_existing(str(state.get("run_id", "")))
        else:
            response = self.loop.run(str(state.get("user_input", "")))
        return {**state, "response": response, "workflow_stage": "executed"}

    def _finalize_response_node(self, state: dict[str, Any]) -> dict[str, Any]:
        response = state.get("response")
        if not isinstance(response, AgentResponse):
            raise RuntimeError("LangGraph workflow did not return an AgentResponse.")
        return {**state, "workflow_stage": "finalized"}


def _response_from_graph_result(result: dict[str, Any]) -> AgentResponse:
    response = result.get("response")
    if not isinstance(response, AgentResponse):
        raise RuntimeError("LangGraph workflow did not return an AgentResponse.")
    return response
