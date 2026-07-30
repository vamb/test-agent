from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from apps.api.settings import PostgresSettings
from tools.historical.pagination import normalize_pagination


ISSUE_TYPES = [
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

ACTION_STATUSES = {"open", "resolved", "ignored", "snoozed"}
SUPPRESSED_ACTION_STATUSES = {"resolved", "ignored", "snoozed"}


class DataQualityService:
    def __init__(self, postgres_settings: PostgresSettings) -> None:
        self.postgres_settings = postgres_settings

    def summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        total = 0
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                self._ensure_actions_table(cur)
                for issue_type in ISSUE_TYPES:
                    raw_count = self._issue_count(cur, issue_type)
                    suppressed = self._suppressed_issue_count(cur, issue_type)
                    count = max(raw_count - suppressed, 0)
                    severity = self._issue_severity(issue_type)
                    summary[issue_type] = {
                        "count": count,
                        "raw_count": raw_count,
                        "handled_count": suppressed,
                        "severity": severity,
                    }
                    total += count
        return {"total_issues": total, "issues": summary}

    def list_issues(
        self,
        issue_type: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        issue_types = ISSUE_TYPES
        if issue_type:
            if issue_type not in issue_types:
                return {"count": 0, "total": 0, "issues": [], "error": "invalid issue_type"}
            issue_types = [issue_type]

        limit, offset = normalize_pagination(limit, offset)
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                self._ensure_actions_table(cur)
                all_issues: list[dict[str, Any]] = []
                for current_type in issue_types:
                    if severity and self._issue_severity(current_type) != severity:
                        continue
                    all_issues.extend(self._issue_rows(cur, current_type))

                all_issues = self._attach_actions(cur, all_issues)

        visible_issues = [
            issue
            for issue in all_issues
            if issue.get("handling_status", "open") not in SUPPRESSED_ACTION_STATUSES
        ]
        visible_issues.sort(key=lambda item: (item["severity_rank"], item["issue_type"], item["title"]))
        paged = visible_issues[offset : offset + limit]
        for issue in paged:
            issue.pop("severity_rank", None)
        return {
            "count": len(paged),
            "total": len(visible_issues),
            "raw_total": len(all_issues),
            "limit": limit,
            "offset": offset,
            "issues": paged,
        }

    def set_issue_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        issue_type = str(payload.get("issue_type", ""))
        target_type = str(payload.get("target_type", ""))
        target_id = str(payload.get("target_id", ""))
        status = str(payload.get("status", "resolved"))
        if issue_type not in ISSUE_TYPES:
            return {"success": False, "error": "invalid issue_type"}
        if not target_type or not target_id:
            return {"success": False, "error": "target_type and target_id are required"}
        if status not in ACTION_STATUSES:
            return {"success": False, "error": "invalid status"}

        issue_key = self._issue_key(issue_type, target_type, target_id)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                self._ensure_actions_table(cur)
                cur.execute(
                    """
                    INSERT INTO data_quality_issue_actions (
                      issue_key,
                      issue_type,
                      target_type,
                      target_id,
                      status,
                      handled_by,
                      reason,
                      metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (issue_key)
                    DO UPDATE SET
                      status = EXCLUDED.status,
                      handled_by = EXCLUDED.handled_by,
                      reason = EXCLUDED.reason,
                      metadata = EXCLUDED.metadata,
                      updated_at = now()
                    RETURNING
                      id::text,
                      issue_key,
                      issue_type,
                      target_type,
                      target_id,
                      status,
                      handled_by,
                      reason,
                      metadata,
                      created_at,
                      updated_at
                    """,
                    [
                        issue_key,
                        issue_type,
                        target_type,
                        target_id,
                        status,
                        str(payload.get("handled_by", "")),
                        str(payload.get("reason", "")),
                        Jsonb(metadata),
                    ],
                )
                action = dict(cur.fetchone())
            conn.commit()
        return {"success": True, "action": action}

    def _issue_severity(self, issue_type: str) -> str:
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

    def _issue_count(self, cur: psycopg.Cursor, issue_type: str) -> int:
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
                FROM event_relations er
                WHERE er.evidence_source_id IS NULL
                  AND er.relation_type <> 'contemporary'
            """,
            "archived_visible": "SELECT count(*) FROM historical_events WHERE status = 'archived' AND visibility = 'public'",
        }
        cur.execute(count_sql[issue_type])
        return int(cur.fetchone()["count"])

    def _issue_rows(self, cur: psycopg.Cursor, issue_type: str) -> list[dict[str, Any]]:
        severity = self._issue_severity(issue_type)
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
            "issue_key": self._issue_key(issue_type, target_type, target_id),
            "handling_status": "open",
            "title": title,
            "message": message,
            "metadata": metadata,
        }

    def _ensure_actions_table(self, cur: psycopg.Cursor) -> None:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS data_quality_issue_actions (
              id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
              issue_key text NOT NULL UNIQUE,
              issue_type text NOT NULL,
              target_type text NOT NULL,
              target_id text NOT NULL,
              status text NOT NULL DEFAULT 'open',
              handled_by text NOT NULL DEFAULT '',
              reason text NOT NULL DEFAULT '',
              metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now(),
              CONSTRAINT data_quality_issue_actions_status
                CHECK (status IN ('open', 'resolved', 'ignored', 'snoozed'))
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_data_quality_issue_actions_status
              ON data_quality_issue_actions (status)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_data_quality_issue_actions_issue_type
              ON data_quality_issue_actions (issue_type)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_data_quality_issue_actions_target
              ON data_quality_issue_actions (target_type, target_id)
            """
        )

    def _suppressed_issue_count(self, cur: psycopg.Cursor, issue_type: str) -> int:
        cur.execute(
            """
            SELECT count(*) AS count
            FROM data_quality_issue_actions
            WHERE issue_type = %s
              AND status = ANY(%s)
            """,
            [issue_type, list(SUPPRESSED_ACTION_STATUSES)],
        )
        return int(cur.fetchone()["count"])

    def _attach_actions(
        self,
        cur: psycopg.Cursor,
        issues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not issues:
            return issues
        issue_keys = [str(issue["issue_key"]) for issue in issues]
        cur.execute(
            """
            SELECT
              issue_key,
              status,
              handled_by,
              reason,
              updated_at
            FROM data_quality_issue_actions
            WHERE issue_key = ANY(%s)
            """,
            [issue_keys],
        )
        actions = {row["issue_key"]: dict(row) for row in cur.fetchall()}
        for issue in issues:
            action = actions.get(issue["issue_key"])
            if action:
                issue["handling_status"] = action["status"]
                issue["handled_by"] = action["handled_by"]
                issue["handling_reason"] = action["reason"]
                issue["handled_at"] = action["updated_at"]
        return issues

    def _issue_key(self, issue_type: str, target_type: str, target_id: str) -> str:
        return f"{issue_type}:{target_type}:{target_id}"
