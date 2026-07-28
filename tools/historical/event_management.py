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

        allowed_fields = {"title", "summary", "confidence", "source_status", "notes"}
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

        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                before = self._get_event_row(cur, event_id)
                if not before:
                    return {"success": False, "error": "event not found", "event_id": event_id}

                set_parts = []
                values: list[Any] = []
                field_to_column = {"source_status": "status"}
                for field, value in updates.items():
                    column = field_to_column.get(field, field)
                    set_parts.append(f"{column} = %s")
                    values.append(value)
                values.append(event_id)
                cur.execute(
                    f"""
                    UPDATE historical_events
                    SET {', '.join(set_parts)}
                    WHERE id = %s
                    """,
                    values,
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
              id::text,
              title,
              start_year,
              end_year,
              summary,
              status::text AS source_status,
              confidence,
              notes
            FROM historical_events
            WHERE id = %s
            """,
            [event_id],
        )
        row = cur.fetchone()
        return dict(row) if row else None

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
