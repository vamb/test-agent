from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from apps.api.settings import PostgresSettings, SecuritySettings
from tools.historical.admin_common import AdminChangeRecorder


class SourceManagementService(AdminChangeRecorder):
    def __init__(
        self,
        postgres_settings: PostgresSettings,
        security_settings: SecuritySettings,
    ) -> None:
        self.postgres_settings = postgres_settings
        self.security_settings = security_settings

    def verify_source(self, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        auth_error = self._authorization_error(payload)
        if auth_error:
            return auth_error

        reliability = payload.get("reliability", 0.8)
        if not isinstance(reliability, (int, float)) or not 0 <= reliability <= 1:
            return {"success": False, "error": "reliability must be between 0 and 1"}

        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                before = self.get_source_row(cur, source_id)
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
                    before_payload=before,
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
                if not self._event_exists(cur, event_id):
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
                before = self.get_source_row(cur, source_id)
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
                before = self.get_source_row(cur, source_id)
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

    def get_event_sources(self, cur: psycopg.Cursor, event_id: str) -> list[dict[str, Any]]:
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

    def get_source_row(self, cur: psycopg.Cursor, source_id: str) -> dict[str, Any] | None:
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

    def _event_exists(self, cur: psycopg.Cursor, event_id: str) -> bool:
        cur.execute("SELECT EXISTS (SELECT 1 FROM historical_events WHERE id = %s) AS exists", [event_id])
        return bool(cur.fetchone()["exists"])

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
