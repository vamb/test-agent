from __future__ import annotations

import json
from typing import Iterable, Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent.models.factory import build_model_adapter
from agent.runtime.workflow import build_agent_workflow
from apps.api.dependencies import agent_queue, recorder, settings, telemetry, tool_registry
from apps.worker.agent_worker import AgentWorker


router = APIRouter()


@router.post("/agent/query")
def query_agent(payload: dict) -> dict:
    user_input = str(payload.get("input", ""))
    agent = build_agent_workflow(
        workflow_engine=settings.agent_runtime.workflow_engine,
        model_adapter=build_model_adapter(settings.model),
        tool_registry=tool_registry,
        recorder=recorder,
        telemetry=telemetry,
    )
    response = agent.run(user_input)
    payload = response.as_payload()
    return {
        **payload,
        "steps": [
            {
                "tool_name": step.tool_name,
                "tool_arguments": step.tool_arguments,
                "observation": step.observation,
            }
            for step in response.steps
        ],
    }


@router.post("/agent/query/async")
def enqueue_agent_query(payload: dict) -> dict:
    user_input = str(payload.get("input", ""))
    user_id = str(payload.get("user_id", ""))
    queued = agent_queue.enqueue(
        user_input=user_input,
        user_id=user_id,
        model_name=build_model_adapter(settings.model).model_name,
    )
    return {
        "run_id": queued.run_id,
        "status": queued.status,
        "queue_backend": queued.queue_backend,
        "queued": True,
    }


@router.post("/agent/query/stream")
def query_agent_stream(payload: dict) -> StreamingResponse:
    user_input = str(payload.get("input", ""))
    agent = build_agent_workflow(
        workflow_engine=settings.agent_runtime.workflow_engine,
        model_adapter=build_model_adapter(settings.model),
        tool_registry=tool_registry,
        recorder=recorder,
        telemetry=telemetry,
    )
    return StreamingResponse(
        _sse_events(agent.stream(user_input)),
        media_type="text/event-stream",
    )


@router.get("/agent/runs/{run_id}")
def get_agent_run(run_id: str) -> dict:
    run = recorder.get_run(run_id)
    if not run:
        return {"found": False, "run_id": run_id}
    run["found"] = True
    link = telemetry.trace_link_for_run_id(run_id)
    run["links"] = [link] if link else []
    return run


@router.get("/agent/queue/health")
def agent_queue_health() -> dict:
    return agent_queue.health()


@router.post("/agent/runs/{run_id}/cancel")
def cancel_agent_run(run_id: str, payload: dict | None = None) -> dict:
    reason = "Cancelled by user"
    if payload:
        reason = str(payload.get("reason", reason))
    cancelled = recorder.cancel_run(run_id, reason)
    return {
        "run_id": run_id,
        "cancelled": cancelled,
        "status": "cancelled" if cancelled else "unchanged",
    }


@router.post("/agent/runs/{run_id}/confirm")
def confirm_agent_run(run_id: str) -> dict:
    agent = build_agent_workflow(
        workflow_engine=settings.agent_runtime.workflow_engine,
        model_adapter=build_model_adapter(settings.model),
        tool_registry=tool_registry,
        recorder=recorder,
        telemetry=telemetry,
    )
    response = agent.confirm_existing(run_id)
    payload = response.as_payload()
    return {
        **payload,
        "confirmed": True,
        "steps": [
            {
                "tool_name": step.tool_name,
                "tool_arguments": step.tool_arguments,
                "observation": step.observation,
            }
            for step in response.steps
        ],
    }


@router.post("/agent/queue/process-one")
def process_one_queued_agent_run() -> dict:
    result = AgentWorker(settings).process_one()
    return {
        "processed": result.processed,
        "run_id": result.run_id,
        "status": result.status,
        "error": result.error,
        "queue_action": result.queue_action,
        "attempts": result.attempts,
        "dead_lettered": result.dead_lettered,
    }


@router.post("/agent/queue/recover-stale")
def recover_stale_agent_runs() -> dict:
    return agent_queue.recover_stale()


def _sse_events(events: Iterable[dict]) -> Iterator[str]:
    for payload in events:
        event_name = str(payload.get("event", "message"))
        data = json.dumps(payload, ensure_ascii=False, default=str)
        yield f"event: {event_name}\ndata: {data}\n\n"
