from __future__ import annotations

import csv
import io
import json
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

    def parse_events(self, content: str, input_format: str = "json") -> dict[str, Any]:
        input_format = input_format.lower()
        if input_format not in {"json", "csv"}:
            return {"parsed": False, "error": "input_format must be json or csv"}
        try:
            if input_format == "json":
                parsed = json.loads(content)
                events = parsed.get("events", parsed) if isinstance(parsed, dict) else parsed
                if not isinstance(events, list):
                    return {"parsed": False, "error": "JSON must be a list or an object with events"}
            else:
                reader = csv.DictReader(io.StringIO(content))
                events = [self._event_from_csv_row(row) for row in reader]
        except Exception as exc:
            return {"parsed": False, "error": str(exc)}

        validations = [self.validate_event_payload(event) for event in events]
        return {
            "parsed": True,
            "input_format": input_format,
            "count": len(events),
            "valid_rows": sum(1 for item in validations if not item.errors),
            "error_rows": sum(1 for item in validations if item.errors),
            "events": events,
            "validation_errors": [item.errors for item in validations],
        }

    def list_batches(
        self,
        status: str | None = None,
        created_by: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        if status:
            where.append("status = %s")
            params.append(status)
        if created_by:
            where.append("created_by = %s")
            params.append(created_by)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT count(*) AS total
                    FROM import_batches
                    {where_sql}
                    """,
                    params,
                )
                total = int(cur.fetchone()["total"])
                cur.execute(
                    f"""
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
                    {where_sql}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    [*params, limit, offset],
                )
                rows = [dict(row) for row in cur.fetchall()]

        return {"count": len(rows), "total": total, "limit": limit, "offset": offset, "batches": rows}

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

    def preview_batch(self, batch_id: str) -> dict[str, Any]:
        staging = self.list_staging_rows(batch_id)
        rows = staging["rows"]
        keys = [self._event_key(row.get("normalized_payload") or row.get("raw_payload") or {}) for row in rows]
        key_counts: dict[str, int] = {}
        for key in keys:
            if key:
                key_counts[key] = key_counts.get(key, 0) + 1

        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                preview_rows: list[dict[str, Any]] = []
                for row, key in zip(rows, keys):
                    payload = row.get("normalized_payload") or row.get("raw_payload") or {}
                    duplicates = self._find_duplicate_events(cur, payload)
                    preview_rows.append(
                        {
                            **row,
                            "duplicate_in_batch": bool(key and key_counts.get(key, 0) > 1),
                            "duplicate_in_batch_count": key_counts.get(key, 0) if key else 0,
                            "duplicate_candidates": duplicates,
                            "has_duplicate_candidates": bool(duplicates),
                            "field_differences": self._field_differences(payload, duplicates[0])
                            if duplicates
                            else {},
                        }
                    )

        return {
            "batch_id": batch_id,
            "count": len(preview_rows),
            "rows": preview_rows,
            "duplicate_rows": sum(1 for row in preview_rows if row["has_duplicate_candidates"]),
            "in_batch_duplicate_rows": sum(1 for row in preview_rows if row["duplicate_in_batch"]),
        }

    def update_staging_row(
        self,
        row_id: str,
        raw_payload: dict[str, Any],
    ) -> dict[str, Any]:
        validation = self.validate_event_payload(raw_payload)
        row_status = "validated" if not validation.errors else "rejected"

        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE import_event_staging
                    SET raw_payload = %s,
                        normalized_payload = %s,
                        validation_errors = %s,
                        status = %s
                    WHERE id = %s
                      AND status <> 'imported'
                    RETURNING
                      id::text,
                      import_batch_id::text,
                      row_number,
                      raw_payload,
                      normalized_payload,
                      validation_errors,
                      status::text,
                      created_at
                    """,
                    [
                        Jsonb(raw_payload),
                        Jsonb(validation.normalized_payload)
                        if validation.normalized_payload is not None
                        else None,
                        validation.errors,
                        row_status,
                        row_id,
                    ],
                )
                row = cur.fetchone()
                if not row:
                    return {"updated": False, "error": "staging row not found or already imported"}
                self._refresh_batch_counts(cur, row["import_batch_id"])
            conn.commit()

        return {"updated": True, "row": dict(row)}

    def merge_staging_row(
        self,
        row_id: str,
        strategy: str,
        target_event_id: str,
    ) -> dict[str, Any]:
        if strategy not in {"keep_existing", "replace_existing", "merge_sources", "merge_categories", "merge_sources_and_categories"}:
            return {"merged": False, "error": "invalid merge strategy"}
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      id::text,
                      import_batch_id::text,
                      raw_payload,
                      status::text
                    FROM import_event_staging
                    WHERE id = %s
                      AND status <> 'imported'
                    """,
                    [row_id],
                )
                row = cur.fetchone()
                if not row:
                    return {"merged": False, "error": "staging row not found or already imported"}
                payload = dict(row["raw_payload"])

                if strategy == "keep_existing":
                    cur.execute(
                        """
                        UPDATE import_event_staging
                        SET normalized_payload = NULL,
                            validation_errors = %s,
                            status = 'rejected'
                        WHERE id = %s
                        RETURNING
                          id::text,
                          import_batch_id::text,
                          row_number,
                          raw_payload,
                          normalized_payload,
                          validation_errors,
                          status::text,
                          created_at
                        """,
                        [[f"duplicate kept existing event {target_event_id}"], row_id],
                    )
                    updated_row = dict(cur.fetchone())
                    self._refresh_batch_counts(cur, row["import_batch_id"])
                    conn.commit()
                    return {"merged": True, "strategy": strategy, "row": updated_row}

                existing = self._event_payload_from_db(cur, target_event_id)
                if not existing:
                    return {"merged": False, "error": "target event not found"}
                payload["id"] = target_event_id
                if strategy in {"merge_sources", "merge_sources_and_categories"}:
                    payload["sources"] = self._merge_unique_sources(
                        existing.get("sources", []),
                        payload.get("sources", []),
                    )
                if strategy in {"merge_categories", "merge_sources_and_categories"}:
                    payload["category"] = sorted(
                        {str(item) for item in existing.get("category", []) + payload.get("category", []) if item}
                    )
                if strategy == "replace_existing":
                    payload["id"] = target_event_id

            conn.commit()

        updated = self.update_staging_row(row_id, payload)
        return {"merged": bool(updated.get("updated")), "strategy": strategy, **updated}

    def revalidate_batch(self, batch_id: str) -> dict[str, Any]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, raw_payload
                    FROM import_event_staging
                    WHERE import_batch_id = %s
                      AND status <> 'imported'
                    ORDER BY row_number
                    """,
                    [batch_id],
                )
                rows = [dict(row) for row in cur.fetchall()]
                if not rows:
                    return {"batch_id": batch_id, "revalidated": False, "error": "batch not found or already imported"}

                for row in rows:
                    validation = self.validate_event_payload(row["raw_payload"])
                    row_status = "validated" if not validation.errors else "rejected"
                    cur.execute(
                        """
                        UPDATE import_event_staging
                        SET normalized_payload = %s,
                            validation_errors = %s,
                            status = %s
                        WHERE id = %s
                        """,
                        [
                            Jsonb(validation.normalized_payload)
                            if validation.normalized_payload is not None
                            else None,
                            validation.errors,
                            row_status,
                            row["id"],
                        ],
                    )
                self._refresh_batch_counts(cur, batch_id)
            conn.commit()

        batch = self.get_batch(batch_id)
        return {"batch_id": batch_id, "revalidated": True, "batch": batch}

    def bulk_revalidate_staging(
        self,
        row_ids: list[str] | None = None,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        if not row_ids and not batch_id:
            return {"success": False, "error": "row_ids or batch_id is required"}

        where = ["status <> 'imported'"]
        params: list[Any] = []
        if row_ids:
            where.append("id = ANY(%s::uuid[])")
            params.append(row_ids)
        if batch_id:
            where.append("import_batch_id = %s")
            params.append(batch_id)

        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id::text, import_batch_id::text, raw_payload
                    FROM import_event_staging
                    WHERE {' AND '.join(where)}
                    ORDER BY row_number
                    """,
                    params,
                )
                rows = [dict(row) for row in cur.fetchall()]
                touched_batches: set[str] = set()
                updated = 0
                rejected = 0
                validated = 0
                for row in rows:
                    validation = self.validate_event_payload(row["raw_payload"])
                    row_status = "validated" if not validation.errors else "rejected"
                    cur.execute(
                        """
                        UPDATE import_event_staging
                        SET normalized_payload = %s,
                            validation_errors = %s,
                            status = %s
                        WHERE id = %s
                        """,
                        [
                            Jsonb(validation.normalized_payload)
                            if validation.normalized_payload is not None
                            else None,
                            validation.errors,
                            row_status,
                            row["id"],
                        ],
                    )
                    updated += 1
                    if row_status == "validated":
                        validated += 1
                    else:
                        rejected += 1
                    touched_batches.add(row["import_batch_id"])
                for touched_batch_id in touched_batches:
                    self._refresh_batch_counts(cur, touched_batch_id)
            conn.commit()

        return {
            "success": True,
            "updated": updated,
            "validated": validated,
            "rejected": rejected,
            "batch_ids": sorted(touched_batches),
        }

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

    def _refresh_batch_counts(self, cur: psycopg.Cursor, batch_id: str) -> None:
        cur.execute(
            """
            SELECT
              count(*) AS total_rows,
              count(*) FILTER (WHERE status = 'validated') AS valid_rows,
              count(*) FILTER (WHERE status = 'rejected') AS error_rows
            FROM import_event_staging
            WHERE import_batch_id = %s
            """,
            [batch_id],
        )
        counts = cur.fetchone()
        batch_status = "validated" if counts["error_rows"] == 0 else "pending"
        cur.execute(
            """
            UPDATE import_batches
            SET status = %s,
                total_rows = %s,
                valid_rows = %s,
                error_rows = %s,
                validated_at = now()
            WHERE id = %s
              AND status <> 'imported'
            """,
            [
                batch_status,
                counts["total_rows"],
                counts["valid_rows"],
                counts["error_rows"],
                batch_id,
            ],
        )

    def _stable_event_id(self, event: HistoricalEvent) -> str:
        key = f"{event.title}:{event.start_year}:{event.region}:{event.polity}"
        return str(uuid5(NAMESPACE_URL, key))

    def _event_from_csv_row(self, row: dict[str, str]) -> dict[str, Any]:
        def text(name: str, default: str = "") -> str:
            return str(row.get(name, default) or "").strip()

        def number(name: str, default: int | None = None) -> int | None:
            value = text(name)
            return int(value) if value else default

        def decimal_number(name: str, default: float) -> float:
            value = text(name)
            return float(value) if value else default

        def list_field(name: str) -> list[str]:
            value = text(name)
            if not value:
                return []
            return [item.strip() for item in value.replace("、", ";").split(";") if item.strip()]

        source_title = text("source_title")
        sources = []
        if source_title:
            sources.append(
                {
                    "source_title": source_title,
                    "source_type": text("source_type", "note") or "note",
                    "url": text("source_url"),
                    "citation": text("citation"),
                    "excerpt": text("excerpt"),
                    "reliability": decimal_number("source_reliability", 0.5),
                }
            )
        return {
            "title": text("title"),
            "start_year": number("start_year", 0),
            "end_year": number("end_year"),
            "start_date_text": text("start_date_text"),
            "end_date_text": text("end_date_text"),
            "time_precision": text("time_precision", "year") or "year",
            "region": text("region"),
            "polity": text("polity"),
            "modern_country": text("modern_country"),
            "category": list_field("category"),
            "summary": text("summary"),
            "causes": list_field("causes"),
            "effects": list_field("effects"),
            "actors": list_field("actors"),
            "source_status": text("source_status", "draft") or "draft",
            "confidence": decimal_number("confidence", 0.5),
            "sources": sources,
        }

    def _event_payload_from_db(self, cur: psycopg.Cursor, event_id: str) -> dict[str, Any] | None:
        cur.execute(
            """
            SELECT
              e.id::text,
              e.title,
              e.start_year,
              e.end_year,
              e.start_date_text,
              e.end_date_text,
              e.time_precision::text,
              coalesce(r.name, '') AS region,
              coalesce(p.name, '') AS polity,
              coalesce(mc.name, '') AS modern_country,
              e.summary,
              e.causes,
              e.effects,
              e.status::text AS source_status,
              e.confidence,
              coalesce(array_agg(DISTINCT c.name) FILTER (WHERE c.name IS NOT NULL), '{}') AS category
            FROM historical_events e
            LEFT JOIN regions r ON r.id = e.region_id
            LEFT JOIN polities p ON p.id = e.polity_id
            LEFT JOIN modern_countries mc ON mc.id = e.primary_modern_country_id
            LEFT JOIN event_categories ec ON ec.event_id = e.id
            LEFT JOIN categories c ON c.id = ec.category_id
            WHERE e.id = %s
            GROUP BY e.id, r.name, p.name, mc.name
            """,
            [event_id],
        )
        row = cur.fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["confidence"] = float(payload["confidence"])
        cur.execute(
            """
            SELECT
              source_title,
              source_type::text,
              url,
              citation,
              excerpt,
              reliability
            FROM event_sources
            WHERE event_id = %s
            ORDER BY source_title
            """,
            [event_id],
        )
        payload["sources"] = [
            {
                **dict(source),
                "reliability": float(source["reliability"]),
            }
            for source in cur.fetchall()
        ]
        return payload

    def _merge_unique_sources(
        self,
        existing_sources: list[dict[str, Any]],
        incoming_sources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for source in [*existing_sources, *incoming_sources]:
            key = (str(source.get("source_title", "")), str(source.get("citation", "")))
            if key not in merged:
                merged[key] = source
            else:
                merged[key] = {
                    **merged[key],
                    **{key: value for key, value in source.items() if value not in ("", None)},
                    "reliability": max(
                        float(merged[key].get("reliability", 0.5)),
                        float(source.get("reliability", 0.5)),
                    ),
                }
        return list(merged.values())

    def _event_key(self, payload: dict[str, Any]) -> str:
        title = str(payload.get("title", "")).strip()
        start_year = payload.get("start_year", "")
        region = str(payload.get("region", "")).strip()
        polity = str(payload.get("polity", "")).strip()
        if not title or start_year == "":
            return ""
        return f"{title}:{start_year}:{region}:{polity}"

    def _find_duplicate_events(
        self,
        cur: psycopg.Cursor,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        title = str(payload.get("title", "")).strip()
        start_year = payload.get("start_year")
        region = str(payload.get("region", "")).strip()
        polity = str(payload.get("polity", "")).strip()
        if not title or start_year is None:
            return []
        cur.execute(
            """
            SELECT
              e.id::text,
              e.title,
              e.start_year,
              e.end_year,
              coalesce(r.name, '') AS region,
              coalesce(p.name, '') AS polity,
              e.summary,
              e.status::text AS source_status,
              e.confidence
            FROM historical_events e
            LEFT JOIN regions r ON r.id = e.region_id
            LEFT JOIN polities p ON p.id = e.polity_id
            WHERE e.title = %s
              AND e.start_year = %s
              AND (%s = '' OR r.name = %s)
              AND (%s = '' OR p.name = %s)
            ORDER BY e.updated_at DESC
            LIMIT 5
            """,
            [title, start_year, region, region, polity, polity],
        )
        return [dict(row) for row in cur.fetchall()]

    def _field_differences(
        self,
        payload: dict[str, Any],
        existing: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        differences: dict[str, dict[str, Any]] = {}
        for field in ("title", "start_year", "end_year", "region", "polity", "summary", "source_status"):
            incoming_value = payload.get(field)
            existing_value = existing.get(field)
            if incoming_value != existing_value:
                differences[field] = {
                    "incoming": incoming_value,
                    "existing": existing_value,
                }
        return differences

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
