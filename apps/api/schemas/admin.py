from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AdminPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    admin_token: str | None = None
    confirmed: bool = False
    confirmed_by: str = ""
    reason: str = ""


class AdminMutationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool | None = None
    error: str | None = None


class AdminCreateEventRequest(AdminPayload):
    filename: str = "event-management-create.json"
    event: dict[str, Any]


class AdminUpdateEventRequest(AdminPayload):
    updates: dict[str, Any] = Field(default_factory=dict)


class AdminBulkUpdateEventsRequest(AdminPayload):
    event_ids: list[str] = Field(default_factory=list)
    updates: dict[str, Any] = Field(default_factory=dict)


class AdminSourceRequest(AdminPayload):
    source: dict[str, Any]


class AdminUpdateSourceRequest(AdminPayload):
    updates: dict[str, Any] = Field(default_factory=dict)


class AdminVerifySourceRequest(AdminPayload):
    reliability: float = 0.8


class AdminBulkVerifySourcesRequest(AdminVerifySourceRequest):
    source_ids: list[str] = Field(default_factory=list)


class AdminQualityIssueActionRequest(AdminPayload):
    issue_type: str
    target_type: str
    target_id: str
    status: str = "resolved"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdminRelationRequest(AdminPayload):
    relation: dict[str, Any]


class AdminUpdateRelationRequest(AdminPayload):
    updates: dict[str, Any] = Field(default_factory=dict)
