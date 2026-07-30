from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from apps.api.settings import PostgresSettings
from tools.historical.admin_common import AdminChangeRecorder


HANDLED_QUALITY_STATUSES = {"resolved", "ignored", "snoozed"}


class ImportBatchReviewService(AdminChangeRecorder):
    def __init__(self, postgres_settings: PostgresSettings) -> None:
        self.postgres_settings = postgres_settings

    def review(self, batch_id: str) -> dict[str, Any]:
        batch, events, duplicate_candidates = self._batch_events_and_duplicates(batch_id)
        if not batch:
            return {"found": False, "batch_id": batch_id}

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

    def report(self, batch_id: str) -> dict[str, Any]:
        batch, events, duplicate_candidates = self._batch_events_and_duplicates(batch_id)
        if not batch:
            return {"found": False, "batch_id": batch_id}

        issue_keys = self._batch_issue_keys(events, duplicate_candidates)
        action_statuses = self._action_statuses(issue_keys)
        handled_count = sum(
            1 for key in issue_keys if action_statuses.get(key) in HANDLED_QUALITY_STATUSES
        )
        issue_count = len(issue_keys)
        open_count = max(issue_count - handled_count, 0)
        handled_rate = handled_count / issue_count if issue_count else 1.0

        return {
            "found": True,
            "batch": self._json_safe(dict(batch)),
            "totals": {
                "staging_rows": int(batch["total_rows"]),
                "valid_rows": int(batch["valid_rows"]),
                "error_rows": int(batch["error_rows"]),
                "imported_events": len(events),
                "quality_issue_count": issue_count,
                "quality_open_count": open_count,
                "quality_handled_count": handled_count,
                "quality_handled_rate": handled_rate,
            },
            "quality": self._quality_breakdown(events, duplicate_candidates, action_statuses),
            "distributions": {
                "event_statuses": self._count_by(events, "source_status"),
                "regions": self._count_by(events, "region"),
                "year_buckets": self._year_buckets(events),
                "confidence_bands": self._confidence_bands(events),
                "source_reliability_bands": self._source_reliability_bands(events),
            },
            "top_open_items": self._top_open_items(events, duplicate_candidates, action_statuses),
        }

    def _batch_events_and_duplicates(
        self,
        batch_id: str,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
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
                    return None, [], []

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

        return dict(batch), events, duplicate_candidates

    def _batch_issue_keys(
        self,
        events: list[dict[str, Any]],
        duplicate_candidates: list[dict[str, Any]],
    ) -> list[str]:
        keys: set[str] = set()
        duplicate_seed_ids = {str(candidate["seed_event_id"]) for candidate in duplicate_candidates}
        for event in events:
            event_id = str(event["id"])
            if float(event["confidence"]) < 0.7:
                keys.add(self._issue_key("low_confidence", "event", event_id))
            if int(event["source_count"]) == 0:
                keys.add(self._issue_key("missing_source", "event", event_id))
            if int(event["source_count"]) > 0 and int(event["reliable_source_count"]) == 0:
                keys.add(self._issue_key("verified_weak_source", "event", event_id))
            if not str(event["summary"]).strip():
                keys.add(self._issue_key("empty_summary", "event", event_id))
            if int(event["causes_count"]) == 0:
                keys.add(self._issue_key("empty_causes", "event", event_id))
            if int(event["effects_count"]) == 0:
                keys.add(self._issue_key("empty_effects", "event", event_id))
            if event_id in duplicate_seed_ids:
                keys.add(self._issue_key("duplicate_title", "event", event_id))
        return sorted(keys)

    def _action_statuses(self, issue_keys: list[str]) -> dict[str, str]:
        if not issue_keys:
            return {}
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                self._ensure_actions_table(cur)
                cur.execute(
                    """
                    SELECT issue_key, status
                    FROM data_quality_issue_actions
                    WHERE issue_key = ANY(%s)
                    """,
                    [issue_keys],
                )
                return {str(row["issue_key"]): str(row["status"]) for row in cur.fetchall()}

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

    def _quality_breakdown(
        self,
        events: list[dict[str, Any]],
        duplicate_candidates: list[dict[str, Any]],
        action_statuses: dict[str, str],
    ) -> dict[str, dict[str, Any]]:
        duplicate_seed_ids = {str(candidate["seed_event_id"]) for candidate in duplicate_candidates}
        definitions = {
            "low_confidence": lambda event: float(event["confidence"]) < 0.7,
            "missing_source": lambda event: int(event["source_count"]) == 0,
            "weak_source": lambda event: int(event["source_count"]) > 0
            and int(event["reliable_source_count"]) == 0,
            "duplicate_title": lambda event: str(event["id"]) in duplicate_seed_ids,
            "empty_summary": lambda event: not str(event["summary"]).strip(),
            "empty_causes": lambda event: int(event["causes_count"]) == 0,
            "empty_effects": lambda event: int(event["effects_count"]) == 0,
        }
        breakdown: dict[str, dict[str, Any]] = {}
        for issue_type, matches in definitions.items():
            matched_events = [event for event in events if matches(event)]
            handled = 0
            for event in matched_events:
                key_type = "verified_weak_source" if issue_type == "weak_source" else issue_type
                key = self._issue_key(key_type, "event", str(event["id"]))
                if action_statuses.get(key) in HANDLED_QUALITY_STATUSES:
                    handled += 1
            count = len(matched_events)
            breakdown[issue_type] = {
                "count": count,
                "open_count": max(count - handled, 0),
                "handled_count": handled,
                "handled_rate": handled / count if count else 1.0,
            }
        return breakdown

    def _top_open_items(
        self,
        events: list[dict[str, Any]],
        duplicate_candidates: list[dict[str, Any]],
        action_statuses: dict[str, str],
    ) -> list[dict[str, Any]]:
        duplicate_seed_ids = {str(candidate["seed_event_id"]) for candidate in duplicate_candidates}
        items: list[dict[str, Any]] = []
        for event in events:
            event_id = str(event["id"])
            checks = [
                ("low_confidence", float(event["confidence"]) < 0.7, "置信度低于 0.7"),
                ("missing_source", int(event["source_count"]) == 0, "事件没有来源"),
                (
                    "verified_weak_source",
                    int(event["source_count"]) > 0 and int(event["reliable_source_count"]) == 0,
                    "缺少可靠度 >= 0.7 的来源",
                ),
                ("duplicate_title", event_id in duplicate_seed_ids, "同标题同年份重复候选"),
                ("empty_summary", not str(event["summary"]).strip(), "摘要为空"),
                ("empty_causes", int(event["causes_count"]) == 0, "缺少结构化原因"),
                ("empty_effects", int(event["effects_count"]) == 0, "缺少结构化影响"),
            ]
            for issue_type, matched, message in checks:
                if not matched:
                    continue
                key = self._issue_key(issue_type, "event", event_id)
                if action_statuses.get(key) in HANDLED_QUALITY_STATUSES:
                    continue
                items.append(
                    {
                        "issue_type": issue_type,
                        "target_id": event_id,
                        "title": event["title"],
                        "start_year": event["start_year"],
                        "region": event["region"],
                        "message": message,
                    }
                )
        return items[:8]

    def _count_by(self, events: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for event in events:
            key = str(event.get(field) or "-")
            counts[key] = counts.get(key, 0) + 1
        return [
            {"label": label, "count": count}
            for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def _year_buckets(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[str, int] = {}
        for event in events:
            year = int(event["start_year"])
            bucket_start = year - year % 50
            label = f"{bucket_start}-{bucket_start + 49}"
            buckets[label] = buckets.get(label, 0) + 1
        return [{"label": label, "count": buckets[label]} for label in sorted(buckets)]

    def _confidence_bands(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        bands = {"<0.5": 0, "0.5-0.69": 0, "0.7-0.84": 0, ">=0.85": 0}
        for event in events:
            confidence = float(event["confidence"])
            if confidence < 0.5:
                bands["<0.5"] += 1
            elif confidence < 0.7:
                bands["0.5-0.69"] += 1
            elif confidence < 0.85:
                bands["0.7-0.84"] += 1
            else:
                bands[">=0.85"] += 1
        return [{"label": label, "count": count} for label, count in bands.items()]

    def _source_reliability_bands(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        bands = {"no source": 0, "<0.7": 0, "0.7-0.84": 0, ">=0.85": 0}
        for event in events:
            reliability = event.get("max_source_reliability")
            if reliability is None:
                bands["no source"] += 1
                continue
            score = float(reliability)
            if score < 0.7:
                bands["<0.7"] += 1
            elif score < 0.85:
                bands["0.7-0.84"] += 1
            else:
                bands[">=0.85"] += 1
        return [{"label": label, "count": count} for label, count in bands.items()]

    def _issue_key(self, issue_type: str, target_type: str, target_id: str) -> str:
        return f"{issue_type}:{target_type}:{target_id}"
