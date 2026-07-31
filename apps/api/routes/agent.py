from __future__ import annotations

import json
from typing import Any, Iterable, Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from agent.models.factory import build_model_adapter
from agent.runtime.workflow import build_agent_workflow
from apps.api.dependencies import (
    agent_queue,
    chat_service,
    memory_service,
    recorder,
    settings,
    telemetry,
    tool_registry,
)
from apps.api.routes.auth import optional_current_user
from apps.worker.agent_worker import AgentWorker


router = APIRouter()


@router.post("/agent/query")
def query_agent(
    payload: dict,
    current_user: Any = Depends(optional_current_user),
) -> dict:
    user_input = str(payload.get("input", ""))
    user = current_user if isinstance(current_user, dict) else None
    agent_input = user_input
    memory_context = ""
    stored_user_message = None
    if user:
        memory_context = memory_service.memory_context(user["id"], user_input)
        agent_input = _with_memory_context(user_input, memory_context)
        stored_user_message = chat_service.store_user_message(
            user_id=user["id"],
            content=user_input,
            conversation_id=_optional_text(payload.get("conversation_id")),
            title_hint=user_input,
        )
    agent = build_agent_workflow(
        workflow_engine=settings.agent_runtime.workflow_engine,
        model_adapter=build_model_adapter(settings.model),
        tool_registry=tool_registry,
        recorder=recorder,
        telemetry=telemetry,
    )
    response = agent.run(agent_input)
    payload = response.as_payload()
    if memory_context:
        payload["memory_context"] = memory_context
    if user and stored_user_message and response.run_id:
        chat_service.bind_agent_run(
            run_id=response.run_id,
            user_id=user["id"],
            conversation_id=stored_user_message.conversation_id,
            input_message_id=stored_user_message.message_id,
        )
        assistant_message = chat_service.create_message(
            user_id=user["id"],
            conversation_id=stored_user_message.conversation_id,
            role="assistant",
            content=response.answer,
            status="done",
            agent_run_id=response.run_id,
            parent_message_id=stored_user_message.message_id,
            metadata={"step_count": len(response.steps)},
        )
        chat_service.add_artifacts(
            assistant_message["id"],
            _artifacts_from_payload(payload),
        )
        chat_service.bind_agent_run(
            run_id=response.run_id,
            user_id=user["id"],
            conversation_id=stored_user_message.conversation_id,
            output_message_id=assistant_message["id"],
        )
        payload["conversation_id"] = stored_user_message.conversation_id
        payload["input_message_id"] = stored_user_message.message_id
        payload["output_message_id"] = assistant_message["id"]
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
def query_agent_stream(
    payload: dict,
    current_user: Any = Depends(optional_current_user),
) -> StreamingResponse:
    user_input = str(payload.get("input", ""))
    user = current_user if isinstance(current_user, dict) else None
    agent_input = user_input
    memory_context = ""
    stored_user_message = None
    if user:
        memory_context = memory_service.memory_context(user["id"], user_input)
        agent_input = _with_memory_context(user_input, memory_context)
        stored_user_message = chat_service.store_user_message(
            user_id=user["id"],
            content=user_input,
            conversation_id=_optional_text(payload.get("conversation_id")),
            title_hint=user_input,
        )
    agent = build_agent_workflow(
        workflow_engine=settings.agent_runtime.workflow_engine,
        model_adapter=build_model_adapter(settings.model),
        tool_registry=tool_registry,
        recorder=recorder,
        telemetry=telemetry,
    )
    events: Iterable[dict] = agent.stream(agent_input)
    if memory_context:
        events = _prepend_memory_context(events, memory_context)
    if user and stored_user_message:
        events = _persist_chat_stream(
            events,
            user=user,
            stored_user_message=stored_user_message,
        )
    return StreamingResponse(
        _sse_events(events),
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


def _prepend_memory_context(events: Iterable[dict], memory_context: str) -> Iterator[dict]:
    yielded = False
    for event in events:
        yield event
        if not yielded and event.get("event") == "run_started":
            yielded = True
            yield {
                "event": "memory_context",
                "memory_context": memory_context,
            }


def _persist_chat_stream(
    events: Iterable[dict],
    user: dict,
    stored_user_message: Any,
) -> Iterator[dict]:
    run_id = ""
    output_message_id = ""
    yield {
        "event": "chat_context",
        "conversation_id": stored_user_message.conversation_id,
        "input_message_id": stored_user_message.message_id,
    }
    for event in events:
        if event.get("run_id"):
            run_id = str(event["run_id"])
            chat_service.bind_agent_run(
                run_id=run_id,
                user_id=user["id"],
                conversation_id=stored_user_message.conversation_id,
                input_message_id=stored_user_message.message_id,
            )
        if event.get("event") in {
            "final_answer",
            "confirmation_required",
            "run_failed",
            "run_cancelled",
        }:
            status = _message_status_for_event(str(event.get("event", "")))
            content = str(
                event.get("answer")
                or event.get("error_message")
                or ("已停止生成。" if status == "cancelled" else "")
            )
            assistant_message = chat_service.create_message(
                user_id=user["id"],
                conversation_id=stored_user_message.conversation_id,
                role="assistant",
                content=content,
                status=status,
                agent_run_id=run_id or None,
                parent_message_id=stored_user_message.message_id,
                metadata={
                    "stream_event": event.get("event"),
                    "step_count": event.get("step_count"),
                },
            )
            output_message_id = assistant_message["id"]
            chat_service.add_artifacts(
                output_message_id,
                _artifacts_from_payload(event),
            )
            if run_id:
                chat_service.bind_agent_run(
                    run_id=run_id,
                    user_id=user["id"],
                    conversation_id=stored_user_message.conversation_id,
                    output_message_id=output_message_id,
                )
            event = {
                **event,
                "conversation_id": stored_user_message.conversation_id,
                "input_message_id": stored_user_message.message_id,
                "output_message_id": output_message_id,
            }
        yield event


def _message_status_for_event(event_name: str) -> str:
    if event_name == "run_failed":
        return "error"
    if event_name == "run_cancelled":
        return "cancelled"
    return "done"


def _artifacts_from_payload(payload: dict) -> dict[str, list[dict[str, Any]]]:
    return {
        "event": [dict(item) for item in payload.get("events") or [] if isinstance(item, dict)],
        "reference": [
            dict(item) for item in payload.get("references") or [] if isinstance(item, dict)
        ],
        "link": [dict(item) for item in payload.get("links") or [] if isinstance(item, dict)],
    }


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _with_memory_context(user_input: str, memory_context: str) -> str:
    if not memory_context:
        return user_input
    return (
        f"{memory_context}\n\n"
        "用户当前问题如下。回答时必须优先使用工具查询到的事实；"
        "长期记忆只用于理解用户偏好和研究兴趣。\n"
        f"{user_input}"
    )
