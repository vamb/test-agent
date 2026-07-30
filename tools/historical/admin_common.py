from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class AdminChangeRecorder:
    postgres_settings: Any
    security_settings: Any

    def _authorization_error(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if payload.get("admin_token") != self.security_settings.admin_api_token:
            return {"success": False, "error": "admin authorization required"}
        if payload.get("confirmed") is not True:
            return {"success": False, "error": "explicit confirmation required"}
        return None

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
