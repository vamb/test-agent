from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from apps.api.settings import PostgresSettings
from tools.historical.models import HistoricalEvent


@dataclass(frozen=True)
class ValidationResult:
    normalized_payload: dict[str, Any] | None
    errors: list[str]


class ImportReviewService:
    def __init__(self, settings: PostgresSettings) -> None:
        self.settings = settings

    def create_batch(
        self,
        filename: str,
        events: list[dict[str, Any]],
        source_note: str = "",
        created_by: str = "",
    ) -> dict[str, Any]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO import_batches (
                      filename,
                      source_note,
                      created_by,
                      total_rows
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING id::text
                    """,
                    [filename, source_note, created_by, len(events)],
                )
                batch_id = cur.fetchone()["id"]

                valid_rows = 0
                error_rows = 0
                for row_number, raw_event in enumerate(events, start=1):
                    validation = self.validate_event_payload(raw_event)
                    row_status = "validated" if not validation.errors else "rejected"
                    if validation.errors:
                        error_rows += 1
                    else:
                        valid_rows += 1

                    cur.execute(
                        """
                        INSERT INTO import_event_staging (
                          import_batch_id,
                          row_number,
                          raw_payload,
                          normalized_payload,
                          validation_errors,
                          status
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        [
                            batch_id,
                            row_number,
                            Jsonb(raw_event),
                            Jsonb(validation.normalized_payload)
                            if validation.normalized_payload is not None
                            else None,
                            validation.errors,
                            row_status,
                        ],
                    )

                batch_status = "validated" if error_rows == 0 else "pending"
                cur.execute(
                    """
                    UPDATE import_batches
                    SET status = %s,
                        valid_rows = %s,
                        error_rows = %s,
                        validated_at = now()
                    WHERE id = %s
                    """,
                    [batch_status, valid_rows, error_rows, batch_id],
                )
            conn.commit()

        batch = self.get_batch(batch_id)
        assert batch is not None
        return batch

    def validate_event_payload(self, raw_event: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        try:
            event = HistoricalEvent.model_validate(raw_event)
        except Exception as exc:
            return ValidationResult(normalized_payload=None, errors=[str(exc)])

        if not event.sources:
            errors.append("event must include at least one source")
        if not event.category:
            errors.append("event should include at least one category")
        if event.source_status == "verified" and event.confidence < 0.7:
            errors.append("verified events should have confidence >= 0.7")

        normalized_payload = event.model_dump(mode="json") if not errors else None
        return ValidationResult(normalized_payload=normalized_payload, errors=errors)

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
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
                      validated_at,
                      imported_at
                    FROM import_batches
                    WHERE id = %s
                    """,
                    [batch_id],
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def list_staging_rows(self, batch_id: str) -> dict[str, Any]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      id::text,
                      row_number,
                      raw_payload,
                      normalized_payload,
                      validation_errors,
                      status::text,
                      created_at
                    FROM import_event_staging
                    WHERE import_batch_id = %s
                    ORDER BY row_number
                    """,
                    [batch_id],
                )
                rows = [dict(row) for row in cur.fetchall()]
        return {"batch_id": batch_id, "count": len(rows), "rows": rows}

    def confirm_import(self, batch_id: str, confirmed_by: str = "") -> dict[str, Any]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                batch = self._get_batch_for_update(cur, batch_id)
                if not batch:
                    return {"batch_id": batch_id, "imported": False, "error": "batch not found"}
                if batch["error_rows"] > 0:
                    return {
                        "batch_id": batch_id,
                        "imported": False,
                        "error": "batch has validation errors",
                    }
                if batch["status"] == "imported":
                    return {"batch_id": batch_id, "imported": False, "error": "already imported"}

                cur.execute(
                    """
                    SELECT normalized_payload
                    FROM import_event_staging
                    WHERE import_batch_id = %s
                      AND status = 'validated'
                    ORDER BY row_number
                    """,
                    [batch_id],
                )
                imported_ids: list[str] = []
                for row in cur.fetchall():
                    event = HistoricalEvent.model_validate(row["normalized_payload"])
                    imported_ids.append(self._insert_event(cur, event, batch_id))

                cur.execute(
                    """
                    UPDATE import_event_staging
                    SET status = 'imported'
                    WHERE import_batch_id = %s
                      AND status = 'validated'
                    """,
                    [batch_id],
                )
                note = f"confirmed_by={confirmed_by}" if confirmed_by else ""
                cur.execute(
                    """
                    UPDATE import_batches
                    SET status = 'imported',
                        source_note = trim(source_note || ' ' || %s),
                        imported_at = now()
                    WHERE id = %s
                    """,
                    [note, batch_id],
                )
            conn.commit()

        return {
            "batch_id": batch_id,
            "imported": True,
            "imported_count": len(imported_ids),
            "event_ids": imported_ids,
        }

    def reject_batch(self, batch_id: str, reason: str = "") -> dict[str, Any]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE import_batches
                    SET status = 'rejected',
                        source_note = trim(source_note || ' ' || %s)
                    WHERE id = %s
                      AND status <> 'imported'
                    RETURNING id::text
                    """,
                    [f"rejected_reason={reason}" if reason else "", batch_id],
                )
                rejected = cur.fetchone() is not None
            conn.commit()
        return {"batch_id": batch_id, "rejected": rejected}

    def _get_batch_for_update(
        self, cur: psycopg.Cursor, batch_id: str
    ) -> dict[str, Any] | None:
        cur.execute(
            """
            SELECT id::text, status::text, total_rows, valid_rows, error_rows
            FROM import_batches
            WHERE id = %s
            FOR UPDATE
            """,
            [batch_id],
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def _stable_event_id(self, event: HistoricalEvent) -> str:
        key = f"{event.title}:{event.start_year}:{event.region}:{event.polity}"
        return str(uuid5(NAMESPACE_URL, key))

    def _ensure_region(self, cur: psycopg.Cursor, name: str) -> str:
        cur.execute(
            """
            INSERT INTO regions (name)
            VALUES (%s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id::text
            """,
            [name],
        )
        return cur.fetchone()["id"]

    def _ensure_country(
        self, cur: psycopg.Cursor, name: str, region_id: str
    ) -> str | None:
        if not name:
            return None
        first_name = name.split("、", maxsplit=1)[0]
        cur.execute(
            """
            INSERT INTO modern_countries (name, region_id)
            VALUES (%s, %s)
            ON CONFLICT (name) DO UPDATE SET
              region_id = coalesce(modern_countries.region_id, EXCLUDED.region_id)
            RETURNING id::text
            """,
            [first_name, region_id],
        )
        return cur.fetchone()["id"]

    def _ensure_polity(
        self, cur: psycopg.Cursor, event: HistoricalEvent, region_id: str
    ) -> str:
        cur.execute("SELECT id::text FROM polities WHERE name = %s", [event.polity])
        row = cur.fetchone()
        if row:
            return row["id"]

        cur.execute(
            """
            INSERT INTO polities (name, region_id, start_year, end_year)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (name, start_year, end_year) DO UPDATE SET
              region_id = EXCLUDED.region_id
            RETURNING id::text
            """,
            [event.polity, region_id, event.start_year, event.end_year],
        )
        return cur.fetchone()["id"]

    def _ensure_category(self, cur: psycopg.Cursor, name: str) -> str:
        cur.execute(
            """
            INSERT INTO categories (name)
            VALUES (%s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id::text
            """,
            [name],
        )
        return cur.fetchone()["id"]

    def _insert_event(
        self,
        cur: psycopg.Cursor,
        event: HistoricalEvent,
        import_batch_id: str,
    ) -> str:
        event_id = event.id or self._stable_event_id(event)
        region_id = self._ensure_region(cur, event.region)
        country_id = self._ensure_country(cur, event.modern_country, region_id)
        polity_id = self._ensure_polity(cur, event, region_id)

        cur.execute(
            """
            INSERT INTO historical_events (
              id,
              title,
              canonical_title,
              start_year,
              end_year,
              start_date_text,
              end_date_text,
              time_precision,
              is_approximate,
              region_id,
              polity_id,
              primary_modern_country_id,
              location_text,
              summary,
              causes,
              effects,
              status,
              confidence,
              import_batch_id
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (id) DO UPDATE SET
              title = EXCLUDED.title,
              canonical_title = EXCLUDED.canonical_title,
              start_year = EXCLUDED.start_year,
              end_year = EXCLUDED.end_year,
              start_date_text = EXCLUDED.start_date_text,
              end_date_text = EXCLUDED.end_date_text,
              time_precision = EXCLUDED.time_precision,
              is_approximate = EXCLUDED.is_approximate,
              region_id = EXCLUDED.region_id,
              polity_id = EXCLUDED.polity_id,
              primary_modern_country_id = EXCLUDED.primary_modern_country_id,
              location_text = EXCLUDED.location_text,
              summary = EXCLUDED.summary,
              causes = EXCLUDED.causes,
              effects = EXCLUDED.effects,
              status = EXCLUDED.status,
              confidence = EXCLUDED.confidence,
              import_batch_id = EXCLUDED.import_batch_id
            """,
            [
                event_id,
                event.title,
                event.title,
                event.start_year,
                event.end_year,
                event.start_date_text,
                event.end_date_text,
                event.time_precision,
                event.time_precision == "approximate",
                region_id,
                polity_id,
                country_id,
                event.modern_country,
                event.summary,
                event.causes,
                event.effects,
                event.source_status,
                event.confidence,
                import_batch_id,
            ],
        )

        cur.execute("DELETE FROM event_categories WHERE event_id = %s", [event_id])
        for category in event.category:
            category_id = self._ensure_category(cur, category)
            cur.execute(
                """
                INSERT INTO event_categories (event_id, category_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                [event_id, category_id],
            )

        cur.execute("DELETE FROM event_sources WHERE event_id = %s", [event_id])
        for source in event.sources:
            cur.execute(
                """
                INSERT INTO event_sources (
                  event_id,
                  source_title,
                  source_type,
                  url,
                  citation,
                  excerpt,
                  reliability
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    event_id,
                    source.source_title,
                    source.source_type,
                    source.url,
                    source.citation,
                    source.excerpt,
                    source.reliability,
                ],
            )

        return event_id
