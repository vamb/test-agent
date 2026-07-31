from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.dependencies import chat_service
from apps.api.routes.auth import require_current_user
from apps.api.schemas.chat import (
    ChatConversationRequest,
    ChatConversationUpdateRequest,
    ChatGroupRequest,
    ChatGroupUpdateRequest,
    ChatMessageRequest,
)


router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/groups")
def list_chat_groups(
    include_archived: bool = False,
    user: dict = Depends(require_current_user),
) -> dict:
    return {
        "groups": chat_service.list_groups(
            user_id=user["id"],
            include_archived=include_archived,
        )
    }


@router.post("/groups")
def create_chat_group(
    payload: ChatGroupRequest,
    user: dict = Depends(require_current_user),
) -> dict:
    return {
        "group": chat_service.create_group(
            user_id=user["id"],
            title=payload.title,
            description=payload.description,
        )
    }


@router.patch("/groups/{group_id}")
def update_chat_group(
    group_id: str,
    payload: ChatGroupUpdateRequest,
    user: dict = Depends(require_current_user),
) -> dict:
    group = chat_service.update_group(
        user_id=user["id"],
        group_id=group_id,
        updates=payload.model_dump(exclude_unset=True),
    )
    if not group:
        raise HTTPException(status_code=404, detail="chat group not found")
    return {"group": group}


@router.delete("/groups/{group_id}")
def archive_chat_group(
    group_id: str,
    user: dict = Depends(require_current_user),
) -> dict:
    group = chat_service.update_group(
        user_id=user["id"],
        group_id=group_id,
        updates={"archived": True},
    )
    if not group:
        raise HTTPException(status_code=404, detail="chat group not found")
    return {"group": group}


@router.get("/conversations")
def list_chat_conversations(
    group_id: str | None = None,
    status: str = "active",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_current_user),
) -> dict:
    return {
        "conversations": chat_service.list_conversations(
            user_id=user["id"],
            group_id=group_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    }


@router.post("/conversations")
def create_chat_conversation(
    payload: ChatConversationRequest,
    user: dict = Depends(require_current_user),
) -> dict:
    try:
        conversation = chat_service.create_conversation(
            user_id=user["id"],
            title=payload.title,
            group_id=payload.group_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"conversation": conversation}


@router.get("/conversations/{conversation_id}")
def get_chat_conversation(
    conversation_id: str,
    user: dict = Depends(require_current_user),
) -> dict:
    conversation = chat_service.get_conversation(user["id"], conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {
        "conversation": conversation,
        "messages": chat_service.list_messages(user["id"], conversation_id),
    }


@router.patch("/conversations/{conversation_id}")
def update_chat_conversation(
    conversation_id: str,
    payload: ChatConversationUpdateRequest,
    user: dict = Depends(require_current_user),
) -> dict:
    conversation = chat_service.update_conversation(
        user_id=user["id"],
        conversation_id=conversation_id,
        updates=payload.model_dump(exclude_unset=True),
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"conversation": conversation}


@router.delete("/conversations/{conversation_id}")
def archive_chat_conversation(
    conversation_id: str,
    user: dict = Depends(require_current_user),
) -> dict:
    conversation = chat_service.update_conversation(
        user_id=user["id"],
        conversation_id=conversation_id,
        updates={"status": "archived"},
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"conversation": conversation}


@router.get("/conversations/{conversation_id}/messages")
def list_chat_messages(
    conversation_id: str,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_current_user),
) -> dict:
    try:
        messages = chat_service.list_messages(
            user_id=user["id"],
            conversation_id=conversation_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"messages": messages}


@router.post("/conversations/{conversation_id}/messages")
def create_chat_message(
    conversation_id: str,
    payload: ChatMessageRequest,
    user: dict = Depends(require_current_user),
) -> dict:
    try:
        message = chat_service.create_message(
            user_id=user["id"],
            conversation_id=conversation_id,
            role=payload.role,
            content=payload.content,
            content_format=payload.content_format,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"message": message}
