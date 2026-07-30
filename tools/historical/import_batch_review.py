from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from apps.api.settings import PostgresSettings
from tools.historical.admin_common import AdminChangeRecorder


class ImportBatchReviewService(AdminChangeRecorder):
    def __init__(self, postgres_settings: PostgresSettings) -> None:
        self.postgres_settings = postgres_settings

    def review(self, batch_id: str) -> dict[str, Any]:
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
