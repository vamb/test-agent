from __future__ import annotations

import json

from fastapi import APIRouter

from apps.api.dependencies import import_review_service
from apps.api.payloads import payload_to_dict
from apps.api.schemas.imports import (
    ImportBatchCreateRequest,
    ImportBulkRevalidateRequest,
    ImportConfirmRequest,
    ImportMutationResponse,
    ImportParseRequest,
    ImportRejectRequest,
    ImportStagingMergeRequest,
    ImportStagingUpdateRequest,
)


router = APIRouter()


@router.post("/imports/batches", response_model=ImportMutationResponse)
def create_import_batch(payload: ImportBatchCreateRequest) -> dict:
    payload = payload_to_dict(payload)
    events = payload.get("events", [])
    if not isinstance(events, list):
        return {"created": False, "error": "events must be a list"}
    batch = import_review_service.create_batch(
        filename=str(payload.get("filename", "manual-import.json")),
        source_note=str(payload.get("source_note", "")),
        created_by=str(payload.get("created_by", "")),
        events=events,
    )
    batch["created"] = True
    return batch


@router.post("/imports/parse", response_model=ImportMutationResponse)
def parse_import_events(payload: ImportParseRequest) -> dict:
    payload = payload_to_dict(payload)
    content = payload.get("content", "")
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    return import_review_service.parse_events(
        content=content,
        input_format=str(payload.get("input_format", "json")),
    )


@router.get("/imports/batches")
def list_import_batches(
    status: str | None = None,
    created_by: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return import_review_service.list_batches(
        status=status,
        created_by=created_by,
        limit=limit,
        offset=offset,
    )


@router.get("/imports/batches/{batch_id}")
def get_import_batch(batch_id: str) -> dict:
    batch = import_review_service.get_batch(batch_id)
    if not batch:
        return {"found": False, "batch_id": batch_id}
    batch["found"] = True
    return batch


@router.get("/imports/batches/{batch_id}/staging")
def get_import_staging_rows(batch_id: str) -> dict:
    return import_review_service.list_staging_rows(batch_id)


@router.get("/imports/batches/{batch_id}/preview")
def preview_import_batch(batch_id: str) -> dict:
    return import_review_service.preview_batch(batch_id)


@router.patch("/imports/staging/{row_id}", response_model=ImportMutationResponse)
def update_import_staging_row(row_id: str, payload: ImportStagingUpdateRequest) -> dict:
    payload = payload_to_dict(payload)
    raw_payload = payload.get("raw_payload", payload.get("event"))
    if not isinstance(raw_payload, dict):
        return {"updated": False, "error": "raw_payload must be an object"}
    return import_review_service.update_staging_row(row_id, raw_payload)


@router.post("/imports/staging/{row_id}/merge", response_model=ImportMutationResponse)
def merge_import_staging_row(row_id: str, payload: ImportStagingMergeRequest) -> dict:
    payload = payload_to_dict(payload)
    return import_review_service.merge_staging_row(
        row_id=row_id,
        strategy=str(payload.get("strategy", "")),
        target_event_id=str(payload.get("target_event_id", "")),
    )


@router.post("/imports/staging/bulk-revalidate", response_model=ImportMutationResponse)
def bulk_revalidate_import_staging(payload: ImportBulkRevalidateRequest) -> dict:
    payload = payload_to_dict(payload)
    row_ids = payload.get("row_ids")
    batch_id = payload.get("batch_id")
    if row_ids is not None and not isinstance(row_ids, list):
        return {"success": False, "error": "row_ids must be a list"}
    return import_review_service.bulk_revalidate_staging(
        row_ids=row_ids,
        batch_id=str(batch_id) if batch_id else None,
    )


@router.post("/imports/batches/{batch_id}/revalidate", response_model=ImportMutationResponse)
def revalidate_import_batch(batch_id: str) -> dict:
    return import_review_service.revalidate_batch(batch_id)


@router.post("/imports/batches/{batch_id}/confirm", response_model=ImportMutationResponse)
def confirm_import_batch(batch_id: str, payload: ImportConfirmRequest | None = None) -> dict:
    payload = payload_to_dict(payload)
    confirmed_by = ""
    if payload:
        confirmed_by = str(payload.get("confirmed_by", ""))
    return import_review_service.confirm_import(batch_id, confirmed_by=confirmed_by)


@router.post("/imports/batches/{batch_id}/reject", response_model=ImportMutationResponse)
def reject_import_batch(batch_id: str, payload: ImportRejectRequest | None = None) -> dict:
    payload = payload_to_dict(payload)
    reason = ""
    if payload:
        reason = str(payload.get("reason", ""))
    return import_review_service.reject_batch(batch_id, reason=reason)
