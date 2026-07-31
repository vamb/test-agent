from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.dependencies import memory_service
from apps.api.routes.auth import require_current_user
from apps.api.schemas.memory import (
    ConversationSummaryRequest,
    MemoryCreateRequest,
    MemoryUpdateRequest,
)


router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/memories")
def list_memories(
    status: str = "enabled",
    memory_type: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(require_current_user),
) -> dict:
    return {
        "memories": memory_service.list_memories(
            user_id=user["id"],
            status=status,
            memory_type=memory_type,
            limit=limit,
        )
    }


@router.post("/memories")
def create_memory(
    payload: MemoryCreateRequest,
    user: dict = Depends(require_current_user),
) -> dict:
    try:
        memory = memory_service.create_memory(
            user_id=user["id"],
            content=payload.content,
            memory_type=payload.memory_type,
            status=payload.status,
            confidence=payload.confidence,
            source_conversation_id=payload.source_conversation_id,
            source_summary_id=payload.source_summary_id,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"memory": memory}


@router.patch("/memories/{memory_id}")
def update_memory(
    memory_id: str,
    payload: MemoryUpdateRequest,
    user: dict = Depends(require_current_user),
) -> dict:
    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        updates["metadata_json"] = updates.pop("metadata")
    memory = memory_service.update_memory(user["id"], memory_id, updates)
    if not memory:
        raise HTTPException(status_code=404, detail="memory not found")
    return {"memory": memory}


@router.delete("/memories/{memory_id}")
def delete_memory(
    memory_id: str,
    user: dict = Depends(require_current_user),
) -> dict:
    memory = memory_service.update_memory(
        user_id=user["id"],
        memory_id=memory_id,
        updates={"status": "deleted"},
    )
    if not memory:
        raise HTTPException(status_code=404, detail="memory not found")
    return {"memory": memory}


@router.get("/recall")
def recall_memories(
    query: str,
    limit: int = Query(5, ge=1, le=10),
    user: dict = Depends(require_current_user),
) -> dict:
    return {
        "memories": memory_service.recall(
            user_id=user["id"],
            query=query,
            limit=limit,
        )
    }


@router.get("/summaries")
def list_conversation_summaries(
    conversation_id: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(require_current_user),
) -> dict:
    return {
        "summaries": memory_service.list_summaries(
            user_id=user["id"],
            conversation_id=conversation_id,
            limit=limit,
        )
    }


@router.post("/conversations/{conversation_id}/summarize")
def summarize_conversation(
    conversation_id: str,
    payload: ConversationSummaryRequest,
    user: dict = Depends(require_current_user),
) -> dict:
    try:
        return memory_service.summarize_conversation(
            user_id=user["id"],
            conversation_id=conversation_id,
            create_memory_candidate=payload.create_memory_candidate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
