from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from apps.api.settings import PostgresSettings, SecuritySettings
from tools.historical.admin_common import AdminChangeRecorder
from tools.historical.entity_resolver import HistoricalEntityResolver
from tools.historical.import_review import ImportReviewService


class EventAdminService(AdminChangeRecorder):
    def __init__(
        self,
        postgres_settings: PostgresSettings,
        security_settings: SecuritySettings,
    ) -> None:
        self.postgres_settings = postgres_settings
        self.security_settings = security_settings
        self.import_review_service = ImportReviewService(postgres_settings)
        self.entity_resolver = HistoricalEntityResolver()

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

        validation_error = self._validate_update_payload(updates)
        if validation_error:
            return validation_error

        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                before = self.get_event_row(cur, event_id)
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
                current_start_year = int(updates.get("start_year", before["start_year"]))
                current_end_year = updates.get("end_year", before["end_year"])
                if current_end_year is not None and current_end_year < current_start_year:
                    return {"success": False, "error": "end_year cannot be earlier than start_year"}

                region_id = before.get("region_id")
                if "region" in updates:
                    region_id = self.entity_resolver.ensure_region(cur, str(updates["region"]))
                if "polity" in updates:
                    polity_name = str(updates["polity"])
                    region_id_for_polity = region_id or before.get("region_id")
                    region_id = region_id_for_polity
                    updates["polity"] = self.entity_resolver.ensure_polity(
                        cur,
                        polity_name,
                        region_id_for_polity,
                        current_start_year,
                        current_end_year,
                    )
                if "modern_country" in updates:
                    updates["modern_country"] = self.entity_resolver.ensure_country(
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
                        category_id = self.entity_resolver.ensure_category(cur, str(category))
                        cur.execute(
                            """
                            INSERT INTO event_categories (event_id, category_id)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            [event_id, category_id],
                        )
                after = self.get_event_row(cur, event_id)
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

    def get_event_row(self, cur: psycopg.Cursor, event_id: str) -> dict[str, Any] | None:
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

    def _validate_update_payload(self, updates: dict[str, Any]) -> dict[str, Any] | None:
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
        return None
