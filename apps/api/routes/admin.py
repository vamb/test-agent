from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.api.dependencies import event_management_service


router = APIRouter()


@router.get("/admin/overview")
def admin_overview() -> dict:
    return event_management_service.overview()


@router.get("/admin/data-quality/summary")
def admin_data_quality_summary() -> dict:
    return event_management_service.data_quality_summary()


@router.get("/admin/data-quality/issues")
def admin_list_data_quality_issues(
    issue_type: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return event_management_service.list_data_quality_issues(
        issue_type=issue_type,
        severity=severity,
        limit=limit,
        offset=offset,
    )


@router.get("/admin/dictionaries")
def admin_dictionaries() -> dict:
    return event_management_service.dictionaries()


@router.get("/admin/import-batches/{batch_id}/review")
def admin_import_batch_review(batch_id: str) -> dict:
    return event_management_service.import_batch_review(batch_id)


@router.get("/admin/events")
def admin_list_events(
    query: str = "",
    start_year: int | None = None,
    end_year: int | None = None,
    regions: Annotated[list[str] | None, Query()] = None,
    statuses: Annotated[list[str] | None, Query()] = None,
    import_batch_id: str | None = None,
    min_confidence: float | None = None,
    has_sources: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return event_management_service.list_events(
        query=query,
        start_year=start_year,
        end_year=end_year,
        regions=regions,
        statuses=statuses,
        import_batch_id=import_batch_id,
        min_confidence=min_confidence,
        has_sources=has_sources,
        limit=limit,
        offset=offset,
    )


@router.post("/admin/events")
def admin_create_event(payload: dict) -> dict:
    return event_management_service.create_event(payload)


@router.post("/admin/events/bulk-update")
def admin_bulk_update_events(payload: dict) -> dict:
    return event_management_service.bulk_update_events(payload)


@router.get("/admin/events/{event_id}/changes")
def admin_get_event_changes(
    event_id: str,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return event_management_service.get_event_changes(event_id, limit=limit, offset=offset)


@router.get("/admin/events/{event_id}")
def admin_get_event_detail(event_id: str) -> dict:
    return event_management_service.get_admin_event_detail(event_id)


@router.patch("/admin/events/{event_id}")
def admin_update_event(event_id: str, payload: dict) -> dict:
    return event_management_service.update_event(event_id, payload)


@router.post("/admin/events/{event_id}/archive")
def admin_archive_event(event_id: str, payload: dict) -> dict:
    return event_management_service.archive_event(event_id, payload)


@router.post("/admin/events/{event_id}/dispute")
def admin_dispute_event(event_id: str, payload: dict) -> dict:
    return event_management_service.mark_event_disputed(event_id, payload)


@router.post("/admin/sources/{source_id}/verify")
def admin_verify_source(source_id: str, payload: dict) -> dict:
    return event_management_service.verify_source(source_id, payload)


@router.post("/admin/sources/bulk-verify")
def admin_bulk_verify_sources(payload: dict) -> dict:
    return event_management_service.bulk_verify_sources(payload)


@router.post("/admin/events/{event_id}/sources")
def admin_add_source(event_id: str, payload: dict) -> dict:
    return event_management_service.add_source(event_id, payload)


@router.patch("/admin/sources/{source_id}")
def admin_update_source(source_id: str, payload: dict) -> dict:
    return event_management_service.update_source(source_id, payload)


@router.delete("/admin/sources/{source_id}")
def admin_delete_source(source_id: str, payload: dict) -> dict:
    return event_management_service.delete_source(source_id, payload)


@router.get("/admin/relations")
def admin_list_relations(
    event_id: str | None = None,
    relation_types: Annotated[list[str] | None, Query()] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return event_management_service.list_relations(
        event_id=event_id,
        relation_types=relation_types,
        limit=limit,
        offset=offset,
    )


@router.post("/admin/relations")
def admin_create_relation(payload: dict) -> dict:
    return event_management_service.create_relation(payload)


@router.patch("/admin/relations/{relation_id}")
def admin_update_relation(relation_id: str, payload: dict) -> dict:
    return event_management_service.update_relation(relation_id, payload)


@router.delete("/admin/relations/{relation_id}")
def admin_delete_relation(relation_id: str, payload: dict) -> dict:
    return event_management_service.delete_relation(relation_id, payload)
