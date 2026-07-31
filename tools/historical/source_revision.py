from __future__ import annotations

from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row

from tools.historical.event_management import EventManagementService


class SourceRevisionToolService:
    def __init__(self, event_management_service: EventManagementService, admin_token: str) -> None:
        self.event_management_service = event_management_service
        self.admin_token = admin_token

    def draft_source_revision(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_id = self._resolve_source_id(payload)
        if not source_id:
            return {
                "success": False,
                "error": "source_id is required, or provide event_id with an optional source_query",
            }
        updates = payload.get("updates", {})
        if not isinstance(updates, dict) or not updates:
            return {"success": False, "error": "updates must be a non-empty object"}

        validation_error = self.event_management_service.source_management_service._validate_source_payload(
            updates,
            partial=True,
        )
        if validation_error:
            return validation_error
        unknown_error = self._unknown_update_fields(updates)
        if unknown_error:
            return unknown_error

        source = self._get_source(source_id)
        if not source:
            return {"success": False, "error": "source not found", "source_id": source_id}

        diff = self._build_diff(source, updates)
        return {
            "success": True,
            "source_id": source_id,
            "event_id": source.get("event_id", ""),
            "source_title": source.get("source_title", ""),
            "reason": str(payload.get("reason", "")),
            "updates": self._json_safe(updates),
            "diff": diff,
            "message": "已生成来源核验/修订草案。确认前不会写入数据库。",
            "next_step": {
                "tool_name": "apply_source_revision",
                "arguments": {
                    "source_id": source_id,
                    "updates": self._json_safe(updates),
                    "reason": str(payload.get("reason", "")),
                    "confirmed_by": str(payload.get("confirmed_by", "agent")),
                },
                "requires_confirmation": True,
            },
        }

    def apply_source_revision(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("confirmed") is not True:
            return {"success": False, "error": "explicit confirmation required"}

        source_id = self._resolve_source_id(payload)
        updates = payload.get("updates", {})
        if not source_id:
            return {"success": False, "error": "source_id is required"}
        if not isinstance(updates, dict) or not updates:
            return {"success": False, "error": "updates must be a non-empty object"}

        before = self._get_source(source_id)
        if not before:
            return {"success": False, "error": "source not found", "source_id": source_id}

        result = self.event_management_service.update_source(
            source_id,
            {
                "admin_token": self.admin_token,
                "confirmed": True,
                "confirmed_by": str(payload.get("confirmed_by", "agent")),
                "reason": str(payload.get("reason", "agent_source_revision")),
                "updates": updates,
            },
        )
        if not result.get("success"):
            return result

        return {
            **result,
            "diff": self._build_diff(before, updates),
            "message": "来源核验/修订已写入数据库，并记录到 event_change_logs。",
        }

    def _resolve_source_id(self, payload: dict[str, Any]) -> str:
        source_id = str(payload.get("source_id", "")).strip()
        if source_id:
            return source_id

        event_id = str(payload.get("event_id", "")).strip()
        if not event_id:
            return ""
        source_query = str(payload.get("source_query", "")).strip().lower()
        detail = self.event_management_service.get_admin_event_detail(event_id)
        sources = list(detail.get("sources") or [])
        if not sources:
            return ""
        if source_query:
            for source in sources:
                haystack = " ".join(
                    str(source.get(field, ""))
                    for field in ("source_title", "citation", "author", "publisher", "url")
                ).lower()
                if source_query in haystack:
                    return str(source.get("id", ""))
        return str(sources[0].get("id", ""))

    def _get_source(self, source_id: str) -> dict[str, Any] | None:
        with psycopg.connect(
            self.event_management_service.postgres_settings.dsn,
            row_factory=dict_row,
        ) as conn:
            with conn.cursor() as cur:
                source = self.event_management_service.source_management_service.get_source_row(
                    cur,
                    source_id,
                )
        return source

    def _unknown_update_fields(self, updates: dict[str, Any]) -> dict[str, Any] | None:
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
        return None

    def _build_diff(self, current_source: dict[str, Any], updates: dict[str, Any]) -> list[dict[str, Any]]:
        diff: list[dict[str, Any]] = []
        for field, after in updates.items():
            before = current_source.get(field)
            if self._json_safe(before) == self._json_safe(after):
                continue
            diff.append(
                {
                    "field": field,
                    "before": self._json_safe(before),
                    "after": self._json_safe(after),
                }
            )
        return diff

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, dict):
            return {key: self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        return value
