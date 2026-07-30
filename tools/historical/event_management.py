from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from apps.api.settings import PostgresSettings, SecuritySettings
from tools.historical.data_quality import DataQualityService
from tools.historical.event_admin import EventAdminService
from tools.historical.import_batch_review import ImportBatchReviewService
from tools.historical.import_review import ImportReviewService
from tools.historical.management_overview import ManagementOverviewService
from tools.historical.pagination import normalize_pagination
from tools.historical.relation_management import RelationManagementService
from tools.historical.source_management import SourceManagementService


class EventManagementService:
    def __init__(
        self,
        postgres_settings: PostgresSettings,
        security_settings: SecuritySettings,
    ) -> None:
        self.postgres_settings = postgres_settings
        self.security_settings = security_settings
        self.import_review_service = ImportReviewService(postgres_settings)
        self.data_quality_service = DataQualityService(postgres_settings)
        self.overview_service = ManagementOverviewService(postgres_settings)
        self.import_batch_review_service = ImportBatchReviewService(postgres_settings)
        self.event_admin_service = EventAdminService(
            postgres_settings,
            security_settings,
        )
        self.source_management_service = SourceManagementService(
            postgres_settings,
            security_settings,
        )
        self.relation_management_service = RelationManagementService(
            postgres_settings,
            security_settings,
        )

    def overview(self) -> dict[str, Any]:
        return self.overview_service.overview()

    def list_events(
        self,
        query: str = "",
        start_year: int | None = None,
        end_year: int | None = None,
        regions: list[str] | None = None,
        statuses: list[str] | None = None,
        import_batch_id: str | None = None,
        min_confidence: float | None = None,
        has_sources: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        page: int | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        if query:
            where.append("(e.title ILIKE %s OR e.summary ILIKE %s OR e.location_text ILIKE %s)")
            like = f"%{query}%"
            params.extend([like, like, like])
        if start_year is not None:
            where.append("coalesce(e.end_year, e.start_year) >= %s")
            params.append(start_year)
        if end_year is not None:
            where.append("e.start_year <= %s")
            params.append(end_year)
        if regions:
            where.append("r.name = ANY(%s)")
            params.append(regions)
        if statuses:
            where.append("e.status = ANY(%s)")
            params.append(statuses)
        if import_batch_id:
            where.append("e.import_batch_id = %s")
            params.append(import_batch_id)
        if min_confidence is not None:
            where.append("e.confidence >= %s")
            params.append(min_confidence)
        if has_sources is True:
            where.append("EXISTS (SELECT 1 FROM event_sources s WHERE s.event_id = e.id)")
        elif has_sources is False:
            where.append("NOT EXISTS (SELECT 1 FROM event_sources s WHERE s.event_id = e.id)")

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        if page is not None or page_size is not None:
            current_page = max(1, int(page or 1))
            limit, _ = normalize_pagination(int(page_size or limit), 0)
            offset = (current_page - 1) * limit
        else:
            limit, offset = normalize_pagination(limit, offset)
            current_page = offset // limit + 1

        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT count(*) AS total
                    FROM historical_events e
                    LEFT JOIN regions r ON r.id = e.region_id
                    LEFT JOIN polities p ON p.id = e.polity_id
                    {where_sql}
                    """,
                    params,
                )
                total = int(cur.fetchone()["total"])
                cur.execute(
                    f"""
                    SELECT
                      e.id::text,
                      e.title,
                      e.start_year,
                      e.end_year,
                      coalesce(r.name, '') AS region,
                      coalesce(p.name, '') AS polity,
                      e.summary,
                      e.status::text AS source_status,
                      e.confidence,
                      e.import_batch_id::text,
                      count(s.id) AS source_count,
                      e.created_at,
                      e.updated_at
                    FROM historical_events e
                    LEFT JOIN regions r ON r.id = e.region_id
                    LEFT JOIN polities p ON p.id = e.polity_id
                    LEFT JOIN event_sources s ON s.event_id = e.id
                    {where_sql}
                    GROUP BY e.id, r.name, p.name
                    ORDER BY e.updated_at DESC, e.start_year DESC
                    LIMIT %s OFFSET %s
                    """,
                    [*params, limit, offset],
                )
                rows = [dict(row) for row in cur.fetchall()]

        return {
            "count": len(rows),
            "total": total,
            "limit": limit,
            "offset": offset,
            "page": current_page,
            "page_size": limit,
            "events": rows,
        }

    def get_event_changes(
        self,
        event_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit, offset = normalize_pagination(limit, offset)
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS total
                    FROM event_change_logs
                    WHERE event_id = %s
                    """,
                    [event_id],
                )
                total = int(cur.fetchone()["total"])
                cur.execute(
                    """
                    SELECT
                      id::text,
                      event_id::text,
                      action,
                      changed_by,
                      before_payload,
                      after_payload,
                      reason,
                      created_at
                    FROM event_change_logs
                    WHERE event_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    [event_id, limit, offset],
                )
                rows = [dict(row) for row in cur.fetchall()]
        return {"event_id": event_id, "count": len(rows), "total": total, "changes": rows}

    def data_quality_summary(self) -> dict[str, Any]:
        return self.data_quality_service.summary()

    def list_data_quality_issues(
        self,
        issue_type: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self.data_quality_service.list_issues(
            issue_type=issue_type,
            severity=severity,
            limit=limit,
            offset=offset,
        )

    def set_data_quality_issue_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.data_quality_service.set_issue_action(payload)

    def dictionaries(self) -> dict[str, Any]:
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, name, description
                    FROM regions
                    ORDER BY name
                    """
                )
                regions = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """
                    SELECT
                      p.id::text,
                      p.name,
                      p.polity_type,
                      p.start_year,
                      p.end_year,
                      coalesce(r.name, '') AS region
                    FROM polities p
                    LEFT JOIN regions r ON r.id = p.region_id
                    ORDER BY p.name, p.start_year
                    """
                )
                polities = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """
                    SELECT id::text, name, description
                    FROM categories
                    ORDER BY name
                    """
                )
                categories = [dict(row) for row in cur.fetchall()]
        return {
            "regions": regions,
            "polities": polities,
            "categories": categories,
            "event_statuses": ["draft", "reviewing", "verified", "disputed", "archived"],
            "source_types": [
                "book",
                "paper",
                "primary_source",
                "encyclopedia",
                "website",
                "dataset",
                "note",
            ],
            "relation_types": [
                "cause",
                "effect",
                "contemporary",
                "influence",
                "trade_link",
                "conflict_link",
                "migration_link",
                "religion_link",
                "technology_link",
                "uncertain",
            ],
            "time_precisions": [
                "day",
                "month",
                "year",
                "decade",
                "century",
                "range",
                "approximate",
                "unknown",
            ],
        }

    def get_admin_event_detail(self, event_id: str) -> dict[str, Any]:
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                event = self.event_admin_service.get_event_row(cur, event_id)
                if not event:
                    return {"found": False, "event_id": event_id}
                sources = self.source_management_service.get_event_sources(cur, event_id)
                relations = self.list_relations(event_id=event_id, limit=100)["relations"]
                changes = self.get_event_changes(event_id, limit=20)["changes"]
                import_batch = None
                cur.execute(
                    """
                    SELECT
                      b.id::text,
                      b.filename,
                      b.status::text,
                      b.created_by,
                      b.created_at,
                      b.imported_at
                    FROM historical_events e
                    JOIN import_batches b ON b.id = e.import_batch_id
                    WHERE e.id = %s
                    """,
                    [event_id],
                )
                batch_row = cur.fetchone()
                if batch_row:
                    import_batch = dict(batch_row)
                embedding_status = {
                    "vector_column_available": self.overview_service.column_exists(
                        cur,
                        "historical_events",
                        "embedding",
                    ),
                    "has_embedding": False,
                }
                if embedding_status["vector_column_available"]:
                    cur.execute(
                        "SELECT embedding IS NOT NULL AS has_embedding FROM historical_events WHERE id = %s",
                        [event_id],
                    )
                    embedding_status["has_embedding"] = bool(cur.fetchone()["has_embedding"])
        return {
            "found": True,
            "event": event,
            "sources": sources,
            "relations": relations,
            "changes": changes,
            "import_batch": import_batch,
            "embedding": embedding_status,
        }

    def import_batch_review(self, batch_id: str) -> dict[str, Any]:
        return self.import_batch_review_service.review(batch_id)

    def import_batch_report(self, batch_id: str) -> dict[str, Any]:
        return self.import_batch_review_service.report(batch_id)

    def create_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.event_admin_service.create_event(payload)

    def update_event(self, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.event_admin_service.update_event(event_id, payload)

    def bulk_update_events(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.event_admin_service.bulk_update_events(payload)

    def archive_event(self, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.event_admin_service.archive_event(event_id, payload)

    def mark_event_disputed(self, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.event_admin_service.mark_event_disputed(event_id, payload)

    def verify_source(self, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.source_management_service.verify_source(source_id, payload)

    def bulk_verify_sources(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.source_management_service.bulk_verify_sources(payload)

    def add_source(self, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.source_management_service.add_source(event_id, payload)

    def update_source(self, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.source_management_service.update_source(source_id, payload)

    def delete_source(self, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.source_management_service.delete_source(source_id, payload)

    def list_relations(
        self,
        event_id: str | None = None,
        relation_types: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self.relation_management_service.list_relations(
            event_id=event_id,
            relation_types=relation_types,
            limit=limit,
            offset=offset,
        )

    def create_relation(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.relation_management_service.create_relation(payload)

    def update_relation(self, relation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.relation_management_service.update_relation(relation_id, payload)

    def delete_relation(self, relation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.relation_management_service.delete_relation(relation_id, payload)
