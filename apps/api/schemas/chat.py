from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatGroupRequest(BaseModel):
    title: str = Field(default="新分组")
    description: str = ""


class ChatGroupUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    pinned: bool | None = None
    archived: bool | None = None


class ChatConversationRequest(BaseModel):
    title: str = "新会话"
    group_id: str | None = None


class ChatConversationUpdateRequest(BaseModel):
    title: str | None = None
    summary: str | None = None
    status: str | None = None
    group_id: str | None = None


class ChatMessageRequest(BaseModel):
    content: str
    role: str = "user"
    content_format: str = "markdown"
    metadata: dict[str, Any] = Field(default_factory=dict)
