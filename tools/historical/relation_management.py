from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from apps.api.settings import PostgresSettings, SecuritySettings
from tools.historical.admin_common import AdminChangeRecorder
from tools.historical.pagination import normalize_pagination


class RelationManagementService(AdminChangeRecorder):
    def __init__(
        self,
        postgres_settings: PostgresSettings,
        security_settings: SecuritySettings,
    ) -> None:
        self.postgres_settings = postgres_settings
        self.security_settings = security_settings

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
        limit, offset = normalize_pagination(limit, offset)
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
                before = self.get_relation_row(cur, relation_id)
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
                before = self.get_relation_row(cur, relation_id)
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

    def get_relation_row(self, cur: psycopg.Cursor, relation_id: str) -> dict[str, Any] | None:
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
