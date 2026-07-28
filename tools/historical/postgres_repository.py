from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from apps.api.settings import PostgresSettings
from tools.historical.models import EventSource, HistoricalEvent


class PostgresHistoricalEventRepository:
    def __init__(self, settings: PostgresSettings) -> None:
        self.settings = settings

    @contextmanager
    def _connect(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            yield conn

    def get(self, event_id: str) -> HistoricalEvent | None:
        with self._connect() as conn:
            rows = self._fetch_events(conn, where_sql="e.id = %s", params=[event_id], limit=1)
        return rows[0] if rows else None

    def find_contemporary_events(
        self,
        event_id: str,
        window_years: int = 10,
        regions: list[str] | None = None,
        limit: int = 50,
    ) -> list[HistoricalEvent]:
        event = self.get(event_id)
        if not event:
            return []
        midpoint = event.start_year
        start_year = midpoint - window_years
        end_year = (event.end_year or midpoint) + window_years
        events = self.search_by_range(
            start_year=start_year,
            end_year=end_year,
            regions=regions,
            limit=limit + 1,
        )
        return [candidate for candidate in events if candidate.id != event_id][:limit]

    def find_related_events(
        self,
        event_id: str,
        relation_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        where = [
            "(er.source_event_id = %s::uuid OR er.target_event_id = %s::uuid)",
        ]
        params: list[Any] = [event_id, event_id]
        if relation_types:
            where.append("er.relation_type = ANY(%s)")
            params.append(relation_types)

        sql = f"""
            SELECT
              er.id::text AS relation_id,
              er.relation_type::text,
              er.explanation,
              er.confidence,
              er.is_directional,
              er.source_event_id::text,
              er.target_event_id::text,
              source_event.title AS source_title,
              target_event.title AS target_title
            FROM event_relations er
            JOIN historical_events source_event ON source_event.id = er.source_event_id
            JOIN historical_events target_event ON target_event.id = er.target_event_id
            WHERE {' AND '.join(where)}
            ORDER BY er.confidence DESC, er.created_at DESC
            LIMIT %s
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [*params, limit])
                rows = list(cur.fetchall())

        return [dict(row) for row in rows]

    def search_by_year(
        self,
        year: int,
        regions: list[str] | None = None,
        polities: list[str] | None = None,
        categories: list[str] | None = None,
        limit: int = 50,
    ) -> list[HistoricalEvent]:
        where = ["e.start_year <= %s", "coalesce(e.end_year, e.start_year) >= %s"]
        params: list[Any] = [year, year]
        self._append_filters(where, params, regions, polities, categories)
        with self._connect() as conn:
            return self._fetch_events(conn, " AND ".join(where), params, limit)

    def search_by_range(
        self,
        start_year: int,
        end_year: int,
        regions: list[str] | None = None,
        polities: list[str] | None = None,
        categories: list[str] | None = None,
        limit: int = 100,
    ) -> list[HistoricalEvent]:
        if end_year < start_year:
            start_year, end_year = end_year, start_year
        where = ["e.start_year <= %s", "coalesce(e.end_year, e.start_year) >= %s"]
        params: list[Any] = [end_year, start_year]
        self._append_filters(where, params, regions, polities, categories)
        with self._connect() as conn:
            return self._fetch_events(conn, " AND ".join(where), params, limit)

    def _append_filters(
        self,
        where: list[str],
        params: list[Any],
        regions: list[str] | None,
        polities: list[str] | None,
        categories: list[str] | None,
    ) -> None:
        if regions:
            where.append("r.name = ANY(%s)")
            params.append(regions)
        if polities:
            where.append("p.name = ANY(%s)")
            params.append(polities)
        if categories:
            where.append(
                """
                EXISTS (
                  SELECT 1
                  FROM event_categories ec_filter
                  JOIN categories c_filter ON c_filter.id = ec_filter.category_id
                  WHERE ec_filter.event_id = e.id
                    AND c_filter.name = ANY(%s)
                )
                """
            )
            params.append(categories)

    def _fetch_events(
        self,
        conn: psycopg.Connection,
        where_sql: str,
        params: list[Any],
        limit: int,
    ) -> list[HistoricalEvent]:
        event_sql = f"""
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
              coalesce(array_agg(DISTINCT c.name) FILTER (WHERE c.name IS NOT NULL), '{{}}') AS category
            FROM historical_events e
            LEFT JOIN regions r ON r.id = e.region_id
            LEFT JOIN polities p ON p.id = e.polity_id
            LEFT JOIN modern_countries mc ON mc.id = e.primary_modern_country_id
            LEFT JOIN event_categories ec ON ec.event_id = e.id
            LEFT JOIN categories c ON c.id = ec.category_id
            WHERE {where_sql}
            GROUP BY e.id, r.name, p.name, mc.name
            ORDER BY e.start_year, r.name, e.title
            LIMIT %s
        """
        with conn.cursor() as cur:
            cur.execute(event_sql, [*params, limit])
            event_rows = list(cur.fetchall())

        if not event_rows:
            return []

        event_ids = [row["id"] for row in event_rows]
        sources_by_event = self._fetch_sources(conn, event_ids)

        events: list[HistoricalEvent] = []
        for row in event_rows:
            events.append(
                HistoricalEvent(
                    id=row["id"],
                    title=row["title"],
                    start_year=row["start_year"],
                    end_year=row["end_year"],
                    start_date_text=row["start_date_text"],
                    end_date_text=row["end_date_text"],
                    time_precision=row["time_precision"],
                    region=row["region"],
                    polity=row["polity"],
                    modern_country=row["modern_country"],
                    category=list(row["category"] or []),
                    summary=row["summary"],
                    causes=list(row["causes"] or []),
                    effects=list(row["effects"] or []),
                    source_status=row["source_status"],
                    confidence=float(row["confidence"]),
                    sources=sources_by_event.get(row["id"], []),
                )
            )
        return events

    def _fetch_sources(
        self, conn: psycopg.Connection, event_ids: list[str]
    ) -> dict[str, list[EventSource]]:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  event_id::text,
                  id::text,
                  source_title,
                  source_type::text,
                  url,
                  citation,
                  excerpt,
                  reliability
                FROM event_sources
                WHERE event_id = ANY(%s::uuid[])
                ORDER BY reliability DESC, source_title
                """,
                [event_ids],
            )
            rows = list(cur.fetchall())

        sources_by_event: dict[str, list[EventSource]] = {}
        for row in rows:
            sources_by_event.setdefault(row["event_id"], []).append(
                EventSource(
                    id=row["id"],
                    source_title=row["source_title"],
                    source_type=row["source_type"],
                    url=row["url"],
                    citation=row["citation"],
                    excerpt=row["excerpt"],
                    reliability=float(row["reliability"]),
                )
            )
        return sources_by_event
