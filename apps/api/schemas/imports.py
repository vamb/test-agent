from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ImportBatchCreateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    filename: str = "manual-import.json"
    source_note: str = ""
    created_by: str = ""
    events: list[dict[str, Any]] = Field(default_factory=list)


class ImportMutationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool | None = None
    created: bool | None = None
    updated: bool | None = None
    merged: bool | None = None
    revalidated: bool | None = None
    imported: bool | None = None
    rejected: bool | None = None
    error: str | None = None


class ImportParseRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    input_format: str = "json"
    content: Any = ""


class ImportStagingUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    raw_payload: dict[str, Any] | None = None
    event: dict[str, Any] | None = None


class ImportStagingMergeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    strategy: str = ""
    target_event_id: str = ""


class ImportBulkRevalidateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    row_ids: list[str] | None = None
    batch_id: str | None = None


class ImportConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    confirmed_by: str = ""


class ImportRejectRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    reason: str = ""
