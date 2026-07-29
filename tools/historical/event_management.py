from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from apps.api.settings import PostgresSettings, SecuritySettings
from tools.historical.import_review import ImportReviewService


class EventManagementService:
    def __init__(
        self,
        postgres_settings: PostgresSettings,
        security_settings: SecuritySettings,
    ) -> None:
        self.postgres_settings = postgres_settings
        self.security_settings = security_settings
        self.import_review_service = ImportReviewService(postgres_settings)

    def overview(self) -> dict[str, Any]:
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                event_embedding_expr = (
                    "count(*) FILTER (WHERE embedding IS NOT NULL)"
                    if self._column_exists(cur, "historical_events", "embedding")
                    else "0"
                )
                cur.execute(
                    f"""
                    SELECT
                      count(*) AS total_events,
                      count(*) FILTER (WHERE status = 'draft') AS draft_events,
                      count(*) FILTER (WHERE status = 'reviewing') AS reviewing_events,
                      count(*) FILTER (WHERE status = 'verified') AS verified_events,
                      count(*) FILTER (WHERE status = 'disputed') AS disputed_events,
                      count(*) FILTER (WHERE status = 'archived') AS archived_events,
                      count(*) FILTER (WHERE confidence < 0.7) AS low_confidence_events,
                      count(*) FILTER (
                        WHERE NOT EXISTS (
                          SELECT 1 FROM event_sources s WHERE s.event_id = historical_events.id
                        )
                      ) AS events_without_sources,
                      {event_embedding_expr} AS events_with_embedding
                    FROM historical_events
                    """
                )
                event_stats = dict(cur.fetchone())
                cur.execute(
                    """
                    SELECT
                      count(*) AS total_batches,
                      count(*) FILTER (WHERE status = 'pending') AS pending_batches,
                      count(*) FILTER (WHERE status = 'validated') AS validated_batches,
                      count(*) FILTER (WHERE status = 'imported') AS imported_batches,
                      count(*) FILTER (WHERE status = 'rejected') AS rejected_batches
                    FROM import_batches
                    """
                )
                import_stats = dict(cur.fetchone())
                cur.execute(
                    """
                    SELECT
                      count(*) AS total_sources,
                      count(*) FILTER (WHERE reliability >= 0.8) AS reliable_sources,
                      count(*) FILTER (WHERE citation = '' AND excerpt = '') AS weak_sources
                    FROM event_sources
                    """
                )
                source_stats = dict(cur.fetchone())
                knowledge_stats = self._knowledge_overview(cur)

        total_events = int(event_stats["total_events"] or 0)
        events_with_embedding = int(event_stats["events_with_embedding"] or 0)
        event_stats["embedding_coverage"] = (
            events_with_embedding / total_events if total_events else 0
        )
        return {
            "events": event_stats,
            "imports": import_stats,
            "sources": source_stats,
            "knowledge": knowledge_stats,
        }

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
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

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

        return {"count": len(rows), "total": total, "limit": limit, "offset": offset, "events": rows}

    def get_event_changes(
        self,
        event_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
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
        issue_types = [
            "missing_source",
            "low_confidence",
            "verified_weak_source",
            "duplicate_event",
            "duplicate_title",
            "empty_summary",
            "empty_causes",
            "empty_effects",
            "relation_missing_evidence",
            "archived_visible",
        ]
        summary: dict[str, Any] = {}
        total = 0
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                for issue_type in issue_types:
                    count = self._quality_issue_count(cur, issue_type)
                    severity = self._quality_issue_severity(issue_type)
                    summary[issue_type] = {"count": count, "severity": severity}
                    total += count
        return {"total_issues": total, "issues": summary}

    def list_data_quality_issues(
        self,
        issue_type: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        issue_types = [
            "missing_source",
            "low_confidence",
            "verified_weak_source",
            "duplicate_event",
            "duplicate_title",
            "empty_summary",
            "empty_causes",
            "empty_effects",
            "relation_missing_evidence",
            "archived_visible",
        ]
        if issue_type:
            if issue_type not in issue_types:
                return {"count": 0, "total": 0, "issues": [], "error": "invalid issue_type"}
            issue_types = [issue_type]

        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                all_issues: list[dict[str, Any]] = []
                for current_type in issue_types:
                    if severity and self._quality_issue_severity(current_type) != severity:
                        continue
                    all_issues.extend(self._quality_issue_rows(cur, current_type))

        all_issues.sort(key=lambda item: (item["severity_rank"], item["issue_type"], item["title"]))
        paged = all_issues[offset : offset + limit]
        for issue in paged:
            issue.pop("severity_rank", None)
        return {
            "count": len(paged),
            "total": len(all_issues),
            "limit": limit,
            "offset": offset,
            "issues": paged,
        }

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
                event = self._get_event_row(cur, event_id)
                if not event:
                    return {"found": False, "event_id": event_id}
                sources = self._get_event_sources(cur, event_id)
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
                    "vector_column_available": self._column_exists(cur, "historical_events", "embedding"),
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
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      id::text,
                      filename,
                      source_note,
                      status::text,
                      total_rows,
                      valid_rows,
                      error_rows,
                      created_by,
                      created_at,
                      imported_at
                    FROM import_batches
                    WHERE id = %s
                    """,
                    [batch_id],
                )
                batch = cur.fetchone()
                if not batch:
                    return {"found": False, "batch_id": batch_id}

                cur.execute(
                    """
                    SELECT
                      e.id::text,
                      e.title,
                      e.start_year,
                      e.end_year,
                      coalesce(r.name, '') AS region,
                      coalesce(p.name, '') AS polity,
                      e.status::text AS source_status,
                      e.confidence,
                      e.summary,
                      coalesce(array_length(e.causes, 1), 0) AS causes_count,
                      coalesce(array_length(e.effects, 1), 0) AS effects_count,
                      count(s.id) AS source_count,
                      count(s.id) FILTER (WHERE s.reliability >= 0.7) AS reliable_source_count,
                      min(s.reliability) AS min_source_reliability,
                      max(s.reliability) AS max_source_reliability
                    FROM historical_events e
                    LEFT JOIN regions r ON r.id = e.region_id
                    LEFT JOIN polities p ON p.id = e.polity_id
                    LEFT JOIN event_sources s ON s.event_id = e.id
                    WHERE e.import_batch_id = %s
                    GROUP BY e.id, r.name, p.name
                    ORDER BY e.start_year, e.title
                    """,
                    [batch_id],
                )
                events = [self._json_safe(dict(row)) for row in cur.fetchall()]

                event_ids = [event["id"] for event in events]
                duplicate_candidates: list[dict[str, Any]] = []
                if event_ids:
                    cur.execute(
                        """
                        SELECT
                          seed.id::text AS seed_event_id,
                          seed.title,
                          seed.start_year,
                          other.id::text AS candidate_event_id,
                          coalesce(r.name, '') AS candidate_region,
                          coalesce(p.name, '') AS candidate_polity,
                          other.status::text AS candidate_status,
                          other.import_batch_id::text AS candidate_import_batch_id
                        FROM historical_events seed
                        JOIN historical_events other
                          ON other.title = seed.title
                         AND other.start_year = seed.start_year
                         AND other.id <> seed.id
                        LEFT JOIN regions r ON r.id = other.region_id
                        LEFT JOIN polities p ON p.id = other.polity_id
                        WHERE seed.id = ANY(%s::uuid[])
                        ORDER BY seed.title, other.updated_at DESC
                        """,
                        [event_ids],
                    )
                    duplicate_candidates = [self._json_safe(dict(row)) for row in cur.fetchall()]

        low_confidence = [event for event in events if float(event["confidence"]) < 0.7]
        weak_sources = [
            event
            for event in events
            if int(event["source_count"]) == 0 or int(event["reliable_source_count"]) == 0
        ]
        empty_structure = [
            event
            for event in events
            if not str(event["summary"]).strip()
            or int(event["causes_count"]) == 0
            or int(event["effects_count"]) == 0
        ]
        return {
            "found": True,
            "batch": self._json_safe(dict(batch)),
            "count": len(events),
            "events": events,
            "review": {
                "low_confidence_count": len(low_confidence),
                "weak_source_count": len(weak_sources),
                "duplicate_candidate_count": len(duplicate_candidates),
                "empty_structure_count": len(empty_structure),
                "ready_for_manual_review": len(events) > 0,
            },
            "issues": {
                "low_confidence": low_confidence,
                "weak_sources": weak_sources,
                "duplicate_candidates": duplicate_candidates,
                "empty_structure": empty_structure,
            },
        }

    def create_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        auth_error = self._authorization_error(payload)
        if auth_error:
            return auth_error

        event_payload = payload.get("event")
        if not isinstance(event_payload, dict):
            return {"success": False, "error": "event must be an object"}

        batch = self.import_review_service.create_batch(
            filename=str(payload.get("filename", "event-management-create.json")),
            source_note="event_management_create",
            created_by=str(payload.get("confirmed_by", "")),
            events=[event_payload],
        )
        if batch["error_rows"] > 0:
            return {
                "success": False,
                "error": "event validation failed",
                "batch_id": batch["id"],
            }

        result = self.import_review_service.confirm_import(
            batch["id"],
            confirmed_by=str(payload.get("confirmed_by", "")),
        )
        if result.get("imported"):
            self._record_change(
                event_id=result["event_ids"][0],
                action="create_event",
                changed_by=str(payload.get("confirmed_by", "")),
                before_payload=None,
                after_payload=event_payload,
                reason=str(payload.get("reason", "")),
            )
        return {"success": bool(result.get("imported")), **result}

    def update_event(self, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        auth_error = self._authorization_error(payload)
        if auth_error:
            return auth_error

        updates = payload.get("updates", {})
        if not isinstance(updates, dict) or not updates:
            return {"success": False, "error": "updates must be a non-empty object"}

        allowed_fields = {
            "title",
            "summary",
            "confidence",
            "source_status",
            "notes",
            "start_year",
            "end_year",
            "start_date_text",
            "end_date_text",
            "time_precision",
            "is_approximate",
            "location_text",
            "causes",
            "effects",
            "importance_score",
            "region",
            "polity",
            "modern_country",
            "category",
        }
        unknown_fields = sorted(set(updates) - allowed_fields)
        if unknown_fields:
            return {
                "success": False,
                "error": f"unsupported update fields: {', '.join(unknown_fields)}",
            }

        if "confidence" in updates:
            confidence = updates["confidence"]
            if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                return {"success": False, "error": "confidence must be between 0 and 1"}

        if "source_status" in updates and updates["source_status"] not in {
            "draft",
            "reviewing",
            "verified",
            "disputed",
            "archived",
        }:
            return {"success": False, "error": "invalid source_status"}
        if "time_precision" in updates and updates["time_precision"] not in {
            "day",
            "month",
            "year",
            "decade",
            "century",
            "range",
            "approximate",
            "unknown",
        }:
            return {"success": False, "error": "invalid time_precision"}
        if "importance_score" in updates:
            importance = updates["importance_score"]
            if not isinstance(importance, (int, float)) or importance < 0:
                return {"success": False, "error": "importance_score must be >= 0"}
        if "start_year" in updates or "end_year" in updates:
            start_year = updates.get("start_year")
            end_year = updates.get("end_year")
            if start_year is not None and not isinstance(start_year, int):
                return {"success": False, "error": "start_year must be an integer"}
            if end_year is not None and not isinstance(end_year, int):
                return {"success": False, "error": "end_year must be an integer"}
        for array_field in ("causes", "effects", "category"):
            if array_field in updates and not isinstance(updates[array_field], list):
                return {"success": False, "error": f"{array_field} must be a list"}

        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                before = self._get_event_row(cur, event_id)
                if not before:
                    return {"success": False, "error": "event not found", "event_id": event_id}

                set_parts = []
                values: list[Any] = []
                field_to_column = {
                    "source_status": "status",
                    "region": "region_id",
                    "polity": "polity_id",
                    "modern_country": "primary_modern_country_id",
                }
                relation_updates = {"region", "polity", "modern_country", "category"}
                current_start_year = int(updates.get("start_year", before["start_year"]))
                current_end_year = updates.get("end_year", before["end_year"])
                if current_end_year is not None and current_end_year < current_start_year:
                    return {"success": False, "error": "end_year cannot be earlier than start_year"}

                region_id = before.get("region_id")
                if "region" in updates:
                    region_id = self._ensure_region(cur, str(updates["region"]))
                if "polity" in updates:
                    polity_name = str(updates["polity"])
                    region_id_for_polity = region_id or before.get("region_id")
                    region_id = region_id_for_polity
                    updates["polity"] = self._ensure_polity(
                        cur,
                        polity_name,
                        region_id_for_polity,
                        current_start_year,
                        current_end_year,
                    )
                if "modern_country" in updates:
                    updates["modern_country"] = self._ensure_country(
                        cur,
                        str(updates["modern_country"]),
                        region_id or before.get("region_id"),
                    )
                if "region" in updates:
                    updates["region"] = region_id

                for field, value in updates.items():
                    if field == "category":
                        continue
                    column = field_to_column.get(field, field)
                    set_parts.append(f"{column} = %s")
                    values.append(value)
                if set_parts:
                    values.append(event_id)
                    cur.execute(
                        f"""
                        UPDATE historical_events
                        SET {', '.join(set_parts)}
                        WHERE id = %s
                        """,
                        values,
                    )
                if "category" in updates:
                    cur.execute("DELETE FROM event_categories WHERE event_id = %s", [event_id])
                    for category in updates["category"]:
                        category_id = self._ensure_category(cur, str(category))
                        cur.execute(
                            """
                            INSERT INTO event_categories (event_id, category_id)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            [event_id, category_id],
                        )
                after = self._get_event_row(cur, event_id)
                self._record_change_with_cursor(
                    cur=cur,
                    event_id=event_id,
                    action="update_event",
                    changed_by=str(payload.get("confirmed_by", "")),
                    before_payload=before,
                    after_payload=after,
                    reason=str(payload.get("reason", "")),
                )
            conn.commit()

        return {"success": True, "event_id": event_id, "event": after}

    def bulk_update_events(self, payload: dict[str, Any]) -> dict[str, Any]:
        auth_error = self._authorization_error(payload)
        if auth_error:
            return auth_error
        event_ids = payload.get("event_ids", [])
        updates = payload.get("updates", {})
        if not isinstance(event_ids, list) or not event_ids:
            return {"success": False, "error": "event_ids must be a non-empty list"}
        if not isinstance(updates, dict) or not updates:
            return {"success": False, "error": "updates must be a non-empty object"}

        results: list[dict[str, Any]] = []
        succeeded = 0
        failed = 0
        for event_id in event_ids:
            result = self.update_event(
                str(event_id),
                {
                    **payload,
                    "updates": updates,
                    "reason": payload.get("reason", "bulk_update_events"),
                },
            )
            results.append({"event_id": str(event_id), **result})
            if result.get("success"):
                succeeded += 1
            else:
                failed += 1
        return {
            "success": failed == 0,
            "updated": succeeded,
            "failed": failed,
            "results": results,
        }

    def archive_event(self, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload = {**payload, "updates": {"source_status": "archived", "notes": payload.get("reason", "")}}
        result = self.update_event(event_id, payload)
        if result.get("success"):
            result["action"] = "archive_event"
        return result

    def mark_event_disputed(self, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        reason = str(payload.get("reason", "marked disputed"))
        payload = {**payload, "updates": {"source_status": "disputed", "notes": reason}}
        result = self.update_event(event_id, payload)
        if result.get("success"):
            result["action"] = "mark_event_disputed"
        return result

    def verify_source(self, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        auth_error = self._authorization_error(payload)
        if auth_error:
            return auth_error

        reliability = payload.get("reliability", 0.8)
        if not isinstance(reliability, (int, float)) or not 0 <= reliability <= 1:
            return {"success": False, "error": "reliability must be between 0 and 1"}

        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      id::text,
                      event_id::text,
                      source_title,
                      reliability,
                      is_primary
                    FROM event_sources
                    WHERE id = %s
                    """,
                    [source_id],
                )
                before = cur.fetchone()
                if not before:
                    return {"success": False, "error": "source not found", "source_id": source_id}

                cur.execute(
                    """
                    UPDATE event_sources
                    SET reliability = greatest(reliability, %s),
                        is_primary = true
                    WHERE id = %s
                    RETURNING
                      id::text,
                      event_id::text,
                      source_title,
                      reliability,
                      is_primary
                    """,
                    [float(reliability), source_id],
                )
                after = dict(cur.fetchone())
                self._record_change_with_cursor(
                    cur=cur,
                    event_id=after["event_id"],
                    action="verify_source",
                    changed_by=str(payload.get("confirmed_by", "")),
                    before_payload=dict(before),
                    after_payload=after,
                    reason=str(payload.get("reason", "")),
                )
            conn.commit()

        return {"success": True, "source": after}

    def bulk_verify_sources(self, payload: dict[str, Any]) -> dict[str, Any]:
        auth_error = self._authorization_error(payload)
        if auth_error:
            return auth_error
        source_ids = payload.get("source_ids", [])
        if not isinstance(source_ids, list) or not source_ids:
            return {"success": False, "error": "source_ids must be a non-empty list"}

        results: list[dict[str, Any]] = []
        succeeded = 0
        failed = 0
        for source_id in source_ids:
            result = self.verify_source(str(source_id), payload)
            results.append({"source_id": str(source_id), **result})
            if result.get("success"):
                succeeded += 1
            else:
                failed += 1
        return {
            "success": failed == 0,
            "verified": succeeded,
            "failed": failed,
            "results": results,
        }

    def add_source(self, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        auth_error = self._authorization_error(payload)
        if auth_error:
            return auth_error
        source = payload.get("source")
        if not isinstance(source, dict):
            return {"success": False, "error": "source must be an object"}
        validation_error = self._validate_source_payload(source, partial=False)
        if validation_error:
            return validation_error

        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                before = self._get_event_row(cur, event_id)
                if not before:
                    return {"success": False, "error": "event not found", "event_id": event_id}
                cur.execute(
                    """
                    INSERT INTO event_sources (
                      event_id,
                      source_title,
                      source_type,
                      author,
                      publisher,
                      published_year,
                      url,
                      citation,
                      excerpt,
                      page_ref,
                      reliability,
                      is_primary
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING
                      id::text,
                      event_id::text,
                      source_title,
                      source_type::text,
                      author,
                      publisher,
                      published_year,
                      url,
                      citation,
                      excerpt,
                      page_ref,
                      reliability,
                      is_primary
                    """,
                    [
                        event_id,
                        source["source_title"],
                        source["source_type"],
                        source.get("author", ""),
                        source.get("publisher", ""),
                        source.get("published_year"),
                        source.get("url", ""),
                        source.get("citation", ""),
                        source.get("excerpt", ""),
                        source.get("page_ref", ""),
                        float(source.get("reliability", 0.5)),
                        bool(source.get("is_primary", False)),
                    ],
                )
                after = dict(cur.fetchone())
                self._record_change_with_cursor(
                    cur,
                    event_id,
                    "add_source",
                    str(payload.get("confirmed_by", "")),
                    None,
                    after,
                    str(payload.get("reason", "")),
                )
            conn.commit()
        return {"success": True, "source": after}

    def update_source(self, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        auth_error = self._authorization_error(payload)
        if auth_error:
            return auth_error
        updates = payload.get("updates", {})
        if not isinstance(updates, dict) or not updates:
            return {"success": False, "error": "updates must be a non-empty object"}
        validation_error = self._validate_source_payload(updates, partial=True)
        if validation_error:
            return validation_error

        allowed_fields = {
            "source_title",
            "source_type",
            "author",
            "publisher",
            "published_year",
            "url",
            "citation",
            "excerpt",
            "page_ref",
            "reliability",
            "is_primary",
        }
        unknown_fields = sorted(set(updates) - allowed_fields)
        if unknown_fields:
            return {"success": False, "error": f"unsupported update fields: {', '.join(unknown_fields)}"}

        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                before = self._get_source_row(cur, source_id)
                if not before:
                    return {"success": False, "error": "source not found", "source_id": source_id}
                set_parts = [f"{field} = %s" for field in updates]
                values = list(updates.values())
                values.append(source_id)
                cur.execute(
                    f"""
                    UPDATE event_sources
                    SET {', '.join(set_parts)}
                    WHERE id = %s
                    RETURNING
                      id::text,
                      event_id::text,
                      source_title,
                      source_type::text,
                      author,
                      publisher,
                      published_year,
                      url,
                      citation,
                      excerpt,
                      page_ref,
                      reliability,
                      is_primary
                    """,
                    values,
                )
                after = dict(cur.fetchone())
                self._record_change_with_cursor(
                    cur,
                    after["event_id"],
                    "update_source",
                    str(payload.get("confirmed_by", "")),
                    before,
                    after,
                    str(payload.get("reason", "")),
                )
            conn.commit()
        return {"success": True, "source": after}

    def delete_source(self, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        auth_error = self._authorization_error(payload)
        if auth_error:
            return auth_error
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                before = self._get_source_row(cur, source_id)
                if not before:
                    return {"success": False, "error": "source not found", "source_id": source_id}
                cur.execute("DELETE FROM event_sources WHERE id = %s", [source_id])
                self._record_change_with_cursor(
                    cur,
                    before["event_id"],
                    "delete_source",
                    str(payload.get("confirmed_by", "")),
                    before,
                    None,
                    str(payload.get("reason", "")),
                )
            conn.commit()
        return {"success": True, "source_id": source_id, "deleted": True}

    def list_relations(
        self,
        event_id: str | None = None,
        relation_types: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        if event_id:
            where.append("(er.source_event_id = %s::uuid OR er.target_event_id = %s::uuid)")
            params.extend([event_id, event_id])
        if relation_types:
            where.append("er.relation_type = ANY(%s)")
            params.append(relation_types)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT count(*) AS total FROM event_relations er {where_sql}", params)
                total = int(cur.fetchone()["total"])
                cur.execute(
                    f"""
                    SELECT
                      er.id::text,
                      er.source_event_id::text,
                      er.target_event_id::text,
                      er.relation_type::text,
                      er.explanation,
                      er.confidence,
                      er.evidence_source_id::text,
                      er.is_directional,
                      er.created_at,
                      source_event.title AS source_title,
                      target_event.title AS target_title
                    FROM event_relations er
                    JOIN historical_events source_event ON source_event.id = er.source_event_id
                    JOIN historical_events target_event ON target_event.id = er.target_event_id
                    {where_sql}
                    ORDER BY er.created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    [*params, limit, offset],
                )
                rows = [dict(row) for row in cur.fetchall()]
        return {"count": len(rows), "total": total, "relations": rows, "limit": limit, "offset": offset}

    def create_relation(self, payload: dict[str, Any]) -> dict[str, Any]:
        auth_error = self._authorization_error(payload)
        if auth_error:
            return auth_error
        relation = payload.get("relation")
        if not isinstance(relation, dict):
            return {"success": False, "error": "relation must be an object"}
        validation_error = self._validate_relation_payload(relation, partial=False)
        if validation_error:
            return validation_error

        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO event_relations (
                      source_event_id,
                      target_event_id,
                      relation_type,
                      explanation,
                      confidence,
                      evidence_source_id,
                      is_directional
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_event_id, target_event_id, relation_type)
                    DO UPDATE SET
                      explanation = EXCLUDED.explanation,
                      confidence = EXCLUDED.confidence,
                      evidence_source_id = EXCLUDED.evidence_source_id,
                      is_directional = EXCLUDED.is_directional
                    RETURNING
                      id::text,
                      source_event_id::text,
                      target_event_id::text,
                      relation_type::text,
                      explanation,
                      confidence,
                      evidence_source_id::text,
                      is_directional,
                      created_at
                    """,
                    [
                        relation["source_event_id"],
                        relation["target_event_id"],
                        relation["relation_type"],
                        relation.get("explanation", ""),
                        float(relation.get("confidence", 0.5)),
                        relation.get("evidence_source_id") or None,
                        bool(relation.get("is_directional", True)),
                    ],
                )
                after = dict(cur.fetchone())
                self._record_change_with_cursor(
                    cur,
                    after["source_event_id"],
                    "create_relation",
                    str(payload.get("confirmed_by", "")),
                    None,
                    after,
                    str(payload.get("reason", "")),
                )
            conn.commit()
        return {"success": True, "relation": after}

    def update_relation(self, relation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        auth_error = self._authorization_error(payload)
        if auth_error:
            return auth_error
        updates = payload.get("updates", {})
        if not isinstance(updates, dict) or not updates:
            return {"success": False, "error": "updates must be a non-empty object"}
        validation_error = self._validate_relation_payload(updates, partial=True)
        if validation_error:
            return validation_error
        allowed_fields = {"relation_type", "explanation", "confidence", "evidence_source_id", "is_directional"}
        unknown_fields = sorted(set(updates) - allowed_fields)
        if unknown_fields:
            return {"success": False, "error": f"unsupported update fields: {', '.join(unknown_fields)}"}

        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                before = self._get_relation_row(cur, relation_id)
                if not before:
                    return {"success": False, "error": "relation not found", "relation_id": relation_id}
                set_parts = [f"{field} = %s" for field in updates]
                values = list(updates.values())
                values.append(relation_id)
                cur.execute(
                    f"""
                    UPDATE event_relations
                    SET {', '.join(set_parts)}
                    WHERE id = %s
                    RETURNING
                      id::text,
                      source_event_id::text,
                      target_event_id::text,
                      relation_type::text,
                      explanation,
                      confidence,
                      evidence_source_id::text,
                      is_directional,
                      created_at
                    """,
                    values,
                )
                after = dict(cur.fetchone())
                self._record_change_with_cursor(
                    cur,
                    after["source_event_id"],
                    "update_relation",
                    str(payload.get("confirmed_by", "")),
                    before,
                    after,
                    str(payload.get("reason", "")),
                )
            conn.commit()
        return {"success": True, "relation": after}

    def delete_relation(self, relation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        auth_error = self._authorization_error(payload)
        if auth_error:
            return auth_error
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                before = self._get_relation_row(cur, relation_id)
                if not before:
                    return {"success": False, "error": "relation not found", "relation_id": relation_id}
                cur.execute("DELETE FROM event_relations WHERE id = %s", [relation_id])
                self._record_change_with_cursor(
                    cur,
                    before["source_event_id"],
                    "delete_relation",
                    str(payload.get("confirmed_by", "")),
                    before,
                    None,
                    str(payload.get("reason", "")),
                )
            conn.commit()
        return {"success": True, "relation_id": relation_id, "deleted": True}

    def _authorization_error(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if payload.get("admin_token") != self.security_settings.admin_api_token:
            return {"success": False, "error": "admin authorization required"}
        if payload.get("confirmed") is not True:
            return {"success": False, "error": "explicit confirmation required"}
        return None

    def _get_event_row(self, cur: psycopg.Cursor, event_id: str) -> dict[str, Any] | None:
        cur.execute(
            """
            SELECT
              e.id::text,
              e.title,
              e.start_year,
              e.end_year,
              e.start_date_text,
              e.end_date_text,
              e.time_precision::text,
              e.is_approximate,
              e.region_id::text,
              e.polity_id::text,
              e.primary_modern_country_id::text,
              coalesce(r.name, '') AS region,
              coalesce(p.name, '') AS polity,
              coalesce(mc.name, '') AS modern_country,
              e.location_text,
              e.summary,
              e.causes,
              e.effects,
              e.status::text AS source_status,
              e.confidence,
              e.importance_score,
              e.notes,
              coalesce(array_agg(DISTINCT c.name) FILTER (WHERE c.name IS NOT NULL), '{}') AS category
            FROM historical_events e
            LEFT JOIN regions r ON r.id = e.region_id
            LEFT JOIN polities p ON p.id = e.polity_id
            LEFT JOIN modern_countries mc ON mc.id = e.primary_modern_country_id
            LEFT JOIN event_categories ec ON ec.event_id = e.id
            LEFT JOIN categories c ON c.id = ec.category_id
            WHERE e.id = %s
            GROUP BY e.id, r.name, p.name, mc.name
            """,
            [event_id],
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def _ensure_region(self, cur: psycopg.Cursor, name: str) -> str | None:
        if not name:
            return None
        cur.execute(
            """
            INSERT INTO regions (name)
            VALUES (%s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id::text
            """,
            [name],
        )
        return cur.fetchone()["id"]

    def _ensure_country(
        self,
        cur: psycopg.Cursor,
        name: str,
        region_id: str | None,
    ) -> str | None:
        if not name:
            return None
        first_name = name.split("、", maxsplit=1)[0]
        cur.execute(
            """
            INSERT INTO modern_countries (name, region_id)
            VALUES (%s, %s)
            ON CONFLICT (name) DO UPDATE SET
              region_id = coalesce(modern_countries.region_id, EXCLUDED.region_id)
            RETURNING id::text
            """,
            [first_name, region_id],
        )
        return cur.fetchone()["id"]

    def _ensure_polity(
        self,
        cur: psycopg.Cursor,
        name: str,
        region_id: str | None,
        start_year: int,
        end_year: int | None,
    ) -> str | None:
        if not name:
            return None
        cur.execute("SELECT id::text FROM polities WHERE name = %s", [name])
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute(
            """
            INSERT INTO polities (name, region_id, start_year, end_year)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (name, start_year, end_year) DO UPDATE SET
              region_id = EXCLUDED.region_id
            RETURNING id::text
            """,
            [name, region_id, start_year, end_year],
        )
        return cur.fetchone()["id"]

    def _ensure_category(self, cur: psycopg.Cursor, name: str) -> str:
        cur.execute(
            """
            INSERT INTO categories (name)
            VALUES (%s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id::text
            """,
            [name],
        )
        return cur.fetchone()["id"]

    def _get_source_row(self, cur: psycopg.Cursor, source_id: str) -> dict[str, Any] | None:
        cur.execute(
            """
            SELECT
              id::text,
              event_id::text,
              source_title,
              source_type::text,
              author,
              publisher,
              published_year,
              url,
              citation,
              excerpt,
              page_ref,
              reliability,
              is_primary
            FROM event_sources
            WHERE id = %s
            """,
            [source_id],
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def _get_event_sources(self, cur: psycopg.Cursor, event_id: str) -> list[dict[str, Any]]:
        cur.execute(
            """
            SELECT
              id::text,
              event_id::text,
              source_title,
              source_type::text,
              author,
              publisher,
              published_year,
              url,
              citation,
              excerpt,
              page_ref,
              reliability,
              is_primary,
              created_at
            FROM event_sources
            WHERE event_id = %s
            ORDER BY reliability DESC, source_title
            """,
            [event_id],
        )
        return [dict(row) for row in cur.fetchall()]

    def _get_relation_row(self, cur: psycopg.Cursor, relation_id: str) -> dict[str, Any] | None:
        cur.execute(
            """
            SELECT
              id::text,
              source_event_id::text,
              target_event_id::text,
              relation_type::text,
              explanation,
              confidence,
              evidence_source_id::text,
              is_directional,
              created_at
            FROM event_relations
            WHERE id = %s
            """,
            [relation_id],
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def _validate_source_payload(
        self,
        source: dict[str, Any],
        partial: bool,
    ) -> dict[str, Any] | None:
        if not partial:
            if not source.get("source_title"):
                return {"success": False, "error": "source_title is required"}
            if not source.get("source_type"):
                return {"success": False, "error": "source_type is required"}
        if "source_type" in source and source["source_type"] not in {
            "book",
            "paper",
            "primary_source",
            "encyclopedia",
            "website",
            "dataset",
            "note",
        }:
            return {"success": False, "error": "invalid source_type"}
        if "reliability" in source:
            reliability = source["reliability"]
            if not isinstance(reliability, (int, float)) or not 0 <= reliability <= 1:
                return {"success": False, "error": "reliability must be between 0 and 1"}
        return None

    def _quality_issue_severity(self, issue_type: str) -> str:
        high = {
            "missing_source",
            "verified_weak_source",
            "duplicate_event",
            "duplicate_title",
            "relation_missing_evidence",
        }
        medium = {"low_confidence", "empty_summary", "archived_visible"}
        if issue_type in high:
            return "high"
        if issue_type in medium:
            return "medium"
        return "low"

    def _quality_issue_count(self, cur: psycopg.Cursor, issue_type: str) -> int:
        count_sql = {
            "missing_source": """
                SELECT count(*)
                FROM historical_events e
                WHERE NOT EXISTS (SELECT 1 FROM event_sources s WHERE s.event_id = e.id)
            """,
            "low_confidence": "SELECT count(*) FROM historical_events WHERE confidence < 0.7",
            "verified_weak_source": """
                SELECT count(*)
                FROM historical_events e
                WHERE e.status = 'verified'
                  AND NOT EXISTS (
                    SELECT 1 FROM event_sources s
                    WHERE s.event_id = e.id
                      AND s.reliability >= 0.7
                  )
            """,
            "duplicate_event": """
                SELECT count(*)
                FROM (
                  SELECT e.title, e.start_year, e.region_id, e.polity_id
                  FROM historical_events e
                  GROUP BY e.title, e.start_year, e.region_id, e.polity_id
                  HAVING count(*) > 1
                ) duplicates
            """,
            "duplicate_title": """
                SELECT count(*)
                FROM (
                  SELECT e.title, e.start_year
                  FROM historical_events e
                  GROUP BY e.title, e.start_year
                  HAVING count(*) > 1
                ) duplicates
            """,
            "empty_summary": "SELECT count(*) FROM historical_events WHERE trim(summary) = ''",
            "empty_causes": "SELECT count(*) FROM historical_events WHERE coalesce(array_length(causes, 1), 0) = 0",
            "empty_effects": "SELECT count(*) FROM historical_events WHERE coalesce(array_length(effects, 1), 0) = 0",
            "relation_missing_evidence": """
                SELECT count(*)
                FROM event_relations
                WHERE evidence_source_id IS NULL
                  AND relation_type <> 'contemporary'
            """,
            "archived_visible": "SELECT count(*) FROM historical_events WHERE status = 'archived' AND visibility = 'public'",
        }
        cur.execute(count_sql[issue_type])
        return int(cur.fetchone()["count"])

    def _quality_issue_rows(self, cur: psycopg.Cursor, issue_type: str) -> list[dict[str, Any]]:
        severity = self._quality_issue_severity(issue_type)
        severity_rank = {"high": 0, "medium": 1, "low": 2}[severity]
        if issue_type == "duplicate_event":
            cur.execute(
                """
                SELECT
                  min(e.id::text) AS target_id,
                  e.title,
                  e.start_year,
                  coalesce(r.name, '') AS region,
                  coalesce(p.name, '') AS polity,
                  count(*) AS duplicate_count
                FROM historical_events e
                LEFT JOIN regions r ON r.id = e.region_id
                LEFT JOIN polities p ON p.id = e.polity_id
                GROUP BY e.title, e.start_year, e.region_id, e.polity_id, r.name, p.name
                HAVING count(*) > 1
                ORDER BY count(*) DESC, e.title
                LIMIT 200
                """
            )
            return [
                self._issue_row(
                    issue_type=issue_type,
                    severity=severity,
                    severity_rank=severity_rank,
                    target_type="event",
                    target_id=row["target_id"],
                    title=row["title"],
                    message=f"同标题、同年份、同地区/政权的事件有 {row['duplicate_count']} 条。",
                    metadata=dict(row),
                )
                for row in cur.fetchall()
            ]

        if issue_type == "duplicate_title":
            cur.execute(
                """
                SELECT
                  min(e.id::text) AS target_id,
                  e.title,
                  e.start_year,
                  count(*) AS duplicate_count,
                  array_agg(e.id::text ORDER BY e.updated_at DESC) AS event_ids,
                  array_agg(coalesce(r.name, '') ORDER BY e.updated_at DESC) AS regions,
                  array_agg(coalesce(p.name, '') ORDER BY e.updated_at DESC) AS polities
                FROM historical_events e
                LEFT JOIN regions r ON r.id = e.region_id
                LEFT JOIN polities p ON p.id = e.polity_id
                GROUP BY e.title, e.start_year
                HAVING count(*) > 1
                ORDER BY count(*) DESC, e.title
                LIMIT 200
                """
            )
            return [
                self._issue_row(
                    issue_type=issue_type,
                    severity=severity,
                    severity_rank=severity_rank,
                    target_type="event",
                    target_id=row["target_id"],
                    title=row["title"],
                    message=f"同标题、同年份的事件有 {row['duplicate_count']} 条，需人工判断是重复还是不同视角记录。",
                    metadata=dict(row),
                )
                for row in cur.fetchall()
            ]

        if issue_type == "relation_missing_evidence":
            cur.execute(
                """
                SELECT
                  er.id::text AS target_id,
                  er.relation_type::text,
                  er.explanation,
                  er.source_event_id::text,
                  er.target_event_id::text,
                  source_event.title AS source_title,
                  target_event.title AS target_title
                FROM event_relations er
                JOIN historical_events source_event ON source_event.id = er.source_event_id
                JOIN historical_events target_event ON target_event.id = er.target_event_id
                WHERE er.evidence_source_id IS NULL
                  AND er.relation_type <> 'contemporary'
                ORDER BY er.created_at DESC
                LIMIT 200
                """
            )
            return [
                self._issue_row(
                    issue_type=issue_type,
                    severity=severity,
                    severity_rank=severity_rank,
                    target_type="relation",
                    target_id=row["target_id"],
                    title=f"{row['source_title']} -> {row['target_title']}",
                    message=f"{row['relation_type']} 关系缺少证据来源。",
                    metadata=dict(row),
                )
                for row in cur.fetchall()
            ]

        where_sql = {
            "missing_source": "NOT EXISTS (SELECT 1 FROM event_sources s WHERE s.event_id = e.id)",
            "low_confidence": "e.confidence < 0.7",
            "verified_weak_source": """
                e.status = 'verified'
                AND NOT EXISTS (
                  SELECT 1 FROM event_sources s
                  WHERE s.event_id = e.id
                    AND s.reliability >= 0.7
                )
            """,
            "empty_summary": "trim(e.summary) = ''",
            "empty_causes": "coalesce(array_length(e.causes, 1), 0) = 0",
            "empty_effects": "coalesce(array_length(e.effects, 1), 0) = 0",
            "archived_visible": "e.status = 'archived' AND e.visibility = 'public'",
        }[issue_type]
        messages = {
            "missing_source": "事件没有绑定任何来源。",
            "low_confidence": "事件置信度低于 0.7。",
            "verified_weak_source": "已验证事件缺少可靠度 >= 0.7 的来源。",
            "empty_summary": "事件摘要为空。",
            "empty_causes": "事件缺少结构化原因。",
            "empty_effects": "事件缺少结构化影响。",
            "archived_visible": "已归档事件仍是 public visibility。",
        }
        cur.execute(
            f"""
            SELECT
              e.id::text AS target_id,
              e.title,
              e.start_year,
              e.end_year,
              e.status::text AS source_status,
              e.confidence,
              coalesce(r.name, '') AS region,
              coalesce(p.name, '') AS polity
            FROM historical_events e
            LEFT JOIN regions r ON r.id = e.region_id
            LEFT JOIN polities p ON p.id = e.polity_id
            WHERE {where_sql}
            ORDER BY e.updated_at DESC
            LIMIT 200
            """
        )
        return [
            self._issue_row(
                issue_type=issue_type,
                severity=severity,
                severity_rank=severity_rank,
                target_type="event",
                target_id=row["target_id"],
                title=row["title"],
                message=messages[issue_type],
                metadata=dict(row),
            )
            for row in cur.fetchall()
        ]

    def _issue_row(
        self,
        issue_type: str,
        severity: str,
        severity_rank: int,
        target_type: str,
        target_id: str,
        title: str,
        message: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "issue_type": issue_type,
            "severity": severity,
            "severity_rank": severity_rank,
            "target_type": target_type,
            "target_id": target_id,
            "title": title,
            "message": message,
            "metadata": metadata,
        }

    def _validate_relation_payload(
        self,
        relation: dict[str, Any],
        partial: bool,
    ) -> dict[str, Any] | None:
        if not partial:
            for field in ("source_event_id", "target_event_id", "relation_type"):
                if not relation.get(field):
                    return {"success": False, "error": f"{field} is required"}
        if "relation_type" in relation and relation["relation_type"] not in {
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
        }:
            return {"success": False, "error": "invalid relation_type"}
        if "confidence" in relation:
            confidence = relation["confidence"]
            if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                return {"success": False, "error": "confidence must be between 0 and 1"}
        return None

    def _knowledge_overview(self, cur: psycopg.Cursor) -> dict[str, Any]:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_name = 'knowledge_documents'
            ) AS exists
            """
        )
        if not cur.fetchone()["exists"]:
            return {
                "total_documents": 0,
                "active_documents": 0,
                "total_chunks": 0,
                "chunks_with_embedding": 0,
                "embedding_coverage": 0,
            }
        cur.execute(
            """
            SELECT
              (SELECT count(*) FROM knowledge_documents) AS total_documents,
              (SELECT count(*) FROM knowledge_documents WHERE status = 'active') AS active_documents,
              (SELECT count(*) FROM knowledge_chunks) AS total_chunks,
              (SELECT count(*) FROM knowledge_chunks WHERE embedding IS NOT NULL) AS chunks_with_embedding
            """
        )
        stats = dict(cur.fetchone())
        total_chunks = int(stats["total_chunks"] or 0)
        chunks_with_embedding = int(stats["chunks_with_embedding"] or 0)
        stats["embedding_coverage"] = chunks_with_embedding / total_chunks if total_chunks else 0
        return stats

    def _column_exists(self, cur: psycopg.Cursor, table_name: str, column_name: str) -> bool:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_name = %s
                AND column_name = %s
            ) AS exists
            """,
            [table_name, column_name],
        )
        return bool(cur.fetchone()["exists"])

    def _record_change(
        self,
        event_id: str,
        action: str,
        changed_by: str,
        before_payload: dict[str, Any] | None,
        after_payload: dict[str, Any] | None,
        reason: str,
    ) -> None:
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                self._record_change_with_cursor(
                    cur=cur,
                    event_id=event_id,
                    action=action,
                    changed_by=changed_by,
                    before_payload=before_payload,
                    after_payload=after_payload,
                    reason=reason,
                )
            conn.commit()

    def _record_change_with_cursor(
        self,
        cur: psycopg.Cursor,
        event_id: str,
        action: str,
        changed_by: str,
        before_payload: dict[str, Any] | None,
        after_payload: dict[str, Any] | None,
        reason: str,
    ) -> None:
        cur.execute(
            """
            INSERT INTO event_change_logs (
              event_id,
              action,
              changed_by,
              before_payload,
              after_payload,
              reason
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                event_id,
                action,
                changed_by,
                Jsonb(self._json_safe(before_payload)) if before_payload is not None else None,
                Jsonb(self._json_safe(after_payload)) if after_payload is not None else None,
                reason,
            ],
        )

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        return value
