from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocumentIngestRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = "Untitled document"
    content: str = ""
    source_type: str = "note"
    source_uri: str = ""
    citation: str = ""
    created_by: str = ""


class KnowledgeMutationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool | None = None
    created: bool | None = None
    updated: bool | None = None
    processed: bool | None = None
    error: str | None = None


class KnowledgeDocumentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    updates: dict[str, Any] = Field(default_factory=dict)


class KnowledgeDocumentRechunkRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    content: str | None = None
    max_chars: int | None = None
    overlap_chars: int | None = None
    changed_by: str = ""
    reason: str = ""


class VectorRebuildRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    target: str = "knowledge"
    limit: int = 100
    created_by: str = ""
    auto_process: bool = False


class VectorProcessPendingRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    limit: int = 1
