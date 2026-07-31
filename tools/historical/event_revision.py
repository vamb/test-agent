from __future__ import annotations

from decimal import Decimal
from typing import Any

from tools.historical.event_management import EventManagementService


class EventRevisionToolService:
    def __init__(self, event_management_service: EventManagementService, admin_token: str) -> None:
        self.event_management_service = event_management_service
        self.admin_token = admin_token

    def draft_event_revision(self, payload: dict[str, Any]) -> dict[str, Any]:
        event_id = str(payload.get("event_id", "")).strip()
        updates = payload.get("updates", {})
        if not event_id:
            return {"success": False, "error": "event_id is required"}
        if not isinstance(updates, dict) or not updates:
            return {"success": False, "error": "updates must be a non-empty object"}

        validation_error = self.event_management_service.event_admin_service._validate_update_payload(updates)
        if validation_error:
            return validation_error

        detail = self.event_management_service.get_admin_event_detail(event_id)
        if not detail.get("found"):
            return {"success": False, "error": "event not found", "event_id": event_id}

        event = dict(detail["event"])
        diff = self._build_diff(event, updates)
        return {
            "success": True,
            "event_id": event_id,
            "event_title": event.get("title", ""),
            "reason": str(payload.get("reason", "")),
            "updates": self._json_safe(updates),
            "diff": diff,
            "message": "已生成事件修订草案。确认前不会写入数据库。",
            "next_step": {
                "tool_name": "apply_event_revision",
                "arguments": {
                    "event_id": event_id,
                    "updates": self._json_safe(updates),
                    "reason": str(payload.get("reason", "")),
                    "confirmed_by": str(payload.get("confirmed_by", "agent")),
                },
                "requires_confirmation": True,
            },
        }

    def apply_event_revision(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("confirmed") is not True:
            return {"success": False, "error": "explicit confirmation required"}

        event_id = str(payload.get("event_id", "")).strip()
        updates = payload.get("updates", {})
        if not event_id:
            return {"success": False, "error": "event_id is required"}
        if not isinstance(updates, dict) or not updates:
            return {"success": False, "error": "updates must be a non-empty object"}

        before = self.event_management_service.get_admin_event_detail(event_id)
        if not before.get("found"):
            return {"success": False, "error": "event not found", "event_id": event_id}

        result = self.event_management_service.update_event(
            event_id,
            {
                "admin_token": self.admin_token,
                "confirmed": True,
                "confirmed_by": str(payload.get("confirmed_by", "agent")),
                "reason": str(payload.get("reason", "agent_event_revision")),
                "updates": updates,
            },
        )
        if not result.get("success"):
            return result

        return {
            **result,
            "diff": self._build_diff(dict(before["event"]), updates),
            "message": "事件修订已写入数据库，并记录到 event_change_logs。",
        }

    def _build_diff(self, current_event: dict[str, Any], updates: dict[str, Any]) -> list[dict[str, Any]]:
        diff: list[dict[str, Any]] = []
        for field, after in updates.items():
            before = current_event.get(field)
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
