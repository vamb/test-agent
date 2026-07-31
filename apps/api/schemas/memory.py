from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MemoryCreateRequest(BaseModel):
    content: str
    memory_type: str = "preference"
    status: str = "enabled"
    confidence: float = Field(default=0.6, ge=0, le=1)
    source_conversation_id: str | None = None
    source_summary_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryUpdateRequest(BaseModel):
    content: str | None = None
    memory_type: str | None = None
    status: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, Any] | None = None


class ConversationSummaryRequest(BaseModel):
    create_memory_candidate: bool = False
